"""Dispatch policy checks."""

from __future__ import annotations

from typing import Any

from modules.mcp.actions.errors import (
    ActionNotDispatchableError,
    DeprecatedActionError,
    PolicyError,
    VersionMismatchError,
)

READ_ONLY = "read_only"


def check_dispatchable(record: dict[str, Any], *, allow_deprecated: bool = False) -> None:
    if not record.get("dispatch_enabled", False):
        raise ActionNotDispatchableError(
            f"Action {record.get('action_id')} is not dispatchable",
            details={"review_required": record.get("review_required", False)},
        )
    if record.get("deprecated") and not allow_deprecated:
        repl = record.get("replacement_action_id")
        msg = f"Action {record.get('action_id')} is deprecated"
        if repl:
            msg += f"; use {repl}"
        raise DeprecatedActionError(msg)


def check_version(record: dict[str, Any], expected_version: int | None) -> list[str]:
    warnings: list[str] = []
    if expected_version is None:
        return warnings
    actual = int(record.get("version") or 1)
    if expected_version != actual:
        raise VersionMismatchError(
            f"Expected action version {expected_version}, registry has {actual}",
            details={"expected_version": expected_version, "action_version": actual},
        )
    return warnings


def check_side_effect_policy(
    record: dict[str, Any],
    *,
    confirmed: bool,
    dry_run: bool,
    pr1_read_only_only: bool = True,
) -> None:
    level = str(record.get("side_effect_level") or READ_ONLY)
    if pr1_read_only_only and level != READ_ONLY:
        raise PolicyError(
            f"Action {record.get('action_id')} has side_effect_level={level}; not enabled in PR1",
            details={"side_effect_level": level, "policy": "pr1_read_only_only"},
        )
    if record.get("confirmation_required") and not confirmed and level != READ_ONLY:
        raise PolicyError(
            "confirmation_required=true; pass confirmed=True",
            details={"action_id": record.get("action_id")},
        )
    if level != READ_ONLY and not dry_run and record.get("dry_run_supported"):
        raise PolicyError(
            "dry_run_supported; call dispatch with dry_run=True first",
            details={"action_id": record.get("action_id")},
        )
