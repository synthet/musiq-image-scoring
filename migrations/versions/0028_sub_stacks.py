"""Add sub_stacks table and images.sub_stack_id for two-level culling.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sub_stacks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stack_id", sa.Integer(), sa.ForeignKey("stacks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("best_image_id", sa.Integer(), nullable=True),
        sa.Column("level1_space", sa.String(64), nullable=True),
        sa.Column("level2_visual_space", sa.String(64), nullable=True),
        sa.Column("level2_semantic_space", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_sub_stacks_stack_id", "sub_stacks", ["stack_id"])
    op.add_column(
        "images",
        sa.Column(
            "sub_stack_id",
            sa.Integer(),
            sa.ForeignKey("sub_stacks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_images_sub_stack_id", "images", ["sub_stack_id"])


def downgrade() -> None:
    op.drop_index("idx_images_sub_stack_id", table_name="images")
    op.drop_column("images", "sub_stack_id")
    op.drop_index("idx_sub_stacks_stack_id", table_name="sub_stacks")
    op.drop_table("sub_stacks")
