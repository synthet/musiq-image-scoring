"""Normalized dispatch result envelope."""

from __future__ import annotations

from typing import Any


def success_envelope(
    record: dict[str, Any],
    *,
    request_id: str,
    data: Any,
    summary: str,
    dry_run: bool = False,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    logs_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "action_id": record.get("action_id"),
        "action_version": int(record.get("version") or 1),
        "request_id": request_id,
        "status": "success",
        "side_effect_level": record.get("side_effect_level", "read_only"),
        "dry_run": dry_run,
        "summary": summary,
        "data": data,
        "warnings": warnings or [],
        "errors": errors or [],
        "artifacts": artifacts or [],
        "logs_ref": logs_ref,
        "canonical_docs": list(record.get("canonical_docs") or []),
    }


def dry_run_envelope(
    record: dict[str, Any],
    *,
    request_id: str,
    validated_args: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return success_envelope(
        record,
        request_id=request_id,
        data={"validated_arguments": validated_args, "would_invoke": record.get("canonical_backend_handler")},
        summary=f"Dry run for {record.get('action_id')}",
        dry_run=True,
        warnings=warnings,
    )


def error_envelope(err: dict[str, Any]) -> dict[str, Any]:
    return err
