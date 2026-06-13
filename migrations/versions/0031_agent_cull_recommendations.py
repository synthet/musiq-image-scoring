"""Agent-assisted cull review groups and per-image recommendations.

Metadata-only removal candidates; does not modify images.cull_decision or delete files.

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_cull_review_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("stack_id", sa.Integer(), sa.ForeignKey("stacks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sub_stack_id", sa.Integer(), sa.ForeignKey("sub_stacks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_unit_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("agent_name", sa.String(64), nullable=True),
        sa.Column("agent_model", sa.String(128), nullable=True),
        sa.Column("agent_version", sa.String(64), nullable=True),
        sa.Column("agent_supports_vision", sa.Boolean(), nullable=True),
        sa.Column("prompt_template_version", sa.String(32), nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("request_json", JSONB(), nullable=True),
        sa.Column("response_raw", sa.Text(), nullable=True),
        sa.Column("response_validated", JSONB(), nullable=True),
        sa.Column("group_decision", sa.String(32), nullable=True),
        sa.Column("group_confidence", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("safety_overrides", JSONB(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("applied_by", sa.String(128), nullable=True),
    )
    op.create_index(
        "idx_agent_cull_groups_unit_created",
        "agent_cull_review_groups",
        ["review_unit_key", "created_at"],
    )
    op.create_index(
        "idx_agent_cull_groups_stack_status",
        "agent_cull_review_groups",
        ["stack_id", "sub_stack_id", "status"],
    )
    op.create_index(
        "idx_agent_cull_groups_status_created",
        "agent_cull_review_groups",
        ["status", "created_at"],
    )

    op.create_table(
        "agent_cull_recommendations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "review_group_id",
            sa.BigInteger(),
            sa.ForeignKey("agent_cull_review_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_decision", sa.String(16), nullable=False),
        sa.Column("final_decision", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("better_alternatives", JSONB(), nullable=True),
        sa.Column("risk_flags", JSONB(), nullable=True),
        sa.Column("safety_overrides", JSONB(), nullable=True),
        sa.Column("candidate_status", sa.String(32), nullable=False, server_default="none"),
        sa.Column("prior_pick_status", sa.SmallInteger(), nullable=True),
        sa.Column("prior_cull_decision", sa.String(20), nullable=True),
        sa.Column("prior_candidate_status", sa.String(32), nullable=True),
        sa.Column("operator_actor", sa.String(128), nullable=True),
        sa.Column("operator_note", sa.Text(), nullable=True),
        sa.Column("operator_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_agent_cull_recs_group",
        "agent_cull_recommendations",
        ["review_group_id"],
    )
    op.create_index(
        "idx_agent_cull_recs_image_status",
        "agent_cull_recommendations",
        ["image_id", "candidate_status"],
    )
    op.create_index(
        "idx_agent_cull_recs_status_image",
        "agent_cull_recommendations",
        ["candidate_status", "image_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_cull_recs_status_image", table_name="agent_cull_recommendations")
    op.drop_index("idx_agent_cull_recs_image_status", table_name="agent_cull_recommendations")
    op.drop_index("idx_agent_cull_recs_group", table_name="agent_cull_recommendations")
    op.drop_table("agent_cull_recommendations")
    op.drop_index("idx_agent_cull_groups_status_created", table_name="agent_cull_review_groups")
    op.drop_index("idx_agent_cull_groups_stack_status", table_name="agent_cull_review_groups")
    op.drop_index("idx_agent_cull_groups_unit_created", table_name="agent_cull_review_groups")
    op.drop_table("agent_cull_review_groups")
