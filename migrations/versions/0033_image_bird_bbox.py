"""images.bird_bbox — bounding box of the detected bird (YOLO ``synthet/bird-detect-v0``).

Populated by the ``bird_species`` phase: the detector localizes the bird, the crop is fed to
BioCLIP for species classification, and the box is stored here as JSON
``{"x1","y1","x2","y2","conf","img_w","img_h"}`` (pixel coordinates). NULL when no bird was
detected (whole image classified) or detection was disabled.

Uses ``ADD COLUMN IF NOT EXISTS`` so this migration stays safe if ``modules/db_postgres``
init DDL already applied the column.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-26
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE images
        ADD COLUMN IF NOT EXISTS bird_bbox JSONB
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS bird_bbox")
