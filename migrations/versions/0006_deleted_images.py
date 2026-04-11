"""deleted_images table + BEFORE DELETE trigger on images.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-10

Tracks removed image rows for Sync/Import skip and Backup manifest cleanup.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_images (
            id              SERIAL PRIMARY KEY,
            original_id     INTEGER,
            image_uuid      VARCHAR(36),
            image_hash      VARCHAR(64),
            file_name       VARCHAR(255),
            original_path   VARCHAR(4000),
            deleted_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_original_id ON deleted_images(original_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_uuid ON deleted_images(image_uuid) "
        "WHERE image_uuid IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_hash ON deleted_images(image_hash) "
        "WHERE image_hash IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_file_uuid ON deleted_images(file_name, image_uuid) "
        "WHERE image_uuid IS NOT NULL;"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_record_deleted_image_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO deleted_images (original_id, image_uuid, image_hash, file_name, original_path)
            VALUES (OLD.id, OLD.image_uuid, OLD.image_hash, OLD.file_name, OLD.file_path);
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_record_deleted_image ON images;")
    op.execute(
        """
        CREATE TRIGGER trg_record_deleted_image
            BEFORE DELETE ON images
            FOR EACH ROW
            EXECUTE PROCEDURE trg_record_deleted_image_fn();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_record_deleted_image ON images;")
    op.execute("DROP FUNCTION IF EXISTS trg_record_deleted_image_fn();")
    op.execute("DROP TABLE IF EXISTS deleted_images;")
