"""Lightweight probe test with no import-time execution side effects."""

from __future__ import annotations

import os

import pytest


@pytest.mark.db
def test_probe_create_culling_session() -> None:
    """Manual DB probe for culling session creation.

    This test is intentionally opt-in because it mutates DB state.
    Run with:
      RUN_MANUAL_DB_PROBE=1 pytest tests/test_probe.py -q
    """
    if os.getenv("RUN_MANUAL_DB_PROBE") != "1":
        pytest.skip("Set RUN_MANUAL_DB_PROBE=1 to run the DB probe test")

    from modules import db

    session_id = db.create_culling_session("probe")
    assert session_id is not None
