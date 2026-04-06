import os
import threading
import logging
from typing import Dict, List, Optional

from modules import db
from modules.version import APP_VERSION
from modules.phases import PhaseCode, PhaseStatus
from modules.events import event_manager, broadcast_run_log_line
from modules.indexing_policy import (
    discovery_extensions,
    path_is_indexing_excluded,
    prune_indexing_excluded_walk_dirs,
)

logger = logging.getLogger(__name__)

INDEXING_VERSION = "1.0.0"

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

    def get_status(self):
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def start_batch(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None):
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
            try:
                self._run_batch_internal(input_path, job_id, skip_existing, resolved_image_ids)
            except Exception:
                logger.exception("IndexingRunner thread crashed (job_id=%s)", job_id)
                self.status_message = "Failed"
            finally:
                self.is_running = False
            if self.status_message == "Failed":
                pass
            elif "Error" in self.status_message:
                self.status_message = "Failed"
            elif not self.status_message.startswith("Done"):
                self.status_message = "Done"

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

    def _run_batch_internal(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None):
        def log(msg):
            self.log_history.append(msg)
            if job_id:
                broadcast_run_log_line(job_id, msg)

        # Handle WSL path conversion if needed
        if input_path and ":" in input_path and len(input_path) > 1 and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            if os.path.exists("/mnt/") and os.path.exists(wsl_path):
                input_path = wsl_path

        self.stop_event.clear()
        log(f"Starting Indexing process on {input_path or 'Selected Images'}...")
        if discovery_extensions() == frozenset({".nef"}):
            log("NEF-only indexing enabled (config indexing.nikon_nef_only).")
        self.status_message = "Running..."
        
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "indexing", 
                "input_path": input_path
            })

        def fail_terminal(error_summary: str):
            self.status_message = error_summary
            if job_id:
                db.update_job_status(job_id, "failed", "\n".join(self.log_history))
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id,
                    "status": "failed",
                    "error": error_summary,
                })

        all_files = []
        
        if resolved_image_ids is not None:
             try:
                 rows = db.get_all_images(limit=-1)
                 selected_ids = {int(i) for i in resolved_image_ids}
                 all_files = [row['file_path'] for row in rows if row.get('id') in selected_ids]
                 log(f"Selector mode enabled. Matched {len(all_files)} images by ID.")
             except Exception as e:
                 log(f"Error fetching from DB: {e}")
                 fail_terminal("Error DB")
                 return
        elif not input_path or not input_path.strip():
             log("Input path empty. Cannot index entire DB from scratch currently.")
             fail_terminal("Error Path")
             return
        elif os.path.exists(input_path):
             all_files = self.discover_files(input_path)
        else:
            log(f"Input path not found: {input_path}")
            fail_terminal("Error Path")
            return

        log(f"Found {len(all_files)} files to potentially index.")
        self.total_count = len(all_files)
        self.current_count = 0

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
                log("Indexing stopped by user.")
                break
                
            self.current_count += 1
            
            # Fast-path check: if skip_existing and file is already in DB
            if skip_existing:
                existing_record = db.get_image_details(file_path)
                if existing_record and existing_record.get('id'):
                    # Check if 'indexing' phase is already DONE
                    phase_status = db.get_image_phase_status(existing_record['id'], PhaseCode.INDEXING)
                    if phase_status and phase_status.get('status') == PhaseStatus.DONE:
                        skipped_count += 1
                        continue

            from modules.utils import calculate_image_hash
            
            try:
                # Need hash for initial upsert
                image_hash = calculate_image_hash(file_path)
                
                # Check if hash exists but path is different (moved file)
                existing = db.get_image_by_hash(image_hash)
                if existing:
                    image_id = existing.get('id')
                    db.register_image_path(image_id, file_path)
                    _assign_indexing_folder_id(image_id, file_path, scan_stop, nef_cache)
                else:
                    # Create new placeholder record
                    # We upsert an empty payload since scoring comes later
                    resolved_folder = _resolve_nef_folder_path(file_path, scan_stop, nef_cache)
                    folder_id = db.get_or_create_folder(resolved_folder) if resolved_folder else None
                    image_id = db.upsert_image(job_id, {
                        "file_path": file_path,
                        "image_hash": image_hash,
                        "folder_id": folder_id,
                    })
                
                # Set Phase Status
                if image_id:
                    db.set_image_phase_status(
                        image_id,
                        PhaseCode.INDEXING,
                        PhaseStatus.DONE,
                        app_version=APP_VERSION,
                        executor_version=INDEXING_VERSION,
                        job_id=job_id
                    )
                    processed_count += 1
                else:
                    skipped_count += 1

            except Exception as e:
                log(f"Error indexing {file_path}: {e}")
                skipped_count += 1

            if self.current_count % 50 == 0:
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
                
        log(f"Done. Processed: {processed_count}, Skipped: {skipped_count}")

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
            job = db.get_job(job_id)
            st = (job.get("status") or "").strip().lower() if job else ""
            if st not in db.JOB_TERMINAL_STATES:
                db.update_job_status(job_id, "completed")

    def stop(self):
        self.stop_event.set()
