"""Add GPS and geocoding fields to image_exif.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("image_exif", sa.Column("gps_latitude", sa.Double(), nullable=True))
    op.add_column("image_exif", sa.Column("gps_longitude", sa.Double(), nullable=True))
    op.add_column("image_exif", sa.Column("gps_altitude", sa.Double(), nullable=True))
    op.add_column("image_exif", sa.Column("gps_position_source", sa.String(20), nullable=True))
    op.add_column("image_exif", sa.Column("location_resolved", JSONB(), nullable=True))
    op.add_column("image_exif", sa.Column("geocoded_at", sa.DateTime(), nullable=True))
    op.add_column("image_exif", sa.Column("geocode_provider", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("image_exif", "geocode_provider")
    op.drop_column("image_exif", "geocoded_at")
    op.drop_column("image_exif", "location_resolved")
    op.drop_column("image_exif", "gps_position_source")
    op.drop_column("image_exif", "gps_altitude")
    op.drop_column("image_exif", "gps_longitude")
    op.drop_column("image_exif", "gps_latitude")
