"""drop legacy per-model score columns

Drop ``images.score_spaq``, ``score_ava``, ``score_koniq``, ``score_paq2piq``
and ``score_liqe``. Per-model scores now live in ``image_model_scores``
(migration 0016).

PRE-DEPLOY REQUIREMENT
======================
Run the backfill BEFORE applying this migration on any environment that
existed before image_model_scores dual-write was introduced::

    python scripts/maintenance/backfill_legacy_model_scores.py --apply

The upgrade aborts loudly if it detects images whose legacy columns are
populated but whose ``image_model_scores`` row is missing — that data would
be silently destroyed otherwise. Set
``ALLOW_DROP_LEGACY_MODEL_SCORES_WITHOUT_BACKFILL=1`` to override (e.g.
greenfield or already-pruned databases).

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-24 12:00:00.000000

"""
from __future__ import annotations

import logging
import os

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


_LEGACY_COLUMNS = ("score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe")
_MODEL_FOR_COLUMN = {
    "score_spaq": "spaq",
    "score_ava": "ava",
    "score_koniq": "koniq",
    "score_paq2piq": "paq2piq",
    "score_liqe": "liqe",
}

logger = logging.getLogger("alembic.runtime.migration")


def _existing_legacy_columns(conn) -> list[str]:
    rows = conn.exec_driver_sql(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'images'
           AND column_name = ANY(%(cols)s)
        """,
        {"cols": list(_LEGACY_COLUMNS)},
    ).fetchall()
    return [r[0] for r in rows]


def _guard_against_unbackfilled_data(conn, present_cols: list[str]) -> None:
    if os.environ.get("ALLOW_DROP_LEGACY_MODEL_SCORES_WITHOUT_BACKFILL") == "1":
        logger.warning(
            "ALLOW_DROP_LEGACY_MODEL_SCORES_WITHOUT_BACKFILL=1; skipping backfill guard"
        )
        return

    leftovers: dict[str, int] = {}
    for col in present_cols:
        model = _MODEL_FOR_COLUMN[col]
        n = conn.exec_driver_sql(
            f"""
            SELECT COUNT(*)
              FROM images i
             WHERE i.{col} IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM image_model_scores ims
                    WHERE ims.image_id = i.id AND ims.model_name = %(m)s
               )
            """,
            {"m": model},
        ).scalar() or 0
        if n:
            leftovers[col] = int(n)

    if leftovers:
        summary = ", ".join(f"{c}: {n}" for c, n in leftovers.items())
        raise RuntimeError(
            "Refusing to drop legacy per-model score columns: "
            f"{summary} images have values that are not yet in image_model_scores. "
            "Run scripts/maintenance/backfill_legacy_model_scores.py --apply first, "
            "or set ALLOW_DROP_LEGACY_MODEL_SCORES_WITHOUT_BACKFILL=1 to override."
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    present = _existing_legacy_columns(bind)
    if not present:
        return

    _guard_against_unbackfilled_data(bind, present)
    for col in present:
        op.execute(f"ALTER TABLE images DROP COLUMN IF EXISTS {col}")


def downgrade() -> None:
    # Re-create the columns as DOUBLE PRECISION; data is not restored.
    # Use scripts/maintenance/backfill_legacy_model_scores.py in reverse,
    # or restore from backup, to repopulate values.
    for col in _LEGACY_COLUMNS:
        op.execute(f"ALTER TABLE images ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION")
