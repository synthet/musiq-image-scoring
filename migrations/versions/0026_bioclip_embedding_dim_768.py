"""Correct bioclip_2_image registry dim: BioCLIP 2 is ViT-L/14 (768-d).

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-25

BioCLIP 2 ``encode_image`` outputs 768-d vectors. The space was incorrectly
registered as 512-d at migration 0012, causing bird_species embedding upserts
to fail with dim mismatch.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE embedding_spaces
            SET dim = 768,
                description = 'BioCLIP 2 image tower ViT-L/14 (open_clip) — bird/species similarity'
            WHERE code = 'bioclip_2_image' AND dim = 512
            """
        )
    )
    # Remove any 512-d rows written before the registry fix (invalid length).
    conn.execute(
        sa.text(
            """
            DELETE FROM image_embeddings_512 e
            USING embedding_spaces s
            WHERE e.embedding_space_id = s.id
              AND s.code = 'bioclip_2_image'
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM image_embeddings_768 e
            USING embedding_spaces s
            WHERE e.embedding_space_id = s.id
              AND s.code = 'bioclip_2_image'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE embedding_spaces
            SET dim = 512,
                description = 'BioCLIP 2 image tower (open_clip) — bird/species similarity'
            WHERE code = 'bioclip_2_image' AND dim = 768
            """
        )
    )
