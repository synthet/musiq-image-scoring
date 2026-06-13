"""Tests for recommendation rollback."""

from unittest.mock import MagicMock, patch

from modules.agent_cull.rollback import rollback_recommendation


def test_rollback_restores_prior_status():
    connector = MagicMock()
    connector.query_one.return_value = {
        "id": 5,
        "review_group_id": 9,
        "prior_candidate_status": "proposed",
        "candidate_status": "operator_approved",
    }
    with patch("modules.agent_cull.rollback.db.get_connector", return_value=connector), patch(
        "modules.agent_cull.rollback.update_review_group"
    ):
        ok = rollback_recommendation(5, actor="operator")
    assert ok is True
    args = connector.execute.call_args[0]
    assert args[1][0] == "proposed"


def test_rollback_missing_returns_false():
    connector = MagicMock()
    connector.query_one.return_value = None
    with patch("modules.agent_cull.rollback.db.get_connector", return_value=connector):
        assert rollback_recommendation(999) is False
