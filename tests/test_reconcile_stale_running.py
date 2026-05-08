"""Unit tests for the wall-clock stale-running reconcile.

Covers ``db.reconcile_stale_running_image_phases`` semantics without a real
database — patches the connector so we can verify the SQL shape, the
threshold-based selection, and the chunking behaviour.
"""

from __future__ import annotations

import datetime

from modules import db


class _FakeConnector:
    """Connector double that records query()/execute() calls and lets tests
    seed the candidate-id list returned by the SELECT."""

    def __init__(self, candidate_ids):
        self.candidate_ids = list(candidate_ids)
        self.queries: list[tuple[str, tuple]] = []
        self.executes: list[tuple[str, tuple]] = []

    def query(self, sql, params=None):
        self.queries.append((sql, tuple(params) if params else ()))
        return [{"id": i} for i in self.candidate_ids]

    def execute(self, sql, params=None):
        self.executes.append((sql, tuple(params) if params else ()))
        # Mimic real driver: rowcount = the number of ids touched in this
        # batch. Two leading params (now, now) plus the chunk of ids.
        if params and "UPDATE" in sql.upper():
            return max(0, len(params) - 2)
        return 0

    def query_one(self, *a, **kw):
        return None


def test_returns_zero_when_no_candidates(monkeypatch):
    fake = _FakeConnector([])
    monkeypatch.setattr(db, "get_connector", lambda: fake)
    n = db.reconcile_stale_running_image_phases(threshold_seconds=60, limit=100)
    assert n == 0
    assert fake.queries, "should have queried for candidates"
    assert not fake.executes, "should not run UPDATE when nothing matches"


def test_updates_in_chunks_and_returns_count(monkeypatch):
    ids = list(range(1, 1801))  # 1800 -> two chunks of 900
    fake = _FakeConnector(ids)
    monkeypatch.setattr(db, "get_connector", lambda: fake)
    n = db.reconcile_stale_running_image_phases(threshold_seconds=60, limit=5000)
    assert n == len(ids), n  # 900 + 900 = 1800 rows updated
    # We expect at least 2 UPDATE batches (chunk_size=900):
    update_calls = [
        (sql, params) for sql, params in fake.executes
        if "UPDATE IMAGE_PHASE_STATUS" in sql.upper()
    ]
    assert len(update_calls) == 2
    # Each batch should set status='failed' and the no_heartbeat error.
    for sql, params in update_calls:
        assert "'failed'" in sql or "failed" in sql.lower()
        assert "reconcile_stale:no_heartbeat" in sql


def test_threshold_floor_protects_against_runaway(monkeypatch):
    """Threshold below 60s should be clamped to 60s before SELECT."""
    fake = _FakeConnector([])
    captured = {}

    def _query(sql, params=None):
        captured["params"] = params
        return []
    fake.query = _query  # type: ignore[assignment]
    monkeypatch.setattr(db, "get_connector", lambda: fake)
    before = datetime.datetime.now()
    db.reconcile_stale_running_image_phases(threshold_seconds=5, limit=100)
    after = datetime.datetime.now()
    cutoff = captured["params"][0]
    # cutoff must be at least 60s before the call (clamped); not the requested 5s.
    assert (before - cutoff).total_seconds() >= 59, cutoff
    # And not absurdly far in the past.
    assert (after - cutoff).total_seconds() < 120, cutoff


def test_default_threshold_reads_config(monkeypatch):
    fake = _FakeConnector([])
    monkeypatch.setattr(db, "get_connector", lambda: fake)
    captured = {}

    def _gcv(key, default=None):
        captured.setdefault("keys", []).append(key)
        if key == "database.stale_running_threshold_seconds":
            return 7200
        return default
    monkeypatch.setattr("modules.config.get_config_value", _gcv)
    db.reconcile_stale_running_image_phases(limit=100)
    assert "database.stale_running_threshold_seconds" in captured["keys"]
