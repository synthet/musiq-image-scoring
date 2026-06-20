"""Service orchestration edge cases for agent cull review."""

from unittest.mock import MagicMock, patch

from modules.agent_cull.cli_adapter import AgentCullRawResponse, MockAgentCullProvider
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.service import run_agent_review_for_unit


def test_failed_cli_with_auth_stdout_is_not_malformed_json():
    unit = ReviewUnit(
        review_unit_key="stack:1:sub:2",
        stack_id=1,
        sub_stack_id=2,
        image_ids=(10, 11),
        picked_ids=(10,),
        rejected_ids=(11,),
        neutral_ids=(),
        usable_ids=(10, 11),
        hierarchy_tier="substack",
    )
    rows_by_id = {
        10: {"id": 10, "file_path": "/a.jpg", "pick_status": 1},
        11: {"id": 11, "file_path": "/b.jpg", "pick_status": -1},
    }
    auth_stdout = (
        "Authentication required. Please visit the URL to log in:\n"
        "Waiting for authentication (timeout 30s)...\n"
        "Error: authentication timed out.\n"
    )
    provider = MockAgentCullProvider(auth_stdout, exit_code=1)
    with (
        patch("modules.agent_cull.service.build_prompt", return_value="prompt"),
        patch("modules.agent_cull.service.build_review_packet", return_value={"schema_version": "agent-cull-request-v1"}),
        patch("modules.agent_cull.service.persist_failed_review", return_value=99) as persist,
    ):
        result = run_agent_review_for_unit(
            unit,
            rows_by_id,
            cfg=MagicMock(dry_run_default=True),
            provider=provider,
        )
    assert result["ok"] is False
    assert result["error"] == "agent_cli_auth_failed"
    assert result["group_id"] == 99
    persist.assert_called_once()
    assert persist.call_args.kwargs["error_code"] == "agent_cli_auth_failed"
