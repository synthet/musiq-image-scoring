"""Execute MCP actions by action_id."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from modules.mcp.actions.envelope import dry_run_envelope, success_envelope
from modules.mcp.actions.errors import McpActionError
from modules.mcp.actions.handlers import invoke_handler
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
