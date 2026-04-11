#!/usr/bin/env python3
"""
Report how many images have a real capture date in EXIF/XMP cache vs missing (import fallback only).

Uses the same effective shot-date rule as the gallery:
  COALESCE(image_exif.date_time_original, image_exif.create_date, image_xmp.create_date)

PostgreSQL only (database.engine = postgres).

Run in WSL with ~/.venvs/tf:
  python scripts/maintenance/report_capture_date_coverage.py
  python scripts/maintenance/report_capture_date_coverage.py --json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report capture-date coverage in the DB")
    parser.add_argument("--json", action="store_true", help="Print one JSON object only")
    args = parser.parse_args()

    from modules import config, db

    if config.get_database_engine() != "postgres":
        logger.error("This report requires database.engine=postgres")
        return 2

    db.init_db()

    sql = """
    SELECT
        COUNT(*)::bigint AS total_images,
        SUM(
            CASE WHEN COALESCE(ex.date_time_original, ex.create_date, xm.create_date) IS NOT NULL
            THEN 1 ELSE 0 END
        )::bigint AS with_shot_date_metadata,
        SUM(
            CASE WHEN COALESCE(ex.date_time_original, ex.create_date, xm.create_date) IS NULL
            THEN 1 ELSE 0 END
        )::bigint AS missing_shot_date_metadata,
        SUM(CASE WHEN ex.image_id IS NULL THEN 1 ELSE 0 END)::bigint AS no_image_exif_row,
        SUM(CASE WHEN ex.date_time_original IS NOT NULL THEN 1 ELSE 0 END)::bigint AS has_date_time_original,
        SUM(
            CASE WHEN ex.date_time_original IS NULL AND ex.create_date IS NOT NULL
            THEN 1 ELSE 0 END
        )::bigint AS has_create_date_only_in_exif,
        SUM(
            CASE WHEN xm.create_date IS NOT NULL
                 AND ex.date_time_original IS NULL
                 AND ex.create_date IS NULL
            THEN 1 ELSE 0 END
        )::bigint AS xmp_create_date_only
    FROM images i
    LEFT JOIN image_exif ex ON ex.image_id = i.id
    LEFT JOIN image_xmp xm ON xm.image_id = i.id
    """
    row = db.get_connector().query_one(sql, ())
    if not row:
        logger.error("Query returned no row")
        return 1

    def _int(k: str) -> int:
        v = row.get(k)
        if v is None:
            return 0
        return int(v)

    total = _int("total_images")
    with_meta = _int("with_shot_date_metadata")
    missing = _int("missing_shot_date_metadata")

    pct = (100.0 * with_meta / total) if total else 0.0
    out = {
        "total_images": total,
        "with_shot_date_metadata": with_meta,
        "missing_shot_date_metadata": missing,
        "pct_with_shot_date_metadata": round(pct, 2),
        "no_image_exif_row": _int("no_image_exif_row"),
        "has_date_time_original": _int("has_date_time_original"),
        "has_create_date_only_in_exif": _int("has_create_date_only_in_exif"),
        "xmp_create_date_only": _int("xmp_create_date_only"),
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    w = max(len(str(total)), 8)
    print("Capture date coverage (EXIF/XMP cache — same COALESCE as Electron gallery)")
    print("-" * 60)
    print(f"{'total_images':<36} {total:>{w}}")
    print(f"{'with_shot_date_metadata':<36} {with_meta:>{w}}  ({out['pct_with_shot_date_metadata']}%)")
    print(f"{'missing_shot_date_metadata':<36} {missing:>{w}}  (fallback to import time in UI)")
    print("-" * 60)
    print(f"{'no_image_exif_row':<36} {out['no_image_exif_row']:>{w}}")
    print(f"{'has_date_time_original':<36} {out['has_date_time_original']:>{w}}")
    print(f"{'has_create_date_only_in_exif':<36} {out['has_create_date_only_in_exif']:>{w}}")
    print(f"{'xmp_create_date_only':<36} {out['xmp_create_date_only']:>{w}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
