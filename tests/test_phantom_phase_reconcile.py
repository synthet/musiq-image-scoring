"""Unit tests for db.reconcile_phantom_complete_image_phases (no DB required).

Patches the connector + ``set_image_phase_status`` + ``get_phase_incomplete_sql`` so the
orchestration logic (which images get marked done, dry-run, unsupported-phase guard,
scope params) is verified without a live database.
"""

from __future__ import annotations

from modules import db_legacy


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append((sql, params))
        return self._rows


def _patch(monkeypatch, rows):
    fake = _FakeConn(rows)
    monkeypatch.setattr(db_legacy, "get_connector", lambda: fake)
    monkeypatch.setattr(db_legacy, "get_phase_incomplete_sql", lambda code, alias="": "1=0")
    return fake


def test_reconcile_marks_phantom_done(monkeypatch):
    _patch(monkeypatch, [{"id": 1}, {"id": 2}, {"id": 3}])
    captured = []
    monkeypatch.setattr(
        db_legacy, "set_image_phase_status",
        lambda iid, code, status, **k: captured.append((iid, code, status)),
    )
    out = db_legacy.reconcile_phantom_complete_image_phases(("scoring",), dry_run=False)
    assert out == {"scoring": 3}
    assert captured == [(1, "scoring", "done"), (2, "scoring", "done"), (3, "scoring", "done")]


def test_reconcile_dry_run_writes_nothing(monkeypatch):
    _patch(monkeypatch, [{"id": 5}])
    calls = []
    monkeypatch.setattr(db_legacy, "set_image_phase_status", lambda *a, **k: calls.append(a))
    out = db_legacy.reconcile_phantom_complete_image_phases(("keywords",), dry_run=True)
    assert out == {"keywords": 1}
    assert calls == []


def test_reconcile_skips_unsupported_phase(monkeypatch):
    fake = _patch(monkeypatch, [{"id": 9}])
    monkeypatch.setattr(db_legacy, "set_image_phase_status", lambda *a, **k: None)
    out = db_legacy.reconcile_phantom_complete_image_phases(("bird_species",), dry_run=False)
    assert out == {"bird_species": 0}
    # Unsupported phase must never be scanned.
    assert fake.queries == []


def test_reconcile_scope_adds_path_clause_and_limit(monkeypatch):
    fake = _patch(monkeypatch, [])
    monkeypatch.setattr(db_legacy, "set_image_phase_status", lambda *a, **k: None)
    db_legacy.reconcile_phantom_complete_image_phases(
        ("scoring",), scope_path="/mnt/d/x", limit=42, dry_run=True
    )
    sql, params = fake.queries[0]
    assert "f.path = ?" in sql
    assert "FETCH FIRST ? ROWS ONLY" in sql
    # params: (code, scope_path, scope_like_unix, scope_like_win, limit)
    assert params[0] == "scoring"
    assert len(params) == 5
    assert params[-1] == 42


def test_reconcile_multiple_phases_independent_counts(monkeypatch):
    _patch(monkeypatch, [{"id": 1}, {"id": 2}])
    monkeypatch.setattr(db_legacy, "set_image_phase_status", lambda *a, **k: None)
    out = db_legacy.reconcile_phantom_complete_image_phases(("scoring", "keywords"), dry_run=True)
    assert out == {"scoring": 2, "keywords": 2}


class _FakeOneConn:
    def __init__(self, row):
        self._row = row
        self.queries = []

    def query_one(self, sql, params=None):
        self.queries.append((sql, params))
        return self._row


def test_scope_has_unattempted_work_true(monkeypatch):
    fake = _FakeOneConn({"1": 1})
    monkeypatch.setattr(db_legacy, "get_connector", lambda: fake)
    monkeypatch.setattr(db_legacy, "get_phase_incomplete_sql", lambda code, alias="": "1=1")
    assert db_legacy.scope_has_unattempted_phase_work("/mnt/d/x", "keywords") is True
    sql, params = fake.queries[0]
    assert "COALESCE(ips.attempt_count, 0) = 0" in sql
    assert "NOT IN ('done', 'skipped', 'running')" in sql
    assert params[0] == "keywords"


def test_scope_has_unattempted_work_false_when_no_row(monkeypatch):
    fake = _FakeOneConn(None)
    monkeypatch.setattr(db_legacy, "get_connector", lambda: fake)
    monkeypatch.setattr(db_legacy, "get_phase_incomplete_sql", lambda code, alias="": "1=1")
    assert db_legacy.scope_has_unattempted_phase_work("/mnt/d/x", "scoring") is False


def test_scope_has_unattempted_work_guards_empty_input(monkeypatch):
    # No connector call should happen for empty scope/phase.
    monkeypatch.setattr(db_legacy, "get_connector", lambda: (_ for _ in ()).throw(AssertionError("called")))
    assert db_legacy.scope_has_unattempted_phase_work("", "keywords") is False
    assert db_legacy.scope_has_unattempted_phase_work("/x", "") is False
