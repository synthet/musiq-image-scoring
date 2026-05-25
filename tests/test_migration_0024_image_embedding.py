"""Smoke tests for migration 0024 (drop images.image_embedding)."""

import pytest

pytestmark = [pytest.mark.postgres]


def test_upgrade_0024_idempotent_when_column_already_dropped(postgres_test_session):
    """Re-running upgrade on a DB without the column must not error."""
    from alembic.config import Config
    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "0024")
