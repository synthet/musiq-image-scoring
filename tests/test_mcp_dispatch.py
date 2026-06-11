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
    details = result.get("details") or {}
    assert details.get("hint")
    assert isinstance(details.get("suggestions"), list)


def test_dispatch_legacy_tool_name_execute_sql():
    with patch("modules.mcp_server.execute_sql", return_value={"rows": []}) as mock_fn:
        result = dispatch_action("execute_sql", {"query": "SELECT 1"})
    assert result.get("status") == "success"
    mock_fn.assert_called_once_with(query="SELECT 1")


def test_dispatch_category_prefixed_legacy_alias():
    with patch("modules.mcp_server.get_image_pipeline_failures", return_value={"items": []}) as mock_fn:
        result = dispatch_action(
            "jobs.get_image_pipeline_failures",
            {"file_path": "/mnt/d/Photos/test.jpg"},
        )
    assert result.get("status") == "success"
    mock_fn.assert_called_once()


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


def test_dispatch_export_debug_bundle_requires_confirmation():
    with patch("modules.debug_bundle_export.write_redacted_debug_bundle") as mock_write:
        result = dispatch_action("support.export_debug_bundle", {})
    assert result.get("status") == "error"
    assert result.get("code") == "confirmation_required"
    mock_write.assert_not_called()


def test_dispatch_export_debug_bundle_rejects_dry_run():
    with patch("modules.debug_bundle_export.write_redacted_debug_bundle") as mock_write:
        result = dispatch_action(
            "support.export_debug_bundle",
            {},
            dry_run=True,
            confirmed=True,
        )
    assert result.get("status") == "error"
    assert result.get("code") == "unsupported_dry_run"
    mock_write.assert_not_called()


def test_dispatch_export_debug_bundle_confirmed(tmp_path):
    zip_path = tmp_path / "bundle.zip"
    with patch("modules.debug_bundle_export.write_redacted_debug_bundle") as mock_write:
        mock_write.return_value = {"success": True, "path": str(zip_path)}
        zip_path.write_bytes(b"fake")
        result = dispatch_action(
            "support.export_debug_bundle",
            {},
            confirmed=True,
        )
    assert result.get("status") == "success"
    assert result.get("review_reminder")
    artifact = result.get("data", {}).get("artifact", {})
    assert artifact.get("kind") == "debug_bundle"
    assert artifact.get("path") == str(zip_path.resolve())
    assert artifact.get("size_bytes") == 4
    mock_write.assert_called_once()


def test_dispatch_export_debug_bundle_bad_extension():
    result = dispatch_action(
        "support.export_debug_bundle",
        {"output_path": "bundle.txt"},
        confirmed=True,
    )
    assert result.get("status") == "error"
    assert result.get("code") == "validation_error"


def test_dispatch_export_debug_bundle_rejects_traversal():
    result = dispatch_action(
        "support.export_debug_bundle",
        {"output_path": "../bundle.zip"},
        confirmed=True,
    )
    assert result.get("status") == "error"
    assert result.get("code") == "policy_rejected"


def test_dispatch_side_effect_not_in_allowlist_even_if_dispatch_enabled():
    """Overlay-only write actions stay blocked without code allowlist entry."""
    fake_record = {
        "action_id": "maintenance.prune_missing_files",
        "dispatch_enabled": True,
        "side_effect_level": "destructive",
        "confirmation_required": True,
        "dry_run_supported": True,
        "version": 1,
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    }
    with patch("modules.mcp.actions.dispatch.require_action", return_value=fake_record):
        result = dispatch_action("maintenance.prune_missing_files", {}, confirmed=True)
    assert result.get("status") == "error"
    assert result.get("code") == "policy_rejected"


def test_dispatch_get_runner_status_mocked():
    with patch("modules.mcp_server.get_runner_status", return_value={"scoring": "idle"}) as mock_fn:
        result = dispatch_action("jobs.get_runner_status", {})
    assert result.get("status") == "success"
    assert result.get("data") == {"scoring": "idle"}
    mock_fn.assert_called_once()


def test_dispatch_get_recent_jobs_mocked():
    with patch("modules.mcp_server.get_recent_jobs", return_value=[{"id": 1}]) as mock_fn:
        result = dispatch_action("jobs.get_recent_jobs", {"limit": 5})
    assert result.get("status") == "success"
    mock_fn.assert_called_once_with(limit=5)


def test_dispatch_get_job_details_mocked():
    with patch("modules.mcp_server.get_job_details", return_value={"id": 42}) as mock_fn:
        result = dispatch_action("jobs.get_job_details", {"job_id": 42})
    assert result.get("status") == "success"
    mock_fn.assert_called_once_with(42)


def test_dispatch_query_images_mocked():
    with patch("modules.mcp_server.query_images", return_value={"images": []}) as mock_fn:
        result = dispatch_action("data.query_images", {"limit": 3, "folder_path": "/photos"})
    assert result.get("status") == "success"
    mock_fn.assert_called_once_with(limit=3, folder_path="/photos")


def test_dispatch_get_image_details_mocked():
    with patch("modules.mcp_server.get_image_details", return_value={"file_path": "/a.jpg"}) as mock_fn:
        result = dispatch_action("data.get_image_details", {"file_path": "/a.jpg"})
    assert result.get("status") == "success"
    mock_fn.assert_called_once_with(file_path="/a.jpg")
