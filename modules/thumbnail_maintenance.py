"""
Batch thumbnail maintenance for API and CLI wrappers.

Single-image generation stays in modules.thumbnails; this module holds
global scans with bounded work (regenerate missing, repair path columns).
"""
from __future__ import annotations

import logging
import os
import platform
import re
from typing import Optional, TypedDict

from modules import config, db, thumbnails

logger = logging.getLogger(__name__)


class RegenerateBatchResult(TypedDict):
    processed: int
    regenerated: int
    skipped_thumb_ok: int
    skipped_missing_original: int
    failed: int


class RepairBatchResult(TypedDict, total=False):
    scanned: int
    repaired: int
    unchanged: int
    used_candidate_filter: bool


def filesystem_path_for_image(db_file_path: str) -> str | None:
    """Resolve DB file_path to a path readable on this OS (Windows / WSL)."""
    p = str(db_file_path).strip()
    if not p:
        return None
    if os.path.isfile(p):
        return p
    if platform.system() == "Linux":
        m = re.match(r"^([a-zA-Z]):[\\/](.*)", p)
        if m:
            wsl = f"/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}"
            if os.path.isfile(wsl):
                return wsl
    if platform.system() == "Windows":
        norm = p.replace("\\", "/")
        m2 = re.match(r"^/mnt/([a-zA-Z])/(.*)", norm, re.I)
        if m2:
            win = f"{m2.group(1).upper()}:{os.sep}{m2.group(2).replace('/', os.sep)}"
            if os.path.isfile(win):
                return win
    return None


def resolved_thumb_ok(thumbnail_path: str | None, thumbnail_path_win: str | None) -> bool:
    p = thumbnails._resolve_thumbnail_filesystem_path(thumbnail_path, thumbnail_path_win)
    if not p or not os.path.isfile(p):
        return False
    try:
        return os.path.getsize(p) > 0
    except OSError:
        return False


def folder_like_patterns(prefix: str) -> list[str]:
    """Build LIKE patterns for file_path (Windows and slash variants)."""
    p = os.path.normpath(prefix.rstrip("/\\"))
    out: list[str] = []
    seen: set[str] = set()

    def add(pat: str) -> None:
        if pat not in seen:
            seen.add(pat)
            out.append(pat)

    add(p + os.sep + "%")
    add(p.replace("\\", "/") + "/%")
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)", p.replace("\\", "/"), re.I)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        win = f"{drive}:\\{rest}"
        add(win + "\\%")
        add(win.replace("\\", "/") + "/%")
    m2 = re.match(r"^([a-zA-Z]):[\\/](.*)", p)
    if m2:
        drive = m2.group(1).lower()
        rest = m2.group(2).replace("\\", "/")
        wsl = f"/mnt/{drive}/{rest}"
        add(wsl + "/%")
    return out


def regenerate_missing_thumbnails_batch(limit: int = 500) -> RegenerateBatchResult:
    """
    Regenerate up to ``limit`` missing/stale thumbnails globally (ordered by image id).

    Fetches up to ``limit * 3`` candidate rows from SQL, then stops after ``limit``
    successful regenerations (many candidates skip as thumb already OK).
    """
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 500
    fetch_n = limit * 3
    rows = db.get_connector().query(
        """
        SELECT id, file_path, thumbnail_path, thumbnail_path_win
        FROM images
        ORDER BY id
        FETCH FIRST ? ROWS ONLY
        """,
        (fetch_n,),
    ) or []

    processed = 0
    regenerated = 0
    skipped_thumb_ok = 0
    skipped_missing_original = 0
    failed = 0

    for row in rows:
        if regenerated >= limit:
            break

        rid = int(row["id"])
        file_path = row.get("file_path")
        tp = row.get("thumbnail_path")
        tw = row.get("thumbnail_path_win")

        processed += 1

        if not file_path or not str(file_path).strip():
            skipped_missing_original += 1
            continue

        fs_path = filesystem_path_for_image(str(file_path))
        if not fs_path:
            logger.warning("Original missing on disk id=%s path=%s", rid, file_path)
            skipped_missing_original += 1
            continue

        if resolved_thumb_ok(tp, tw):
            skipped_thumb_ok += 1
            continue

        gen_kw: dict = {}
        if fs_path != file_path:
            gen_kw["source_path"] = fs_path
        new_thumb = thumbnails.generate_thumbnail(file_path, **gen_kw)
        if not new_thumb or not os.path.isfile(new_thumb) or os.path.getsize(new_thumb) <= 0:
            logger.error("Thumbnail generation failed id=%s file=%s", rid, file_path)
            failed += 1
            continue

        if db.update_image_thumbnail_paths(rid, new_thumb, None):
            regenerated += 1
        else:
            logger.error("DB update failed id=%s (thumb file at %s)", rid, new_thumb)
            failed += 1

    return RegenerateBatchResult(
        processed=processed,
        regenerated=regenerated,
        skipped_thumb_ok=skipped_thumb_ok,
        skipped_missing_original=skipped_missing_original,
        failed=failed,
    )


def repair_thumbnail_paths_batch(
    limit: Optional[int] = 1000,
    *,
    repair_all_pairs: bool = False,
    dry_run: bool = False,
) -> RepairBatchResult:
    """
    Repair malformed thumbnail_path / thumbnail_path_win values.

    Scans rows with non-null thumb columns until ``limit`` rows are actually
    updated (or rows are exhausted). Pass ``limit=None`` for no cap (CLI full run).
    ``repair_all_pairs`` matches ``--all`` on the CLI: normalize every row where
    values change, not only ``thumbnail_pair_needs_repair``.
    """
    cap: Optional[int]
    if limit is None:
        cap = None
    else:
        try:
            cap = max(1, int(limit))
        except (TypeError, ValueError):
            cap = 1000

    use_candidate_filter = not repair_all_pairs and config.get_database_engine() == "postgres"
    base_where = "(thumbnail_path IS NOT NULL OR thumbnail_path_win IS NOT NULL)"
    if use_candidate_filter:
        # Skip full-table scans when the library is mostly clean: only rows that commonly
        # need repair (Docker /app paths, static leaks, repo-relative, or a missing column).
        thumb_where = f"""
        {base_where}
        AND (
            COALESCE(thumbnail_path, '') ILIKE '%/app/thumbnails%'
            OR COALESCE(thumbnail_path, '') ILIKE '%thumbnails/app/thumbnails%'
            OR COALESCE(thumbnail_path, '') ILIKE '%static/app/thumbnails%'
            OR COALESCE(thumbnail_path, '') ILIKE '%../image-scoring%thumbnails%'
            OR REPLACE(COALESCE(thumbnail_path_win, ''), E'\\\\', '/') ILIKE '%/app/thumbnails%'
            OR (thumbnail_path IS NOT NULL AND thumbnail_path_win IS NULL)
            OR (thumbnail_path_win IS NOT NULL AND thumbnail_path IS NULL)
        )
        """
        sql = f"""
        SELECT id, thumbnail_path, thumbnail_path_win
        FROM images
        WHERE {thumb_where}
        ORDER BY id
        """
    else:
        sql = f"""
        SELECT id, thumbnail_path, thumbnail_path_win
        FROM images
        WHERE {base_where}
        ORDER BY id
        """

    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()

    scanned = 0
    repaired = 0
    unchanged = 0
    skip_needs_check = repair_all_pairs or use_candidate_filter

    for row in rows:
        if cap is not None and repaired >= cap:
            break

        rid = row["id"] if hasattr(row, "keys") else row[0]
        tp = row["thumbnail_path"] if hasattr(row, "keys") else row[1]
        tw = row["thumbnail_path_win"] if hasattr(row, "keys") else row[2]
        scanned += 1
        if scanned % 5000 == 0:
            logger.info("Repair scan progress: scanned=%s repaired=%s", scanned, repaired)

        if not skip_needs_check and not thumbnails.thumbnail_pair_needs_repair(tp, tw):
            unchanged += 1
            continue

        new_tp, new_tw = thumbnails.normalize_stored_thumbnail_pair(tp, tw)
        if new_tp is None and new_tw is None:
            logger.warning("id=%s: could not normalize, leaving row unchanged", rid)
            unchanged += 1
            continue
        if new_tw is None and new_tp:
            new_tw = thumbnails.thumb_path_to_win(new_tp)
        if (new_tp, new_tw) == (tp, tw):
            unchanged += 1
            continue

        if not dry_run:
            db.update_image_thumbnail_paths(int(rid), new_tp, new_tw)
        repaired += 1

    out: RepairBatchResult = {
        "scanned": scanned,
        "repaired": repaired,
        "unchanged": unchanged,
    }
    if use_candidate_filter:
        out["used_candidate_filter"] = True
    return out
