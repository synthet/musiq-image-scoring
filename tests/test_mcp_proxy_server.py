from __future__ import annotations

import os

import pytest

pytest.importorskip("mcp")

from modules.mcp.compact_tools import _should_proxy_dispatch


def test_should_proxy_dispatch_unknown_action():
    assert _should_proxy_dispatch("nope.missing", {"status": "error", "code": "unknown_action"}) is True


def test_should_proxy_dispatch_allowlist_action_id(monkeypatch):
    monkeypatch.setenv("MCP_WEBUI_PROXY_ACTION_IDS", "data.execute_sql, diagnostics.get_error_summary")
    assert _should_proxy_dispatch("diagnostics.get_error_summary", {"status": "success"}) is True


def test_should_proxy_dispatch_allowlist_prefix(monkeypatch):
    monkeypatch.setenv("MCP_WEBUI_PROXY_PREFIXES", "webui.,live.")
    assert _should_proxy_dispatch("live.some_action", {"status": "success"}) is True
    assert _should_proxy_dispatch("jobs.get_recent_jobs", {"status": "success"}) is False


def test_should_proxy_dispatch_default_off(monkeypatch):
    monkeypatch.delenv("MCP_WEBUI_PROXY_ACTION_IDS", raising=False)
    monkeypatch.delenv("MCP_WEBUI_PROXY_PREFIXES", raising=False)
    assert _should_proxy_dispatch("jobs.get_recent_jobs", {"status": "success"}) is False

