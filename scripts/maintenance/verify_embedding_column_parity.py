#!/usr/bin/env python3
"""
Audit parity between legacy ``images.image_embedding`` and ``image_embeddings``.

Reports column-only, table-only, and (optionally sampled) vector mismatches for the
default space ``mobilenet_v2_imagenet_gap``. Postgres-only.

Usage (WSL + ~/.venvs/tf):
  python scripts/maintenance/verify_embedding_column_parity.py
  python scripts/maintenance/verify_embedding_column_parity.py --backfill
  python scripts/maintenance/verify_embedding_column_parity.py --sample-mismatch 50
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
from modules.embedding_spaces import DEFAULT_EMBEDDING_SPACE_CODE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_BACKFILL_SQL = """
INSERT INTO image_embeddings (image_id, embedding_space_id, embedding, updated_at)
SELECT i.id, s.id, i.image_embedding, CURRENT_TIMESTAMP
FROM images i
CROSS JOIN (
    SELECT id FROM embedding_spaces WHERE code = %s LIMIT 1
) s
WHERE i.image_embedding IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM image_embeddings ie
      WHERE ie.image_id = i.id AND ie.embedding_space_id = s.id
  )
ON CONFLICT (image_id, embedding_space_id) DO NOTHING
"""


def _require_postgres() -> None:
    if config.get_database_engine() != "postgres":
        logger.error("This script requires database.engine=postgres")
        sys.exit(2)


def _space_id():
    from modules import db_postgres

    row = db_postgres.execute_select_one(
        "SELECT id FROM embedding_spaces WHERE code = %s",
        (DEFAULT_EMBEDDING_SPACE_CODE,),
    )
    if not row:
        logger.error("embedding_spaces row missing for %s", DEFAULT_EMBEDDING_SPACE_CODE)
        sys.exit(2)
    return int(row["id"])


def _column_exists() -> bool:
    from modules import db

    return db._postgres_images_has_image_embedding_column()


def run_audit(sample_mismatch: int = 0) -> dict:
    from modules import db_postgres

    if not _column_exists():
        both = db_postgres.execute_select_one(
            """
            SELECT COUNT(DISTINCT ie.image_id) AS c
            FROM image_embeddings ie
            JOIN embedding_spaces es ON es.id = ie.embedding_space_id
            WHERE es.code = %s
            """,
            (DEFAULT_EMBEDDING_SPACE_CODE,),
        )
        with_emb = int((both or {}).get("c") or 0)
        return {
            "embedding_space": DEFAULT_EMBEDDING_SPACE_CODE,
            "column_only": 0,
            "table_only": with_emb,
            "both_present": with_emb,
            "legacy_column_rows": 0,
            "legacy_column_dropped": True,
            "sampled_mismatches": 0,
        }

    space_id = _space_id()
    column_only = db_postgres.execute_select_one(
        """
        SELECT COUNT(*) AS c FROM images i
        WHERE i.image_embedding IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM image_embeddings ie
              WHERE ie.image_id = i.id AND ie.embedding_space_id = %s
          )
        """,
        (space_id,),
    )
    table_only = db_postgres.execute_select_one(
        """
        SELECT COUNT(*) AS c FROM images i
        WHERE i.image_embedding IS NULL
          AND EXISTS (
              SELECT 1 FROM image_embeddings ie
              WHERE ie.image_id = i.id AND ie.embedding_space_id = %s
          )
        """,
        (space_id,),
    )
    both = db_postgres.execute_select_one(
        """
        SELECT COUNT(*) AS c FROM images i
        WHERE i.image_embedding IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM image_embeddings ie
              WHERE ie.image_id = i.id AND ie.embedding_space_id = %s
          )
        """,
        (space_id,),
    )
    legacy_column_rows = db_postgres.execute_select_one(
        "SELECT COUNT(*) AS c FROM images WHERE image_embedding IS NOT NULL",
        (),
    )

    report = {
        "embedding_space": DEFAULT_EMBEDDING_SPACE_CODE,
        "column_only": int((column_only or {}).get("c") or 0),
        "table_only": int((table_only or {}).get("c") or 0),
        "both_present": int((both or {}).get("c") or 0),
        "legacy_column_rows": int((legacy_column_rows or {}).get("c") or 0),
        "legacy_column_dropped": False,
        "sampled_mismatches": 0,
    }

    if sample_mismatch > 0 and report["both_present"] > 0:
        import numpy as np

        rows = db_postgres.execute_select(
            """
            SELECT i.id,
                   i.image_embedding AS col_emb,
                   ie.embedding AS tbl_emb
            FROM images i
            JOIN image_embeddings ie
              ON ie.image_id = i.id AND ie.embedding_space_id = %s
            WHERE i.image_embedding IS NOT NULL
            ORDER BY i.id
            LIMIT %s
            """,
            (space_id, int(sample_mismatch)),
        )
        mismatches = 0
        for r in rows:
            col = np.asarray(r["col_emb"], dtype=np.float32).reshape(-1)
            tbl = np.asarray(r["tbl_emb"], dtype=np.float32).reshape(-1)
            if col.shape != tbl.shape or not np.allclose(col, tbl, rtol=1e-5, atol=1e-6):
                mismatches += 1
        report["sampled_mismatches"] = mismatches

    return report


def run_backfill() -> int:
    from modules import db_postgres

    if not _column_exists():
        logger.info("Legacy column already dropped; backfill not needed")
        return 0

    with db_postgres.PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(_BACKFILL_SQL, (DEFAULT_EMBEDDING_SPACE_CODE,))
            return int(cur.rowcount or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Copy column-only vectors into image_embeddings (idempotent)",
    )
    parser.add_argument(
        "--sample-mismatch",
        type=int,
        default=0,
        metavar="N",
        help="Compare up to N rows where both column and table have data",
    )
    parser.add_argument("--json", action="store_true", help="Print report as JSON")
    args = parser.parse_args()

    _require_postgres()

    if args.backfill:
        inserted = run_backfill()
        logger.info("Backfill finished (rowcount hint): %s", inserted)

    report = run_audit(sample_mismatch=args.sample_mismatch)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for k, v in report.items():
            logger.info("%s: %s", k, v)

    if report["column_only"] > 0:
        logger.warning(
            "column_only > 0: run with --backfill before disabling legacy column writes"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
