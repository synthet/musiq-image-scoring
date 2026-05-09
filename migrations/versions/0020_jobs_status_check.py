"""Add CHECK constraint on jobs.status (Phase 5 D2 — completes 0015 normalization).

Revision 0015 rewrote the legacy ``canceled`` (US) rows to ``cancelled`` (UK).
This revision locks in the surviving vocabulary so a future writer cannot
re-introduce the spelling drift that produced the audit gap of 2026-05-09.

Allowed values come from ``docs/planning/database/STATUS_VOCABULARY.md`` §2,
matching every literal that current application code paths write to
``jobs.status``:

    pending | queued | running | paused | user_pause |
    completed | failed | cancelled | interrupted

``error`` is **excluded** intentionally — the vocab doc treats it as resolved
(`failed` is the canonical terminal-error value; ``error`` only appears in
``runner_state`` / dataclass return values, never in ``jobs.status``).

Idempotent: re-running the upgrade after the constraint exists is a no-op
(``ADD CONSTRAINT IF NOT EXISTS`` semantics emulated via duplicate-name guard).

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-09
"""

from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


_JOBS_CHECK_NAME = "ck_jobs_status"
_JOBS_ALLOWED = (
    "pending",
    "queued",
    "running",
    "paused",
    "user_pause",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
)


def _allowed_in_clause(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{_JOBS_CHECK_NAME}'
                  AND conrelid = 'jobs'::regclass
            ) THEN
                ALTER TABLE jobs
                ADD CONSTRAINT {_JOBS_CHECK_NAME}
                CHECK (status IS NULL OR status IN ({_allowed_in_clause(_JOBS_ALLOWED)}));
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE jobs DROP CONSTRAINT IF EXISTS {_JOBS_CHECK_NAME}"
    )
