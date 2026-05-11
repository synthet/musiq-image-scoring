"""Unit tests for the consistency-repair helpers added in v7.14 / 2026-05-09 audit.

Covers (no real DB needed — connector is monkeypatched):
  - ``db.refresh_folder_phase_aggregates_with_ancestors`` — ensures every
    ancestor's path gets force-refreshed at a phase boundary.
  - ``db.backfill_missing_phase_rows`` — finds (image_id, phase) pairs missing
    an IPS row and (in non-dry-run) calls ``set_image_phase_status`` per pair.
  - ``db.repair_zombie_score_rows`` — clears ``images.score=0/label`` for the
    cohort with ``score_general IS NULL`` (Issue A3).
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Defensive module restoration
# ---------------------------------------------------------------------------
# ``test_clustering_representative.py`` stubs ``modules.config`` at import
# time with a partial replacement that only carries ``get_config_section``.
# When pytest loads tests alphabetically that stub lands first and strips
# ``get_database_engine`` — which ``modules.db_legacy.py`` calls at *module
# import time* (line ~807). Importing ``db_legacy`` after that point crashes
# with ``AttributeError: 'get_database_engine'``.
#
# Restore the real ``modules.config`` here, then load ``db_legacy`` eagerly so
# both are in ``sys.modules`` before any test runs. ``_stub()`` in clustering
# is a no-op when its target is already present, so this is safe.
_existing_config = sys.modules.get("modules.config")
if _existing_config is not None and not hasattr(_existing_config, "get_database_engine"):
    # Stubbed by an earlier test — drop it so the next import gets the real module.
    del sys.modules["modules.config"]
import modules.config  # noqa: E402,F401  -- repopulate sys.modules with real impl
import modules.db_legacy as _db_module  # noqa: E402,F401


class _FakeConnector:
    """Minimal connector that replays scripted query/execute results.

    ``query`` and ``query_one`` take any SQL; the test sets ``responses`` keyed
    by a substring match (uppercased SQL → result). ``execute`` records every
    call so the test can assert against it. Order of registration matters when
    the same substring is matched more than once — we pop FIFO from a list.
    """

    def __init__(self, *, query_responses: Dict[str, List[Any]] | None = None,
                 query_one_responses: Dict[str, List[Any]] | None = None):
        self._query_q = {k: list(v) for k, v in (query_responses or {}).items()}
        self._query_one_q = {k: list(v) for k, v in (query_one_responses or {}).items()}
        self.executed: List[tuple[str, tuple]] = []

    def _take(self, queue: Dict[str, List[Any]], sql: str, default: Any) -> Any:
        upper = sql.upper()
        for needle, results in queue.items():
            if needle.upper() in upper and results:
                return results.pop(0)
        return default

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        return self._take(self._query_q, sql, [])

    def query_one(self, sql: str, params: Optional[tuple] = None) -> Optional[Dict]:
        return self._take(self._query_one_q, sql, None)

    def execute(self, sql: str, params: Optional[tuple] = None) -> int:
        self.executed.append((sql, tuple(params) if params else ()))
        return 1


# --------------------------------------------------------------------------- #
# refresh_folder_phase_aggregates_with_ancestors
# --------------------------------------------------------------------------- #

def test_refresh_folder_phase_aggregates_with_ancestors_walks_chain(monkeypatch):
    """Every ancestor path returned by ``_get_folder_ancestor_ids`` should be
    fed to ``get_folder_phase_summary(force_refresh=True)`` exactly once."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    refreshed: list[tuple[str, bool]] = []
    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 42)
    monkeypatch.setattr(db, "_get_folder_ancestor_ids", lambda fid: [42, 7, 1])
    fake_conn = _FakeConnector(query_responses={
        "SELECT path FROM folders WHERE id IN": [
            [
                {"path": "/mnt/d/Photos/Z6ii/2026/2026-05-09"},
                {"path": "/mnt/d/Photos/Z6ii/2026"},
                {"path": "/mnt/d/Photos"},
            ],
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    def _fake_summary(path, force_refresh=False):
        refreshed.append((path, bool(force_refresh)))
        return []
    monkeypatch.setattr(db, "get_folder_phase_summary", _fake_summary)

    db.refresh_folder_phase_aggregates_with_ancestors(folder_path="/mnt/d/Photos/Z6ii/2026/2026-05-09")

    paths = [p for p, _ in refreshed]
    assert paths == [
        "/mnt/d/Photos/Z6ii/2026/2026-05-09",
        "/mnt/d/Photos/Z6ii/2026",
        "/mnt/d/Photos",
    ]
    assert all(force is True for _, force in refreshed), \
        "ancestor refresh must always force_refresh=True"


def test_refresh_folder_phase_aggregates_with_ancestors_no_folder_id(monkeypatch):
    """When the path can't be resolved to a folder_id, the helper is a no-op."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    monkeypatch.setattr(db, "get_or_create_folder", lambda p: None)

    called = {"summary": 0}

    def _fake_summary(path, force_refresh=False):
        called["summary"] += 1
        return []
    monkeypatch.setattr(db, "get_folder_phase_summary", _fake_summary)

    db.refresh_folder_phase_aggregates_with_ancestors(folder_path="/does/not/exist")

    assert called["summary"] == 0


def test_refresh_folder_phase_aggregates_with_ancestors_swallow_per_path_errors(monkeypatch):
    """A single ancestor refresh failure must not stop the rest of the walk."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 99)
    monkeypatch.setattr(db, "_get_folder_ancestor_ids", lambda fid: [99, 5])
    fake_conn = _FakeConnector(query_responses={
        "SELECT path FROM folders WHERE id IN": [
            [{"path": "/leaf"}, {"path": "/root"}],
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    seen: list[str] = []

    def _flaky_summary(path, force_refresh=False):
        seen.append(path)
        if path == "/leaf":
            raise RuntimeError("simulated failure")
        return []
    monkeypatch.setattr(db, "get_folder_phase_summary", _flaky_summary)

    db.refresh_folder_phase_aggregates_with_ancestors(folder_path="/leaf")

    assert seen == ["/leaf", "/root"], "root refresh must run even if leaf raised"


# --------------------------------------------------------------------------- #
# backfill_missing_phase_rows
# --------------------------------------------------------------------------- #

def test_backfill_missing_phase_rows_dry_run_counts_per_phase(monkeypatch):
    """Dry-run mode reports counts per phase and does not call set_image_phase_status."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    phase_id_map = {"indexing": 1, "metadata": 2, "scoring": 3, "keywords": 5, "culling": 4}
    monkeypatch.setattr(db, "get_phase_id", lambda code: phase_id_map.get(code))

    # Per-phase missing image IDs. Use FIFO list — connector pops one bucket per query call.
    fake_conn = _FakeConnector(query_responses={
        "FROM IMAGES I": [
            [{"id": 1001}],                              # indexing: 1
            [{"id": 1001}, {"id": 1002}],                # metadata: 2
            [{"id": 1001}, {"id": 1002}, {"id": 1003}],  # scoring: 3
            [{"id": 1003}, {"id": 1004}],                # keywords: 2
            [],                                          # culling: 0
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    set_calls: list = []
    monkeypatch.setattr(db, "set_image_phase_status",
                        lambda *a, **kw: set_calls.append((a, kw)) or 7)

    out = db.backfill_missing_phase_rows(dry_run=True)

    assert out["dry_run"] is True
    assert out["inserted"] == 0
    assert set_calls == [], "dry-run must not call set_image_phase_status"
    assert out["by_phase"] == {
        "indexing": 1, "metadata": 2, "scoring": 3, "keywords": 2, "culling": 0,
    }
    assert out["matched"] == 1 + 2 + 3 + 2 + 0


def test_backfill_missing_phase_rows_live_invokes_set_image_phase_status(monkeypatch):
    """Live mode hits set_image_phase_status once per (image_id, phase) pair and
    invalidates the folder cache when scoped to a path."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    monkeypatch.setattr(db, "get_phase_id", lambda code: {"scoring": 3, "keywords": 5}.get(code))

    fake_conn = _FakeConnector(query_responses={
        "FROM IMAGES I": [
            [{"id": 1001}, {"id": 1002}],  # scoring: 2
            [{"id": 1003}],                # keywords: 1
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)
    monkeypatch.setattr(
        db, "convert_path_to_wsl",
        lambda p: p, raising=False,
    )

    set_calls: list = []
    monkeypatch.setattr(db, "set_image_phase_status",
                        lambda iid, code, status: set_calls.append((iid, code, status)) or 42)

    invalidate_calls: list = []
    monkeypatch.setattr(db, "invalidate_folder_phase_aggregates",
                        lambda **kw: invalidate_calls.append(kw))

    out = db.backfill_missing_phase_rows(
        folder_path="/mnt/d/Photos/Z6ii/2026/2026-05-09",
        phase_codes=["scoring", "keywords"],
        dry_run=False,
    )

    assert out["dry_run"] is False
    assert out["matched"] == 3
    assert out["inserted"] == 3
    assert set_calls == [
        (1001, "scoring", "not_started"),
        (1002, "scoring", "not_started"),
        (1003, "keywords", "not_started"),
    ]
    assert invalidate_calls and invalidate_calls[0]["folder_path"].endswith("2026-05-09")


def test_backfill_missing_phase_rows_skips_unknown_phase(monkeypatch):
    """Unknown phase codes should be logged and skipped, not crash the run."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    monkeypatch.setattr(db, "get_phase_id", lambda code: 3 if code == "scoring" else None)
    fake_conn = _FakeConnector(query_responses={
        "FROM IMAGES I": [[{"id": 1}]],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    out = db.backfill_missing_phase_rows(phase_codes=["scoring", "ghost_phase"], dry_run=True)

    assert "scoring" in out["by_phase"]
    assert "ghost_phase" not in out["by_phase"]


# --------------------------------------------------------------------------- #
# repair_zombie_score_rows
# --------------------------------------------------------------------------- #

def test_repair_zombie_score_rows_dry_run(monkeypatch):
    """Dry-run reports matched count and performs no UPDATE."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    fake_conn = _FakeConnector(query_responses={
        "SELECT ID FROM IMAGES": [
            [{"id": 100}, {"id": 200}, {"id": 300}],
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    out = db.repair_zombie_score_rows(dry_run=True)

    assert out == {"matched": 3, "cleared": 0, "dry_run": True}
    assert fake_conn.executed == [], "dry-run must not run any UPDATE"


def test_repair_zombie_score_rows_live_clears(monkeypatch):
    """Live mode runs the UPDATE with the matched ids and re-asserts the predicate."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    fake_conn = _FakeConnector(query_responses={
        "SELECT ID FROM IMAGES": [
            [{"id": 100}, {"id": 200}],
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    out = db.repair_zombie_score_rows(dry_run=False)

    assert out["matched"] == 2
    assert out["cleared"] == 1  # _FakeConnector.execute returns 1 (rows affected stub)
    assert out["dry_run"] is False
    assert len(fake_conn.executed) == 1
    sql, params = fake_conn.executed[0]
    upper = sql.upper()
    assert "UPDATE IMAGES" in upper
    assert "SCORE = NULL" in upper
    assert "LABEL = NULL" in upper
    assert "RATING" not in upper, "rating must be left alone"
    assert tuple(params) == (100, 200)


def test_repair_zombie_score_rows_no_matches_short_circuits(monkeypatch):
    """When no rows match, live mode reports 0 and runs no UPDATE."""
    # Patch on db_legacy directly: the modules.db facade may have been
    # replaced by a bare stub in sys.modules by an earlier test
    # (test_clustering_representative._stub("modules.db")) that runs first
    # alphabetically. db_legacy is never stubbed and holds the real helpers.
    from modules import db_legacy as db

    fake_conn = _FakeConnector(query_responses={
        "SELECT ID FROM IMAGES": [[]],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    out = db.repair_zombie_score_rows(dry_run=False)

    assert out == {"matched": 0, "cleared": 0, "dry_run": False}
    assert fake_conn.executed == []


# --------------------------------------------------------------------------- #
# find_active_job_for_folder
# --------------------------------------------------------------------------- #

def test_find_active_job_collapses_windows_and_wsl_paths(monkeypatch):
    """Submitting a Windows-form path should hit an existing WSL-form job."""
    from modules import db_legacy as db

    fake_conn = _FakeConnector(query_responses={
        "FROM JOBS": [
            [
                {"id": 2351, "input_path": "D:\\Photos\\Z8\\180-600mm\\2026\\2026-05-09"},
                {"id": 2352, "input_path": "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-09"},
            ],
        ],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    # Probe with the WSL form — should find the *first* matching active job.
    found = db.find_active_job_for_folder(
        "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-09"
    )
    assert found in (2351, 2352)


def test_find_active_job_returns_none_when_no_match(monkeypatch):
    """A folder with no active job returns None."""
    from modules import db_legacy as db

    fake_conn = _FakeConnector(query_responses={
        "FROM JOBS": [[{"id": 99, "input_path": "/mnt/d/Photos/Z6ii/different/folder"}]],
    })
    monkeypatch.setattr(db, "get_connector", lambda: fake_conn)

    found = db.find_active_job_for_folder("/mnt/d/Photos/Z8/2026-05-09")
    assert found is None


def test_find_active_job_filters_by_job_type(monkeypatch):
    """Passing job_type narrows the SQL with an AND clause."""
    from modules import db_legacy as db

    captured: list = []
    real_conn = _FakeConnector()

    def _query(sql, params=None):
        captured.append((sql, tuple(params) if params else ()))
        return [{"id": 99, "input_path": "/x"}]

    real_conn.query = _query  # type: ignore[assignment]
    monkeypatch.setattr(db, "get_connector", lambda: real_conn)

    db.find_active_job_for_folder("/x", job_type="scoring")

    sql, params = captured[0]
    assert "job_type = ?" in sql
    assert params[-1] == "scoring"


def test_find_active_job_empty_input_returns_none(monkeypatch):
    """Defensive: empty/None input_path is not a duplicate."""
    from modules import db_legacy as db

    monkeypatch.setattr(db, "get_connector", lambda: _FakeConnector())
    assert db.find_active_job_for_folder("") is None
    assert db.find_active_job_for_folder(None) is None
