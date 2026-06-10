#!/usr/bin/env python3
"""
move_misplaced_by_lens.py

Identify images in a lens folder whose EXIF lens does not match the folder
(e.g., 105mm lens in 180-600mm folder), move them physically to the correct
lens folder, and update all database path references.

Folder convention: D:\\Photos\\{camera}\\{lens}\\{year}\\{date}\\ (same layout as gallery sync).
The lens segment must match the lens used per EXIF.

Requires ``image_exif.lens_model`` populated (images without an ``image_exif`` row are skipped).

Usage:
    python scripts/maintenance/move_misplaced_by_lens.py --source "D:\\Photos\\Z8\\180-600mm\\2026" [--dry-run] [--yes]

Options:
    --source   Root folder to scan (required)
    --dry-run  Preview only, no file or DB changes
    --yes, -y  Skip confirmation prompt

Works with ``database.engine: postgres`` (default) or legacy Firebird: ``get_db()`` uses the
same SQL dialect translation as the app (``?`` placeholders, ``SELECT FIRST`` → ``LIMIT``).

Run in WSL with app venv:
    source ~/.venvs/tf/bin/activate
    python scripts/maintenance/move_misplaced_by_lens.py --dry-run --source "D:\\Photos\\Z8\\180-600mm\\2026"
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# Add project root to path
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import (
    get_db,
    get_or_create_folder,
    init_db,
    invalidate_folder_phase_aggregates,
)
from modules.lens_folder_name import (
    extract_lens_token_from_model,
    extract_lens_token_from_path_segment,
)
from modules.thumbnails import (
    get_thumb_path,
    thumb_path_to_win,
    thumb_path_to_wsl,
)


# ── Path translation (from update_db_paths.py) ──────────────────────────────

def _to_wsl_path(win_path: str) -> str:
    """Convert Windows path (D:\\Photos\\...) to WSL path (/mnt/d/Photos/...)."""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def _to_win_path(wsl_path: str) -> str:
    """Convert WSL path (/mnt/d/Photos/...) to Windows path (D:\\Photos\\...)."""
    if wsl_path.startswith("/mnt/"):
        parts = wsl_path.split("/")
        if len(parts) >= 3:
            drive = parts[2].upper()
            rest = "\\".join(parts[3:])
            return f"{drive}:\\{rest}"
    return wsl_path.replace("/", "\\")


_DB_USES_WSL: bool | None = None


def _db_uses_wsl() -> bool:
    global _DB_USES_WSL
    if _DB_USES_WSL is not None:
        return _DB_USES_WSL
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT FIRST 1 file_path FROM images")
        row = cur.fetchone()
        con.close()
        if row:
            fp = str(row[0])
            _DB_USES_WSL = fp.startswith("/mnt/")
            return _DB_USES_WSL
    except Exception:
        pass
    _DB_USES_WSL = False
    return False


def _normalize_for_db(win_or_wsl_path: str) -> str:
    """Return path in the format the DB expects (WSL or Windows)."""
    if _db_uses_wsl():
        p = win_or_wsl_path.replace("\\", "/")
        if len(p) >= 2 and p[1] == ":":
            return _to_wsl_path(win_or_wsl_path)
        return win_or_wsl_path
    else:
        if win_or_wsl_path.startswith("/mnt/"):
            return _to_win_path(win_or_wsl_path)
        return win_or_wsl_path.replace("/", "\\")


def _extract_lens_from_model(lens_model: str | None) -> str | None:
    return extract_lens_token_from_model(lens_model)


def _extract_lens_from_path(path: str) -> str | None:
    """Extract canonical lens token from path (``180-600mm`` or ``35 35 1.8 1.8`` → ``35mm``)."""
    if not path:
        return None
    normalized = path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    for p in parts:
        token = extract_lens_token_from_path_segment(p)
        if token:
            return token
    return None


def _replace_lens_in_path(path: str, old_lens: str, new_lens: str) -> str:
    """Replace the lens segment in path. Preserves year/date subfolders."""
    if not path or not old_lens or not new_lens:
        return path
    # Use replace - the lens segment is unique in the path
    normalized = path.replace("\\", "/")
    old_norm = old_lens.replace("\\", "/")
    new_norm = new_lens.replace("\\", "/")
    # Match whole segment (avoid partial matches like 05mm in 105mm)
    pattern = re.compile(r"(?<=/)(" + re.escape(old_norm) + r")(?=/)", re.IGNORECASE)
    result = pattern.sub(new_norm, normalized, count=1)
    if result == normalized:
        # Fallback: simple replace if pattern didn't match (e.g. path ends with lens)
        result = normalized.replace("/" + old_norm + "/", "/" + new_norm + "/")
        if result == normalized:
            result = normalized.replace(old_norm, new_norm, 1)
    return result.replace("/", "\\") if "\\" in path else result


# ── Sidecar discovery ──────────────────────────────────────────────────────

_SIDECAR_EXTENSIONS = (".xmp",)


def _find_sidecars(main_path: str) -> list[str]:
    """Find sidecar files (e.g. .xmp) with same basename."""
    base = Path(main_path)
    stem = base.stem
    parent = base.parent
    found = []
    for ext in _SIDECAR_EXTENSIONS:
        sidecar = parent / (stem + ext)
        if sidecar.exists() and sidecar != base:
            found.append(str(sidecar))
    return found


# ── Main logic ──────────────────────────────────────────────────────────────

def find_misplaced(source_prefix: str) -> list[dict]:
    """
    Query DB for images in source folder whose lens_model does not match
    the folder's lens segment. Returns list of dicts with id, file_path,
    file_name, thumbnail_path, thumbnail_path_win, folder_id, lens_model,
    path_lens, exif_lens, new_path.
    """
    _db_uses_wsl()

    # Build path prefixes for LIKE (both WSL and Windows)
    win_prefix = source_prefix.replace("/", "\\").rstrip("\\")
    wsl_prefix = _to_wsl_path(win_prefix).rstrip("/")

    conn = get_db()
    cur = conn.cursor()

    query = """
    SELECT i.id, i.file_path, i.file_name, i.thumbnail_path, i.thumbnail_path_win,
           i.folder_id, e.lens_model
    FROM images i
    JOIN image_exif e ON i.id = e.image_id
    WHERE (i.file_path LIKE ? OR i.file_path LIKE ?)
    """
    cur.execute(query, (win_prefix + "%", wsl_prefix + "%"))
    rows = cur.fetchall()
    conn.close()

    misplaced = []
    for row in rows:
        # RowWrapper iterates (key, value) pairs — use column names, not tuple unpack.
        image_id = row["id"]
        file_path = str(row["file_path"] or "")
        file_name = row["file_name"]
        thumb_path = row["thumbnail_path"]
        thumb_path_win = row["thumbnail_path_win"]
        folder_id = row["folder_id"]
        lens_model = str(row["lens_model"] or "")

        path_lens = _extract_lens_from_path(file_path)
        exif_lens = _extract_lens_from_model(lens_model)

        if not exif_lens:
            continue  # Cannot determine correct lens
        if not path_lens:
            continue  # Cannot parse path
        if path_lens == exif_lens:
            continue  # Already in correct folder

        new_path = _replace_lens_in_path(file_path, path_lens, exif_lens)
        if new_path == file_path:
            continue

        misplaced.append({
            "id": image_id,
            "file_path": file_path,
            "file_name": file_name,
            "thumbnail_path": thumb_path,
            "thumbnail_path_win": thumb_path_win,
            "folder_id": folder_id,
            "lens_model": lens_model,
            "path_lens": path_lens,
            "exif_lens": exif_lens,
            "new_path": new_path,
        })
    return misplaced


def _resolve_native_path(path: str) -> str:
    """Convert path to native format for filesystem operations."""
    if path.startswith("/mnt/"):
        return _to_win_path(path) if os.name == "nt" else path
    return path


def _thumb_db_columns_from_disk(thumb_fs: str) -> tuple[str | None, str | None]:
    """Derive thumbnail_path / thumbnail_path_win for the DB from an on-disk thumb path."""
    if not thumb_fs or not os.path.exists(thumb_fs):
        return None, None
    norm = thumb_fs.replace("\\", "/")
    if norm.startswith("/mnt/"):
        return norm, thumb_path_to_win(thumb_fs)
    wsl = thumb_path_to_wsl(thumb_fs)
    return wsl, thumb_fs


def move_and_update_db(misplaced: list[dict], dry_run: bool) -> dict:
    """
    For each misplaced item: move file + sidecars, copy thumbnail, update DB.
    Returns summary dict.
    """
    _db_uses_wsl()

    updated = 0
    skipped = 0
    failed = []
    target_exists = []

    conn = get_db()
    cur = conn.cursor()

    for item in misplaced:
        old_path = item["file_path"]
        new_path = item["new_path"]
        image_id = item["id"]
        old_folder_id = item["folder_id"]

        try:
            # Canonical DB path first — get_thumb_path() hashes this string; must match images.file_path.
            new_path_db = _normalize_for_db(new_path)
            old_native = _resolve_native_path(old_path)
            new_native = _resolve_native_path(new_path_db)

            if dry_run:
                print(f"  [DRY-RUN] Would move:\n    {old_path}\n    -> {new_path_db} (DB form)")
                updated += 1
                continue

            # Check target exists (don't overwrite)
            if os.path.exists(new_native) and os.path.exists(old_native):
                target_exists.append(new_path)
                skipped += 1
                continue

            # Source missing: if target exists, file was moved in prior run (e.g. deadlock);
            # just update DB. Otherwise fail.
            if not os.path.exists(old_native):
                if not os.path.exists(new_native):
                    failed.append((old_path, "Source file not found"))
                    continue
                # Target exists, source gone -> DB update only; copy thumb if present
                old_thumb_fs = get_thumb_path(old_path)
                new_thumb_fs = get_thumb_path(new_path_db)
                if os.path.exists(old_thumb_fs) and not os.path.exists(new_thumb_fs):
                    os.makedirs(os.path.dirname(new_thumb_fs), exist_ok=True)
                    shutil.copy2(old_thumb_fs, new_thumb_fs)
            else:
                # Create target dir
                new_dir = os.path.dirname(new_native)
                os.makedirs(new_dir, exist_ok=True)

                # Find sidecars before moving (same dir as main file)
                sidecars = _find_sidecars(old_native)

                # Move main file
                shutil.move(old_native, new_native)

                # Move sidecars
                for sidecar in sidecars:
                    if os.path.exists(sidecar):
                        target_sidecar = os.path.join(new_dir, os.path.basename(sidecar))
                        if not os.path.exists(target_sidecar):
                            shutil.move(sidecar, target_sidecar)

                # Copy thumbnail (MD5 keyed to DB path string — use new_path_db, not new_path)
                old_thumb_fs = get_thumb_path(old_path)
                new_thumb_fs = get_thumb_path(new_path_db)
                if os.path.exists(old_thumb_fs):
                    os.makedirs(os.path.dirname(new_thumb_fs), exist_ok=True)
                    shutil.copy2(old_thumb_fs, new_thumb_fs)

            # Thumbnail columns: prefer on-disk file for new_path_db hash; else keep existing DB values
            new_thumb_path_db, new_thumb_win_db = _thumb_db_columns_from_disk(get_thumb_path(new_path_db))
            if new_thumb_path_db is None:
                tp, tw = item["thumbnail_path"], item["thumbnail_path_win"]
                new_thumb_path_db = str(tp) if tp else None
                new_thumb_win_db = str(tw) if tw else None

            new_folder = new_path_db.rsplit("/", 1)[0] if _DB_USES_WSL else str(Path(new_path_db).parent)

            # Create folder record
            folder_id = get_or_create_folder(new_folder)
            conn.commit()

            # Update images
            cur.execute(
                """UPDATE images SET file_path = ?, folder_id = ?, thumbnail_path = ?, thumbnail_path_win = ?
                   WHERE id = ?""",
                (new_path_db, folder_id, new_thumb_path_db, new_thumb_win_db, image_id),
            )
            if cur.rowcount == 0:
                failed.append((old_path, "UPDATE images had no effect"))
                continue

            # Update file_paths (path column for this image_id)
            new_path_wsl = new_path_db if new_path_db.startswith("/mnt/") else _to_wsl_path(new_path_db)
            new_path_win = new_path_db if (len(new_path_db) >= 2 and new_path_db[1] == ":") else _to_win_path(new_path_db)
            old_path_wsl = old_path if old_path.startswith("/mnt/") else _to_wsl_path(old_path)
            old_path_win = old_path if (len(old_path) >= 2 and old_path[1] == ":") else _to_win_path(old_path)
            cur.execute("SELECT id, path, path_type FROM file_paths WHERE image_id = ?", (image_id,))
            fp_rows = cur.fetchall()
            for fp_row in fp_rows:
                fp_id = fp_row["id"]
                fp_path = fp_row["path"]
                fp_type = fp_row["path_type"]
                fp_path_str = str(fp_path) if fp_path else ""
                if fp_path_str in (old_path, old_path_wsl, old_path_win, old_native):
                    new_fp_path = new_path_wsl if (fp_type or "").upper() == "WSL" else new_path_win
                    cur.execute("UPDATE file_paths SET path = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?", (new_fp_path, fp_id))

            # Invalidate folder aggregates
            invalidate_folder_phase_aggregates(folder_id=folder_id)
            if old_folder_id and old_folder_id != folder_id:
                invalidate_folder_phase_aggregates(folder_id=old_folder_id)

            conn.commit()
            updated += 1

        except Exception as e:
            failed.append((old_path, str(e)))
            conn.rollback()

    conn.close()
    return {
        "updated": updated,
        "skipped": skipped,
        "target_exists": target_exists,
        "failed": failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move misplaced images to correct lens folder and update DB paths."
    )
    parser.add_argument("--source", required=True, help="Root folder to scan (e.g. D:\\Photos\\Z8\\180-600mm\\2026)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no file or DB changes")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    source = args.source.strip()
    if not source:
        print("[ERROR] --source is required and cannot be empty.")
        sys.exit(1)

    # Initialize DB to ensure schema is ready
    init_db()

    print(f"Scanning for misplaced images in: {source}")
    misplaced = find_misplaced(source)
    print(f"Found {len(misplaced)} misplaced image(s).")

    if not misplaced:
        print("Nothing to do.")
        return

    # Show sample
    for item in misplaced[:5]:
        lm = (item["lens_model"] or "")[:40]
        print(f"  {item['file_name']}: {item['path_lens']} -> {item['exif_lens']} ({lm}...)")
    if len(misplaced) > 5:
        print(f"  ... and {len(misplaced) - 5} more")

    if not args.dry_run and not args.yes:
        confirm = input(f"\nMove {len(misplaced)} file(s) and update DB? (yes/no): ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return

    result = move_and_update_db(misplaced, dry_run=args.dry_run)

    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"\n{prefix}Results:")
    print(f"  Updated:       {result['updated']}")
    print(f"  Skipped:      {result['skipped']}")
    if result["target_exists"]:
        print(f"  Target exists: {len(result['target_exists'])}")
        for p in result["target_exists"][:3]:
            print(f"    {p}")
        if len(result["target_exists"]) > 3:
            print(f"    ... and {len(result['target_exists']) - 3} more")
    if result["failed"]:
        print(f"  Failed:       {len(result['failed'])}")
        for p, e in result["failed"][:5]:
            print(f"    {p}: {e}")
        if len(result["failed"]) > 5:
            print(f"    ... and {len(result['failed']) - 5} more")

    if args.dry_run:
        print("\n[DRY-RUN complete — no changes made. Remove --dry-run to execute.]")
    else:
        print("\nDone.")


if __name__ == "__main__":
    main()
