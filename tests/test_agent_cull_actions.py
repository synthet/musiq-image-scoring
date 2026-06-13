"""Tests for agent cull action guards."""

from unittest.mock import patch

from modules.agent_cull.actions import (
    apply_candidates_action,
    approve_action,
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
