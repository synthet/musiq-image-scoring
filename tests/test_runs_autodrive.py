from __future__ import annotations

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
        lambda: {folder: summary},
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
        lambda: {folder: summary},
    )
    monkeypatch.setattr(runs_autodrive, "_active_job_path_keys", lambda: set())

    result = runs_autodrive.build_folder_buckets(limit=10, target_phases=["scoring"])

    assert result["items"][0]["bucket"] == "blocked"
    assert result["items"][0]["blocked_by"] == {"scoring": ["metadata"]}


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
