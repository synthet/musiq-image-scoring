"""Tests for queue_payload.reason (run/job manifest)."""

from __future__ import annotations

from modules.run_manifest import (
    REASON_SOURCE_AUTO_DRIVE,
    REASON_SOURCE_MANUAL_SUBMIT,
    attach_run_reason,
    build_auto_drive_summary,
    build_manual_submit_summary,
    build_retry_summary,
    summarize_planner_reasons,
)


def test_summarize_planner_reasons_counts_and_narrowing():
    repair = {
        "issue_counts_by_reason": {
            "not_started": 5,
            "missing_data": 2,
            "stale_executor": 99,
        }
    }
    fragment, counts = summarize_planner_reasons(
        repair,
        enqueued_phases=["scoring", "keywords"],
        requested_phases=["indexing", "metadata", "scoring", "keywords"],
    )
    assert counts == {"not_started": 5, "missing_data": 2, "stale_executor": 99}
    assert "JIT narrowed" in fragment
    assert "not_started=5" in fragment


def test_build_manual_submit_summary():
    repair = {"issue_counts_by_reason": {"failed": 1}}
    summary, criteria = build_manual_submit_summary(
        scope_paths=["D:/Photos/2026/event"],
        enqueued_phases=["scoring"],
        requested_phases=["scoring", "keywords"],
        repair_plan=repair,
    )
    assert "Manual run queued" in summary
    assert "event" in summary
    assert criteria["enqueued_phases"] == ["scoring"]
    assert criteria["requested_phases"] == ["scoring", "keywords"]
    assert criteria["planner_reason_counts"] == {"failed": 1}


def test_build_auto_drive_summary_includes_bucket():
    repair = {"issue_counts_by_reason": {"not_started": 3}}
    summary, criteria = build_auto_drive_summary(
        scope_paths=["D:/Photos/leaf"],
        enqueued_phases=["scoring"],
        requested_phases=["scoring", "keywords"],
        auto_drive_bucket="awaiting_scoring",
        auto_drive_overall_percent=12,
        auto_drive_plan_key="abc123",
        repair_plan=repair,
        run_mode="process_stale_or_missing",
    )
    assert "Auto-drive queued" in summary
    assert "awaiting_scoring" in summary
    assert criteria["auto_drive_bucket"] == "awaiting_scoring"
    assert criteria["include_stale_executor"] is False
    assert criteria["run_mode"] == "process_stale_or_missing"


def test_attach_run_reason_overwrites():
    payload = {"reason": {"summary": "old", "source": "legacy_api"}}
    out = attach_run_reason(
        payload,
        source=REASON_SOURCE_MANUAL_SUBMIT,
        summary="New summary.",
        trigger="api",
        tool_id="run_submit",
    )
    assert out["reason"]["source"] == REASON_SOURCE_MANUAL_SUBMIT
    assert out["reason"]["summary"] == "New summary."
    assert out["reason"]["trigger"] == "api"


def test_build_retry_summary_force_vs_retry():
    force = build_retry_summary(
        source="force_run",
        original_run_id=42,
        job_type="scoring",
        input_path="D:/Photos/x",
    )
    retry = build_retry_summary(
        source="retry",
        original_run_id=42,
        job_type="scoring",
        input_path="D:/Photos/x",
    )
    assert "Force re-queue" in force
    assert "Retry of run #42" in retry


def test_auto_drive_reason_shape_via_attach():
    summary, criteria = build_auto_drive_summary(
        scope_paths=["/mnt/d/Photos/f"],
        enqueued_phases=["keywords"],
        requested_phases=["keywords", "bird_species"],
        auto_drive_bucket="awaiting_keywords",
        repair_plan={"issue_counts_by_reason": {"missing_data": 4}},
        run_mode="process_stale_or_missing",
    )
    payload = attach_run_reason(
        {"tool_id": "runs_auto_drive", "trigger": "api"},
        source=REASON_SOURCE_AUTO_DRIVE,
        summary=summary,
        criteria=criteria,
        trigger="api",
        tool_id="runs_auto_drive",
    )
    reason = payload["reason"]
    assert reason["source"] == REASON_SOURCE_AUTO_DRIVE
    assert reason["criteria"]["planner_reason_counts"]["missing_data"] == 4
