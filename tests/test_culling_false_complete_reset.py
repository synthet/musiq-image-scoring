"""Issue #340 — culling may not be recorded complete without a clustering work product.

Fast unit tests: no DB, no ML. The connector and ``set_image_phase_status`` are
stubbed so the SQL shape and the sweep orchestration are verified in isolation.
"""

from __future__ import annotations

import modules.db_legacy as dbl


# ──────────────────────────────────────────────────────────────────────────────
# _sql_culling_similarity_artefacts_missing
# ──────────────────────────────────────────────────────────────────────────────

def test_artefacts_missing_sql_shape_on_postgres(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(
        dbl, "_postgres_has_default_embedding_sql", lambda alias="i": f"(EMB {alias})"
    )
    sql = dbl._sql_culling_similarity_artefacts_missing("i")
    # A cull decision was recorded ...
    assert "i.cull_decision IS NOT NULL" in sql
    # ... on a clustering-eligible row that never got a stack ...
    assert "i.stack_id IS NULL" in sql
    assert "i.image_hash IS NOT NULL" in sql
    # ... and never got the default-space embedding clustering itself persists.
    assert "NOT ((EMB i))" in sql


def test_artefacts_missing_sql_honours_table_alias(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(
        dbl, "_postgres_has_default_embedding_sql", lambda alias="i": f"(EMB {alias})"
    )
    sql = dbl._sql_culling_similarity_artefacts_missing("img")
    assert "img.stack_id IS NULL" in sql
    assert "i.stack_id" not in sql
    assert "(EMB img)" in sql


def test_artefacts_missing_sql_is_inert_off_postgres(monkeypatch):
    """``bird_bbox``-style engine guard: the default-space lookup has no Firebird form."""
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "firebird")
    assert dbl._sql_culling_similarity_artefacts_missing("i") == "1=0"


# ──────────────────────────────────────────────────────────────────────────────
# reset_false_complete_culling_phases
# ──────────────────────────────────────────────────────────────────────────────

class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append((sql, params))
        return self._rows


def _patch_reset(monkeypatch, rows):
    fake = _FakeConn(rows)
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "get_connector", lambda: fake)
    monkeypatch.setattr(
        dbl, "_sql_culling_similarity_artefacts_missing", lambda alias="i": "ARTEFACTS_MISSING"
    )
    return fake


def test_reset_returns_rows_to_not_started(monkeypatch):
    _patch_reset(monkeypatch, [{"image_id": 11}, {"image_id": 12}])
    captured = []
    monkeypatch.setattr(
        dbl, "set_image_phase_status",
        lambda iid, code, status, **k: captured.append((iid, code, status)),
    )
    assert dbl.reset_false_complete_culling_phases(limit=50) == 2
    assert captured == [
        (11, "culling", "not_started"),
        (12, "culling", "not_started"),
    ]


def test_reset_scans_terminal_rows_only(monkeypatch):
    """``running`` rows belong to the stale-running reaper, not to this sweep."""
    fake = _patch_reset(monkeypatch, [])
    monkeypatch.setattr(dbl, "set_image_phase_status", lambda *a, **k: None)
    dbl.reset_false_complete_culling_phases(limit=7)
    sql, params = fake.queries[0]
    assert "LOWER(TRIM(ips.status)) IN ('done', 'skipped')" in sql
    assert "ARTEFACTS_MISSING" in sql
    assert "'culling'" in sql
    assert "FETCH FIRST ? ROWS ONLY" in sql
    assert params == (7,)


def test_reset_is_inert_off_postgres(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "firebird")
    monkeypatch.setattr(
        dbl, "get_connector",
        lambda: (_ for _ in ()).throw(AssertionError("must not query off postgres")),
    )
    assert dbl.reset_false_complete_culling_phases() == 0


def test_reset_survives_a_failing_row(monkeypatch):
    """One bad row must not abort the sweep — matches the metadata reset's behaviour."""
    _patch_reset(monkeypatch, [{"image_id": 1}, {"image_id": 2}, {"image_id": 3}])

    def _flaky(iid, code, status, **k):
        if iid == 2:
            raise RuntimeError("row locked")

    monkeypatch.setattr(dbl, "set_image_phase_status", _flaky)
    assert dbl.reset_false_complete_culling_phases() == 2


def test_reset_clamps_bad_limit(monkeypatch):
    fake = _patch_reset(monkeypatch, [])
    monkeypatch.setattr(dbl, "set_image_phase_status", lambda *a, **k: None)
    dbl.reset_false_complete_culling_phases(limit="nonsense")  # type: ignore[arg-type]
    assert fake.queries[0][1] == (500,)
