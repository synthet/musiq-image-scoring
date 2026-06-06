"""
Release stale image_phase_work_claims rows on terminal jobs.

Open claims (queued/running) on interrupted/failed/completed/canceled jobs block
JIT run planning. Safe to run repeatedly (idempotent).

Usage (WSL + ~/.venvs/tf):
  python scripts/maintenance/reconcile_orphan_work_claims.py
  python scripts/maintenance/reconcile_orphan_work_claims.py --dry-run
  python scripts/maintenance/reconcile_orphan_work_claims.py --limit-jobs 1000
  python scripts/maintenance/reconcile_orphan_work_claims.py --until-clear
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from modules import db
from modules.phase_work_claims import (
    _TERMINAL_JOB_STATUSES,
    reconcile_orphan_work_claims,
    reconcile_orphan_work_claims_all,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _count_open_orphan_claims() -> int:
    placeholders = ",".join("?" * len(_TERMINAL_JOB_STATUSES))
    row = db.get_connector().query_one(
        f"""
        SELECT COUNT(*) AS cnt
        FROM image_phase_work_claims c
        JOIN jobs j ON j.id = c.job_id
        WHERE c.status IN ('queued', 'running')
          AND j.status IN ({placeholders})
        """,
        tuple(_TERMINAL_JOB_STATUSES),
    )
    return int((row or {}).get("cnt") or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Release orphan phase work claims on terminal jobs")
    parser.add_argument("--dry-run", action="store_true", help="Report counts only; do not release")
    parser.add_argument("--limit-jobs", type=int, default=500, help="Max distinct jobs per pass")
    parser.add_argument(
        "--until-clear",
        action="store_true",
        help="Repeat passes until no claims released (max 20 passes)",
    )
    args = parser.parse_args()

    before = _count_open_orphan_claims()
    logger.info("Open orphan claims before: %s", before)
    if args.dry_run:
        logger.info("Dry run — no changes applied")
        return 0

    if args.until_clear:
        summary = reconcile_orphan_work_claims_all(limit_jobs=args.limit_jobs)
    else:
        summary = reconcile_orphan_work_claims(limit_jobs=args.limit_jobs)
    after = _count_open_orphan_claims()
    logger.info(
        "Released %s row(s) in %s pass(es) across job_ids=%s; open orphan claims after: %s",
        summary.get("released_rows"),
        summary.get("passes", 1),
        summary.get("job_ids"),
        after,
    )
    if after > 0:
        logger.warning(
            "Still %s open orphan claim(s); re-run with --until-clear or raise --limit-jobs",
            after,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
