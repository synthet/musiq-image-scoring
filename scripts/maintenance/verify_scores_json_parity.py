#!/usr/bin/env python3
"""
Audit parity between legacy ``images.scores_json`` and ``image_model_scores``.

Reports column-only rows (blob present, no production IMS outputs), ims-only rows
(expected when dual-write is disabled), and both-present overlap. Postgres-only.

Usage (WSL + ~/.venvs/tf):
  python scripts/maintenance/verify_scores_json_parity.py
  python scripts/maintenance/verify_scores_json_parity.py --backfill
  python scripts/maintenance/verify_scores_json_parity.py --backfill --limit 500
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _require_postgres() -> None:
    if config.get_database_engine() != "postgres":
        logger.error("This script requires database.engine=postgres")
        sys.exit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Parse column-only scores_json blobs into image_model_scores (idempotent upsert)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Max rows to backfill (0 = all column-only rows)",
    )
    parser.add_argument("--json", action="store_true", help="Print report as JSON")
    args = parser.parse_args()

    _require_postgres()

    from modules import db

    if args.backfill:
        n = db.backfill_image_model_scores_from_scores_json(limit=args.limit)
        logger.info("Backfill processed %s image(s)", n)

    report = db.get_scores_json_parity_report()
    if "error" in report:
        logger.error("Audit failed: %s", report["error"])
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for k, v in report.items():
            logger.info("%s: %s", k, v)

    if report.get("legacy_column_dropped"):
        return 0

    if report.get("column_only", 0) > 0:
        logger.warning(
            "column_only > 0: run with --backfill before disabling legacy column writes "
            "or dropping images.scores_json"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
