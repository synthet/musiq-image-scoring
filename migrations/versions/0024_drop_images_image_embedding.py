"""drop legacy images.image_embedding column

Default MobileNet vectors live in ``image_embeddings`` (migration 0004+).
Removes duplicate ``images.image_embedding`` and its HNSW index.

PRE-DEPLOY: run ``python scripts/maintenance/verify_embedding_column_parity.py --backfill``
and confirm ``column_only`` is 0.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-24 18:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

_DEFAULT_SPACE = "mobilenet_v2_imagenet_gap"

_BACKFILL = sa.text(
    f"""
    INSERT INTO image_embeddings (image_id, embedding_space_id, embedding, updated_at)
    SELECT i.id, s.id, i.image_embedding, CURRENT_TIMESTAMP
    FROM images i
    CROSS JOIN (
        SELECT id FROM embedding_spaces WHERE code = '{_DEFAULT_SPACE}' LIMIT 1
    ) s
    WHERE i.image_embedding IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM image_embeddings ie
          WHERE ie.image_id = i.id AND ie.embedding_space_id = s.id
      )
    ON CONFLICT (image_id, embedding_space_id) DO NOTHING
    """
)


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "images" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("images")}
    if "image_embedding" not in cols:
        return

    conn.execute(_BACKFILL)
    op.execute("DROP INDEX IF EXISTS idx_images_embedding_hnsw")
    op.drop_column("images", "image_embedding")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.execute(sa.text("ALTER TABLE images ADD COLUMN IF NOT EXISTS image_embedding vector(1280)"))
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_images_embedding_hnsw
            ON images USING hnsw (image_embedding vector_cosine_ops)
            """
        )
    )
    conn.execute(
        sa.text(
            f"""
            UPDATE images i
            SET image_embedding = ie.embedding
            FROM image_embeddings ie
            JOIN embedding_spaces es ON es.id = ie.embedding_space_id
            WHERE ie.image_id = i.id AND es.code = '{_DEFAULT_SPACE}'
            """
        )
    )
