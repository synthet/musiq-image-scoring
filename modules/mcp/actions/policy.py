"""Dispatch policy checks."""

from __future__ import annotations

from typing import Any

from modules.mcp.actions.errors import (
    ActionNotDispatchableError,
    ConfirmationRequiredError,
    DeprecatedActionError,
    PolicyError,
    UnsupportedDryRunError,
    VersionMismatchError,
)

READ_ONLY = "read_only"

ALLOWED_SIDE_EFFECT_ACTIONS = frozenset(
    {
        "support.export_debug_bundle",
        "browser.run_code_unsafe",
    }
)


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
) -> None:
    level = str(record.get("side_effect_level") or READ_ONLY)
    action_id = str(record.get("action_id") or "")

    if level != READ_ONLY:
        if action_id not in ALLOWED_SIDE_EFFECT_ACTIONS:
            raise PolicyError(
                f"Action {action_id} has side_effect_level={level}; not in ALLOWED_SIDE_EFFECT_ACTIONS",
                details={"side_effect_level": level, "policy": "side_effect_allowlist"},
            )

    if dry_run and level != READ_ONLY and not record.get("dry_run_supported"):
        raise UnsupportedDryRunError(
            f"Action {action_id} does not support dry_run",
            details={"action_id": action_id, "dry_run_supported": False},
        )

    if record.get("confirmation_required") and not confirmed and level != READ_ONLY:
        raise ConfirmationRequiredError(
            "confirmation_required=true; pass confirmed=True",
            details={"action_id": action_id},
        )

    if level != READ_ONLY and not dry_run and record.get("dry_run_supported"):
        raise PolicyError(
            "dry_run_supported; call dispatch with dry_run=True first",
            details={"action_id": action_id},
        )
