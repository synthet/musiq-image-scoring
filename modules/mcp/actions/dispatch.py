"""Execute MCP actions by action_id."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from modules.mcp.actions.envelope import dry_run_envelope, success_envelope
from modules.mcp.actions.errors import McpActionError, ValidationError
from modules.mcp.actions.handlers import invoke_handler
from modules.mcp.actions.path_safety import validate_debug_bundle_output_path
from modules.mcp.actions.policy import (
    check_dispatchable,
    check_side_effect_policy,
    check_version,
)
from modules.mcp.actions.registry import require_action
from modules.mcp.actions.schema import validate_arguments

logger = logging.getLogger(__name__)


def _sanitize(data: Any) -> Any:
    try:
        from modules.mcp_server import _sanitize_for_mcp

        return _sanitize_for_mcp(data)
    except Exception:
        return data


_REVIEW_REMINDER = (
    "Review the zip before sharing. secrets.json is excluded. See docs/DIAGNOSTICS.md."
)


def _dispatch_export_debug_bundle(
    record: dict[str, Any],
    validated: dict[str, Any],
    *,
    request_id: str,
    warnings: list[str],
) -> dict[str, Any]:
    from modules.debug_bundle_export import write_redacted_debug_bundle

    output_path = validated.get("output_path")
    if output_path is not None and not isinstance(output_path, str):
        raise ValidationError("output_path must be a string", details={"field": "output_path"})

    resolved = validate_debug_bundle_output_path(
        output_path if isinstance(output_path, str) else None,
    )
    raw = write_redacted_debug_bundle(output_zip=resolved)
    if not raw.get("success"):
        raise McpActionError(
            str(raw.get("error") or "export failed"),
            details={"path": raw.get("path")},
        )

    zip_path = Path(str(raw["path"])).resolve()
    size_bytes = zip_path.stat().st_size if zip_path.is_file() else 0
    data = {
        "artifact": {
            "kind": "debug_bundle",
            "path": str(zip_path),
            "size_bytes": size_bytes,
        }
    }
    return success_envelope(
        record,
        request_id=request_id,
        data=data,
        summary="Redacted debug bundle written.",
        dry_run=False,
        warnings=warnings,
        review_reminder=_REVIEW_REMINDER,
    )


def dispatch_action(
    action_id: str,
    arguments: dict | None = None,
    *,
    dry_run: bool = False,
    confirmed: bool = False,
    request_id: str | None = None,
    allow_deprecated: bool = False,
    expected_version: int | None = None,
) -> dict[str, Any]:
    rid = (request_id or "").strip() or str(uuid.uuid4())
    started = time.perf_counter()
    record: dict[str, Any] | None = None
    try:
        record = require_action(action_id)
        check_dispatchable(record, allow_deprecated=allow_deprecated)
        warnings = check_version(record, expected_version)
        check_side_effect_policy(record, confirmed=confirmed, dry_run=dry_run)

        validated = validate_arguments(record.get("input_schema"), dict(arguments or {}))

        if dry_run and record.get("dry_run_supported"):
            return dry_run_envelope(record, request_id=rid, validated_args=validated, warnings=warnings)

        if dry_run:
            return dry_run_envelope(
                record,
                request_id=rid,
                validated_args=validated,
                warnings=warnings + ["dry_run has no effect for read-only actions"],
            )

        if action_id == "support.export_debug_bundle":
            return _dispatch_export_debug_bundle(record, validated, request_id=rid, warnings=warnings)

        if record.get("handler_domain") == "playwright":
            if dry_run:
                return dry_run_envelope(
                    record,
                    request_id=rid,
                    validated_args=validated,
                    warnings=warnings + ["dry_run has no effect for read-only actions"],
                )
            legacy_tool = str(record.get("legacy_tool_name") or "")
            if not legacy_tool:
                raise McpActionError(
                    "Playwright action missing legacy_tool_name",
                    details={"action_id": action_id},
                )
            return {
                "status": "proxy",
                "code": "playwright_delegate",
                "action_id": action_id,
                "action_version": record.get("version"),
                "request_id": rid,
                "legacy_tool_name": legacy_tool,
                "validated_args": validated,
                "side_effect_level": record.get("side_effect_level"),
            }

        raw = invoke_handler(record, validated)
        data = _sanitize(raw)
        summary = f"{record.get('title') or action_id} completed."
        return success_envelope(
            record,
            request_id=rid,
            data=data,
            summary=summary,
            dry_run=False,
            warnings=warnings,
        )
    except McpActionError as exc:
        logger.info(
            "mcp_dispatch action=%s request_id=%s status=error code=%s duration_ms=%.1f",
            action_id,
            rid,
            exc.code,
            (time.perf_counter() - started) * 1000,
        )
        return exc.to_dict(action_id=action_id, request_id=rid)
    except Exception as exc:
        logger.exception("mcp_dispatch action=%s request_id=%s failed", action_id, rid)
        err = McpActionError(str(exc), details={"type": type(exc).__name__})
        return err.to_dict(action_id=action_id, request_id=rid)
    finally:
        if record is not None:
            logger.info(
                "mcp_dispatch action=%s request_id=%s version=%s dry_run=%s confirmed=%s duration_ms=%.1f",
                action_id,
                rid,
                record.get("version"),
                dry_run,
                confirmed,
                (time.perf_counter() - started) * 1000,
            )
