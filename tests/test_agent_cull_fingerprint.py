"""Tests for agent cull stale-state fingerprint checks."""

import json
from unittest.mock import patch

from modules.agent_cull.fingerprint import (
    check_group_staleness,
    compute_state_fingerprint,
    load_current_image_states,
    state_snapshot_from_packet,
)
from modules.agent_cull.actions import apply_candidates_action, approve_action


class _FakeConnector:
    """Mirrors the real connector surface: `query` exists, `query_all` does not.

    Guards against regressing to `connector.query_all(...)`, which raised
    `'PostgresConnector' object has no attribute 'query_all'` (HTTP 500) on approve/apply.
    """

    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def query(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        return self._rows


def _sample_packet(*, pick_100: int = -1, pick_101: int = 1) -> dict:
    return {
        "images": [
            {"id": 100, "pick_status": pick_100, "cull_decision": "reject"},
            {"id": 101, "pick_status": pick_101, "cull_decision": "pick"},
        ]
    }


def test_fingerprint_stable_for_same_states():
    states = {100: (-1, "reject"), 101: (1, "pick")}
    assert compute_state_fingerprint(states) == compute_state_fingerprint(dict(states))


def test_fingerprint_changes_when_pick_status_changes():
    before = {100: (-1, "reject"), 101: (1, "pick")}
    after = {100: (0, "reject"), 101: (1, "pick")}
    assert compute_state_fingerprint(before) != compute_state_fingerprint(after)


def test_state_snapshot_from_packet():
    snap = state_snapshot_from_packet(_sample_packet())
    assert snap == {100: (-1, "reject"), 101: (1, "pick")}


def test_load_current_image_states_uses_connector_query():
    """Regression: must call connector.query (not the non-existent query_all)."""
    fake = _FakeConnector([
        {"id": 100, "pick_status": -1, "cull_decision": "reject"},
        {"id": 101, "pick_status": 1, "cull_decision": "pick"},
    ])
    with patch("modules.agent_cull.fingerprint.db.get_connector", return_value=fake):
        states = load_current_image_states([100, 101])
    assert states == {100: (-1, "reject"), 101: (1, "pick")}
    assert "WHERE id IN" in fake.last_sql
    assert fake.last_params == (100, 101)


def test_load_current_image_states_empty_short_circuits():
    assert load_current_image_states([]) == {}


@patch("modules.agent_cull.fingerprint.load_current_image_states")
@patch("modules.agent_cull.fingerprint.db.get_connector")
def test_check_group_staleness_false_when_states_match(mock_get_connector, mock_load_current):
    mock_get_connector.return_value.query_one.return_value = {
        "request_json": json.dumps(_sample_packet()),
    }
    mock_load_current.return_value = {100: (-1, "reject"), 101: (1, "pick")}
    assert check_group_staleness(1) is False


@patch("modules.agent_cull.fingerprint.load_current_image_states")
@patch("modules.agent_cull.fingerprint.db.get_connector")
def test_check_group_staleness_true_when_pick_status_changed(mock_get_connector, mock_load_current):
    mock_get_connector.return_value.query_one.return_value = {
        "request_json": json.dumps(_sample_packet()),
    }
    mock_load_current.return_value = {100: (1, "reject"), 101: (1, "pick")}
    assert check_group_staleness(1) is True


@patch("modules.agent_cull.actions.apply_agent_remove_candidates")
@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_apply_candidates_blocked_when_stale(mock_cfg, mock_group, mock_stale, mock_apply):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 1, "dry_run": False}
    mock_stale.return_value = True
    result = apply_candidates_action(1)
    assert result == {"ok": False, "error": "stale_group_state"}
    mock_apply.assert_not_called()


@patch("modules.agent_cull.actions.apply_agent_remove_candidates")
@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_apply_candidates_succeeds_when_fresh(mock_cfg, mock_group, mock_stale, mock_apply):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 1, "dry_run": False}
    mock_stale.return_value = False
    mock_apply.return_value = {"ok": True, "updated": 1, "group_id": 1}
    result = apply_candidates_action(1)
    assert result["ok"] is True
    mock_apply.assert_called_once()


@patch("modules.agent_cull.actions.approve_recommendations")
@patch("modules.agent_cull.actions.check_group_staleness")
@patch("modules.agent_cull.actions.get_group_row")
@patch("modules.agent_cull.actions.load_agent_cull_config")
def test_approve_blocked_when_stale(mock_cfg, mock_group, mock_stale, mock_approve):
    mock_cfg.return_value.enabled = True
    mock_group.return_value = {"id": 1, "dry_run": False}
    mock_stale.return_value = True
    result = approve_action(1)
    assert result == {"ok": False, "error": "stale_group_state"}
    mock_approve.assert_not_called()
