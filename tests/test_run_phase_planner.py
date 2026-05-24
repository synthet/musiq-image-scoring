"""Tests for run_phase_planner reason bucketing."""

from unittest.mock import patch

from modules.run_phase_planner import _reason_bucket, plan_scope, to_legacy_repair_plan


def test_reason_bucket_mapping():
    assert _reason_bucket("missing_phase_status") == "missing_row"
    assert _reason_bucket("status_not_started") == "not_started"
    assert _reason_bucket("status_failed") == "failed"
    assert _reason_bucket("executor_version_changed") == "stale_executor"
    assert _reason_bucket("already_running") == "stale_running"
    assert _reason_bucket("missing_scoring_data") == "missing_data"


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2])
@patch("modules.run_phase_planner._needs_work_for_phase")
def test_plan_scope_dry_run_shape(mock_needs, _mock_scope):
    mock_needs.side_effect = [
        (True, "missing_phase_status"),
        (False, "already_done_current_executor"),
        (True, "executor_version_changed"),
    ]
    plan = plan_scope(["/tmp"], ["indexing"], dry_run=True)
    legacy = to_legacy_repair_plan(plan)
    assert legacy["dry_run"] is True
    assert "stage_queues" in legacy
    assert "issue_counts_by_reason" in plan
    assert plan["stage_queues"]["indexing"] == [1]
