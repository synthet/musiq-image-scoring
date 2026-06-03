"""Smoke tests for migration 0024 (drop images.image_embedding)."""

import pytest

pytestmark = [pytest.mark.postgres]


def test_upgrade_0024_idempotent_when_column_already_dropped(postgres_test_session):
    """Re-running upgrade on a DB without the column must not error."""
    from alembic.config import Config
    from alembic import command

    # Schema comes from init_db(); stamp 0023 then apply/double-apply 0024 only.
    cfg = Config("alembic.ini")
    command.stamp(cfg, "0023")
    command.upgrade(cfg, "0024")
    command.upgrade(cfg, "0024")
