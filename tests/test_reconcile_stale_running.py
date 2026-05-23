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
    seed the candidate-id list returned by the SELECT.

    By default salvage UPDATEs (SET status='done') return 0 rows and fail
    UPDATEs return the chunk size, matching the common case where no rows
    qualify for salvage.  Pass ``salvage_scoring`` and/or ``salvage_culling``
    to override the per-chunk count returned for each salvage pass.
    """

    def __init__(self, candidate_ids, *, salvage_scoring: int = 0, salvage_culling: int = 0):
        self.candidate_ids = list(candidate_ids)
        self.salvage_scoring = salvage_scoring
        self.salvage_culling = salvage_culling
        self.queries: list[tuple[str, tuple]] = []
        self.executes: list[tuple[str, tuple]] = []

    def query(self, sql, params=None):
        self.queries.append((sql, tuple(params) if params else ()))
        return [{"id": i} for i in self.candidate_ids]

    def execute(self, sql, params=None):
        self.executes.append((sql, tuple(params) if params else ()))
        if "UPDATE" not in sql.upper():
            return 0
        if "SET status = 'done'" in sql or "SET STATUS = 'DONE'" in sql.upper():
            if "code = 'culling'" in sql or "CODE = 'CULLING'" in sql.upper():
                return self.salvage_culling
            return self.salvage_scoring
        # Fail UPDATE: chunk size = params minus the two leading (now, now).
        return max(0, len(params) - 2) if params else 0

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
    fake = _FakeConnector(ids)  # salvage counts default to 0
    monkeypatch.setattr(db, "get_connector", lambda: fake)
    n = db.reconcile_stale_running_image_phases(threshold_seconds=60, limit=5000)
    assert n == len(ids), n  # 900 + 900 = 1800 rows updated (all via fail path)
    # Expect 3 UPDATEs per chunk × 2 chunks = 6 total (2 salvage + 1 fail each).
    update_calls = [
        (sql, params) for sql, params in fake.executes
        if "UPDATE IMAGE_PHASE_STATUS" in sql.upper()
    ]
    assert len(update_calls) == 6, update_calls
    fail_calls = [(s, p) for s, p in update_calls if "'failed'" in s]
    assert len(fail_calls) == 2
    for sql, _ in fail_calls:
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


# --- Issue #161: no-heartbeat salvage -------------------------------------------


def test_no_heartbeat_salvages_scoring_rows_with_outputs(monkeypatch):
    """Stale scoring rows whose outputs are persisted must be flipped to 'done',
    not 'failed', even via the wall-clock (no-heartbeat) reconciler path.
    """
    fake = _FakeConnector([1, 2, 3, 4, 5], salvage_scoring=3, salvage_culling=0)
    monkeypatch.setattr(db, "get_connector", lambda: fake)

    n = db.reconcile_stale_running_image_phases(threshold_seconds=60, limit=100)

    update_calls = [(s, p) for s, p in fake.executes if "UPDATE IMAGE_PHASE_STATUS" in s.upper()]
    # Expect: salvage-scoring, salvage-culling, fail (one chunk).
    assert len(update_calls) == 3, update_calls

    salvage_sql, _ = update_calls[0]
    assert "SET status = 'done'" in salvage_sql
    assert "code = 'scoring'" in salvage_sql
    assert "no_heartbeat:outputs_present" in salvage_sql
    assert "score IS NOT NULL" in salvage_sql
    assert "scores_json IS NOT NULL" in salvage_sql

    fail_sql, _ = update_calls[2]
    assert "SET status = 'failed'" in fail_sql
    assert "reconcile_stale:no_heartbeat'" in fail_sql

    # Total = salvaged scoring (3) + fail (5, fake returns chunk size).
    assert n == 3 + 5


def test_no_heartbeat_salvages_culling_rows_with_stack(monkeypatch):
    """Stale culling rows for images that already have a stack_id must be
    salvaged to 'done' rather than failed by the no-heartbeat reconciler.
    """
    fake = _FakeConnector([10, 11, 12], salvage_scoring=0, salvage_culling=2)
    monkeypatch.setattr(db, "get_connector", lambda: fake)

    n = db.reconcile_stale_running_image_phases(threshold_seconds=60, limit=100)

    update_calls = [(s, p) for s, p in fake.executes if "UPDATE IMAGE_PHASE_STATUS" in s.upper()]
    assert len(update_calls) == 3, update_calls

    cull_salvage_sql, _ = update_calls[1]
    assert "SET status = 'done'" in cull_salvage_sql
    assert "code = 'culling'" in cull_salvage_sql
    assert "no_heartbeat:outputs_present" in cull_salvage_sql
    assert "stack_id IS NOT NULL" in cull_salvage_sql

    # Total = salvaged culling (2) + fail (3, fake returns chunk size).
    assert n == 2 + 3
