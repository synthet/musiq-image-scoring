"""Tests for MCP action registry."""

from __future__ import annotations

import pytest

from modules.mcp.actions.registry import action_by_id, load_action_registry, registry_actions


def test_registry_loads_actions():
    reg = load_action_registry()
    actions = registry_actions(reg)
    assert len(actions) >= 14
    ids = [a["action_id"] for a in actions]
    assert len(ids) == len(set(ids))


def test_all_pr1_actions_dispatch_enabled():
    expected = {
        "diagnostics.run_doctor",
        "diagnostics.get_error_summary",
        "diagnostics.check_database_health",
        "diagnostics.validate_config",
        "diagnostics.get_database_engine_info",
        "diagnostics.verify_environment",
        "diagnostics.get_model_status",
        "logs.read_debug_log",
        "logs.get_server_log_tail",
        "logs.search_logs",
        "config.get_config",
        "jobs.get_failed_images",
        "jobs.get_run_diagnostics",
        "data.get_embedding_stats",
    }
    reg = load_action_registry()
    ids = {a["action_id"] for a in registry_actions(reg) if a.get("dispatch_enabled")}
    assert expected <= ids


def test_action_has_version_and_schema():
    action = action_by_id("diagnostics.get_error_summary")
    assert action is not None
    assert int(action.get("version") or 0) >= 1
    assert action.get("input_schema") is not None
    assert action.get("side_effect_level") == "read_only"
