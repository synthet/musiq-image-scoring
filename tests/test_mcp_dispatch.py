"""Tests for MCP action dispatch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.mcp.actions.dispatch import dispatch_action
from modules.mcp.actions.errors import UnknownActionError


def test_dispatch_unknown_action():
    result = dispatch_action("maintenance.prune_missing_files", {})
    assert result.get("status") == "error"
    assert result.get("code") == "unknown_action"


def test_dispatch_run_doctor_no_gpu():
    fake_report = {
        "overall": "PASS",
        "failures": [],
        "warnings": [],
        "database_engine_info": {},
    }
    with patch("modules.doctor_cli.run_doctor", return_value=fake_report):
        with patch("modules.doctor_cli.format_report", return_value="PASS"):
            result = dispatch_action(
                "diagnostics.run_doctor",
                {"no_gpu": True},
            )
    assert result.get("status") == "success"
    assert result.get("action_id") == "diagnostics.run_doctor"
    assert result.get("action_version") == 1
    assert result.get("request_id")


def test_dispatch_envelope_version_warning():
    result = dispatch_action(
        "diagnostics.get_error_summary",
        {},
        expected_version=999,
    )
    assert result.get("status") == "error"
    assert result.get("code") == "version_mismatch"


def test_dispatch_get_error_summary_mocked():
    with patch("modules.mcp_server.get_error_summary", return_value={"ok": True}) as mock_fn:
        result = dispatch_action("diagnostics.get_error_summary", {})
    assert result.get("status") == "success"
    assert result.get("data") == {"ok": True}
    mock_fn.assert_called_once()


def test_dispatch_run_diagnostics_requires_run_id():
    result = dispatch_action("jobs.get_run_diagnostics", {})
    assert result.get("status") == "error"
    assert result.get("code") == "validation_error"
