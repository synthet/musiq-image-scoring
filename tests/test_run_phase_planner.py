"""Tests for run_phase_planner reason bucketing."""

from unittest.mock import patch

from modules.phases import PhaseCode, PhaseExecutor, PhaseRegistry, SCORING_EXECUTOR_VERSION
from modules import phases_policy
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


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2])
@patch("modules.run_phase_planner._needs_work_for_phase")
def test_plan_scope_can_ignore_stale_executor(mock_needs, _mock_scope):
    mock_needs.side_effect = [
        (True, "executor_version_changed"),
        (True, "missing_scoring_data"),
    ]

    plan = plan_scope(
        ["/tmp"],
        ["scoring"],
        dry_run=True,
        include_stale_executor=False,
    )

    assert plan["stage_queues"]["scoring"] == [2]
    assert plan["issue_counts_by_reason"] == {"missing_data": 1}
    assert plan["ignored_counts_by_reason"] == {"stale_executor": 1}


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2])
def test_plan_scope_empty_queues_legacy_null_metadata_and_canonical_scoring(_mock_scope, monkeypatch):
    """Legacy done rows with NULL executor_version must not inflate stage_queues."""
    PhaseRegistry._executors.clear()
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.METADATA, executor_version="1.0.0"))
    PhaseRegistry.register(
        PhaseExecutor(code=PhaseCode.SCORING, executor_version=SCORING_EXECUTOR_VERSION),
    )

    def _statuses(image_id):
        return {
            "metadata": {"status": "done", "executor_version": None},
            "scoring": {"status": "done", "executor_version": SCORING_EXECUTOR_VERSION},
        }

    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", _statuses)
    monkeypatch.setattr(phases_policy.db, "is_image_metadata_complete", lambda _i: True)
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda _i: True)

    plan = plan_scope(["/tmp/folder"], ["metadata", "scoring"], dry_run=True)

    PhaseRegistry._executors.clear()
    assert plan["stage_queues"]["metadata"] == []
    assert plan["stage_queues"]["scoring"] == []
