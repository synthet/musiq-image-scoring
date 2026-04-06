#!/usr/bin/env python3
"""
Repair malformed images.thumbnail_path / thumbnail_path_win values.

Canonical form (see modules.thumbnails.thumbnail_pair_needs_repair):
  thumbnail_path:      /mnt/<drive>/.../thumbnails/<2-hex>/<md5>.jpg
  thumbnail_path_win:  <Drive>:\\...\\thumbnails\\<2-hex>\\<md5>.jpg

Fixes Docker-style /app/thumbnails/..., static/cwd leaks, relative ../ paths,
and rows missing one of the two columns. Repoints to real files under
backend thumbnails/ when possible.

Prevention (Docker): set IMAGE_SCORING_HOST_PROJECT_WSL and
IMAGE_SCORING_HOST_PROJECT_WIN (or paths.host_project_root_* in config.json)
so new writes store /mnt/... and D:\\... instead of /app/thumbnails/...

For bounded batches from the Web UI, use POST /api/maintenance/repair-thumbnail-paths.

Usage (WSL, same venv as webapp):
  python scripts/maintenance/repair_thumbnail_path_columns.py --dry-run
  python scripts/maintenance/repair_thumbnail_path_columns.py
  python scripts/maintenance/repair_thumbnail_path_columns.py --all --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from modules import db  # noqa: E402
from modules.thumbnail_maintenance import repair_thumbnail_paths_batch  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair thumbnail_path columns in images table.")
    parser.add_argument("--dry-run", action="store_true", help="Log changes only, do not UPDATE")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Consider every non-empty row; update when normalize_stored_thumbnail_pair changes values (slower)",
    )
    args = parser.parse_args()

    db.init_db()
    r = repair_thumbnail_paths_batch(
        limit=None,
        repair_all_pairs=args.all,
        dry_run=args.dry_run,
    )
    logger.info("Done. rows_scanned=%s updated=%s unchanged=%s", r["scanned"], r["repaired"], r["unchanged"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
