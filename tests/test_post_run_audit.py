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
