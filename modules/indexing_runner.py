import json
import logging
import os
import platform
import threading
from typing import Any, Dict, List, Optional

from modules import db
from modules.utils import is_docker_runtime, resolve_scope_input_path
from modules.version import APP_VERSION
from modules.phases import PhaseCode, PhaseStatus
from modules.events import event_manager
from modules.run_log import runner_emit
from modules.indexing_policy import (
    discovery_extensions,
    path_is_indexing_excluded,
    prune_indexing_excluded_walk_dirs,
)

logger = logging.getLogger(__name__)

INDEXING_VERSION = "1.0.0"
PROGRESS_INTERVAL = 50
# Stored in images.metadata: skip full-file SHA-256 when size+mtime match (job reruns / phase retries).
_INDEXING_CONTENT_FP_KEY = "indexing_content_fp"
# Keep jobs.log bounded when persisting during long runs (Run detail polling + LogPanel fallback).
_MAX_PERSISTED_JOB_LOG_CHARS = 250_000


def _parse_metadata_dict(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _looks_like_transient_mount_path(raw: str) -> bool:
    """True for paths that may transiently 404 due to mount/drvfs/UNC blips.

    On Linux/WSL ``/mnt/<drive>/...`` is a 9P/drvfs mount that can briefly fail
    `os.path.exists()` after heavy host I/O; on Windows ``\\\\server\\share`` UNC
    paths have the same property. Pure local paths are not retried.
    """
    if not raw:
        return False
    s = str(raw).strip().replace("\\", "/")
    if s.startswith("/mnt/"):
        return True
    if s.startswith("//"):  # UNC normalized
        return True
    return False


def _resolve_scope_input_path_with_retry(
    raw: str,
    *,
    log,
    max_attempts: int = 3,
    base_delay: float = 1.0,
):
    """Soft-retry wrapper around :func:`resolve_scope_input_path`.

    A first miss on a WSL/UNC mount is treated as transient and re-tried with
    short backoff. Local paths are checked exactly once (no retry).
    """
    import time

    resolved, tried = resolve_scope_input_path(raw)
    if resolved or not _looks_like_transient_mount_path(raw):
        return resolved, tried

    for attempt in range(2, max_attempts + 1):
        delay = base_delay * (2 ** (attempt - 2))
        log(
            "WARNING",
            f"Path not found yet ({raw!r}); transient mount suspected, "
            f"retrying in {delay:.1f}s (attempt {attempt}/{max_attempts}).",
        )
        time.sleep(delay)
        resolved, tried = resolve_scope_input_path(raw)
        if resolved:
            log(
                "INFO",
                f"Path resolved on retry attempt {attempt}: {resolved}",
            )
            return resolved, tried
    return None, tried


def _image_row_has_identity_hash(row: Optional[Dict[str, Any]]) -> bool:
    """True when ``images.image_hash`` is non-empty (matches ``get_phase_incomplete_sql('indexing')``)."""
    if not row:
        return False
    h = row.get("image_hash")
    if h is None:
        return False
    if isinstance(h, str):
        return bool(h.strip())
    return bool(str(h).strip())


def _content_fp_matches_file(fp: Any, file_path: str) -> bool:
    if not isinstance(fp, dict):
        return False
    try:
        st = os.stat(file_path)
    except OSError:
        return False
    if st.st_size != fp.get("size"):
        return False
    want_ns = fp.get("mtime_ns")
    if want_ns is not None:
        try:
            return int(st.st_mtime_ns) == int(want_ns)
        except (TypeError, ValueError):
            return False
    return False


def _attach_indexing_content_fp(meta: Dict[str, Any], file_path: str) -> Dict[str, Any]:
    out = dict(meta)
    try:
        st = os.stat(file_path)
    except OSError:
        return out
    out[_INDEXING_CONTENT_FP_KEY] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
    return out


def _persist_indexing_content_fp(
    image_id: int, file_path: str, indexing_hash_mode: Optional[str] = None
) -> None:
    """Merge indexing_content_fp into images.metadata for duplicate-hash rows (no upsert)."""
    if not image_id:
        return
    try:
        st = os.stat(file_path)
    except OSError:
        return
    fp_val = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
    try:
        if db._get_db_engine() == "postgres":
            # Single UPDATE with jsonb merge — no SELECT round-trip needed.
            patch = {_INDEXING_CONTENT_FP_KEY: fp_val}
            if indexing_hash_mode is not None:
                patch["indexing_hash_mode"] = indexing_hash_mode
            from modules.db_postgres import PGConnectionManager
            with PGConnectionManager(commit=True) as pg_conn:
                with pg_conn.cursor() as cur:
                    cur.execute(
                        "UPDATE images SET metadata = COALESCE(metadata::jsonb, '{}'::jsonb) || %s::jsonb WHERE id = %s",
                        (json.dumps(patch), int(image_id)),
                    )
        else:
            # Fallback: SELECT + UPDATE for non-Postgres engines.
            row = db.get_connector().query_one("SELECT metadata FROM images WHERE id = ?", (int(image_id),))
            prev = row.get("metadata") if row else None
            merged = _attach_indexing_content_fp(_parse_metadata_dict(prev), file_path)
            if indexing_hash_mode is not None:
                merged["indexing_hash_mode"] = indexing_hash_mode
            db.update_image_field(int(image_id), "metadata", json.dumps(merged))
    except Exception:
        logger.debug("Indexing: could not persist %s for image_id=%s", _INDEXING_CONTENT_FP_KEY, image_id, exc_info=True)

SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif',
    '.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng'
}


def _path_under_or_equal(child: str, ancestor: str) -> bool:
    c = os.path.normpath(child)
    a = os.path.normpath(ancestor)
    if c == a:
        return True
    prefix = a if a.endswith(os.sep) else a + os.sep
    return c.startswith(prefix)


def _dir_directly_contains_nef(dir_path: str, cache: Dict[str, bool]) -> bool:
    if dir_path in cache:
        return cache[dir_path]
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(".nef"):
                    cache[dir_path] = True
                    return True
    except OSError:
        cache[dir_path] = False
        return False
    cache[dir_path] = False
    return False


def _resolve_nef_folder_path(file_path: str, scan_stop: Optional[str], cache: Dict[str, bool]) -> Optional[str]:
    """
    Deepest directory at or above dirname(file_path) that directly contains a .nef file.
    When scan_stop is set (normalized directory), do not walk above it.
    """
    cur = os.path.normpath(os.path.dirname(file_path))
    stop = os.path.normpath(scan_stop) if scan_stop else None
    while cur:
        if stop and not _path_under_or_equal(cur, stop):
            break
        if _dir_directly_contains_nef(cur, cache):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        if stop and not _path_under_or_equal(parent, stop):
            break
        cur = parent
    return None


def _assign_indexing_folder_id(image_id: int, file_path: str, scan_stop: Optional[str], nef_cache: Dict[str, bool]) -> None:
    resolved = _resolve_nef_folder_path(file_path, scan_stop, nef_cache)
    new_fid = db.get_or_create_folder(resolved) if resolved else None
    try:
        row_old = db.get_connector().query_one("SELECT folder_id FROM images WHERE id = ?", (image_id,))
        old_fid = row_old["folder_id"] if row_old else None
        if old_fid == new_fid:
            return
        db.get_connector().execute("UPDATE images SET folder_id = ? WHERE id = ?", (new_fid, image_id))
        if new_fid:
            db.invalidate_folder_phase_aggregates(folder_id=new_fid)
        if old_fid and old_fid != new_fid:
            db.invalidate_folder_phase_aggregates(folder_id=old_fid)
        db.invalidate_folder_images_cache(os.path.dirname(file_path))
    except Exception:
        logger.exception("Indexing: failed to update folder_id for image_id=%s path=%s", image_id, file_path)


def _resolve_split_brain_collision(
    *,
    track_id: int,
    hash_row_id: int,
    file_path: str,
    image_hash: str,
    hash_version: int,
    existing: Dict[str, Any],
    existing_by_path: Optional[Dict[str, Any]],
    log,
) -> int:
    """Resolve the case where lookup-by-path (track_id) and lookup-by-hash (hash_row_id)
    return different image rows for the same physical file.

    Postgres enforces both UNIQUE(file_path) and UNIQUE(image_hash, hash_version), so we
    cannot keep both rows. Two cases:

      (A) track_id has no hash → adopt hash_row_id as primary, drop track_id.
      (B) track_id already has a hash (e.g. stale, or two indexings of the same content
          via different mounts) → prefer track_id (its file_path matches the current scan),
          merge metadata from hash_row_id, delete hash_row_id, then adopt the freshly
          computed hash on track_id.

    Without (B), the trailing UPDATE images SET file_path=? WHERE id=hash_row_id collides
    with track_id's path and the job fails — workflow healing then respawns it forever.

    Returns the resolved primary image_id (or hash_row_id if the merge errors out, since
    the caller's downstream UPDATE assumes hash_row_id is primary by default).
    """
    t_row = db.get_connector().query_one(
        "SELECT image_hash, file_path, rating, label, folder_id FROM images WHERE id = ?",
        (track_id,),
    )
    t_hash = (t_row.get("image_hash") or "").strip() if t_row else ""

    if t_row and not t_hash:
        try:
            update_existing = {}
            t_rating = t_row.get("rating") or 0
            e_rating = existing.get("rating") or 0
            if t_rating > e_rating:
                update_existing["rating"] = t_rating

            t_label = (t_row.get("label") or "").strip()
            e_label = (existing.get("label") or "").strip()
            if t_label and not e_label:
                update_existing["label"] = t_label

            for field, val in update_existing.items():
                db.update_image_field(hash_row_id, field, val)

            db.delete_image(file_path, delete_related=True)

            log(
                "INFO",
                f"Merged metadata from redundant row {track_id} into {hash_row_id} and deleted {track_id}",
                image_id=hash_row_id,
            )

            tid_fid = (existing_by_path or {}).get("folder_id")
            if tid_fid:
                db.invalidate_folder_phase_aggregates(folder_id=tid_fid)
            return hash_row_id
        except Exception as e:
            log("WARNING", f"Failed to merge split-brain record {track_id}: {e}", image_id=track_id)
            return hash_row_id

    if t_row:
        try:
            update_track = {}
            e_rating = existing.get("rating") or 0
            t_rating = t_row.get("rating") or 0
            if e_rating > t_rating:
                update_track["rating"] = e_rating

            e_label = (existing.get("label") or "").strip()
            t_label = (t_row.get("label") or "").strip()
            if e_label and not t_label:
                update_track["label"] = e_label

            for field, val in update_track.items():
                db.update_image_field(track_id, field, val)

            redundant_path = (existing.get("file_path") or "").strip() or None
            if redundant_path and redundant_path != file_path:
                db.delete_image(redundant_path, delete_related=True)
            else:
                db.get_connector().execute(
                    "DELETE FROM images WHERE id = ?", (hash_row_id,)
                )

            if t_hash != image_hash:
                db.update_image_field(track_id, "image_hash", image_hash)
                db.update_image_field(track_id, "hash_version", hash_version)

            log(
                "INFO",
                f"Merged hash-collision row {hash_row_id} (path={redundant_path}) into {track_id}",
                image_id=track_id,
            )

            hr_fid = existing.get("folder_id")
            if hr_fid:
                db.invalidate_folder_phase_aggregates(folder_id=hr_fid)
            return track_id
        except Exception as e:
            log(
                "WARNING",
                f"Failed to merge hash-collision record {hash_row_id} into {track_id}: {e}",
                image_id=track_id,
            )
            return hash_row_id

    return hash_row_id


class IndexingRunner:
    """
    Independent runner for the Indexing (Discovery) phase.
    Walks directories, computes basic info, and inserts rows into the `images` table.
    """
    def __init__(self):
        self.stop_event = threading.Event()
        self.is_running = False
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0

    def _persist_log_to_job_row(self, job_id: Optional[int]) -> None:
        """Persist in-memory log to ``jobs.log`` without mutating ``jobs.status``."""
        if not job_id:
            return
        try:
            text = "\n".join(self.log_history)
            if len(text) > _MAX_PERSISTED_JOB_LOG_CHARS:
                text = text[-_MAX_PERSISTED_JOB_LOG_CHARS:]

            db.update_job_log(job_id, text)
        except Exception:
            logger.exception(
                "IndexingRunner: failed to persist log to jobs row (job_id=%s)",
                job_id,
            )

    def get_status(self):
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def start_batch(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None, report_collector=None):
        if self.is_running:
            return "Error: Already running."

        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0

        if job_id is None:
            job_id = db.create_job(input_path or "ALL_IMAGES_INDEXING", job_type="indexing")

        def target():
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                try:
                    from modules.pipeline_diagnostics import phase_timer
                    with phase_timer("IndexingRunner.batch", job_id):
                        self._run_batch_internal(input_path, job_id, skip_existing, resolved_image_ids, report_collector=report_collector)
                except Exception:
                    self.status_message = "Failed"
                    raise
                finally:
                    if self.status_message == "Failed":
                        pass
                    elif "Error" in self.status_message:
                        self.status_message = "Failed"
                    elif not self.status_message.startswith("Done"):
                        self.status_message = "Done"

            safe_runner_thread(self, job_id, target_wrapper)

        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def discover_files(self, directory: str) -> List[str]:
        valid_files = []
        exts = discovery_extensions()
        if os.path.isfile(directory):
            if path_is_indexing_excluded(directory):
                return valid_files
            ext = os.path.splitext(directory)[1].lower()
            if ext in exts:
                valid_files.append(directory)
            return valid_files

        try:
            norm_dir = os.path.normpath(directory)
        except (OSError, ValueError):
            norm_dir = directory
        if os.path.isdir(norm_dir) and path_is_indexing_excluded(norm_dir):
            return valid_files

        for root, dirs, files in os.walk(directory):
            prune_indexing_excluded_walk_dirs(root, dirs)
            for file in files:
                fp = os.path.join(root, file)
                if path_is_indexing_excluded(fp):
                    continue
                ext = os.path.splitext(file)[1].lower()
                if ext in exts:
                    valid_files.append(fp)
        return valid_files


    def _process_indexing_file(
        self,
        file_path,
        *,
        skip_existing,
        job_id,
        report_collector,
        log,
        processed_count,
        skipped_count,
        scan_stop=None,
        nef_cache=None,
    ):
        """Process one item in a batch run."""
        if nef_cache is None:
            nef_cache = {}
        self.current_count += 1



        # Fast-path: skip_existing and indexing already complete for this file

        existing_by_path = None  # cached for reuse after skip_existing check

        if skip_existing:

            existing_by_path = db.get_image_details(file_path)

            if existing_by_path and existing_by_path.get("id"):

                phase_status = db.get_image_phase_status(existing_by_path["id"], PhaseCode.INDEXING)

                # Do not treat phase=done as complete if image_hash is still missing; otherwise

                # "Process unprocessed" / heal re-runs skip forever (matches workflow healing predicate).

                if (

                    phase_status

                    and phase_status.get("status") == PhaseStatus.DONE

                    and _image_row_has_identity_hash(existing_by_path)

                ):

                    sid = int(existing_by_path["id"])

                    # Do not overwrite IPS done→skipped (illegal transition; reads like regression in UI).

                    # Per-run "no work" stays on the job report / job_image_actions.

                    skipped_count += 1

                    if report_collector:

                        report_collector.record_skip(sid, "already_indexed")

                    log("DEBUG", f"Skip (already indexed): {file_path}", image_id=sid)

                    if self.current_count % PROGRESS_INTERVAL == 0:

                        log(

                            "INFO",

                            f"Progress {self.current_count}/{self.total_count} "

                            f"(processed={processed_count}, skipped={skipped_count})",

                        )

                        self._persist_log_to_job_row(job_id)

                        event_manager.broadcast_threadsafe(

                            "job_progress",

                            {

                                "job_id": job_id,

                                "job_type": "indexing",

                                "phase_code": "indexing",

                                "current": self.current_count,

                                "total": self.total_count,

                            },

                        )

                    return processed_count, skipped_count



        from modules.config import get_config_value

        from modules import image_identity_hash



        if existing_by_path is None:

            existing_by_path = db.get_image_details(file_path)

        track_id = int(existing_by_path["id"]) if existing_by_path and existing_by_path.get("id") else None



        image_id = None

        existing = None

        try:

            meta_dict = _parse_metadata_dict((existing_by_path or {}).get("metadata"))

            cfg_mode = (

                get_config_value("indexing.hash_mode", "content_preview") or "content_preview"

            ).strip().lower()

            stored_hash = (existing_by_path or {}).get("image_hash")

            if isinstance(stored_hash, str):

                stored_hash = stored_hash.strip() or None

            fp = meta_dict.get(_INDEXING_CONTENT_FP_KEY)

            prev_mode = meta_dict.get("indexing_hash_mode")

            image_hash = None

            hash_version: Optional[int] = None

            if (

                stored_hash

                and _content_fp_matches_file(fp, file_path)

                and prev_mode == cfg_mode

            ):

                image_hash = stored_hash

                try:

                    hash_version = int((existing_by_path or {}).get("hash_version") or 1)

                except (TypeError, ValueError):

                    hash_version = 1

                log(

                    "DEBUG",

                    f"Reusing stored hash (content fingerprint unchanged): {file_path}",

                    image_id=int(existing_by_path["id"]) if existing_by_path and existing_by_path.get("id") else None,

                )

            else:

                # Try UUID-based shortcut: adopt hash from an existing record

                # matched by image_uuid (helps moved/renamed files avoid rehashing).

                uuid_adopted = False

                if meta_dict:

                    try:

                        candidate_uuid = db.generate_image_uuid(meta_dict)

                        if candidate_uuid:

                            uuid_record_id = db.find_image_id_by_uuid(candidate_uuid)

                            if uuid_record_id:

                                uuid_row = db.get_connector().query_one(

                                    "SELECT image_hash, hash_version FROM images WHERE id = ?",

                                    (uuid_record_id,),

                                )

                                uh = (uuid_row.get("image_hash") or "").strip() if uuid_row else ""

                                if uh:

                                    image_hash = uh

                                    try:

                                        hash_version = int(uuid_row.get("hash_version") or 1)

                                    except (TypeError, ValueError):

                                        hash_version = 1

                                    uuid_adopted = True

                                    log(

                                        "DEBUG",

                                        f"Adopted hash from UUID match (id={uuid_record_id}): {file_path}",

                                        image_id=uuid_record_id,

                                    )

                    except Exception:

                        logger.debug("UUID shortcut failed for %s", file_path, exc_info=True)



                if not uuid_adopted:

                    log("DEBUG", f"Hashing: {file_path}", image_id=track_id)

                    ident = image_identity_hash.compute_image_identity_hash(file_path)

                    if not ident:

                        log("ERROR", f"Could not compute identity hash for {file_path}", image_id=track_id)

                        skipped_count += 1

                        return processed_count, skipped_count

                    image_hash, hash_version = ident



            merged_meta = _attach_indexing_content_fp(meta_dict, file_path)

            merged_meta["indexing_hash_mode"] = cfg_mode



            existing = db.get_image_by_hash(image_hash, hash_version)

            if existing:

                hash_row_id = int(existing.get("id"))

                image_id = hash_row_id



                if track_id and track_id != hash_row_id:

                    image_id = _resolve_split_brain_collision(

                        track_id=track_id,

                        hash_row_id=hash_row_id,

                        file_path=file_path,

                        image_hash=image_hash,

                        hash_version=hash_version,

                        existing=existing,

                        existing_by_path=existing_by_path,

                        log=log,

                    )



                db.register_image_path(image_id, file_path)

                _fname = os.path.basename(file_path)

                db.get_connector().execute(

                    "UPDATE images SET file_path = ?, file_name = ? WHERE id = ?",

                    (file_path, _fname, image_id),

                )



                _assign_indexing_folder_id(image_id, file_path, scan_stop, nef_cache)

                _persist_indexing_content_fp(int(image_id), file_path, cfg_mode)

                log(

                    "DEBUG",

                    f"Registered path and updated record image_id={image_id}: {file_path}",

                    image_id=int(image_id) if image_id else None,

                )

            else:

                resolved_folder = _resolve_nef_folder_path(file_path, scan_stop, nef_cache)

                folder_id = db.get_or_create_folder(resolved_folder) if resolved_folder else None

                image_id = db.upsert_image(

                    job_id,

                    {

                        "image_path": file_path,

                        "image_hash": image_hash,

                        "hash_version": hash_version,

                        "folder_id": folder_id,

                        "metadata": merged_meta,

                    },

                )

                if not image_id:

                    detail = db.get_image_details(file_path)

                    image_id = detail.get("id") if detail else None

                log(

                    "DEBUG",

                    f"Upsert new row image_id={image_id}: {file_path}",

                    image_id=int(image_id) if image_id else None,

                )



            if job_id and image_id:

                db.set_image_phase_status(

                    int(image_id),

                    PhaseCode.INDEXING,

                    PhaseStatus.RUNNING,

                    app_version=APP_VERSION,

                    executor_version=INDEXING_VERSION,

                    job_id=job_id,

                )



            if image_id:

                db.set_image_phase_status(

                    int(image_id),

                    PhaseCode.INDEXING,

                    PhaseStatus.DONE,

                    app_version=APP_VERSION,

                    executor_version=INDEXING_VERSION,

                    job_id=job_id,

                )

                processed_count += 1

                if report_collector:

                    report_collector.record_after(int(image_id), {}, action="processed")

                log("DEBUG", f"Indexed image_id={image_id}: {file_path}", image_id=int(image_id))

            else:

                skipped_count += 1

                log("WARNING", f"No image_id after upsert for {file_path}")



        except Exception as e:

            log("ERROR", f"Error indexing {file_path}: {e}", image_id=track_id or image_id)

            skipped_count += 1

            if report_collector and (track_id or image_id):

                report_collector.record_failure(int(track_id or image_id), str(e))

            fail_id = track_id

            try:

                if existing and existing.get("id"):

                    fail_id = int(existing["id"])

                elif image_id:

                    fail_id = int(image_id)

            except (TypeError, ValueError):

                pass

            if fail_id:

                try:

                    db.set_image_phase_status(

                        fail_id,

                        PhaseCode.INDEXING,

                        PhaseStatus.FAILED,

                        app_version=APP_VERSION,

                        executor_version=INDEXING_VERSION,

                        job_id=job_id,

                        error=str(e),

                    )

                except Exception:

                    logger.exception("IndexingRunner: failed to set FAILED ips")



        if self.current_count % PROGRESS_INTERVAL == 0:

            event_manager.broadcast_threadsafe(

                "job_progress",

                {

                    "job_id": job_id,

                    "job_type": "indexing",

                    "phase_code": "indexing",

                    "current": self.current_count,

                    "total": self.total_count,

                },

            )

            log(

                "INFO",

                f"Progress {self.current_count}/{self.total_count} "

                f"(processed={processed_count}, skipped={skipped_count})",

            )

            self._persist_log_to_job_row(job_id)



        return processed_count, skipped_count

    def _run_batch_internal(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None, report_collector=None):
        def log(level: str, msg: str, image_id: Optional[int] = None) -> None:
            runner_emit(self.log_history, job_id, msg, level, phase="indexing", image_id=image_id)

        def fail_terminal(error_summary: str):
            self.status_message = error_summary
            if job_id:
                db.update_job_status(job_id, "failed", "\n".join(self.log_history))
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id,
                    "status": "failed",
                    "error": error_summary,
                })

        self.stop_event.clear()

        # Match API scope validation: /mnt/d/... is not visible to native Windows Python, etc.
        if resolved_image_ids is None:
            if not input_path or not input_path.strip():
                log("ERROR", "Input path empty. Cannot index entire DB from scratch currently.")
                fail_terminal("Error Path")
                return
            stripped = input_path.strip()
            resolved_local, tried = _resolve_scope_input_path_with_retry(
                stripped, log=log
            )
            if not resolved_local:
                uniq_try = list(dict.fromkeys(tried))
                preview = ", ".join(repr(t) for t in uniq_try[:5])
                if len(uniq_try) > 5:
                    preview += ", …"
                msg = (
                    f"Input path not found: {stripped}. Checked: {preview or '(no variants)'}. "
                    f"This process runs on {platform.system()}."
                )
                sl = stripped.replace("\\", "/")
                if platform.system() == "Windows" and sl.startswith("/mnt/"):
                    msg += (
                        " Native Windows Python cannot read WSL paths under /mnt/; use D:\\Photos\\... "
                        "or run the WebUI from WSL."
                    )
                elif platform.system() == "Linux" and sl.startswith("/mnt/"):
                    segs = [x for x in sl.split("/") if x]
                    if len(segs) >= 2 and segs[0] == "mnt":
                        mroot = f"/mnt/{segs[1]}"
                        if not os.path.exists(mroot):
                            msg += f" {mroot}/ is not mounted here."
                if is_docker_runtime():
                    msg += (
                        " Docker: only bind-mounted paths exist inside the container — see PHOTOS_BIND_SOURCE / compose volumes."
                    )
                log("ERROR", msg)
                fail_terminal("Error Path")
                return
            try:
                if os.path.normpath(resolved_local) != os.path.normpath(stripped):
                    log("INFO", f"Resolved input path {stripped!r} -> {resolved_local!r}")
            except (OSError, ValueError):
                pass
            input_path = resolved_local

        log("INFO", f"Starting Indexing process on {input_path or 'Selected Images'}...")
        if discovery_extensions() == frozenset({".nef"}):
            log("INFO", "NEF-only indexing enabled (config indexing.nikon_nef_only).")
        self.status_message = "Running..."
        
        if job_id:
            db.update_job_status(job_id, "running")
            self._persist_log_to_job_row(job_id)
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "indexing", 
                "input_path": input_path
            })

        all_files = []
        
        if resolved_image_ids is not None:
             try:
                 rows = db.get_all_images(limit=-1)
                 selected_ids = {int(i) for i in resolved_image_ids}
                 all_files = [row['file_path'] for row in rows if row.get('id') in selected_ids]
                 log("INFO", f"Selector mode enabled. Matched {len(all_files)} images by ID.")
             except Exception as e:
                 log("ERROR", f"Error fetching from DB: {e}")
                 fail_terminal("Error DB")
                 return
        else:
            all_files = self.discover_files(input_path)

        log("INFO", f"Found {len(all_files)} files to potentially index.")
        self.total_count = len(all_files)
        self.current_count = 0

        if report_collector is not None:
            targeted = len(resolved_image_ids) if resolved_image_ids is not None else len(all_files)
            report_collector.set_scope_counts(in_scope=len(all_files), targeted=targeted)

        scan_stop: Optional[str] = None
        nef_cache: Dict[str, bool] = {}
        if resolved_image_ids is None and input_path and os.path.exists(input_path):
            if os.path.isdir(input_path):
                scan_stop = os.path.normpath(input_path)
            elif os.path.isfile(input_path):
                scan_stop = os.path.normpath(os.path.dirname(input_path))
        
        processed_count = 0
        skipped_count = 0
        
        for file_path in all_files:
            if self.stop_event.is_set():
                log("WARNING", "Indexing stopped by user.")
                break
            if job_id and db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("WARNING", "Indexing paused (job status).")
                break


            processed_count, skipped_count = self._process_indexing_file(
                file_path,
                skip_existing=skip_existing,
                job_id=job_id,
                report_collector=report_collector,
                log=log,
                processed_count=processed_count,
                skipped_count=skipped_count,
                scan_stop=scan_stop,
                nef_cache=nef_cache,
            )

        log("INFO", f"Done. Processed: {processed_count}, Skipped: {skipped_count}")
        self._persist_log_to_job_row(job_id)

        try:
            if resolved_image_ids is not None:
                seen_parents = set()
                for fp in all_files:
                    if not fp:
                        continue
                    parent = os.path.normpath(os.path.dirname(fp))
                    if parent and parent not in seen_parents:
                        seen_parents.add(parent)
                        db.invalidate_folder_phase_aggregates(folder_path=parent)
            elif input_path and os.path.isdir(input_path):
                db.invalidate_folder_phase_aggregates(folder_path=input_path)
        except Exception:
            logger.exception("IndexingRunner: invalidate_folder_phase_aggregates after batch failed")

        if job_id:
            if self.stop_event.is_set() or db.job_should_stop_processing(job_id):
                try:
                    db.reconcile_stale_running_phases_for_jobs(
                        [job_id],
                        error_message=db.GRACEFUL_PAUSE_MSG,
                        in_flight_to="not_started",
                    )
                except Exception:
                    logger.exception("indexing: reconcile after stop failed (job_id=%s)", job_id)
                j = db.get_job(job_id)
                st = (j.get("status") or "").strip().lower() if j else ""
                if st == "running":
                    final_log = "\n".join(self.log_history)
                    if len(final_log) > _MAX_PERSISTED_JOB_LOG_CHARS:
                        final_log = final_log[-_MAX_PERSISTED_JOB_LOG_CHARS:]
                    try:
                        db.update_job_status(job_id, "paused", log=final_log)
                    except Exception:
                        pass
            else:
                self._finalize_report(job_id, report_collector)
                job = db.get_job(job_id)
                st = (job.get("status") or "").strip().lower() if job else ""
                final_log = "\n".join(self.log_history)
                if len(final_log) > _MAX_PERSISTED_JOB_LOG_CHARS:
                    final_log = final_log[-_MAX_PERSISTED_JOB_LOG_CHARS:]
                if st not in db.JOB_TERMINAL_STATES:
                    db.update_job_status(job_id, "completed", log=final_log)
                elif (
                    st == "failed"
                    and resolved_image_ids is None
                    and self.total_count > 0
                    and ("Done. Processed:" in final_log or processed_count > 0 or skipped_count > 0)
                ):
                    # Rare race: job/phase row marked failed before the indexer finishes writing
                    # (e.g. dispatcher + stale phase snapshot). Reconcile so multi-phase runs can continue.
                    try:
                        phases = db.get_job_phases(job_id) or []
                        n_phases = len(phases)
                        db.set_job_phase_state(job_id, "indexing", "completed", error_message=None)
                        if n_phases > 1:
                            db.update_job_status(
                                job_id, "running", log=final_log, runner_state="running"
                            )
                        else:
                            db.update_job_status(
                                job_id, "completed", log=final_log, runner_state="completed"
                            )
                    except Exception:
                        logger.exception(
                            "indexing: failed to reconcile stray failed job after successful batch (job_id=%s)",
                            job_id,
                        )

    @staticmethod
    def _finalize_report(job_id, report_collector):
        if report_collector is None:
            return
        try:
            from modules.report_collector import finalize_and_save_report
            finalize_and_save_report(job_id, report_collector.run_mode, [report_collector])
        except Exception:
            logger.debug("Failed to finalize report for job %s", job_id, exc_info=True)

    def stop(self):
        self.stop_event.set()
