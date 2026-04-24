"""Multi-dimension image embeddings: 512-d and 768-d tables + spaces.

Adds per-dimension fact tables ``image_embeddings_512`` and
``image_embeddings_768`` (same shape as existing 1280-d ``image_embeddings``)
with HNSW cosine indexes, and seeds three new ``embedding_spaces`` rows for
CLIP, BioCLIP, and BLIP image-tower features.

See ``docs/plans/database/DB_VECTORS_REFACTOR.md`` (Pattern B: registry +
keyed fact table per dimension family) and the checklist in
``docs/technical/EMBEDDINGS.md``.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


_NEW_SPACES = (
    ("clip_vit_b32_image", 512, "CLIP ViT-B/32 image tower (transformers) — tagging/similarity"),
    ("bioclip_2_image", 512, "BioCLIP 2 image tower (open_clip) — bird/species similarity"),
    ("blip_vit_b16_image", 768, "BLIP base vision encoder pooler_output — caption-aligned similarity"),
)


def _create_per_dim_table(conn: "sa.engine.Connection", dim: int) -> None:
    table = f"image_embeddings_{dim}"
    op.create_table(
        table,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("embedding_space_id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["embedding_space_id"], ["embedding_spaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "image_id", "embedding_space_id", name=f"uq_{table}_image_space"
        ),
    )
    conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN embedding vector({dim}) NOT NULL;"))
    op.create_index(f"idx_{table}_image", table, ["image_id"], unique=False)
    op.create_index(f"idx_{table}_space", table, ["embedding_space_id"], unique=False)
    conn.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{table}_hnsw
            ON {table} USING hnsw (embedding vector_cosine_ops);
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

    _create_per_dim_table(conn, 512)
    _create_per_dim_table(conn, 768)

    for code, dim, description in _NEW_SPACES:
        conn.execute(
            sa.text(
                """
                INSERT INTO embedding_spaces (code, dim, description, active)
                SELECT :code, :dim, :description, 1
                WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = :code);
                """
            ),
            {"code": code, "dim": dim, "description": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for code, _dim, _desc in _NEW_SPACES:
        conn.execute(
            sa.text("DELETE FROM embedding_spaces WHERE code = :code"),
            {"code": code},
        )
    for dim in (768, 512):
        table = f"image_embeddings_{dim}"
        conn.execute(sa.text(f"DROP INDEX IF EXISTS idx_{table}_hnsw;"))
        op.drop_index(f"idx_{table}_space", table_name=table)
        op.drop_index(f"idx_{table}_image", table_name=table)
        op.drop_table(table)
