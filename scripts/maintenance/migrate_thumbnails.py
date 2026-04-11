#!/usr/bin/env python3
"""
Migrate thumbnails from flat layout to nested 2-char prefix subdirectories
and align images.thumbnail_path / thumbnail_path_win with on-disk files.

Layout change:
  thumbnails/{hash}.jpg  -->  thumbnails/{hash[:2]}/{hash}.jpg

Steps:
  1. Move flat 32-hex JPG files from thumbnails/ root into prefix subfolders.
  2. Re-normalize thumbnail DB columns from disk (repair_thumbnail_paths_batch --all).
  3. Backfill rows with empty thumbnail columns when a file exists at the expected path.

Run in WSL with the app venv:
  source ~/.venvs/tf/bin/activate
  python scripts/maintenance/migrate_thumbnails.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import shutil
import logging
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from modules import db
from modules.thumbnail_maintenance import repair_thumbnail_paths_batch
from modules.thumbnails import THUMB_DIR, database_thumbnail_pair_from_fs_path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger(__name__)


def migrate_files(dry_run=False):
    """Move flat thumbnails into nested {hash[:2]}/ subdirectories."""
    moved = 0
    skipped = 0
    errors = 0

    if not os.path.isdir(THUMB_DIR):
        log.warning("Thumbnail directory does not exist: %s", THUMB_DIR)
        return moved, skipped, errors

    for fname in os.listdir(THUMB_DIR):
        fpath = os.path.join(THUMB_DIR, fname)
        if not os.path.isfile(fpath) or not fname.endswith('.jpg'):
            continue

        stem = fname[:-4]  # strip .jpg
        if len(stem) != 32:
            skipped += 1
            continue

        prefix = stem[:2]
        target_dir = os.path.join(THUMB_DIR, prefix)
        target_path = os.path.join(target_dir, fname)

        if os.path.exists(target_path):
            skipped += 1
            continue

        try:
            if not dry_run:
                os.makedirs(target_dir, exist_ok=True)
                shutil.move(fpath, target_path)
            moved += 1
        except Exception as e:
            log.error("Failed to move %s -> %s: %s", fpath, target_path, e)
            errors += 1

    return moved, skipped, errors


def _thumb_path_candidates_for_file_path(file_path: str) -> tuple[str, str]:
    """Expected nested and legacy flat paths for an image file_path (matches get_thumb_path layout)."""
    path_hash = hashlib.md5(str(file_path).encode("utf-8")).hexdigest()
    prefix = path_hash[:2]
    nested = os.path.join(THUMB_DIR, prefix, f"{path_hash}.jpg")
    legacy = os.path.join(THUMB_DIR, f"{path_hash}.jpg")
    return nested, legacy


def backfill_null_thumbnail_paths(dry_run: bool = False) -> tuple[int, int]:
    """
    Set thumbnail_path / thumbnail_path_win when both are empty but a thumbnail file exists
    at the canonical nested or legacy flat path for file_path.
    """
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, file_path FROM images
        WHERE file_path IS NOT NULL
          AND (thumbnail_path IS NULL OR thumbnail_path = '')
          AND (thumbnail_path_win IS NULL OR thumbnail_path_win = '')
        """
    )
    rows = c.fetchall()
    conn.close()

    updated = 0
    skipped = 0

    for row in rows:
        rid = row["id"] if hasattr(row, "keys") else row[0]
        file_path = row["file_path"] if hasattr(row, "keys") else row[1]

        if not file_path or not str(file_path).strip():
            skipped += 1
            continue

        nested, legacy = _thumb_path_candidates_for_file_path(str(file_path))
        abs_path = None
        if os.path.isfile(nested):
            abs_path = os.path.abspath(nested)
        elif os.path.isfile(legacy):
            abs_path = os.path.abspath(legacy)

        if not abs_path:
            skipped += 1
            continue

        new_tp, new_tw = database_thumbnail_pair_from_fs_path(abs_path)
        if not new_tp and not new_tw:
            log.warning("id=%s: could not build DB pair for %s", rid, abs_path)
            skipped += 1
            continue

        if not dry_run:
            db.update_image_thumbnail_paths(int(rid), new_tp, new_tw or None)
        updated += 1

    return updated, skipped


def main():
    parser = argparse.ArgumentParser(description="Migrate thumbnails to nested directory layout")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying anything")
    parser.add_argument(
        "--skip-repair",
        action="store_true",
        help="Skip DB re-normalization (repair_thumbnail_paths_batch); only move files and optional backfill",
    )
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="Skip backfilling empty thumbnail columns when a file exists on disk",
    )
    args = parser.parse_args()

    if args.dry_run:
        log.info("=== DRY RUN MODE (no changes will be made) ===")

    log.info("Step 1/3: Moving thumbnail files to nested directories...")
    moved, skipped, file_errors = migrate_files(dry_run=args.dry_run)
    log.info("  Files moved: %d, skipped: %d, errors: %d", moved, skipped, file_errors)

    if not args.skip_repair:
        log.info("Step 2/3: Re-normalizing thumbnail_path columns from disk...")
        db.init_db()
        r = repair_thumbnail_paths_batch(
            limit=None,
            repair_all_pairs=True,
            dry_run=args.dry_run,
        )
        log.info(
            "  Repair: scanned=%s repaired=%s unchanged=%s",
            r["scanned"],
            r["repaired"],
            r["unchanged"],
        )
    else:
        log.info("Step 2/3: Skipped (--skip-repair).")

    if not args.skip_backfill:
        log.info("Step 3/3: Backfilling empty thumbnail columns when files exist...")
        if args.skip_repair:
            db.init_db()
        bf_ok, bf_skip = backfill_null_thumbnail_paths(dry_run=args.dry_run)
        log.info("  Backfill: updated=%d skipped_or_no_file=%d", bf_ok, bf_skip)
    else:
        log.info("Step 3/3: Skipped (--skip-backfill).")

    log.info("Migration complete.")
    if file_errors:
        log.warning("There were file errors - review the log above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
