"""SQL placeholder parity for agent cull discovery queries."""

from modules.agent_cull.discovery_db import _stack_member_query
from modules.db_legacy import _count_placeholders_firebird_style


def test_stack_member_query_placeholders_match_params_with_stack_filter():
    sql, params = _stack_member_query(folder_id=42, stack_id=28556)
    assert _count_placeholders_firebird_style(sql) == len(params)
    assert "ORDER BY kd.keyword_display" in sql
    assert " AND i.stack_id = ?" in sql


def test_stack_member_query_placeholders_match_params_without_stack_filter():
    sql, params = _stack_member_query(folder_id=None, stack_id=None)
    assert _count_placeholders_firebird_style(sql) == len(params)
    assert " AND i.stack_id = ?" not in sql
