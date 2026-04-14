#!/usr/bin/env python3
"""Backfill or upgrade image hashes in the database (PostgreSQL-first).

Usage:
    python scripts/python/backfill_hashes.py                  # fill missing hashes
    python scripts/python/backfill_hashes.py --force           # recompute all
    python scripts/python/backfill_hashes.py --upgrade-version # upgrade v1 RAW -> v2
    python scripts/python/backfill_hashes.py --dry-run         # preview without writes
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db
from modules import image_identity_hash
from modules.config import get_config_value
from modules.indexing_runner import (
    _parse_metadata_dict,
    _attach_indexing_content_fp,
    _content_fp_matches_file,
    _INDEXING_CONTENT_FP_KEY,
)

logger = logging.getLogger("backfill_hashes")

_TIFF_RAW_EXTENSIONS = frozenset({
    ".nef", ".nrw", ".arw", ".cr2", ".cr3", ".dng", ".tif", ".tiff",
})


def backfill_hashes(
    force: bool = False,
    upgrade_version: bool = False,
    dry_run: bool = False,
    batch_size: int = 50,
):
    db.init_db()
    connector = db.get_connector()
    cfg_mode = (
        get_config_value("indexing.hash_mode", "content_preview") or "content_preview"
    ).strip().lower()

    # Build query based on mode
    if upgrade_version:
        rows = list(connector.query(
            "SELECT id, file_path, image_hash, hash_version, metadata "
            "FROM images WHERE hash_version = 1 AND image_hash IS NOT NULL"
        ))
        # Filter to RAW extensions client-side
        rows = [
            r for r in rows
            if os.path.splitext(r.get("file_path", "") or "")[1].lower() in _TIFF_RAW_EXTENSIONS
        ]
        logger.info("Upgrade mode: %d RAW files with hash_version=1", len(rows))
    elif force:
        rows = list(connector.query(
            "SELECT id, file_path, image_hash, hash_version, metadata FROM images"
        ))
    else:
        rows = list(connector.query(
            "SELECT id, file_path, image_hash, hash_version, metadata "
            "FROM images WHERE image_hash IS NULL OR image_hash = ''"
        ))

    total = len(rows)
    logger.info("Found %d images to process.", total)

    updated = 0
    errors = 0
    skipped = 0

    for i, row in enumerate(rows):
        img_id = row["id"]
        file_path = row.get("file_path") or ""

        if not file_path or not os.path.exists(file_path):
            logger.debug("File not found, skipping id=%s: %s", img_id, file_path)
            skipped += 1
            continue

        # Check fingerprint — skip if unchanged and not force/upgrade
        meta = _parse_metadata_dict(row.get("metadata"))
        fp = meta.get(_INDEXING_CONTENT_FP_KEY)
        prev_mode = meta.get("indexing_hash_mode")
        stored_hash = (row.get("image_hash") or "").strip() or None

        if (
            not force
            and not upgrade_version
            and stored_hash
            and _content_fp_matches_file(fp, file_path)
            and prev_mode == cfg_mode
        ):
            skipped += 1
            continue

        ident = image_identity_hash.compute_image_identity_hash(file_path)
        if not ident:
            logger.warning("Hash computation failed for id=%s: %s", img_id, file_path)
            errors += 1
            continue

        img_hash, hv = ident

        # For upgrade mode, skip if result is still v1 (no embedded JPEG found)
        if upgrade_version and hv == image_identity_hash.HASH_VERSION_FULL_FILE:
            skipped += 1
            continue

        if dry_run:
            logger.info(
                "[DRY-RUN] id=%s v%d->v%d hash=%s...: %s",
                img_id, row.get("hash_version", 1), hv, img_hash[:16], file_path,
            )
            updated += 1
            continue

        try:
            db.update_image_field(int(img_id), "image_hash", img_hash)
            db.update_image_field(int(img_id), "hash_version", int(hv))

            # Persist fingerprint + mode in metadata
            merged = _attach_indexing_content_fp(meta, file_path)
            merged["indexing_hash_mode"] = cfg_mode
            db.update_image_field(int(img_id), "metadata", json.dumps(merged))

            # Ensure file_paths row exists
            db.register_image_path(int(img_id), file_path)

            updated += 1
        except Exception as e:
            logger.error("Error updating id=%s (%s): %s", img_id, file_path, e)
            errors += 1

        if (i + 1) % batch_size == 0:
            logger.info(
                "Progress: %d/%d (updated=%d, skipped=%d, errors=%d)",
                i + 1, total, updated, skipped, errors,
            )

    logger.info(
        "Backfill complete. Total=%d, Updated=%d, Skipped=%d, Errors=%d",
        total, updated, skipped, errors,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Backfill/upgrade image hashes")
    parser.add_argument("--force", action="store_true", help="Recompute all hashes")
    parser.add_argument(
        "--upgrade-version", action="store_true",
        help="Upgrade v1 RAW hashes to v2 content_preview",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writes")
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Progress reporting interval (default: 50)",
    )
    args = parser.parse_args()
    backfill_hashes(
        force=args.force,
        upgrade_version=args.upgrade_version,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )
