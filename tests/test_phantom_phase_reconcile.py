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


# ──────────────────────────────────────────────────────────────────────────────
# Issue #340 — culling may never be recorded complete without a work product
# ──────────────────────────────────────────────────────────────────────────────

def test_culling_skips_images_missing_similarity_artefacts(monkeypatch):
    """An image that reached pick/reject but never clustered must not be marked done."""
    _patch(monkeypatch, [{"id": 1}, {"id": 2}, {"id": 3}])
    captured = []
    monkeypatch.setattr(
        db_legacy, "set_image_phase_status",
        lambda iid, code, status, **k: captured.append((iid, code, status)),
    )
    # 1 and 3 never clustered; only 2 carries the visual work product.
    monkeypatch.setattr(
        db_legacy, "is_image_culling_similarity_artefacts_missing",
        lambda iid: iid in (1, 3),
    )
    out = db_legacy.reconcile_phantom_complete_image_phases(("culling",), dry_run=False)
    assert out == {"culling": 1}
    assert captured == [(2, "culling", "done")]


def test_culling_dry_run_count_matches_what_would_be_written(monkeypatch):
    """The guard applies before the dry-run count, so preview and apply agree."""
    _patch(monkeypatch, [{"id": 1}, {"id": 2}])
    monkeypatch.setattr(db_legacy, "set_image_phase_status", lambda *a, **k: None)
    monkeypatch.setattr(
        db_legacy, "is_image_culling_similarity_artefacts_missing", lambda iid: True
    )
    assert db_legacy.reconcile_phantom_complete_image_phases(
        ("culling",), dry_run=True
    ) == {"culling": 0}


def test_guard_does_not_touch_other_phases(monkeypatch):
    """Scoring/keywords keep their existing behaviour — the guard is culling-only."""
    _patch(monkeypatch, [{"id": 7}])
    captured = []
    monkeypatch.setattr(
        db_legacy, "set_image_phase_status",
        lambda iid, code, status, **k: captured.append((iid, code, status)),
    )
    monkeypatch.setattr(
        db_legacy, "is_image_culling_similarity_artefacts_missing",
        lambda iid: (_ for _ in ()).throw(AssertionError("must not be consulted")),
    )
    out = db_legacy.reconcile_phantom_complete_image_phases(("scoring",), dry_run=False)
    assert out == {"scoring": 1}
    assert captured == [(7, "scoring", "done")]


def test_auto_drive_preflight_no_longer_reconciles_culling():
    """The drive preflight must not include culling — that is what caused #340."""
    import inspect

    from modules import runs_autodrive

    src = inspect.getsource(runs_autodrive._reconcile_stale_ips_for_drive)
    assert "reconcile_phantom_complete_image_phases" in src
    tuple_start = src.index("reconcile_phantom_complete_image_phases")
    tuple_src = src[tuple_start:tuple_start + 300]
    assert '"culling"' not in tuple_src
    for code in ("indexing", "metadata", "scoring", "keywords"):
        assert f'"{code}"' in tuple_src
    # The self-healing reset must run instead.
    assert "reset_false_complete_culling_phases" in src


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
