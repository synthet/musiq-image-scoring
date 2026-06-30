"""Tests for agent cull apply paths and guards."""

from unittest.mock import MagicMock, patch

from modules.agent_cull.apply import (
    PICK_QUALITY_ADVISORY_STATUS,
    _persist_picked_advisories,
    apply_agent_remove_candidates,
    candidate_status_for_decision,
)


def test_dry_run_proposed_only():
    assert candidate_status_for_decision("remove", dry_run=True) == "proposed"
    assert candidate_status_for_decision("remove", dry_run=False) == "agent_remove_candidate"


def test_keep_and_uncertain_no_candidate():
    assert candidate_status_for_decision("keep", dry_run=False) == "none"
    assert candidate_status_for_decision("uncertain", dry_run=True) == "none"


def test_no_delete_helpers_in_module():
    import modules.agent_cull.apply as apply_mod
    import modules.agent_cull.service as service_mod

    forbidden = ("os.remove", "os.unlink", "shutil.rmtree", "delete_file", "move_to_trash")
    source = "\n".join(
        open(apply_mod.__file__, encoding="utf-8").read()
        + open(service_mod.__file__, encoding="utf-8").read()
    )
    for token in forbidden:
        assert token not in source


@patch("modules.agent_cull.apply.update_review_group")
@patch("modules.agent_cull.apply.list_recommendations_for_group")
@patch("modules.agent_cull.apply.db.get_connector")
def test_apply_blocks_dry_run_group(mock_get_connector, mock_list_recs, _mock_update):
    mock_get_connector.return_value.query_one.return_value = {"id": 1, "dry_run": True}
    result = apply_agent_remove_candidates(1)
    assert result["ok"] is False
    assert result["error"] == "dry_run_group"
    mock_list_recs.assert_not_called()


@patch("modules.agent_cull.apply.audit.audit_context")
@patch("modules.agent_cull.apply.update_review_group")
@patch("modules.agent_cull.apply.list_recommendations_for_group")
@patch("modules.agent_cull.apply.db.get_connector")
def test_apply_respects_recommendation_ids(
    mock_get_connector,
    mock_list_recs,
    mock_update_group,
    mock_audit_ctx,
):
    mock_audit_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_audit_ctx.return_value.__exit__ = MagicMock(return_value=False)
    connector = MagicMock()
    mock_get_connector.return_value = connector
    connector.query_one.return_value = {"id": 1, "dry_run": False}
    mock_list_recs.return_value = [
        {"id": 10, "final_decision": "remove", "candidate_status": "proposed"},
        {"id": 11, "final_decision": "remove", "candidate_status": "proposed"},
        {"id": 12, "final_decision": "keep", "candidate_status": "none"},
    ]
    result = apply_agent_remove_candidates(1, recommendation_ids=[11])
    assert result["ok"] is True
    assert result["updated"] == 1
    connector.execute.assert_called_once()
    args = connector.execute.call_args[0]
    assert args[1][1] == 11


@patch("modules.agent_cull.apply.insert_recommendation")
def test_persist_picked_advisories_inserts_advisory_rows(mock_insert):
    mock_insert.return_value = 1
    validated = {
        "picked_image_advisories": [
            {
                "image_id": 195193,
                "filename": "DSC_8825.NEF",
                "issue": "misfocus",
                "confidence": 0.88,
                "reason": "Foreground fawn soft; adults sharp behind.",
                "suggested_alternatives": [195199],
                "risk_flags": ["foreground_soft", "score_technical_mismatch"],
            }
        ]
    }
    rows = {195193: {"pick_status": 1, "cull_decision": "pick"}}
    inserted = _persist_picked_advisories(
        group_id=42,
        validated=validated,
        rows_by_id=rows,
        picked_ids={195193, 195199},
    )
    assert inserted == 1
    kwargs = mock_insert.call_args.kwargs
    assert kwargs["image_id"] == 195193
    assert kwargs["agent_decision"] == "advisory"
    assert kwargs["final_decision"] == "keep"
    assert kwargs["candidate_status"] == PICK_QUALITY_ADVISORY_STATUS
    assert kwargs["better_alternatives"] == [195199]
    assert "misfocus" in kwargs["reason"]


@patch("modules.agent_cull.apply.insert_recommendation")
def test_persist_picked_advisories_skips_non_picked(mock_insert):
    validated = {
        "picked_image_advisories": [
            {"image_id": 10, "issue": "blur", "reason": "x", "suggested_alternatives": []}
        ]
    }
    inserted = _persist_picked_advisories(
        group_id=1,
        validated=validated,
        rows_by_id={},
        picked_ids={11},  # 10 not picked
    )
    assert inserted == 0
    mock_insert.assert_not_called()


@patch("modules.agent_cull.apply.audit.audit_context")
@patch("modules.agent_cull.apply.update_review_group")
@patch("modules.agent_cull.apply.list_recommendations_for_group")
@patch("modules.agent_cull.apply.db.get_connector")
def test_apply_skips_pick_quality_advisory(
    mock_get_connector,
    mock_list_recs,
    mock_update_group,
    mock_audit_ctx,
):
    mock_audit_ctx.return_value.__enter__ = MagicMock(return_value=None)
    mock_audit_ctx.return_value.__exit__ = MagicMock(return_value=False)
    connector = MagicMock()
    mock_get_connector.return_value = connector
    connector.query_one.return_value = {"id": 1, "dry_run": False}
    # Advisory row defensively carries a remove final_decision; must still be skipped.
    mock_list_recs.return_value = [
        {
            "id": 20,
            "final_decision": "remove",
            "candidate_status": PICK_QUALITY_ADVISORY_STATUS,
        },
        {"id": 21, "final_decision": "remove", "candidate_status": "proposed"},
    ]
    result = apply_agent_remove_candidates(1)
    assert result["ok"] is True
    assert result["updated"] == 1
    connector.execute.assert_called_once()
    assert connector.execute.call_args[0][1][1] == 21
