"""add image_xmp accessibility columns

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-25 12:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "image_xmp" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("image_xmp")}
    if "alt_text" not in cols:
        op.add_column("image_xmp", sa.Column("alt_text", sa.Text(), nullable=True))
    if "extended_description" not in cols:
        op.add_column(
            "image_xmp",
            sa.Column("extended_description", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "image_xmp" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("image_xmp")}
    if "extended_description" in cols:
        op.drop_column("image_xmp", "extended_description")
    if "alt_text" in cols:
        op.drop_column("image_xmp", "alt_text")
