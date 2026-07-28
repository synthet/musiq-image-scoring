"""images.bird_bbox — bounding box of the detected bird (YOLO ``synthet/bird-detect-v0``).

Populated by the ``bird_species`` phase or ``scripts/backfill_bird_bbox.py``: the detector
localizes the bird, (for species jobs) the crop is fed to BioCLIP, and the box is stored
here as JSON ``{"x1","y1","x2","y2","conf","img_w","img_h"}`` (pixel coordinates).

Semantics:
  - ``NULL`` — never scanned (detector has not run for this row).
  - ``{"detected": false}`` — detector ran and found no bird (``BBOX_NOT_DETECTED``).
  - xyxy object — highest-confidence bird box in EXIF-oriented pixel space.

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
