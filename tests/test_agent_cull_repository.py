"""Repository insert must commit (execute_returning, not read-only query_one)."""

from unittest.mock import MagicMock, patch

from modules.agent_cull.repository import insert_review_group


def test_insert_review_group_uses_execute_returning():
    connector = MagicMock()
    connector.execute_returning.return_value = [{"id": 42}]
    with patch("modules.agent_cull.repository.db.get_connector", return_value=connector):
        group_id = insert_review_group(
            stack_id=1,
            sub_stack_id=2,
            review_unit_key="stack:1:sub:2",
            dry_run=True,
            status="discovered",
            request_json={"schema_version": "agent-cull-request-v1"},
        )
    assert group_id == 42
    connector.execute_returning.assert_called_once()
    connector.query_one.assert_not_called()
