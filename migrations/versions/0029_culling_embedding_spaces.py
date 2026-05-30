"""Register optional culling embedding spaces (768-d towers from the 2026-05-29 spike).

Adds registry rows for OpenCLIP L/14, OpenAI CLIP L/14, DINOv2-reg base, and
SigLIP2 base image towers so they are selectable per two-level culling level
(``culling.two_level.level*.embedding_space``). Additive and idempotent — vectors
land in the existing ``image_embeddings_768`` table; no new physical storage.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

# (code, dim, description) — keep in sync with modules/embedding_spaces.SPACE_DIMS
# and modules/db_postgres._SEED_EXTRA_EMBEDDING_SPACES_SQL.
_CULLING_SPACES = [
    (
        "openclip_l14_laion2b_image",
        768,
        "OpenCLIP ViT-L/14 laion2b_s32b_b82k image tower — culling grouping (A/B)",
    ),
    (
        "openai_clip_vit_l14_image",
        768,
        "OpenAI CLIP ViT-L/14 image tower — culling grouping / semantic sub-stack",
    ),
    (
        "dinov2_reg_base_image",
        768,
        "DINOv2-reg base image tower (timm proxy) — culling grouping (HOLD)",
    ),
    (
        "siglip2_base_image",
        768,
        "SigLIP2 base patch16-224 image tower — culling grouping / keywords",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, dim, description in _CULLING_SPACES:
        conn.exec_driver_sql(
            """
            INSERT INTO embedding_spaces (code, dim, description, active)
            SELECT %s, %s, %s, 1
            WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = %s)
            """,
            (code, dim, description, code),
        )


def downgrade() -> None:
    conn = op.get_bind()
    for code, _dim, _description in _CULLING_SPACES:
        # Only drop the registry row; per-dim fact rows (if any were generated)
        # cascade via the embedding_space_id FK.
        conn.exec_driver_sql(
            "DELETE FROM embedding_spaces WHERE code = %s",
            (code,),
        )
