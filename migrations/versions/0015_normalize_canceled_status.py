"""Normalize US-spelling ``canceled`` to UK ``cancelled`` (Phase 5 D2 prep).

Production inventory at 2026-04-25 found the US spelling co-existing with the
canonical UK spelling on two columns, all from removed code paths:

- ``jobs.status``           — 21 rows ``canceled`` vs 48 ``cancelled``
- ``job_phases.state``      — 17 rows ``canceled`` vs (no current writer)

Application code only ever writes ``cancelled``. This revision rewrites the
stale rows so a follow-up migration can add a ``CHECK`` constraint matching the
canonical vocabulary documented in
``docs/planning/database/STATUS_VOCABULARY.md`` (Phase 5 D2).

Idempotent: re-running the UPDATEs after the first pass touches 0 rows.

Downgrade is intentionally a no-op. The pre-normalization split mixed legacy
writes from removed code paths with no surviving discriminator, so we cannot
recover the original ``canceled`` / ``cancelled`` partition.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-25
"""

from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE jobs SET status = 'cancelled' WHERE status = 'canceled'")
    op.execute("UPDATE job_phases SET state = 'cancelled' WHERE state = 'canceled'")


def downgrade() -> None:
    # Intentionally a no-op — see module docstring.
    pass
