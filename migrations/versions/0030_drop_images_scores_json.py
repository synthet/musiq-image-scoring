"""drop legacy images.scores_json column

Per-model scores live in ``image_model_scores`` (migration 0016); aggregates on
``images``; technical failures in ``image_technical_failures``.

PRE-DEPLOY: run ``python scripts/maintenance/verify_scores_json_parity.py --backfill``
and confirm ``column_only`` is 0 or only non-scoring metadata blobs (no ``models`` block).

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "images" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("images")}
    if "scores_json" not in cols:
        return
    op.drop_column("images", "scores_json")


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "images" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("images")}
    if "scores_json" in cols:
        return
    op.add_column("images", sa.Column("scores_json", sa.Text(), nullable=True))
