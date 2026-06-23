"""One-shot backfill: sync images.pick_status from images.cull_decision.

Run after enabling pick_status sync in batch_update_cull_decisions for libraries
that already have cull_decision set but pick_status still 0.

WSL + ~/.venvs/tf:
  python -m scripts.backfill_pick_status_from_cull_decision --dry-run
  python -m scripts.backfill_pick_status_from_cull_decision
"""

from __future__ import annotations

import argparse
import logging

from modules import db

logger = logging.getLogger(__name__)

_BACKFILL_SQL = """
UPDATE images
SET pick_status = CASE LOWER(TRIM(cull_decision))
    WHEN 'pick' THEN 1
    WHEN 'reject' THEN -1
    WHEN 'neutral' THEN 0
    ELSE pick_status
END
WHERE cull_decision IS NOT NULL
  AND TRIM(cull_decision) <> ''
  AND LOWER(TRIM(cull_decision)) IN ('pick', 'reject', 'neutral')
  AND (
    pick_status IS NULL
    OR pick_status <> CASE LOWER(TRIM(cull_decision))
        WHEN 'pick' THEN 1
        WHEN 'reject' THEN -1
        WHEN 'neutral' THEN 0
        ELSE pick_status
    END
  )
"""

_COUNT_SQL = """
SELECT COUNT(*)::int AS n
FROM images
WHERE cull_decision IS NOT NULL
  AND TRIM(cull_decision) <> ''
  AND LOWER(TRIM(cull_decision)) IN ('pick', 'reject', 'neutral')
  AND (
    pick_status IS NULL
    OR pick_status <> CASE LOWER(TRIM(cull_decision))
        WHEN 'pick' THEN 1
        WHEN 'reject' THEN -1
        WHEN 'neutral' THEN 0
        ELSE pick_status
    END
  )
"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count rows only; no UPDATE")
    args = parser.parse_args()

    conn = db.get_connector()
    row = conn.query_one(_COUNT_SQL) or {}
    pending = int(row.get("n") or 0)
    logger.info("Rows needing pick_status sync: %d", pending)
    if args.dry_run or pending == 0:
        return 0

    conn.execute(_BACKFILL_SQL)
    logger.info("Backfill complete (%d rows)", pending)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
