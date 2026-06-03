"""Cohesion-only culling heal must not re-queue folders after repeated completed heals."""

from __future__ import annotations

from contextlib import contextmanager

from modules import workflow_healing


def test_apply_cohesion_reheal_suppression_skips_after_max_attempts(monkeypatch):
    monkeypatch.setattr(
        workflow_healing,
        "_cohesion_reheal_limits",
        lambda: (2, 168.0),
    )
    monkeypatch.setattr(
        workflow_healing,
        "_folder_cohesion_only_culling_gaps",
        lambda _fp: True,
    )
    monkeypatch.setattr(
        workflow_healing,
        "_count_completed_culling_heals",
        lambda _fp, _h: 3,
    )

    kept, skipped = workflow_healing._apply_cohesion_reheal_suppression(
        [{"folder_path": "/mnt/d/Photos/example/2017-06-25", "image_count": 8}]
    )
    assert kept == []
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "cohesion_heal_exhausted"
    assert skipped[0]["prior_heal_attempts"] == 3


def test_apply_cohesion_reheal_suppression_keeps_when_under_max(monkeypatch):
    monkeypatch.setattr(
        workflow_healing,
        "_cohesion_reheal_limits",
        lambda: (2, 168.0),
    )
    monkeypatch.setattr(
        workflow_healing,
        "_folder_cohesion_only_culling_gaps",
        lambda _fp: True,
    )
    monkeypatch.setattr(
        workflow_healing,
        "_count_completed_culling_heals",
        lambda _fp, _h: 1,
    )

    folder = {"folder_path": "/mnt/d/Photos/example/2017-06-25", "image_count": 8}
    kept, skipped = workflow_healing._apply_cohesion_reheal_suppression([folder])
    assert kept == [folder]
    assert skipped == []


def test_heal_culling_wires_cohesion_suppression_into_result(monkeypatch):
    outer_calls: list[str] = []

    @contextmanager
    def _connection():
        class _Cur:
            def execute(self, *_a, **_k):
                pass

            def fetchall(self):
                return []

        yield type("Conn", (), {"cursor": lambda self: _Cur()})()

    monkeypatch.setattr(workflow_healing.db, "connection", _connection)
    monkeypatch.setattr(workflow_healing.db, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(
        workflow_healing.db,
        "get_culling_incomplete_predicate_sql",
        lambda *a, **k: "1=0",
    )
    monkeypatch.setattr(workflow_healing.db, "culling_cohesion_folders_aggregate_sql", lambda: "SELECT 1 WHERE 1=0")
    monkeypatch.setattr(workflow_healing, "_get_active_jobs_snapshot", lambda: [])
    monkeypatch.setattr(
        workflow_healing,
        "_apply_cohesion_reheal_suppression",
        lambda folders: (folders, [{"folder_path": "/x", "reason": "cohesion_heal_exhausted"}]),
    )

    result = workflow_healing.heal_phase_data("culling", dry_run=True, budget=1)
    assert result["cohesion_suppressed"] == 1
    assert len(result["skipped"]) == 1
