from __future__ import annotations

from modules.mcp.compact_tools import _should_proxy_dispatch, handle_search, invoke_compact_tool


def test_invoke_compact_tool_unknown():
    result = invoke_compact_tool("nope", {})
    assert result["code"] == "unknown_tool"


def test_handle_search_empty_query():
    result = handle_search("")
    assert result["count"] == 0
    assert result["low_confidence"] is True


def test_should_proxy_dispatch_unknown_action():
    assert _should_proxy_dispatch("nope.missing", {"status": "error", "code": "unknown_action"}) is True
