"""Partial unique index on (image_hash, hash_version) where image_hash is set.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-13

Replaces non-unique idx_images_hash_version with a partial UNIQUE index so the same
digest + version cannot appear on two rows when image_hash is non-null.

If upgrade fails with a uniqueness violation, deduplicate ``images`` rows first, e.g.::

    SELECT image_hash, hash_version, COUNT(*) FROM images
    WHERE image_hash IS NOT NULL
    GROUP BY image_hash, hash_version HAVING COUNT(*) > 1;
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_images_hash_version;")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_hash_hash_version
        ON images (image_hash, hash_version)
        WHERE image_hash IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_images_image_hash_hash_version;")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_images_hash_version
        ON images(image_hash, hash_version)
        WHERE image_hash IS NOT NULL;
        """
    )
