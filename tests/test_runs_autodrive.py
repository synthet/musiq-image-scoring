from __future__ import annotations

import datetime
import json
import os

import pytest

from modules import runs_autodrive


def _local_bucket_path(raw: str) -> str:
    """Expected ``path`` / ``folder_path`` from bucket builders on this host."""
    return runs_autodrive._local_path(raw)


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
            {"id": 99, "status": "failed", "queue_payload": job_payload},
            {"id": 98, "status": "failed", "queue_payload": job_payload},
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
        lambda *_a, **_k: {
            "repeat": {
                "failure_attempts": 2,
                "completed_attempts": 0,
                "last_completed_percent": 0.0,
                "last_run_id": 77,
                "last_status": "failed",
            }
        },
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["scheduled"] == []
    assert result["loop_detected"] == 1
    assert result["skipped"][0]["reason"] == "loop_detected"
    assert result["skipped"][0]["last_run_id"] == 77


def test_force_bypasses_loop_guard_for_scoped_folder(monkeypatch):
    folder = "/mnt/d/Photos/2026-05-04"
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets_for_autodrive",
        lambda **_kwargs: {
            "items": [
                {
                    "path": folder,
                    "bucket": "awaiting_scoring",
                    "next_phases": ["scoring"],
                    "plan_key": "repeat",
                    "overall_percent": 50.0,
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
        lambda *_a, **_k: {
            "repeat": {
                "failure_attempts": 2,
                "completed_attempts": 0,
                "last_completed_percent": 0.0,
                "last_run_id": 77,
                "last_status": "failed",
            }
        },
    )
    monkeypatch.setattr(
        runs_autodrive,
        "_resolve_enqueue_phases_with_refresh",
        lambda *_a, **_k: ["scoring"],
    )
    monkeypatch.setattr(
        runs_autodrive,
        "_enqueue_auto_bucket",
        lambda *_a, **_k: (42, 1, None),
    )
    monkeypatch.setattr(runs_autodrive.db, "count_running_pipeline_jobs", lambda **_k: 0)

    result = runs_autodrive.auto_drive_runs(
        dry_run=False,
        max_repeats=2,
        force=True,
        folder_paths=[folder],
    )

    assert result["loop_detected"] == 0
    assert len(result["scheduled"]) == 1
    assert result["scheduled"][0]["job_id"] == 42


def test_summarize_result_includes_skipped_detail():
    result = {
        "scheduled": [],
        "skipped": [
            {
                "folder_path": "/mnt/d/x",
                "reason": "failed_exhausted",
                "failed_phase": "culling",
                "failed_images": [{"image_id": 1, "file_path": "/a.jpg", "attempt_count": 3}],
            }
        ],
        "candidates": 1,
        "total_outstanding": 1,
        "loop_detected": 1,
        "skip_reason_counts": {"failed_exhausted": 1},
        "bucket_counts": {"awaiting_culling": 1},
    }
    summary = runs_autodrive._summarize_result(result, last_tick_reason="no_enqueue_progress")
    assert summary["skipped"] == 1
    assert summary["skipped_detail"][0]["reason"] == "failed_exhausted"
    assert summary["skipped_detail"][0]["failed_images"][0]["file_path"] == "/a.jpg"


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

    assert counts["plan_a"]["failure_attempts"] == 2
    assert counts["plan_a"]["completed_attempts"] == 0
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
        lambda *_a, **_k: {
            "plan_a": {
                "failure_attempts": 2,
                "completed_attempts": 0,
                "last_completed_percent": 0.0,
                "last_run_id": 102,
                "last_status": "running",
            }
        },
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["scheduled"] == []
    assert result["loop_detected"] == 1


def test_auto_drive_skips_enqueue_when_in_flight_cap(monkeypatch):
    folder = "/mnt/d/Photos/in-flight-cap"
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets_for_autodrive",
        lambda **_kwargs: {
            "items": [
                {
                    "path": folder,
                    "bucket": "awaiting_metadata",
                    "next_phases": ["metadata"],
                    "plan_key": "cap_plan",
                    "overall_percent": 80.0,
                }
            ],
            "total": 1,
            "bucket_counts": {"awaiting_metadata": 1},
            "phase_counts": {"metadata": 1},
        },
    )
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda *_a, **_k: {})
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: (folder, [folder]),
    )
    monkeypatch.setattr(
        runs_autodrive,
        "resolve_auto_drive_enqueue_phases",
        lambda *_a, **_k: ["metadata"],
    )
    monkeypatch.setattr(runs_autodrive.db, "count_running_pipeline_jobs", lambda **kw: 2)

    def _boom(*_a, **_k):
        raise AssertionError("enqueue should be blocked by in_flight_cap")

    monkeypatch.setattr(runs_autodrive, "_enqueue_auto_bucket", _boom)

    result = runs_autodrive.auto_drive_runs(dry_run=False, limit=10, max_repeats=2)

    assert result["scheduled"] == []
    assert result["skipped"]
    assert result["skipped"][0]["reason"] == "in_flight_cap"


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

    monkeypatch.setattr(runs_autodrive, "build_folder_buckets_for_autodrive", fake_build)
    monkeypatch.setattr(runs_autodrive, "_recent_auto_attempt_counts", lambda *_a, **_k: {})

    runs_autodrive.auto_drive_runs(limit=300)

    assert "limit" not in captured
    assert captured.get("planner_preview_limit", 0) == 0 or "refresh_dirty_limit" in captured


def test_recent_auto_attempt_counts_separates_completed_from_failures(monkeypatch):
    rows = [
        {
            "id": 1,
            "status": "completed",
            "queue_payload": json.dumps({
                "tool_id": "runs_auto_drive",
                "auto_drive_plan_key": "plan_a",
                "auto_drive_overall_percent": 40.0,
            }),
        },
        {
            "id": 2,
            "status": "completed",
            "queue_payload": json.dumps({
                "tool_id": "runs_auto_drive",
                "auto_drive_plan_key": "plan_a",
                "auto_drive_overall_percent": 55.0,
            }),
        },
    ]
    monkeypatch.setattr(runs_autodrive.db, "get_jobs", lambda **kwargs: rows)

    counts = runs_autodrive._recent_auto_attempt_counts(["plan_a"])

    # Completed runs are tracked separately and never count as failures; they only trip the
    # guard later if the folder made no progress past the highest recorded percent.
    assert counts["plan_a"]["failure_attempts"] == 0
    assert counts["plan_a"]["completed_attempts"] == 2
    assert counts["plan_a"]["last_completed_percent"] == 55.0


def _bird_folder_buckets(overall_percent):
    return lambda **_kwargs: {
        "items": [
            {
                "path": "/mnt/d/Photos/bird-folder",
                "bucket": "awaiting_bird_species",
                "next_phases": ["bird_species"],
                "plan_key": "bird_plan",
                "overall_percent": overall_percent,
            }
        ],
        "total": 1,
        "bucket_counts": {"awaiting_bird_species": 1},
        "phase_counts": {"bird_species": 1},
    }


def _two_completed_bird_jobs(recorded_percent):
    job_payload = json.dumps({
        "tool_id": "runs_auto_drive",
        "auto_drive_plan_key": runs_autodrive._plan_key(
            "/mnt/d/Photos/bird-folder",
            ["bird_species"],
        ),
        "auto_drive_overall_percent": recorded_percent,
    })
    return [
        {"id": 10, "status": "completed", "queue_payload": job_payload},
        {"id": 11, "status": "completed", "queue_payload": job_payload},
    ]


def test_auto_drive_allows_third_enqueue_after_progress(monkeypatch):
    """Multi-pass bird work: completed runs are forgiven when the folder advanced."""
    # Live percent (60) > highest recorded completed percent (40) => progress was made.
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets_for_autodrive",
        _bird_folder_buckets(60.0),
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive,
        "phases_with_work_from_repair_plan",
        lambda *_a, **_k: ["bird_species"],
    )
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs", lambda **_k: _two_completed_bird_jobs(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive, "_enqueue_auto_bucket", lambda *_a, **_k: (42, 1, None)
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 0
    assert len(result["scheduled"]) == 1


def test_loop_guard_trips_on_completed_without_progress(monkeypatch):
    """Two completed runs with no progress since the last pass => bounded, not re-queued forever."""
    # Live percent (40) == highest recorded completed percent (40) => no progress.
    monkeypatch.setattr(
        runs_autodrive,
        "build_folder_buckets_for_autodrive",
        _bird_folder_buckets(40.0),
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive,
        "phases_with_work_from_repair_plan",
        lambda *_a, **_k: ["bird_species"],
    )
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs", lambda **_k: _two_completed_bird_jobs(40.0)
    )
    # No genuinely un-attempted work -> the bypass does not apply, guard trips.
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_unattempted_phase_work", lambda *_a, **_k: False
    )
    monkeypatch.setattr(
        runs_autodrive, "_enqueue_auto_bucket", lambda *_a, **_k: (42, 1, None)
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 1
    assert len(result["scheduled"]) == 0


def test_loop_guard_bypassed_when_unattempted_work_exists(monkeypatch):
    """No-op completions must not block work that was never attempted (attempt_count == 0)."""
    monkeypatch.setattr(
        runs_autodrive, "build_folder_buckets_for_autodrive", _bird_folder_buckets(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive, "phases_with_work_from_repair_plan", lambda *_a, **_k: ["bird_species"]
    )
    # Two completed no-op runs, no progress -> would normally trip the guard...
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs", lambda **_k: _two_completed_bird_jobs(40.0)
    )
    # ...but the folder holds genuinely un-attempted work, so the guard is bypassed.
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_unattempted_phase_work", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        runs_autodrive, "_enqueue_auto_bucket", lambda *_a, **_k: (42, 1, None)
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 0
    assert len(result["scheduled"]) == 1


def test_loop_guard_not_bypassed_when_failures_present(monkeypatch):
    """A truly broken runner (failures) must still loop-block, even with un-attempted work."""
    monkeypatch.setattr(
        runs_autodrive, "build_folder_buckets_for_autodrive", _bird_folder_buckets(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive, "phases_with_work_from_repair_plan", lambda *_a, **_k: ["bird_species"]
    )
    plan_key = runs_autodrive._plan_key("/mnt/d/Photos/bird-folder", ["bird_species"])
    failed_payload = json.dumps({"tool_id": "runs_auto_drive", "auto_drive_plan_key": plan_key})
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs",
        lambda **_k: [
            {"id": 20, "status": "failed", "queue_payload": failed_payload},
            {"id": 21, "status": "failed", "queue_payload": failed_payload},
        ],
    )
    # Un-attempted work exists, but failures must still loop-block (bypass is failure-gated).
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_unattempted_phase_work", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        runs_autodrive, "_enqueue_auto_bucket", lambda *_a, **_k: (42, 1, None)
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 1
    assert len(result["scheduled"]) == 0


def test_loop_guard_classifies_failed_exhausted(monkeypatch):
    """A folder whose only remaining work is retry-exhausted failures is surfaced as
    ``failed_exhausted`` (naming the bad images), not opaque ``loop_detected``."""
    monkeypatch.setattr(
        runs_autodrive, "build_folder_buckets_for_autodrive", _bird_folder_buckets(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive, "phases_with_work_from_repair_plan", lambda *_a, **_k: ["bird_species"]
    )
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs", lambda **_k: _two_completed_bird_jobs(40.0)
    )
    # Nothing left to retry (no un-attempted work) ...
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_unattempted_phase_work", lambda *_a, **_k: False
    )
    # ... and the shortfall is images that exhausted their per-image retry budget.
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_exhausted_phase_work", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        runs_autodrive.db,
        "get_scope_exhausted_failed_images",
        lambda *_a, **_k: [
            {
                "image_id": 190235,
                "file_path": "/mnt/d/Photos/bird-folder/DSC_6280.NEF",
                "attempt_count": 2,
                "last_error": "RAW Conversion Failed",
            }
        ],
    )

    def _boom(*_a, **_k):
        raise AssertionError("exhausted folder must not be re-enqueued")

    monkeypatch.setattr(runs_autodrive, "_enqueue_auto_bucket", _boom)

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["scheduled"] == []
    assert result["loop_detected"] == 1
    skip = result["skipped"][0]
    assert skip["reason"] == "failed_exhausted"
    assert skip["failed_phase"] == "bird_species"
    assert skip["failed_images"][0]["image_id"] == 190235
    assert result["skip_reason_counts"].get("failed_exhausted") == 1


def test_loop_guard_failed_exhausted_can_be_disabled(monkeypatch):
    """With the kill switch off, an exhausted-failed folder falls back to ``loop_detected``
    and the exhausted-work probe is never consulted."""
    monkeypatch.setattr(
        runs_autodrive, "build_folder_buckets_for_autodrive", _bird_folder_buckets(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive, "phases_with_work_from_repair_plan", lambda *_a, **_k: ["bird_species"]
    )
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs", lambda **_k: _two_completed_bird_jobs(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_unattempted_phase_work", lambda *_a, **_k: False
    )
    monkeypatch.setattr(runs_autodrive, "_treat_exhausted_failed_as_terminal", lambda: False)

    def _boom(*_a, **_k):
        raise AssertionError("exhausted probe must be skipped when feature disabled")

    monkeypatch.setattr(runs_autodrive.db, "scope_has_exhausted_phase_work", _boom)

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 1
    assert result["skipped"][0]["reason"] == "loop_detected"


def test_exhausted_failed_min_attempts_from_config(monkeypatch):
    """``scoring.max_image_retries`` (total attempts) maps to attempt_count >= max-1."""
    def _cfg(key, default=None):
        return 4 if key == "scoring.max_image_retries" else default

    monkeypatch.setattr("modules.config.get_config_value", _cfg)
    assert runs_autodrive._exhausted_failed_min_attempts() == 3


def test_loop_guard_bypassed_after_interrupted_with_unattempted_work(monkeypatch):
    """An ``interrupted`` job (backend restart) must not permanently strand never-attempted work.

    Regression: a single involuntary interruption was counted as a hard failure, which
    closed the un-attempted-work bypass forever even though the folder had genuinely
    unscored images (see folders 2026-05-24/05-30).
    """
    monkeypatch.setattr(
        runs_autodrive, "build_folder_buckets_for_autodrive", _bird_folder_buckets(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    monkeypatch.setattr(
        runs_autodrive, "phases_with_work_from_repair_plan", lambda *_a, **_k: ["bird_species"]
    )
    plan_key = runs_autodrive._plan_key("/mnt/d/Photos/bird-folder", ["bird_species"])
    payload = json.dumps({
        "tool_id": "runs_auto_drive",
        "auto_drive_plan_key": plan_key,
        "auto_drive_overall_percent": 40.0,
    })
    # One interruption + two no-op completions => effective_attempts trips max_repeats,
    # but the only "failure" is an interruption, so the bypass should still apply.
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs",
        lambda **_k: [
            {"id": 30, "status": "interrupted", "queue_payload": payload},
            {"id": 31, "status": "completed", "queue_payload": payload},
            {"id": 32, "status": "completed", "queue_payload": payload},
        ],
    )
    monkeypatch.setattr(
        runs_autodrive.db, "scope_has_unattempted_phase_work", lambda *_a, **_k: True
    )
    monkeypatch.setattr(
        runs_autodrive, "_enqueue_auto_bucket", lambda *_a, **_k: (42, 1, None)
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 0
    assert len(result["scheduled"]) == 1


def test_loop_guard_bypass_checks_all_phase_values_not_just_first(monkeypatch):
    """Un-attempted work in a later phase must trigger the bypass when the first phase is a no-op.

    Regression: the bypass only probed ``phase_values[0]`` (e.g. ``metadata``, whose data is
    already present), so it missed real never-attempted ``scoring`` work further down the plan.
    """
    monkeypatch.setattr(
        runs_autodrive, "build_folder_buckets_for_autodrive", _bird_folder_buckets(40.0)
    )
    monkeypatch.setattr(
        runs_autodrive.utils,
        "resolve_scope_input_path",
        lambda _path: ("/mnt/d/Photos/bird-folder", ["/mnt/d/Photos/bird-folder"]),
    )
    # Plan has a no-op first phase (metadata) and real work later (scoring).
    monkeypatch.setattr(
        runs_autodrive,
        "phases_with_work_from_repair_plan",
        lambda *_a, **_k: ["metadata", "scoring"],
    )
    plan_key = runs_autodrive._plan_key(
        "/mnt/d/Photos/bird-folder", ["metadata", "scoring"]
    )
    payload = json.dumps({
        "tool_id": "runs_auto_drive",
        "auto_drive_plan_key": plan_key,
        "auto_drive_overall_percent": 40.0,
    })
    monkeypatch.setattr(
        runs_autodrive.db, "get_jobs",
        lambda **_k: [
            {"id": 40, "status": "completed", "queue_payload": payload},
            {"id": 41, "status": "completed", "queue_payload": payload},
        ],
    )
    # Only the non-first phase (scoring) has un-attempted work.
    monkeypatch.setattr(
        runs_autodrive.db,
        "scope_has_unattempted_phase_work",
        lambda _resolved, phase, *_a, **_k: phase == "scoring",
    )
    monkeypatch.setattr(
        runs_autodrive, "_enqueue_auto_bucket", lambda *_a, **_k: (42, 1, None)
    )

    result = runs_autodrive.auto_drive_runs(dry_run=False, max_repeats=2)

    assert result["loop_detected"] == 0
    assert len(result["scheduled"]) == 1


def test_retry_unattempted_on_loop_config(monkeypatch):
    monkeypatch.setattr(
        "modules.config.get_config_value",
        lambda key, default=None: False if key == "auto_drive.retry_unattempted_on_loop" else default,
    )
    assert runs_autodrive._retry_unattempted_on_loop() is False


def test_select_autodrive_candidates_reserves_bird_backlog_slots():
    items = []
    for i in range(10):
        items.append({
            "path": f"/photos/early/{i}",
            "path_key": f"/photos/early/{i}",
            "bucket": "awaiting_indexing",
            "next_phases": ["indexing"],
        })
    for i in range(200):
        items.append({
            "path": f"/photos/bird/{i}",
            "path_key": f"/photos/bird/{i}",
            "bucket": "awaiting_bird_species",
            "next_phases": ["bird_species"],
        })

    picked = runs_autodrive._select_autodrive_candidates(
        items,
        limit=50,
        bucket_counts={"awaiting_bird_species": 200, "awaiting_indexing": 10},
    )

    bird_picked = sum(1 for x in picked if x.get("bucket") == "awaiting_bird_species")
    assert bird_picked >= 15
    assert len(picked) == 50


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
    runs_autodrive.invalidate_autodrive_buckets_cache()
    yield
    runs_autodrive.stop_drive("test_teardown")
    runs_autodrive.invalidate_autodrive_buckets_cache()


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


def test_drive_survives_loop_guard_then_stalls_at_absolute_cap(monkeypatch):
    monkeypatch.setattr(
        runs_autodrive,
        "auto_drive_runs",
        lambda **k: _drive_result(
            scheduled=0,
            outstanding=100,
            candidates=47,
            loop_detected=39,
            skipped=[{"reason": "loop_detected"}] * 39 + [{"reason": "nothing_to_queue"}] * 6,
            bucket_counts={"awaiting_bird_species": 90, "awaiting_keywords": 10},
        ),
    )

    runs_autodrive.start_drive(limit=50)

    # Loop-blocked ticks must NOT trip the normal short stall (multi-pass work may resume)...
    for _ in range(runs_autodrive.DRIVE_MAX_NOPROGRESS_TICKS + 1):
        _force_next_tick()
        runs_autodrive.drive_tick()
    mid = runs_autodrive.get_drive_state()
    assert mid["enabled"] is True
    assert mid.get("stop_reason") is None

    # ...but the absolute cap guarantees the drive eventually stalls instead of spinning forever.
    for _ in range(runs_autodrive.DRIVE_MAX_LOOPBLOCKED_TICKS + 2):
        _force_next_tick()
        runs_autodrive.drive_tick()
    state = runs_autodrive.get_drive_state()
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

    assert result["items"][0]["path"] == _local_bucket_path(new_path)
    assert result["items"][0]["is_newly_imported"] is True
    assert result["items"][1]["path"] == _local_bucket_path(old_path)
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

    assert result["items"][0]["path"] == _local_bucket_path(newer_new)
    assert result["items"][1]["path"] == _local_bucket_path(older_new)


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

    assert result["items"][0]["path"] == _local_bucket_path(old_path)
    assert result["items"][0]["is_newly_imported"] is False
    assert result["items"][1]["path"] == _local_bucket_path(new_path)


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
    assert result["scheduled"][0]["folder_path"] == _local_bucket_path(new_path)


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
    assert result["items"][0]["path"] == _local_bucket_path(target)


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


# ---------------------------------------------------------------------------
# Productivity-aware candidate cooldown (lever #2)
# ---------------------------------------------------------------------------

def test_cooldown_records_and_blocks_within_window():
    runs_autodrive._clear_all_folder_cooldowns()
    now = 1000.0
    runs_autodrive._record_unproductive_cooldown("/p/a", percent=50.0, now=now, cooldown_sec=600.0)
    # Still cooled 5 min later at the same percent.
    assert runs_autodrive._is_folder_cooled("/p/a", current_percent=50.0, now=now + 300) is True
    # Expired after the window.
    assert runs_autodrive._is_folder_cooled("/p/a", current_percent=50.0, now=now + 601) is False


def test_cooldown_voided_when_folder_advances():
    runs_autodrive._clear_all_folder_cooldowns()
    now = 1000.0
    runs_autodrive._record_unproductive_cooldown("/p/b", percent=50.0, now=now, cooldown_sec=600.0)
    # Folder advanced since we cooled it -> eligible again even inside the window.
    assert runs_autodrive._is_folder_cooled("/p/b", current_percent=60.0, now=now + 10) is False


def test_cooldown_clear_helpers():
    runs_autodrive._clear_all_folder_cooldowns()
    runs_autodrive._record_unproductive_cooldown("/p/c", percent=0.0, now=1000.0, cooldown_sec=600.0)
    runs_autodrive._clear_folder_cooldown("/p/c")
    assert runs_autodrive._is_folder_cooled("/p/c", current_percent=0.0, now=1000.0) is False


def test_cooldown_empty_path_key_is_noop():
    runs_autodrive._clear_all_folder_cooldowns()
    runs_autodrive._record_unproductive_cooldown("", percent=0.0, now=1000.0, cooldown_sec=600.0)
    assert runs_autodrive._is_folder_cooled("", current_percent=0.0, now=1000.0) is False


def test_cooldown_disabled_via_config(monkeypatch):
    monkeypatch.setattr(
        "modules.config.get_config_value",
        lambda key, default=None: False if key == "auto_drive.unproductive_cooldown_enabled" else default,
    )
    assert runs_autodrive._unproductive_cooldown_sec() == 0.0


def test_cooldown_sec_reads_config_value(monkeypatch):
    def _cfg(key, default=None):
        if key == "auto_drive.unproductive_cooldown_enabled":
            return True
        if key == "auto_drive.unproductive_cooldown_sec":
            return 120
        return default

    monkeypatch.setattr("modules.config.get_config_value", _cfg)
    assert runs_autodrive._unproductive_cooldown_sec() == 120.0


def test_first_post_audit_stage_with_work_prefers_earliest_phase():
    stage_queues = {
        "metadata": {"total": 0},
        "scoring": {"total": 44},
        "culling": {"total": 44},
    }
    first = runs_autodrive._first_post_audit_stage_with_work(stage_queues)
    assert first == ("scoring", 44)


def test_maybe_schedule_post_audit_followup_metadata_gap(monkeypatch):
    captured = []

    def _enqueue(bucket, **kwargs):
        captured.append((bucket, kwargs))
        return 88, 1, None

    monkeypatch.setattr(runs_autodrive, "_enqueue_auto_bucket", _enqueue)
    follow_id = runs_autodrive.maybe_schedule_post_audit_followup(
        1,
        {
            "tool_id": "runs_auto_drive",
            "scope_paths": ["/mnt/d/foo"],
            "target_phases": ["metadata", "scoring", "culling"],
        },
        {
            "status": "issues_remaining",
            "stage_queues": {"metadata": {"total": 5}},
        },
    )
    assert follow_id == 88
    assert captured[0][0]["bucket"] == "awaiting_metadata"
    assert captured[0][1]["phase_values"] == ["metadata", "scoring", "culling"]


def test_maybe_schedule_post_audit_followup_scoring_gap_when_metadata_clean(monkeypatch):
    captured = []

    def _enqueue(bucket, **kwargs):
        captured.append((bucket, kwargs))
        return 99, 1, None

    monkeypatch.setattr(runs_autodrive, "_enqueue_auto_bucket", _enqueue)
    follow_id = runs_autodrive.maybe_schedule_post_audit_followup(
        4281,
        {
            "tool_id": "runs_auto_drive",
            "scope_paths": ["/mnt/d/Photos/Z8/180-600mm/2026/2026-06-24"],
            "target_phases": ["metadata", "scoring", "culling", "keywords", "bird_species"],
        },
        {
            "status": "issues_remaining",
            "stage_queues": {
                "metadata": {"total": 0},
                "scoring": {"total": 292},
                "culling": {"total": 292},
            },
        },
    )
    assert follow_id == 99
    assert captured[0][0]["bucket"] == "awaiting_scoring"
    assert captured[0][1]["phase_values"] == [
        "scoring",
        "culling",
        "keywords",
        "bird_species",
    ]


def test_maybe_schedule_post_audit_followup_skips_clean_audit():
    assert runs_autodrive.maybe_schedule_post_audit_followup(
        1,
        {"tool_id": "runs_auto_drive", "scope_paths": ["/mnt/d/foo"]},
        {"status": "clean", "stage_queues": {}},
    ) is None
