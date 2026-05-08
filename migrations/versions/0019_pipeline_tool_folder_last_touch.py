"""pipeline_tool_folder_last_touch — round-robin scheduling for Pipeline Tools.

Tracks last time each folder was successfully touched by a given tool (heal phase
or backfill action) so selectors can deprioritize recently processed folders.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-07
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_tool_folder_last_touch (
            tool_key TEXT NOT NULL,
            folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
            last_touched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tool_key, folder_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pipeline_tool_folder_touch_tool_time
        ON pipeline_tool_folder_last_touch (tool_key, last_touched_at)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pipeline_tool_folder_touch_tool_time")
    op.execute("DROP TABLE IF EXISTS pipeline_tool_folder_last_touch")
