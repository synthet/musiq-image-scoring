"""MCP SQL normalization guards (no DB)."""

import pytest

pytest.importorskip("psycopg2")

from modules.mcp_server import (
    _is_mcp_read_only_sql,
    _mcp_sql_single_statement,
    _strip_sql_comments_for_mcp,
)


def test_strip_comments_leading_with_select():
    q = "-- comment\n/* block */\nWITH a AS (SELECT 1 AS x) SELECT * FROM a"
    n = _strip_sql_comments_for_mcp(q)
    assert _is_mcp_read_only_sql(n)
    ok, err = _mcp_sql_single_statement(n)
    assert ok and err is None


def test_reject_multiple_statements():
    n = "SELECT 1; SELECT 2"
    ok, err = _mcp_sql_single_statement(n)
    assert not ok
    assert err


def test_reject_non_select():
    assert not _is_mcp_read_only_sql("UPDATE images SET rating = 1")


def test_allow_plain_select():
    n = _strip_sql_comments_for_mcp("SELECT 1 AS n")
    assert _is_mcp_read_only_sql(n)
