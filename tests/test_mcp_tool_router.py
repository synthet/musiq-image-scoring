"""Tests for MCP BM25 tool router."""

from __future__ import annotations

import importlib
import os

import pytest

from modules.mcp.bm25 import Bm25Index
from modules.mcp.catalog import catalog_tools, load_tool_catalog


@pytest.fixture
def catalog():
    return load_tool_catalog()


@pytest.fixture
def index(catalog):
    return Bm25Index(catalog_tools(catalog), catalog.get("field_weights"))


def test_bm25_exact_name_ranks_first(index):
    hits = index.search("get_error_summary", limit=5)
    assert hits
    assert hits[0][0]["name"] == "get_error_summary"


def test_bm25_triage_query_finds_diagnostics(index):
    hits = index.search("why did scoring fail", limit=8)
    names = [h[0]["name"] for h in hits]
    assert "get_error_summary" in names or "get_failed_images" in names


def test_bm25_domain_filter(index):
    hits = index.search("job status", limit=10, domain="jobs")
    assert hits
    assert all(h[0]["domain"] == "jobs" for h in hits)
    assert not any(h[0]["name"] == "execute_code" for h in hits)


def test_catalog_profile_tools_cover_all_tools(catalog):
    names = {t["name"] for t in catalog_tools(catalog)}
    profile_names: set[str] = set()
    for domain, tools in (catalog.get("profile_tools") or {}).items():
        if domain == "full":
            continue
        profile_names |= set(tools)
    assert names == profile_names


def test_mcp_profile_filtering_removes_tools(monkeypatch):
    monkeypatch.setenv("MCP_TOOL_PROFILE", "diagnostics")
    import modules.mcp_server as mcp_server

    importlib.reload(mcp_server)
    prof = mcp_server.get_mcp_active_profile()
    assert prof == "diagnostics"

    mgr = mcp_server.mcp._tool_manager
    remaining = set(mgr._tools.keys())
    from modules.mcp.profiles import get_profile_tool_names

    expected = set(get_profile_tool_names("diagnostics"))
    assert remaining == expected
    assert "execute_code" not in remaining
    assert "get_error_summary" in remaining

    monkeypatch.delenv("MCP_TOOL_PROFILE", raising=False)
    importlib.reload(mcp_server)
