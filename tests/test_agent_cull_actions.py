"""Tests for agent cull action guards."""

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from modules.agent_cull.actions import (
    apply_candidates_action,
    approve_action,
    delete_approved_action,
    reject_action,
    rollback_action,
)


@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_apply_blocked_when_feature_disabled(mock_cfg):
    mock_cfg.return_value.enabled = False
    result = apply_candidates_action(1)
    assert result == {"ok": False, "error": "agent_review_disabled"}


@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_approve_blocked_when_feature_disabled(mock_cfg, mock_group):
    mock_cfg.return_value.enabled = False
    result = approve_action(1)
    assert result == {"ok": False, "error": "agent_review_disabled"}
    mock_group.assert_not_called()


@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_reject_blocked_when_feature_disabled(mock_cfg, mock_group):
    mock_cfg.return_value.enabled = False
    result = reject_action(1)
    assert result == {"ok": False, "error": "agent_review_disabled"}
    mock_group.assert_not_called()


@patch("modules.agent_cull.actions.rollback_recommendation")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_rollback_blocked_when_feature_disabled(mock_cfg, mock_rollback):
    mock_cfg.return_value.enabled = False
    result = rollback_action(5)
    assert result == {"ok": False, "error": "agent_review_disabled"}
    mock_rollback.assert_not_called()


@patch("modules.agent_cull.actions.apply_agent_remove_candidates")
@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_apply_passes_recommendation_ids(mock_cfg, mock_group, mock_stale, mock_apply):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 1, "dry_run": False}
    mock_stale.return_value = False
    mock_apply.return_value = {"ok": True, "updated": 1, "group_id": 1}
    apply_candidates_action(1, recommendation_ids=[7, 8])
    mock_apply.assert_called_once_with(1, applied_by="operator", recommendation_ids=[7, 8])


# ── delete_approved_action (permanent file + DB record deletion) ───────────────

@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_delete_approved_blocked_when_disabled(mock_cfg, mock_group):
    mock_cfg.return_value.enabled = False
    result = delete_approved_action(9)
    assert result == {"ok": False, "error": "agent_review_disabled"}
    mock_group.assert_not_called()


@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_delete_approved_blocked_on_dry_run(mock_cfg, mock_group, mock_stale):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 9, "dry_run": True}
    result = delete_approved_action(9)
    assert result == {"ok": False, "error": "dry_run_group"}
    mock_stale.assert_not_called()


@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_delete_approved_blocked_when_stale(mock_cfg, mock_group, mock_stale):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 9, "dry_run": False}
    mock_stale.return_value = True
    result = delete_approved_action(9)
    assert result == {"ok": False, "error": "stale_group_state"}


@patch("modules.agent_cull.actions.list_recommendations_for_group")
@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_delete_approved_noop_when_none_approved(mock_cfg, mock_group, mock_stale, mock_list):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 9, "dry_run": False}
    mock_stale.return_value = False
    # A remove rec that's only approved-pending (operator hasn't approved) must not be deleted.
    mock_list.return_value = [
        {"id": 1, "image_id": 100, "final_decision": "remove", "candidate_status": "agent_remove_candidate"},
    ]
    result = delete_approved_action(9)
    assert result["ok"] is True
    assert result["updated"] == 0
    assert result["error"] == "no_approved_candidates"


@patch("modules.agent_cull.actions.os")
@patch("modules.agent_cull.actions.audit")
@patch("modules.agent_cull.actions.db")
@patch("modules.agent_cull.actions.list_recommendations_for_group")
@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_delete_approved_deletes_file_and_record(
    mock_cfg, mock_group, mock_stale, mock_list, mock_db, mock_audit, mock_os
):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 9, "dry_run": False}
    mock_stale.return_value = False
    mock_list.return_value = [
        {"id": 1, "image_id": 100, "final_decision": "remove", "candidate_status": "operator_approved"},
        # Not approved → must be skipped.
        {"id": 2, "image_id": 101, "final_decision": "remove", "candidate_status": "proposed"},
    ]
    mock_audit.audit_context.return_value = nullcontext()
    conn = MagicMock()
    conn.query_one.return_value = {
        "file_path": "/mnt/d/Photos/DSC_0100.NEF",
        "thumbnail_path": "/app/thumbnails/aa/0100.jpg",
        "thumbnail_path_win": None,
    }
    mock_db.get_connector.return_value = conn
    mock_db.delete_image.return_value = (True, "deleted")
    mock_os.path.exists.return_value = True

    result = delete_approved_action(9)

    assert result["ok"] is True
    assert result["updated"] == 1
    assert result["deleted"] == [{"image_id": 100, "file_path": "/mnt/d/Photos/DSC_0100.NEF"}]
    # DB record removed via the shared helper (with related rows), for the approved image only.
    mock_db.delete_image.assert_called_once_with("/mnt/d/Photos/DSC_0100.NEF", delete_related=True)
    # Source file + thumbnail unlinked from disk.
    removed = {c.args[0] for c in mock_os.remove.call_args_list}
    assert "/mnt/d/Photos/DSC_0100.NEF" in removed
    assert "/app/thumbnails/aa/0100.jpg" in removed
    # The approved recommendation is marked terminal (status passed as a bound param);
    # the un-approved one is untouched (only one UPDATE).
    assert conn.execute.call_count == 1
    mark_sql, mark_params = conn.execute.call_args.args
    assert "agent_cull_recommendations" in mark_sql
    assert mark_params[0] == "operator_deleted"
    assert mark_params[-1] == 1  # recommendation id
