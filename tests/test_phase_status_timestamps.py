"""Issue #341 — ``finished_at`` must be cleared when a phase row re-enters ``running``.

Leaving the previous run's stamp makes ``finished_at < started_at`` for the whole
re-run, so every consumer that subtracts the two reports a negative duration — most
visibly the run-detail work-item list. Fast unit tests: no DB, no ML.
"""

from __future__ import annotations

import modules.db_legacy as dbl
from modules.phases import PhaseStatus


class _FakeTx:
    def __init__(self, existing):
        self._existing = existing
        self.executed = []

    def query_one(self, sql, params=None):
        if "FROM image_phase_status" in sql:
            return self._existing
        if "folder_id FROM images" in sql:
            return {"folder_id": None}
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


class _TxConn:
    def __init__(self, tx):
        self.tx = tx

    def run_transaction(self, fn):
        return fn(self.tx)


def _run_status_write(monkeypatch, existing, status):
    tx = _FakeTx(existing)
    monkeypatch.setattr(dbl, "get_phase_id", lambda code: 4)
    monkeypatch.setattr(dbl, "get_connector", lambda: _TxConn(tx))
    monkeypatch.setattr(dbl, "_apply_done_postcondition_gate", lambda i, p, s, e: (s, e))
    monkeypatch.setattr(dbl, "record_phase_status_audit", lambda *a, **k: None, raising=False)
    dbl.set_image_phase_status(1, "culling", status)
    return tx


def _update_sql(tx):
    return next(
        sql for sql, _ in tx.executed if sql.startswith("UPDATE image_phase_status")
    )


def test_running_clears_stale_finished_at(monkeypatch):
    """Re-running a done row must not leave finished_at < started_at (negative durations)."""
    tx = _run_status_write(
        monkeypatch,
        {"id": 9, "status": PhaseStatus.DONE, "attempt_count": 1},
        PhaseStatus.RUNNING,
    )
    sql = _update_sql(tx)
    assert "finished_at = NULL" in sql
    assert "started_at = ?" in sql


def test_terminal_write_still_stamps_finished_at(monkeypatch):
    tx = _run_status_write(
        monkeypatch,
        {"id": 9, "status": PhaseStatus.RUNNING, "attempt_count": 1},
        PhaseStatus.DONE,
    )
    sql = _update_sql(tx)
    assert "finished_at = ?" in sql
    assert "finished_at = NULL" not in sql
