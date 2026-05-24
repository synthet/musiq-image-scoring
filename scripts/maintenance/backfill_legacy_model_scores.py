#!/usr/bin/env python3
"""Backfill legacy ``images.score_*`` columns into ``image_model_scores``.

The five typed columns ``score_spaq``, ``score_ava``, ``score_koniq``,
``score_paq2piq`` and ``score_liqe`` predate the per-model ``image_model_scores``
table (migration 0016). New scoring dual-writes both, but rows scored before
the dual-write only exist in the typed columns. This script copies the missing
rows into ``image_model_scores`` so the typed columns can be retired.

Policy:
- The legacy columns store **already-normalized** 0-1 values
  (see ``docs/technical/MODEL_INPUT_SPECIFICATIONS.md``), so we set both
  ``raw_score`` and ``normalized`` to the column value.
- Idempotent: only inserts when no ``(image_id, model_name)`` row exists.
- Status is always ``success`` (legacy columns are never written on failure).
- ``model_version`` is ``"legacy-backfill"``.

Run from WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python scripts/maintenance/backfill_legacy_model_scores.py --dry-run
    python scripts/maintenance/backfill_legacy_model_scores.py
    python scripts/maintenance/backfill_legacy_model_scores.py --model spaq --batch-size 5000
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Iterable

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db, db_postgres  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

LEGACY_MODELS: tuple[tuple[str, str], ...] = (
    ("spaq", "score_spaq"),
    ("ava", "score_ava"),
    ("koniq", "score_koniq"),
    ("paq2piq", "score_paq2piq"),
    ("liqe", "score_liqe"),
)

_MODEL_VERSION = "legacy-backfill"


def _gap_count(model_name: str, column: str) -> int:
    sql = (
        f"SELECT COUNT(*) AS n FROM images i "
        f"WHERE i.{column} IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM image_model_scores ims "
        f"WHERE ims.image_id = i.id AND ims.model_name = %s)"
    )
    row = db_postgres.execute_select_one(sql, (model_name,))
    return int(row["n"]) if row else 0


def _backfill_model(model_name: str, column: str, batch_size: int) -> int:
    """Insert missing rows for one model. Returns number of rows inserted."""
    sql = (
        "INSERT INTO image_model_scores "
        "(image_id, model_name, raw_score, normalized, status, is_shadow, model_version, scored_at) "
        f"SELECT i.id, %s, i.{column}, i.{column}, 'success', FALSE, %s, "
        "COALESCE(i.updated_at, i.created_at, CURRENT_TIMESTAMP) "
        "FROM images i "
        f"WHERE i.{column} IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM image_model_scores ims "
        "WHERE ims.image_id = i.id AND ims.model_name = %s) "
        "ORDER BY i.id "
        "LIMIT %s "
        "ON CONFLICT (image_id, model_name) DO NOTHING"
    )

    total_inserted = 0
    while True:
        inserted = db_postgres.execute_write(sql, (model_name, _MODEL_VERSION, model_name, batch_size))
        if not inserted:
            break
        total_inserted += inserted
        logger.info("  %s: inserted %d (running total %d)", model_name, inserted, total_inserted)
        if inserted < batch_size:
            break
    return total_inserted


def _selected_models(only: Iterable[str] | None) -> list[tuple[str, str]]:
    if not only:
        return list(LEGACY_MODELS)
    wanted = {m.strip().lower() for m in only if m and m.strip()}
    unknown = wanted - {m for m, _ in LEGACY_MODELS}
    if unknown:
        raise SystemExit(f"Unknown model(s): {sorted(unknown)}. Valid: {[m for m, _ in LEGACY_MODELS]}")
    return [(m, c) for m, c in LEGACY_MODELS if m in wanted]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill images.score_* columns into image_model_scores (Postgres-only).",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=None,
        choices=[m for m, _ in LEGACY_MODELS],
        help="Restrict to these models (repeatable). Default: all five legacy models.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Rows inserted per statement (default 10000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report counts; do not insert.",
    )
    args = parser.parse_args()

    db.init_db()

    conn = db.get_connector()
    if getattr(conn, "type", None) != "postgres":
        logger.error("Backfill is Postgres-only (current engine: %s).", getattr(conn, "type", "?"))
        return 1

    models = _selected_models(args.model)
    logger.info("Backfill targets: %s", [m for m, _ in models])

    gaps = {m: _gap_count(m, c) for m, c in models}
    total_gap = sum(gaps.values())
    for m, _ in models:
        logger.info("  %s: %d images need a row", m, gaps[m])
    logger.info("Total candidate rows: %d", total_gap)

    if args.dry_run or total_gap == 0:
        return 0

    t0 = time.time()
    grand_total = 0
    for model_name, column in models:
        if gaps[model_name] == 0:
            continue
        logger.info("Backfilling %s from images.%s", model_name, column)
        inserted = _backfill_model(model_name, column, max(1, args.batch_size))
        grand_total += inserted
        logger.info("  %s: done (%d inserted)", model_name, inserted)

    logger.info(
        "Backfill complete. inserted=%d elapsed=%.1fs",
        grand_total,
        time.time() - t0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
