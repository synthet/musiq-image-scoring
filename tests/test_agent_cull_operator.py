"""Tests for operator approve/reject (mocked DB)."""

from unittest.mock import MagicMock, patch

from modules.agent_cull.operator import approve_recommendations, reject_recommendations


def test_approve_skips_non_remove():
    recs = [
        {"id": 1, "final_decision": "keep", "candidate_status": "proposed"},
        {"id": 2, "final_decision": "remove", "candidate_status": "proposed"},
    ]
    connector = MagicMock()
    with patch("modules.agent_cull.operator.list_recommendations_for_group", return_value=recs), patch(
        "modules.agent_cull.operator.db.get_connector", return_value=connector
    ), patch("modules.agent_cull.operator.update_review_group"):
        result = approve_recommendations(9)
    assert result["updated"] == 1
    assert connector.execute.call_count == 1


def test_reject_updates_matching():
    recs = [
        {"id": 3, "final_decision": "remove", "candidate_status": "agent_remove_candidate"},
    ]
    connector = MagicMock()
    with patch("modules.agent_cull.operator.list_recommendations_for_group", return_value=recs), patch(
        "modules.agent_cull.operator.db.get_connector", return_value=connector
    ):
        result = reject_recommendations(9, recommendation_ids=[3])
    assert result["updated"] == 1


def test_approve_never_calls_delete():
    import modules.agent_cull.operator as op

    source = open(op.__file__, encoding="utf-8").read()
    assert "os.remove" not in source
    assert "unlink" not in source
