"""Compact SSE MCP surface (is-be-live default)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

pytest.importorskip("mcp")

from modules.mcp.names import DISPATCH, SEARCH
from modules.mcp.router_tools import register_compact_tools
from modules.mcp_server import get_mcp_sse_profile, resolve_mcp_sse_app


def test_get_mcp_sse_profile_defaults_compact():
    with patch.dict(os.environ, {}, clear=True):
        assert get_mcp_sse_profile() == "compact"


def test_get_mcp_sse_profile_full_aliases():
    with patch.dict(os.environ, {"MCP_SSE_PROFILE": "legacy"}, clear=False):
        assert get_mcp_sse_profile() == "full"
    with patch.dict(os.environ, {"MCP_SSE_PROFILE": "full"}, clear=False):
        assert get_mcp_sse_profile() == "full"


def test_resolve_mcp_sse_app_returns_profile():
    with patch.dict(os.environ, {"MCP_SSE_PROFILE": "compact"}, clear=False):
        app, profile = resolve_mcp_sse_app("/")
        assert app is not None
        assert profile == "compact"


def test_compact_mcp_registers_search_and_dispatch_only():
    from mcp.server.fastmcp import FastMCP

    inst = FastMCP("test-compact")
    register_compact_tools(inst)
    mgr = getattr(inst, "_tool_manager", None)
    tools_map = getattr(mgr, "_tools", None) if mgr else None
    assert isinstance(tools_map, dict)
    assert set(tools_map.keys()) == {SEARCH, DISPATCH}
