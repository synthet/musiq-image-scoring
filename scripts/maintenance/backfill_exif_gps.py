#!/usr/bin/env python3
"""Re-extract EXIF from disk for rows missing gps_latitude / gps_longitude in image_exif."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db  # noqa: E402
from modules.exif_extractor import backfill_exif_gps  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "Backfill GPS coordinates in image_exif by re-reading files with exiftool "
            "for rows missing gps_latitude or gps_longitude."
        )
    )
    p.add_argument("--limit", type=int, default=5000, help="Rows per batch (default 5000)")
    p.add_argument(
        "--once",
        action="store_true",
        help="Single batch only; do not loop until no rows remain",
    )
    p.add_argument(
        "--path-like",
        metavar="PATTERN",
        help=r"Optional SQL LIKE filter on images.file_path (e.g. %/Photos/2024/%)",
    )
    args = p.parse_args()

    db.init_db()
    grand = {
        "checked": 0,
        "updated": 0,
        "skipped_no_file": 0,
        "skipped_no_exif": 0,
        "skipped_still_missing": 0,
        "errors": 0,
    }
    while True:
        stats = backfill_exif_gps(limit=args.limit, path_like=args.path_like)
        for k in grand:
            grand[k] += stats[k]
        logger.info("batch %s | cumulative %s", stats, grand)
        if args.once or stats["checked"] == 0:
            break
    logger.info("finished %s", grand)


if __name__ == "__main__":
    main()
