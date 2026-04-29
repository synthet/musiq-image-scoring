from __future__ import annotations

from contextlib import contextmanager

from modules import workflow_healing


class _FakeCursor:
    def __init__(self, folder_rows):
        self._folder_rows = folder_rows
        self._last_query = ""

    def execute(self, query, params):
        self._last_query = query

    def fetchall(self):
        if "GROUP BY f.path" in self._last_query:
            return self._folder_rows
        return []


class _FakeConn:
    def __init__(self, folder_rows):
        self._cursor = _FakeCursor(folder_rows)

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_heal_bird_species_excludes_done_current_version(monkeypatch):
    @contextmanager
    def _connection():
        # Same-version terminal rows should be excluded by SQL predicate.
        yield _FakeConn(folder_rows=[])

    monkeypatch.setattr(workflow_healing.db, "connection", _connection)
    monkeypatch.setattr(workflow_healing.db, "get_phase_incomplete_sql", lambda *a, **k: "1=1")
    monkeypatch.setattr(workflow_healing, "get_phase_executor_version", lambda *a, **k: "1.0.0")
    monkeypatch.setattr(workflow_healing, "_get_active_jobs_snapshot", lambda: [])

    result = workflow_healing.heal_phase_data(
        "bird_species",
        dry_run=True,
        budget=5,
    )

    assert result["false_positives_found"] == 0
    assert result["folders_needing_work"] == 0
    assert result["eligible_folders"] == 0
    assert result["scheduled"] == []


def test_heal_bird_species_includes_when_executor_version_changes(monkeypatch):
    @contextmanager
    def _connection():
        # Simulate one folder becoming eligible (e.g. old executor_version rows).
        yield _FakeConn(folder_rows=[("/mnt/d/Photos/Z8/2026/2026-04-09", 12)])

    monkeypatch.setattr(workflow_healing.db, "connection", _connection)
    monkeypatch.setattr(workflow_healing.db, "get_phase_incomplete_sql", lambda *a, **k: "1=1")
    monkeypatch.setattr(workflow_healing, "get_phase_executor_version", lambda *a, **k: "2.0.0")
    monkeypatch.setattr(workflow_healing, "_get_active_jobs_snapshot", lambda: [])

    result = workflow_healing.heal_phase_data(
        "bird_species",
        dry_run=True,
        budget=5,
    )

    assert result["false_positives_found"] == 0
    assert result["folders_needing_work"] == 1
    assert result["eligible_folders"] == 1
    assert len(result["scheduled"]) == 1
