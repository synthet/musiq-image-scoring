"""Add images.hash_version for content-identity hashing.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-13

1 = full-file SHA-256; 2 = embedded JPEG / preview payload SHA-256 (see modules/image_identity_hash.py).
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE images
        ADD COLUMN IF NOT EXISTS hash_version INTEGER NOT NULL DEFAULT 1;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_images_hash_version
        ON images(image_hash, hash_version)
        WHERE image_hash IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_images_hash_version;")
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS hash_version;")
