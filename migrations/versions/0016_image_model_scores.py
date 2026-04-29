"""image_model_scores table — generic per-model score storage.

Replaces the per-model column pattern (``score_spaq``, ``score_ava``, etc.)
for *new* models added via the pluggable scoring framework. Existing typed
columns on ``images`` are kept for Electron / legacy reads (see
``modules/db_legacy.py:upsert_image`` for the dual-write path).

Each row is one (image, model) pair with its raw + normalized score, status,
shadow flag, model version, and timestamp. ``is_shadow=true`` rows are
written by models that run alongside production but are excluded from
fusion (Phase 1 shadow-mode rollout per
``docs/planning/models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md``).

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-27
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_model_scores (
            image_id        INTEGER     NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            model_name      VARCHAR(64) NOT NULL,
            raw_score       DOUBLE PRECISION,
            normalized      DOUBLE PRECISION,
            status          VARCHAR(16) NOT NULL,
            is_shadow       BOOLEAN     NOT NULL DEFAULT FALSE,
            model_version   VARCHAR(64),
            scored_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (image_id, model_name)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ims_model_name ON image_model_scores(model_name);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ims_shadow ON image_model_scores(is_shadow) "
        "WHERE is_shadow;"
    )
    op.execute(
        "ALTER TABLE image_model_scores DROP CONSTRAINT IF EXISTS image_model_scores_status_check;"
    )
    op.execute(
        "ALTER TABLE image_model_scores ADD CONSTRAINT image_model_scores_status_check "
        "CHECK (status IN ('success', 'failed', 'not_loaded'));"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS image_model_scores;")
