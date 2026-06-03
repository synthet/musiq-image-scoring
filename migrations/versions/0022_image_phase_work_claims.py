"""image phase work claims

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_phase_work_claims",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", sa.Integer(), sa.ForeignKey("images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase_code", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("claimed_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_ipwc_job_phase",
        "image_phase_work_claims",
        ["job_id", "phase_code"],
    )
    op.create_index(
        "idx_ipwc_image_phase",
        "image_phase_work_claims",
        ["image_id", "phase_code"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_ipwc_open_image_phase
        ON image_phase_work_claims (image_id, phase_code)
        WHERE status IN ('queued', 'running')
        """
    )


def downgrade() -> None:
    op.drop_index("uq_ipwc_open_image_phase", table_name="image_phase_work_claims")
    op.drop_index("idx_ipwc_image_phase", table_name="image_phase_work_claims")
    op.drop_index("idx_ipwc_job_phase", table_name="image_phase_work_claims")
    op.drop_table("image_phase_work_claims")
