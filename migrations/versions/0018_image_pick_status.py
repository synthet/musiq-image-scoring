"""images.pick_status — first-class pick/reject flag for the Culling workspace.

Values:  1 = picked, -1 = rejected, 0 = unflagged (default).
The PATCH /api/images/{id} endpoint mirrors this to legacy rating/label so existing
gallery filters keep working until Electron migrates.

Uses ``ADD COLUMN IF NOT EXISTS`` so this migration stays safe if ``modules/db_postgres``
init DDL already applied the column.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-02
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE images
        ADD COLUMN IF NOT EXISTS pick_status SMALLINT NOT NULL DEFAULT 0
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_images_pick_status ON images(pick_status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_images_pick_status")
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS pick_status")
