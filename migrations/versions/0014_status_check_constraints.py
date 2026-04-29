"""Add CHECK constraint on image_phase_status.status (Phase 5 D2, partial).

Adds a domain CHECK matching ``modules.phases.PhaseStatus`` (9 values) to
``image_phase_status.status``. The constraint is verified non-violating against
all rows in production prior to adding (only ``done``, ``skipped``,
``not_started``, ``running`` observed — all members of PhaseStatus).

``jobs.status`` and ``job_phases.state`` are intentionally excluded from this
revision: empirical inventory showed values not yet documented in
docs/planning/database/STATUS_VOCABULARY.md (e.g. ``canceled`` vs
``cancelled`` co-existing in jobs.status; ``pending``/``interrupted``/
``paused``/``skipped`` in job_phases.state). Those need a data-normalization
pass before a CHECK can be added.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-25
"""

from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


_IPS_CHECK_NAME = "ck_image_phase_status_status"
_IPS_ALLOWED = (
    "not_started",
    "queued",
    "running",
    "paused",
    "cancel_requested",
    "restarting",
    "done",
    "skipped",
    "failed",
)


def _allowed_in_clause(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE image_phase_status "
        f"ADD CONSTRAINT {_IPS_CHECK_NAME} "
        f"CHECK (status IN ({_allowed_in_clause(_IPS_ALLOWED)}))"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE image_phase_status DROP CONSTRAINT IF EXISTS {_IPS_CHECK_NAME}"
    )
