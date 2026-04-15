"""Add job execution trail: report_json, phase counters, job_image_actions table.

Supports per-image before/after score snapshots and structured run reports
for troubleshooting validate_and_repair and other run modes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-14
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- jobs.report_json --
    op.add_column("jobs", sa.Column("report_json", JSONB(), nullable=True))

    # -- job_phases counter columns --
    op.add_column("job_phases", sa.Column("images_in_scope", sa.Integer(), server_default="0"))
    op.add_column("job_phases", sa.Column("images_targeted", sa.Integer(), server_default="0"))
    op.add_column("job_phases", sa.Column("images_processed", sa.Integer(), server_default="0"))
    op.add_column("job_phases", sa.Column("images_skipped", sa.Integer(), server_default="0"))
    op.add_column("job_phases", sa.Column("images_failed", sa.Integer(), server_default="0"))

    # -- job_image_actions table --
    op.create_table(
        "job_image_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_code", sa.String(50), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before_snapshot", JSONB(), nullable=True),
        sa.Column("after_snapshot", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_jia_job_id", "job_image_actions", ["job_id"])
    op.create_index("idx_jia_job_phase", "job_image_actions", ["job_id", "phase_code"])
    op.create_index("idx_jia_image_id", "job_image_actions", ["image_id"])
    op.create_index("idx_jia_created_at", "job_image_actions", ["created_at"])


def downgrade() -> None:
    op.drop_table("job_image_actions")

    op.drop_column("job_phases", "images_failed")
    op.drop_column("job_phases", "images_skipped")
    op.drop_column("job_phases", "images_processed")
    op.drop_column("job_phases", "images_targeted")
    op.drop_column("job_phases", "images_in_scope")

    op.drop_column("jobs", "report_json")
