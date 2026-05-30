"""Add auditlog table: RFC 6902 (JSON Patch) change records for critical writes.

Captures insert/update mutations on critical entities (images, jobs,
image_phase_status, cull decisions) for debugging. ``patch`` is an RFC 6902 op
array (``add`` on insert, ``replace`` on update, with a non-standard
``oldValue`` retaining prior state). Correlation columns: ``thread_name`` (which
handler/runner thread), ``run_id`` (the job/run), ``phase_code`` and ``source``.

Written by ``modules/audit.py``; gated by config ``database.audit_log_enabled``.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auditlog",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("record_id", sa.BigInteger(), nullable=True),
        sa.Column("operation", sa.String(16), nullable=False),
        sa.Column("patch", JSONB(), nullable=False),
        sa.Column("thread_name", sa.String(128), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("phase_code", sa.String(50), nullable=True),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_auditlog_table_record", "auditlog", ["table_name", "record_id"])
    op.create_index(
        "idx_auditlog_run_id",
        "auditlog",
        ["run_id"],
        postgresql_where=sa.text("run_id IS NOT NULL"),
    )
    op.create_index("idx_auditlog_created_at", "auditlog", ["created_at"])
    op.create_index("idx_auditlog_thread_name", "auditlog", ["thread_name"])


def downgrade() -> None:
    op.drop_index("idx_auditlog_thread_name", table_name="auditlog")
    op.drop_index("idx_auditlog_created_at", table_name="auditlog")
    op.drop_index("idx_auditlog_run_id", table_name="auditlog")
    op.drop_index("idx_auditlog_table_record", table_name="auditlog")
    op.drop_table("auditlog")
