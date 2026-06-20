"""Tests for Playwright action registry merge and search."""

from __future__ import annotations

import os
from unittest.mock import patch

from modules.mcp.actions.registry import (
    action_by_id,
    clear_registry_cache,
    load_action_registry,
)
from modules.mcp.actions.search import reset_search_index, search_actions


def setup_function():
    clear_registry_cache()
    reset_search_index()


def test_playwright_registry_merged_by_default():
    reg = load_action_registry()
    entry = action_by_id("browser.navigate", reg)
    assert entry is not None
    assert entry.get("handler_domain") == "playwright"
    assert entry.get("legacy_tool_name") == "browser_navigate"


def test_playwright_registry_opt_out():
    with patch.dict(os.environ, {"MCP_PLAYWRIGHT_ENABLED": "0"}, clear=False):
        clear_registry_cache()
        reset_search_index()
        reg = load_action_registry()
        assert action_by_id("browser.navigate", reg) is None


def test_search_finds_browser_navigate():
    result = search_actions("navigate browser webui", limit=5)
    ids = [r["action_id"] for r in result.get("results") or []]
    assert "browser.navigate" in ids
