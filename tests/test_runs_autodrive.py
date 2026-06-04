from __future__ import annotations

import datetime
import json
import os

import pytest

from modules import runs_autodrive


def _phase(code: str, status: str, total: int = 10, done: int = 0, skipped: int = 0):
    return {
        "code": code,
        "name": code.title(),
        "status": status,
        "total_count": total,
        "done_count": done,
        "skipped_count": skipped,
        "failed_count": 0,
        "running_count": 0,
        "queued_count": 0,
        "paused_count": 0,
        "cancel_requested_count": 0,
        "restarting_count": 0,
    }


def test_build_folder_buckets_plans_suffix_from_first_incomplete(monkeypatch):
    folder = "/mnt/d/Photos/2026-05-01"
    summary = [
        _phase("indexing", "done", done=10),
        _phase("metadata", "done", done=10),
        _phase("scoring", "not_started"),
        _phase("culling", "not_started"),
        _phase("keywords", "not_started"),
        _phase("bird_species", "not_started"),
    ]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 1, "direct_count": 10}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {folder: summary},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    result = runs_autodrive.build_folder_buckets(limit=10)

    assert result["total"] == 1
    item = result["items"][0]
    assert item["bucket"] == "awaiting_scoring"
    assert item["current_phase"] == "scoring"
    assert item["next_phases"] == ["scoring", "culling", "keywords", "bird_species"]
    assert item["overall_percent"] == 33.3


def test_build_folder_buckets_marks_prereq_blocked_when_target_omits_missing_prereq(monkeypatch):
    folder = "/mnt/d/Photos/2026-05-02"
    summary = [
        _phase("indexing", "done", done=10),
        _phase("metadata", "not_started"),
        _phase("scoring", "not_started"),
    ]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 1, "direct_count": 10}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {folder: summary},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    result = runs_autodrive.build_folder_buckets(limit=10, target_phases=["scoring"])

    assert result["items"][0]["bucket"] == "blocked"
    assert result["items"][0]["blocked_by"] == {"scoring": ["metadata"]}


def test_build_folder_buckets_non_bird_folder_complete_when_bird_species_skipped(monkeypatch):
    folder = "/mnt/d/Photos/non-bird-only"
    summary = [
        _phase("indexing", "done", done=5),
        _phase("metadata", "done", done=5),
        _phase("scoring", "done", done=5),
        _phase("culling", "done", done=5),
        _phase("keywords", "done", done=5),
        _phase("bird_species", "skipped", total=0, skipped=0),
    ]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 1, "direct_count": 5}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {folder: summary},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    monkeypatch.setattr(runs_autodrive.db, "folder_has_bird_species_work", lambda _p: False)
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    result = runs_autodrive.build_folder_buckets(limit=10, include_complete=True)

    assert result["items"][0]["bucket"] == "complete"
    assert result["items"][0]["next_phases"] == []


def test_build_folder_buckets_culling_not_blocked_when_prereqs_done_outside_target(monkeypatch):
    folder = "/mnt/d/Photos/2026-05-10"
    summary = [
        _phase("indexing", "done", done=10),
        _phase("metadata", "done", done=10),
        _phase("scoring", "done", done=10),
        _phase("culling", "not_started"),
    ]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 1, "direct_count": 10}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {folder: summary},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    result = runs_autodrive.build_folder_buckets(limit=10, target_phases=["culling"])

    assert result["items"][0]["bucket"] == "awaiting_culling"
    assert result["items"][0]["blocked_by"] == {}


def test_path_intersects_active_does_not_mark_ancestor_in_flight():
    assert runs_autodrive._path_intersects_active("/photos/2026", {"/photos/2026/event"}) is False
    assert runs_autodrive._path_intersects_active("/photos/2026/event", {"/photos/2026"}) is True
    assert runs_autodrive._path_intersects_active("/photos/2026", {"/photos/2026"}) is True


def test_phases_with_work_from_repair_plan_skips_empty_and_clustering_alias(monkeypatch):
    def fake_plan(paths, stages, dry_run, include_stale_executor=True):
        assert dry_run is True
        assert include_stale_executor is False
        return {
            "stage_queues": {
                "indexing": [],
                "scoring": [1, 2, 3],
                "clustering": [99],
                "keywords": [],
            }
        }

    monkeypatch.setattr(runs_autodrive.db, "build_validation_repair_plan", fake_plan)

    out = runs_autodrive.phases_with_work_from_repair_plan(
        ["/mnt/d/Photos/x"],
        ["indexing", "scoring", "keywords"],
        dry_run=True,
    )

    assert out == ["scoring"]


def test_build_folder_buckets_attaches_planner_next_phases(monkeypatch):
    folder = "/mnt/d/Photos/planner-preview"
    summary = [
        _phase("indexing", "done", done=3),
        _phase("metadata", "done", done=3),
        _phase("scoring", "not_started"),
    ]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 3, "direct_count": 3}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {folder: summary},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    monkeypatch.setattr(runs_autodrive.db, "folder_has_bird_species_work", lambda _p: False)
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda p: (p, []),
    )

    def fake_planner(paths, stages, dry_run=True, include_stale_executor=False):
        assert include_stale_executor is False
        return ["scoring"]

    monkeypatch.setattr(runs_autodrive, "phases_with_work_from_repair_plan", fake_planner)

    result = runs_autodrive.build_folder_buckets(limit=10, planner_preview_limit=5)

    item = result["items"][0]
    assert item["planner_next_phases"] == ["scoring"]
    assert item["next_phases"][0] == "scoring"


def test_build_folder_buckets_refreshes_when_bulk_cache_missing(monkeypatch):
    folder = "/mnt/d/Photos/missing-bulk-cache"
    fresh_summary = [
        _phase("indexing", "done", done=4),
        _phase("metadata", "done", done=4),
        _phase("scoring", "done", done=4),
        _phase("culling", "done", done=4),
        _phase("keywords", "done", done=4),
        _phase("bird_species", "skipped", total=0),
    ]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 2, "direct_count": 4}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    refreshed = []

    def _refresh(path, force_refresh=False):
        refreshed.append((path, force_refresh))
        return fresh_summary

    monkeypatch.setattr(runs_autodrive.db, "get_folder_phase_summary", _refresh)
    monkeypatch.setattr(runs_autodrive.db, "folder_has_bird_species_work", lambda _p: False)
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    result = runs_autodrive.build_folder_buckets(
        limit=10,
        refresh_dirty_limit=10,
        include_complete=True,
    )

    assert len(refreshed) == 1
    assert refreshed[0][1] is True
    assert result["items"][0]["bucket"] == "complete"


def test_enqueue_auto_bucket_uses_only_repair_plan_phases_with_work(monkeypatch):
    folder = "/mnt/d/Photos/2026-05-20"
    bucket = {
        "path": folder,
        "next_phases": ["indexing", "metadata", "scoring", "keywords"],
        "bucket": "awaiting_indexing",
    }
    plan_calls = []

    def fake_plan(paths, stages, dry_run, include_stale_executor=True):
        plan_calls.append((list(paths), list(stages), dry_run, include_stale_executor))
        if dry_run:
            return {"stage_queues": {"indexing": [], "scoring": [10, 11], "keywords": [10]}}
        return {
            "stage_queues": {"scoring": [10, 11], "keywords": [10]},
            "issue_counts_by_reason": {"stale_executor": 2},
        }

    monkeypatch.setattr(runs_autodrive.db, "build_validation_repair_plan", fake_plan)
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda p: (p, []),
    )
    monkeypatch.setattr(runs_autodrive.os.path, "isdir", lambda _p: True)
    monkeypatch.setattr(runs_autodrive, "assert_prereqs_for_scope", lambda *_a, **_k: None)
    enqueued = {}

    def fake_enqueue(path, first_phase, job_type, payload, description, phase_codes=None, **_kw):
        enqueued["phase_codes"] = list(phase_codes or [])
        enqueued["payload_phases"] = payload.get("target_phases")
        enqueued["reason"] = payload.get("reason")
        return 9001, 1

    monkeypatch.setattr(runs_autodrive.db, "enqueue_job_with_phases", fake_enqueue)
    monkeypatch.setattr(runs_autodrive, "augment_queue_payload_for_audit", lambda p, **_k: p)
    monkeypatch.setattr(
        runs_autodrive,
        "build_run_submit_description",
        lambda **_k: "test",
    )

    job_id, pos, skip = runs_autodrive._enqueue_auto_bucket(bucket, generate_captions=False)

    assert skip is None
    assert job_id == 9001
    assert enqueued["phase_codes"] == ["indexing", "metadata", "scoring", "keywords"]
    assert plan_calls[0][2] is True
    assert plan_calls[1][2] is False
    assert plan_calls[1][1] == ["indexing", "metadata", "scoring", "keywords"]
    assert plan_calls[0][3] is False
    assert plan_calls[1][3] is False
    assert enqueued["reason"]["source"] == "auto_drive"
    assert enqueued["reason"]["criteria"]["enqueued_phases"] == ["indexing", "metadata", "scoring", "keywords"]
    assert enqueued["reason"]["criteria"]["planner_reason_counts"]["stale_executor"] == 2


def test_build_folder_buckets_refreshes_dirty_folder(monkeypatch):
    folder = "/mnt/d/Photos/dirty-folder"
    fresh_summary = [_phase("scoring", "done", done=3)]

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {folder: {"folder_id": 1, "direct_count": 3}},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: {os.path.normpath(folder)},
    )
    refreshed = []

    def _refresh(path, force_refresh=False):
        refreshed.append((path, force_refresh))
        return fresh_summary

    monkeypatch.setattr(runs_autodrive.db, "get_folder_phase_summary", _refresh)
    monkeypatch.setattr(runs_autodrive.db, "folder_has_bird_species_work", lambda _p: False)
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    runs_autodrive.build_folder_buckets(limit=10, refresh_dirty_limit=5)

    assert len(refreshed) == 1
    assert refreshed[0][1] is True


def test_auto_drive_skips_non_leaf_parent(monkeypatch):
    parent = "/mnt/d/Photos/parent"
    child = "/mnt/d/Photos/parent/child"
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {
            parent: {"folder_id": 1, "direct_count": 0},
            child: {"folder_id": 2, "direct_count": 5},
        },
    )
    monkeypatch.setattr(runs_autodrive, "_reconcile_stale_ips_for_drive", lambda: None)
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets",
        lambda **_kwargs: {
            "items": [
                {
                    "path": parent,
                    "bucket": "awaiting_scoring",
                    "next_phases": ["scoring"],
                    "plan_key": "parent",
                },
                {
                    "path": child,
                    "bucket": "awaiting_scoring",
                    "next_phases": ["scoring"],
                    "plan_key": "child",
                },
            ],
            "total": 2,
            "bucket_counts": {"awaiting_scoring": 2},
            "phase_counts": {"scoring": 2},
        },
    )
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda *_a, **_k: {})

    result = runs_autodrive.auto_drive_runs(dry_run=True, limit=10)

    scheduled_paths = [s["folder_path"] for s in result["scheduled"]]
    assert child in scheduled_paths
    assert parent not in scheduled_paths


def test_auto_drive_dry_run_returns_candidates(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets",
        lambda **_kwargs: {
            "items": [
                {
                    "path": "/mnt/d/Photos/2026-05-03",
                    "bucket": "awaiting_metadata",
                    "next_phases": ["metadata", "scoring"],
                    "plan_key": "abc",
                }
            ],
            "total": 1,
            "bucket_counts": {"awaiting_metadata": 1},
            "phase_counts": {"metadata": 1},
        },
    )
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda *_a, **_k: {"abc": {"attempts": 0}})

    result = runs_autodrive.auto_drive_runs(dry_run=True)

    assert result["dry_run"] is True
    assert len(result["scheduled"]) == 1
    assert result["scheduled"][0]["phases"] == ["metadata", "scoring"]


def test_auto_drive_skips_throwaway_planner_preview(monkeypatch):
    """The drive must not pay for the JIT planner preview it never reads."""
    captured: dict = {}

    def _fake_buckets(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "total": 0,
            "bucket_counts": {},
            "phase_counts": {},
        }

    monkeypatch.setattr(runs_autodrive, "_reconcile_stale_ips_for_drive", lambda: None)
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {},
    )
    monkeypatch.setattr(runs_autodrive, "build_folder_buckets", _fake_buckets)
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda *_a, **_k: {})

    runs_autodrive.auto_drive_runs(dry_run=True, limit=10)

    assert captured.get("planner_preview_limit") == 0


def test_auto_drive_plan_key_matches_enqueue_when_phases_narrowed(monkeypatch):
    """Loop guard must count prior jobs under the SAME key used at enqueue.

    Regression for RCA root cause #2: ``_enqueue_auto_bucket`` stores the
    JIT-narrowed ``_plan_key(resolved, phase_values)`` on the job payload, so the
    guard must look prior jobs up by that narrowed key — not the wider structural
    ``next_phases`` bucket key. This exercises the REAL ``_recent_auto_attempt_counts``
    (only ``db.get_jobs`` is faked); keying it on the bucket key (the prior bug)
    leaves the narrowed jobs uncounted and the guard never fires.
    """
    folder = "/mnt/d/Photos/Z8/28-400mm/2026/2026-05-28"
    enqueue_key = runs_autodrive._plan_key(folder, ["keywords"])
    structural_key = runs_autodrive._plan_key(folder, ["keywords", "bird_species"])
    assert enqueue_key != structural_key

    monkeypatch.setattr(runs_autodrive, "_reconcile_stale_ips_for_drive", lambda: None)
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: {},
    )
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets",
        lambda **_kwargs: {
            "items": [
                {
                    "path": folder,
                    "bucket": "awaiting_keywords",
                    "next_phases": ["keywords", "bird_species"],
                    "plan_key": structural_key,
                }
            ],
            "total": 1,
            "bucket_counts": {"awaiting_keywords": 1},
            "phase_counts": {"keywords": 1},
        },
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: (folder, [folder]),
    )
    monkeypatch.setattr(
        runs_autodrive,
        "phases_with_work_from_repair_plan",
        lambda _paths, _stages, dry_run=True, **kwargs: ["keywords"],
    )
    # Two prior auto-drive jobs stored under the NARROWED enqueue key.
    job_payload = json.dumps({"tool_id": "runs_auto_drive", "auto_drive_plan_key": enqueue_key})
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_jobs",
        lambda **_k: [
            {"id": 99, "status": "completed", "queue_payload": job_payload},
            {"id": 98, "status": "completed", "queue_payload": job_payload},
        ],
    )

    def _boom(*_a, **_k):
        raise AssertionError("loop guard should have skipped enqueue")

    monkeypatch.setattr(runs_autodrive, "_enqueue_auto_bucket", _boom)

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 1
    assert result["scheduled"] == []
    assert result["skipped"]
    assert result["skipped"][0]["reason"] == "loop_detected"


def test_auto_drive_loop_guard_skips_repeated_plan(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets",
        lambda **_kwargs: {
            "items": [
                {
                    "path": "/mnt/d/Photos/2026-05-04",
                    "bucket": "awaiting_scoring",
                    "next_phases": ["scoring"],
                    "plan_key": "repeat",
                }
            ],
            "total": 1,
            "bucket_counts": {"awaiting_scoring": 1},
            "phase_counts": {"scoring": 1},
        },
    )
    monkeypatch.setattr(
        runs_autodrive,
        "_recent_auto_attempt_counts",
        lambda *_a, **_k: {"repeat": {"attempts": 2, "last_run_id": 77, "last_status": "failed"}},
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["scheduled"] == []
    assert result["loop_detected"] == 1
    assert result["skipped"][0]["reason"] == "loop_detected"
    assert result["skipped"][0]["last_run_id"] == 77


def test_recent_auto_attempt_counts_includes_in_flight_jobs(monkeypatch):
    rows = [
        {
            "id": 101,
            "status": "running",
            "queue_payload": json.dumps({
                "tool_id": "runs_auto_drive",
                "auto_drive_plan_key": "plan_a",
            }),
        },
        {
            "id": 102,
            "status": "running",
            "queue_payload": json.dumps({
                "tool_id": "runs_auto_drive",
                "auto_drive_plan_key": "plan_a",
            }),
        },
    ]
    monkeypatch.setattr(runs_autodrive.db, "get_jobs", lambda **kwargs: rows)

    counts = runs_autodrive._recent_auto_attempt_counts(["plan_a"])

    assert counts["plan_a"]["attempts"] == 2
    assert counts["plan_a"]["last_run_id"] == 101
    assert counts["plan_a"]["last_status"] == "running"


def test_auto_drive_loop_guard_blocks_third_enqueue_when_two_in_flight(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets",
        lambda **_kwargs: {
            "items": [
                {
                    "path": "/mnt/d/Photos/in-flight",
                    "bucket": "awaiting_scoring",
                    "next_phases": ["scoring"],
                    "plan_key": "plan_a",
                }
            ],
            "total": 1,
            "bucket_counts": {"awaiting_scoring": 1},
            "phase_counts": {"scoring": 1},
        },
    )
    monkeypatch.setattr(
        runs_autodrive,
        "_recent_auto_attempt_counts",
        lambda *_a, **_k: {"plan_a": {"attempts": 2, "last_run_id": 102, "last_status": "running"}},
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["scheduled"] == []
    assert result["loop_detected"] == 1


def test_auto_drive_passes_limit_to_build_folder_buckets(monkeypatch):
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "total": 0,
            "bucket_counts": {},
            "phase_counts": {},
        }

    monkeypatch.setattr(runs_autodrive, "build_folder_buckets", fake_build)
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda *_a, **_k: {})

    runs_autodrive.auto_drive_runs(limit=300)

    assert captured.get("limit") == 300


def test_get_drive_status_with_outstanding_uses_target_phases(monkeypatch):
    with runs_autodrive._DRIVE_LOCK:
        runs_autodrive._DRIVE_STATE["target_phases"] = ["scoring"]

    runs_autodrive.get_drive_status_with_outstanding()
    assert runs_autodrive.get_drive_state()["target_phases"] == ["scoring"]


def test_get_drive_status_with_outstanding_uses_last_result_when_present():
    with runs_autodrive._DRIVE_LOCK:
        runs_autodrive._DRIVE_STATE["last_result"] = {
            "scheduled": 1,
            "skipped": 0,
            "candidates": 2,
            "total_outstanding": 12,
            "loop_detected": 0,
            "bucket_counts": {"awaiting_scoring": 12},
            "phase_counts": {"scoring": 12},
            "health": runs_autodrive._bucket_health_from_counts({"awaiting_scoring": 12}),
        }

    out = runs_autodrive.get_drive_status_with_outstanding()

    assert out["outstanding"]["source"] == "last_result"
    assert out["outstanding"]["total_outstanding"] == 12
    assert out["outstanding"]["bucket_counts"]["awaiting_scoring"] == 12


# ---------------------------------------------------------------------------
# Durable drive loop
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_drive(monkeypatch):
    """Silence broadcasts and reset the module-global drive state per test."""
    monkeypatch.setattr(runs_autodrive, "_broadcast_drive", lambda *a, **k: None)
    monkeypatch.setattr(runs_autodrive, "_config_server_loop_enabled", lambda: True)
    with runs_autodrive._DRIVE_LOCK:
        runs_autodrive._DRIVE_STATE.update(
            {
                "enabled": False,
                "root_path": None,
                "limit": 50,
                "max_repeats": 2,
                "generate_captions": True,
                "target_phases": None,
                "started_at": None,
                "last_tick_at": 0.0,
                "last_result": None,
                "stop_reason": None,
                "idle_no_progress_ticks": 0,
            }
        )
    yield
    runs_autodrive.stop_drive("test_teardown")


def _drive_result(scheduled: int = 0, outstanding: int = 0, **extra):
    bucket_counts = extra.pop("bucket_counts", None)
    if bucket_counts is None:
        if outstanding > 0 and scheduled == 0:
            if extra.get("candidates", 0) == 0 and "in_flight" not in extra:
                bucket_counts = {"in_flight": outstanding}
            else:
                bucket_counts = {"awaiting_scoring": outstanding}
        else:
            bucket_counts = {}
    candidates = extra.pop("candidates", scheduled if scheduled else (outstanding if bucket_counts.get("awaiting_scoring") else 0))
    health = runs_autodrive._bucket_health_from_counts(bucket_counts)
    return {
        "scheduled": [{"folder_path": f"/f{i}"} for i in range(scheduled)],
        "skipped": [],
        "candidates": candidates,
        "total_outstanding": outstanding,
        "loop_detected": 0,
        "bucket_counts": bucket_counts,
        "phase_counts": {},
        "health": health,
        **extra,
    }


def _force_next_tick():
    with runs_autodrive._DRIVE_LOCK:
        runs_autodrive._DRIVE_STATE["last_tick_at"] = 0.0


def test_start_drive_runs_first_batch_and_enables(monkeypatch):
    calls = []

    def fake_auto(**kwargs):
        calls.append(kwargs)
        return _drive_result(scheduled=2, outstanding=5)

    monkeypatch.setattr(runs_autodrive, "auto_drive_runs", fake_auto)

    out = runs_autodrive.start_drive(root_path="/mnt/d/Photos", limit=10)

    assert out["state"]["enabled"] is True
    assert out["state"]["root_path"] == "/mnt/d/Photos"
    assert out["result"]["scheduled"] == 2
    assert len(calls) == 1
    assert calls[0]["dry_run"] is False
    assert calls[0]["root_path"] == "/mnt/d/Photos"


def test_drive_tick_noop_when_disabled(monkeypatch):
    called = []
    monkeypatch.setattr(runs_autodrive, "auto_drive_runs", lambda **k: called.append(k) or _drive_result())

    assert runs_autodrive.drive_tick() is None
    assert called == []


def test_drive_tick_noop_when_kill_switch_off(monkeypatch):
    monkeypatch.setattr(runs_autodrive, "auto_drive_runs", lambda **k: _drive_result(scheduled=1, outstanding=5))
    runs_autodrive.start_drive(limit=5)
    monkeypatch.setattr(runs_autodrive, "_config_server_loop_enabled", lambda: False)
    _force_next_tick()

    assert runs_autodrive.drive_tick() is None
    assert runs_autodrive.get_drive_state()["enabled"] is True  # still armed, just paused


def test_drive_stops_when_outstanding_zero(monkeypatch):
    monkeypatch.setattr(runs_autodrive, "auto_drive_runs", lambda **k: _drive_result(scheduled=1, outstanding=0))

    runs_autodrive.start_drive(limit=5)

    state = runs_autodrive.get_drive_state()
    assert state["enabled"] is False
    assert state["stop_reason"] == "complete"


def test_drive_stops_when_stalled(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "auto_drive_runs",
        lambda **k: _drive_result(
            scheduled=0,
            outstanding=3,
            candidates=3,
            bucket_counts={"awaiting_scoring": 3},
        ),
    )

    runs_autodrive.start_drive(limit=5)  # forced batch #1 -> 1 no-progress tick
    assert runs_autodrive.get_drive_state()["enabled"] is True

    for _ in range(runs_autodrive.DRIVE_MAX_NOPROGRESS_TICKS):
        _force_next_tick()
        runs_autodrive.drive_tick()

    state = runs_autodrive.get_drive_state()
    assert state["enabled"] is False
    assert state["stop_reason"] == "stalled"


def test_drive_continues_when_all_outstanding_in_flight(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "auto_drive_runs",
        lambda **k: _drive_result(
            scheduled=0,
            outstanding=3,
            candidates=0,
            bucket_counts={"in_flight": 3},
        ),
    )

    runs_autodrive.start_drive(limit=5)
    assert runs_autodrive.get_drive_state()["enabled"] is True

    for _ in range(runs_autodrive.DRIVE_MAX_NOPROGRESS_TICKS + 2):
        _force_next_tick()
        runs_autodrive.drive_tick()

    state = runs_autodrive.get_drive_state()
    assert state["enabled"] is True
    assert state["idle_no_progress_ticks"] == 0
    assert state["last_result"]["last_tick_reason"] == "waiting_in_flight"


def test_drive_stops_when_only_blocked_folders_remain(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "auto_drive_runs",
        lambda **k: _drive_result(
            scheduled=0,
            outstanding=2,
            candidates=0,
            bucket_counts={"blocked": 2},
        ),
    )

    runs_autodrive.start_drive(limit=5)

    state = runs_autodrive.get_drive_state()
    assert state["enabled"] is False
    assert state["stop_reason"] == "blocked"


def test_drive_tick_respects_cooldown(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runs_autodrive,
        "auto_drive_runs",
        lambda **k: calls.append(1) or _drive_result(scheduled=1, outstanding=5),
    )

    runs_autodrive.start_drive(limit=5)  # forced batch
    assert len(calls) == 1

    runs_autodrive.drive_tick()  # within cooldown -> skipped
    assert len(calls) == 1

    _force_next_tick()
    runs_autodrive.drive_tick()  # cooldown bypassed -> runs
    assert len(calls) == 2


def _bucket_folder_meta(
    *,
    folder_id: int,
    direct_count: int,
    created_at: datetime.datetime,
) -> dict:
    return {
        "folder_id": folder_id,
        "direct_count": direct_count,
        "created_at": created_at,
    }


def _patch_folder_buckets_db(monkeypatch, folder_map: dict, summaries: dict):
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: folder_map,
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_all_folder_phase_summaries_bulk",
        lambda **_kwargs: summaries,
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_agg_dirty_local_paths",
        lambda: set(),
    )
    monkeypatch.setattr(runs_autodrive.db, "folder_has_bird_species_work", lambda _p: False)
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())
    monkeypatch.setattr(runs_autodrive, "_autodrive_prioritize_new_folders", lambda: True)
    monkeypatch.setattr(runs_autodrive, "_autodrive_new_folder_days", lambda: 7)


def test_build_folder_buckets_prioritizes_new_folder_across_phases(monkeypatch):
    now = datetime.datetime.now()
    old_path = "/mnt/d/Photos/2025/old-shoot"
    new_path = "/mnt/d/Photos/2026/new-shoot"
    folder_map = {
        old_path: _bucket_folder_meta(folder_id=1, direct_count=500, created_at=now - datetime.timedelta(days=30)),
        new_path: _bucket_folder_meta(folder_id=2, direct_count=50, created_at=now),
    }
    summaries = {
        old_path: [
            _phase("indexing", "done", done=10),
            _phase("metadata", "not_started"),
            _phase("scoring", "not_started"),
        ],
        new_path: [
            _phase("indexing", "done", done=10),
            _phase("metadata", "done", done=10),
            _phase("scoring", "not_started"),
        ],
    }
    _patch_folder_buckets_db(monkeypatch, folder_map, summaries)

    result = runs_autodrive.build_folder_buckets(limit=10)

    assert result["items"][0]["path"] == new_path
    assert result["items"][0]["is_newly_imported"] is True
    assert result["items"][1]["path"] == old_path
    assert result["items"][1]["is_newly_imported"] is False


def test_build_folder_buckets_new_folder_tiebreak_prefers_newer_created_at(monkeypatch):
    now = datetime.datetime.now()
    older_new = "/mnt/d/Photos/2026/older-new"
    newer_new = "/mnt/d/Photos/2026/newer-new"
    folder_map = {
        older_new: _bucket_folder_meta(folder_id=1, direct_count=200, created_at=now - datetime.timedelta(hours=2)),
        newer_new: _bucket_folder_meta(folder_id=2, direct_count=20, created_at=now),
    }
    summary = [
        _phase("indexing", "done", done=5),
        _phase("metadata", "not_started"),
        _phase("scoring", "not_started"),
    ]
    summaries = {older_new: summary, newer_new: summary}
    _patch_folder_buckets_db(monkeypatch, folder_map, summaries)

    result = runs_autodrive.build_folder_buckets(limit=10)

    assert result["items"][0]["path"] == newer_new
    assert result["items"][1]["path"] == older_new


def test_build_folder_buckets_legacy_sort_when_prioritize_disabled(monkeypatch):
    now = datetime.datetime.now()
    old_path = "/mnt/d/Photos/2025/old-shoot"
    new_path = "/mnt/d/Photos/2026/new-shoot"
    folder_map = {
        old_path: _bucket_folder_meta(folder_id=1, direct_count=10, created_at=now - datetime.timedelta(days=30)),
        new_path: _bucket_folder_meta(folder_id=2, direct_count=10, created_at=now),
    }
    summaries = {
        old_path: [
            _phase("indexing", "done", done=10),
            _phase("metadata", "not_started"),
        ],
        new_path: [
            _phase("indexing", "done", done=10),
            _phase("metadata", "done", done=10),
            _phase("scoring", "not_started"),
        ],
    }
    _patch_folder_buckets_db(monkeypatch, folder_map, summaries)
    monkeypatch.setattr(runs_autodrive, "_autodrive_prioritize_new_folders", lambda: False)

    result = runs_autodrive.build_folder_buckets(limit=10)

    assert result["items"][0]["path"] == old_path
    assert result["items"][0]["is_newly_imported"] is False
    assert result["items"][1]["path"] == new_path


def test_auto_drive_runs_dry_run_schedules_new_folder_first(monkeypatch):
    now = datetime.datetime.now()
    old_path = "/mnt/d/Photos/2025/old-shoot"
    new_path = "/mnt/d/Photos/2026/new-shoot"
    folder_map = {
        old_path: _bucket_folder_meta(folder_id=1, direct_count=100, created_at=now - datetime.timedelta(days=30)),
        new_path: _bucket_folder_meta(folder_id=2, direct_count=30, created_at=now),
    }
    summaries = {
        old_path: [
            _phase("indexing", "done", done=5),
            _phase("metadata", "not_started"),
        ],
        new_path: [
            _phase("indexing", "done", done=5),
            _phase("metadata", "done", done=5),
            _phase("scoring", "not_started"),
        ],
    }
    _patch_folder_buckets_db(monkeypatch, folder_map, summaries)
    monkeypatch.setattr(runs_autodrive, "_reconcile_stale_ips_for_drive", lambda: None)
    monkeypatch.setattr(
        runs_autodrive,
        "phases_with_work_from_repair_plan",
        lambda paths, stages, **kw: list(stages),
    )

    result = runs_autodrive.auto_drive_runs(limit=5, dry_run=True)

    assert result["scheduled"]
    assert result["scheduled"][0]["folder_path"] == new_path


def test_build_folder_buckets_explicit_paths_use_scoped_direct_counts(monkeypatch):
    target = "/mnt/d/Photos/test"
    scoped_paths: list[list[str]] = []

    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: (_ for _ in ()).throw(AssertionError("full library scan should not run")),
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_for_paths",
        lambda paths: scoped_paths.append(list(paths))
        or {target: {"folder_id": 1, "direct_count": 3, "created_at": None}},
    )
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_phase_summary",
        lambda path, force_refresh=False: [
            _phase("indexing", "done", done=3),
            _phase("metadata", "not_started"),
        ],
    )
    monkeypatch.setattr(runs_autodrive.db, "folder_has_bird_species_work", lambda _p: False)

    result = runs_autodrive.build_folder_buckets(
        folder_paths=[target],
        limit=5,
        refresh_dirty_limit=1,
    )

    assert scoped_paths == [[target]]
    assert len(result["items"]) == 1
    assert result["items"][0]["path"] == target


def test_auto_drive_explicit_paths_skip_library_reconcile_and_leaf_filter(monkeypatch):
    target = "/mnt/d/Photos/parent"
    reconcile_called = []

    monkeypatch.setattr(
        runs_autodrive,
        "_reconcile_stale_ips_for_drive",
        lambda: reconcile_called.append(True),
    )
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets",
        lambda **kwargs: {
            "items": [{
                "path": target,
                "next_phases": ["metadata"],
                "bucket": "awaiting_metadata",
            }],
            "total": 1,
            "bucket_counts": {"awaiting_metadata": 1},
            "phase_counts": {},
        },
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_folder_direct_image_counts_by_local_path_norm",
        lambda: (_ for _ in ()).throw(AssertionError("full library scan should not run")),
    )
    monkeypatch.setattr(
        runs_autodrive,
        "_is_leaf_folder_for_autodrive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("leaf filter should not run")),
    )
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda _keys: {})
    monkeypatch.setattr(
        runs_autodrive,
        "_enqueue_auto_bucket",
        lambda bucket, **kwargs: (42, 1, None),
    )

    result = runs_autodrive.auto_drive_runs(
        folder_paths=[target],
        limit=1,
        dry_run=False,
    )

    assert reconcile_called == []
    assert result["scheduled"][0]["job_id"] == 42


def test_resolve_auto_drive_enqueue_phases_includes_pipeline_prefix(monkeypatch):
    folder = "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-31"

    def fake_plan(paths, stages, dry_run, include_stale_executor=False):
        return {
            "stage_queues": {
                "metadata": [],
                "scoring": [1, 2],
                "culling": [1],
                "keywords": [1],
                "bird_species": [1],
            }
        }

    monkeypatch.setattr(runs_autodrive.db, "build_validation_repair_plan", fake_plan)
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda p: (p, []),
    )
    monkeypatch.setattr(runs_autodrive.os.path, "isdir", lambda _p: True)
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        lambda path, force_refresh=False: [
            _phase("indexing", "done", done=10),
            _phase("metadata", "not_started"),
            _phase("scoring", "not_started"),
        ],
    )

    candidates = ["metadata", "scoring", "culling", "keywords", "bird_species"]
    phases = runs_autodrive.resolve_auto_drive_enqueue_phases(folder, candidates, dry_run=True)
    assert phases == candidates

    bucket = {
        "path": folder,
        "next_phases": candidates,
        "bucket": "awaiting_metadata",
    }
    enqueued = {}

    def fake_enqueue(path, first_phase, job_type, payload, description, phase_codes=None, **_kw):
        enqueued["phase_codes"] = list(phase_codes or [])
        return 77, 1

    monkeypatch.setattr(runs_autodrive.db, "enqueue_job_with_phases", fake_enqueue)
    monkeypatch.setattr(runs_autodrive, "augment_queue_payload_for_audit", lambda p, **_k: p)
    monkeypatch.setattr(runs_autodrive, "build_run_submit_description", lambda **_k: "test")

    job_id, pos, skip = runs_autodrive._enqueue_auto_bucket(bucket, generate_captions=False)

    assert skip is None
    assert job_id == 77
    assert enqueued["phase_codes"] == candidates
