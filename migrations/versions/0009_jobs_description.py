"""Add jobs.description for human troubleshooting context.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "description")
