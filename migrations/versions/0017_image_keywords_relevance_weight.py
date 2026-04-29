"""image_keywords.relevance_weight — per-tag relevance for ranking/filtering.

``confidence`` remains the model/source confidence; ``relevance_weight`` holds
relative importance of the keyword for the image (default 1.0).

Uses ``ADD COLUMN IF NOT EXISTS`` so this migration stays safe if ``modules/db_postgres``
init DDL already applied the column.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-28
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE image_keywords
        ADD COLUMN IF NOT EXISTS relevance_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE image_keywords DROP COLUMN IF EXISTS relevance_weight")
