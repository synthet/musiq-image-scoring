"""Add image_incidents table for durable image-scoped failure/validation history.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_incidents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("folder_id", sa.Integer(), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phase_id", sa.Integer(), sa.ForeignKey("pipeline_phases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "idx_image_incidents_created_at",
        "image_incidents",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index("idx_image_incidents_image_id", "image_incidents", ["image_id"])
    op.create_index("idx_image_incidents_folder_id", "image_incidents", ["folder_id"])
    op.create_index("idx_image_incidents_job_id", "image_incidents", ["job_id"])
    op.create_index("idx_image_incidents_kind", "image_incidents", ["kind"])


def downgrade() -> None:
    op.drop_table("image_incidents")
