"""Post-run data quality audit helpers (no DB required)."""

from unittest.mock import patch

from modules import db
from modules.run_modes import CANONICAL_RUN_MODE


def test_should_run_respects_explicit_false():
    assert (
        db.should_run_post_completion_audit(
            {"run_mode": CANONICAL_RUN_MODE, "post_run_audit": False}
        )
        is False
    )


def test_should_run_stale_missing_mode():
    assert db.should_run_post_completion_audit({"run_mode": CANONICAL_RUN_MODE}) is True


def test_should_run_global_config(monkeypatch):
    monkeypatch.setattr(
        "modules.config.get_config_value",
        lambda k, default=None: True if k == "processing.post_run_data_quality_audit" else default,
    )
    assert db.should_run_post_completion_audit({"run_mode": "legacy_ignored"}) is True


def test_cap_id_list_truncates():
    sample, truncated = db._cap_id_list(list(range(5)), cap=3)
    assert sample == [0, 1, 2] and truncated is True


@patch("modules.runs_autodrive.maybe_schedule_post_audit_followup")
@patch.object(db, "_maybe_fail_job_on_post_audit_issues")
@patch.object(db, "_append_job_log_line")
@patch.object(db, "build_validation_repair_plan")
@patch.object(db, "update_job_payload")
@patch.object(db, "get_connector")
def test_run_post_completion_audit_merges_payload(
    mock_conn, mock_update, mock_plan, _mock_log, _mock_fail, _mock_followup
):
    mock_conn.return_value.query_one.return_value = {
        "id": 42,
        "queue_payload": f'{{"scope_paths":["/tmp"],"run_mode":"{CANONICAL_RUN_MODE}"}}',
        "status": "completed",
    }
    mock_plan.return_value = {
        "issue_counts": {"scoring_needs_work": 0},
        "stage_queues": {},
        "dry_run": True,
    }

    out = db.run_post_completion_data_quality_audit(42)
    assert out is not None
    assert out.get("status") == "clean"
    mock_update.assert_called_once()


@patch("modules.runs_autodrive.maybe_schedule_post_audit_followup")
@patch.object(db, "_maybe_fail_job_on_post_audit_issues")
@patch.object(db, "_append_job_log_line")
@patch.object(db, "build_validation_repair_plan")
@patch.object(db, "update_job_payload")
@patch.object(db, "get_connector")
def test_run_post_completion_audit_scopes_badge_to_executed_phase(
    mock_conn, mock_update, mock_plan, _mock_log, _mock_fail, _mock_followup
):
    """A single-phase indexing run must not be flagged for downstream culling work."""
    mock_conn.return_value.query_one.return_value = {
        "id": 4555,
        "queue_payload": f'{{"scope_paths":["/tmp"],"run_mode":"{CANONICAL_RUN_MODE}"}}',
        "status": "completed",
        "job_type": "indexing",
    }
    mock_plan.return_value = {
        "issue_counts": {"culling_not_started": 9},
        "stage_queues": {"culling": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
        "dry_run": True,
    }

    out = db.run_post_completion_data_quality_audit(4555)
    assert out is not None
    # Badge clean (indexing executed cleanly) ...
    assert out.get("status") == "clean"
    assert out.get("severity") == "info"
    assert out.get("executed_phases") == ["indexing"]
    # ... but full pipeline still reports downstream work for chaining/diagnostics.
    assert out.get("pipeline_status") == "issues_remaining"
    assert "culling" in out.get("stage_queues", {})


@patch("modules.runs_autodrive.maybe_schedule_post_audit_followup")
@patch.object(db, "_maybe_fail_job_on_post_audit_issues")
@patch.object(db, "_append_job_log_line")
@patch.object(db, "build_validation_repair_plan")
@patch.object(db, "update_job_payload")
@patch.object(db, "get_connector")
def test_run_post_completion_audit_flags_badge_on_executed_phase_gap(
    mock_conn, mock_update, mock_plan, _mock_log, _mock_fail, _mock_followup
):
    """When the executed phase itself left gaps, the badge fires."""
    mock_conn.return_value.query_one.return_value = {
        "id": 4556,
        "queue_payload": f'{{"scope_paths":["/tmp"],"run_mode":"{CANONICAL_RUN_MODE}"}}',
        "status": "completed",
        "job_type": "indexing",
    }
    mock_plan.return_value = {
        "issue_counts": {"indexing_missing_data": 2},
        "stage_queues": {"indexing": [1, 2]},
        "dry_run": True,
    }

    out = db.run_post_completion_data_quality_audit(4556)
    assert out is not None
    assert out.get("status") == "issues_remaining"
    assert out.get("pipeline_status") == "issues_remaining"
    assert out.get("executed_phases") == ["indexing"]


@patch("modules.runs_autodrive.maybe_schedule_post_audit_followup")
@patch.object(db, "_maybe_fail_job_on_post_audit_issues")
@patch.object(db, "_append_job_log_line")
@patch.object(db, "build_validation_repair_plan")
@patch.object(db, "update_job_payload")
@patch.object(db, "get_connector")
def test_run_post_completion_audit_multiphase_uses_full_status(
    mock_conn, mock_update, mock_plan, _mock_log, _mock_fail, _mock_followup
):
    """A multi-phase/unknown job_type falls back to whole-pipeline badge status."""
    mock_conn.return_value.query_one.return_value = {
        "id": 4557,
        "queue_payload": f'{{"scope_paths":["/tmp"],"run_mode":"{CANONICAL_RUN_MODE}"}}',
        "status": "completed",
        "job_type": "pipeline",
    }
    mock_plan.return_value = {
        "issue_counts": {"culling_not_started": 3},
        "stage_queues": {"culling": [1, 2, 3]},
        "dry_run": True,
    }

    out = db.run_post_completion_data_quality_audit(4557)
    assert out is not None
    assert out.get("status") == "issues_remaining"
    assert out.get("pipeline_status") == "issues_remaining"
    assert out.get("executed_phases") == []
