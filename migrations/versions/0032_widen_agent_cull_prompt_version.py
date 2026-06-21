"""Widen agent_cull_review_groups.prompt_template_version for v3 study prompts.

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agent_cull_review_groups",
        "prompt_template_version",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "agent_cull_review_groups",
        "prompt_template_version",
        existing_type=sa.String(64),
        type_=sa.String(32),
        existing_nullable=True,
    )
