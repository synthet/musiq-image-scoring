"""Workflow heal folder discovery uses touch metadata when engine is Postgres."""

from __future__ import annotations

from contextlib import contextmanager

from modules import workflow_healing


class _FakeCursor:
    def __init__(self):
        self._last_query = ""
        self._last_params: tuple = ()

    def execute(self, query, params):
        self._last_query = query
        self._last_params = tuple(params) if params is not None else ()

    def fetchall(self):
        if "GROUP BY f.id, f.path" in self._last_query:
            return []
        return []


class _FakeConn:
    def __init__(self):
        self._cursor = _FakeCursor()

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_heal_postgres_folder_sql_joins_touch_table(monkeypatch):
    outer_conn = _FakeConn()

    @contextmanager
    def _connection():
        yield outer_conn

    monkeypatch.setattr(workflow_healing.db, "connection", _connection)
    monkeypatch.setattr(workflow_healing.db, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(workflow_healing.db, "get_phase_incomplete_sql", lambda *a, **k: "1=0")
    monkeypatch.setattr(workflow_healing, "_get_active_jobs_snapshot", lambda: [])

    workflow_healing.heal_phase_data("scoring", dry_run=True, budget=3)

    q = outer_conn._cursor._last_query
    assert "pipeline_tool_folder_last_touch" in q
    assert "NULLS FIRST" in q
    assert "heal_workflow_scoring" in outer_conn._cursor._last_params


def test_heal_firebird_skips_touch_join(monkeypatch):
    outer_conn = _FakeConn()

    @contextmanager
    def _connection():
        yield outer_conn

    monkeypatch.setattr(workflow_healing.db, "connection", _connection)
    monkeypatch.setattr(workflow_healing.db, "_get_db_engine", lambda: "firebird")
    monkeypatch.setattr(workflow_healing.db, "get_phase_incomplete_sql", lambda *a, **k: "1=0")
    monkeypatch.setattr(workflow_healing, "_get_active_jobs_snapshot", lambda: [])

    workflow_healing.heal_phase_data("scoring", dry_run=True, budget=3)

    q = outer_conn._cursor._last_query
    assert "pipeline_tool_folder_last_touch" not in q
    assert "GROUP BY f.path ORDER BY image_count DESC" in q.replace("\n", " ")
