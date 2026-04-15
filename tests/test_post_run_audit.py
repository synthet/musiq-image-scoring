"""Post-run data quality audit helpers (no DB required)."""

from unittest.mock import patch

from modules import db


def test_should_run_respects_explicit_false_with_validate_and_repair():
    assert (
        db.should_run_post_completion_audit(
            {"run_mode": "validate_and_repair", "post_run_audit": False}
        )
        is False
    )


def test_should_run_validate_and_repair():
    assert db.should_run_post_completion_audit({"run_mode": "validate_and_repair"}) is True


def test_should_run_global_config(monkeypatch):
    monkeypatch.setattr(
        "modules.config.get_config_value",
        lambda k, default=None: True if k == "processing.post_run_data_quality_audit" else default,
    )
    assert db.should_run_post_completion_audit({"run_mode": "process_unprocessed_or_empty"}) is True


def test_cap_id_list_truncates():
    sample, truncated = db._cap_id_list(list(range(5)), cap=3)
    assert sample == [0, 1, 2] and truncated is True


def test_cap_id_list_dedupes_and_sorts():
    sample, truncated = db._cap_id_list([3, 1, 2, 1], cap=10)
    assert sample == [1, 2, 3] and truncated is False


def test_parse_queue_payload_dict_nested_string():
    raw = '{"a": 1}'
    assert db.parse_queue_payload_dict(raw) == {"a": 1}


@patch.object(db, "_maybe_fail_job_on_post_audit_issues")
@patch.object(db, "_append_job_log_line")
@patch.object(db, "build_validation_repair_plan")
@patch.object(db, "update_job_payload")
@patch.object(db, "get_connector")
def test_run_post_completion_audit_merges_payload(
    mock_conn, mock_update, mock_plan, _mock_log, _mock_fail
):
    mock_conn.return_value.query_one.return_value = {
        "id": 42,
        "queue_payload": '{"scope_paths":["/tmp"],"run_mode":"validate_and_repair"}',
        "status": "completed",
    }
    mock_plan.return_value = {
        "issue_counts": {"scoring_incomplete": 0},
        "stage_queues": {},
        "dry_run": True,
    }

    out = db.run_post_completion_data_quality_audit(42)
    assert out is not None
    assert out.get("status") == "clean"
    mock_update.assert_called_once()
    merged = __import__("json").loads(mock_update.call_args[0][1])
    assert "post_run_audit" in merged
    assert merged["post_run_audit"]["status"] == "clean"


@patch.object(db, "get_job", return_value=None)
def test_get_run_diagnostics_job_not_found(_mock_get):
    out = db.get_run_diagnostics(99999)
    assert out.get("error") == "job_not_found"
