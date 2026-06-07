"""Structured errors for MCP dispatch."""

from __future__ import annotations


class McpActionError(Exception):
    code: str = "action_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self, *, action_id: str | None = None, request_id: str | None = None) -> dict:
        return {
            "status": "error",
            "code": self.code,
            "message": self.message,
            "action_id": action_id,
            "request_id": request_id,
            "details": self.details,
        }


class UnknownActionError(McpActionError):
    code = "unknown_action"


class ActionNotDispatchableError(McpActionError):
    code = "not_dispatchable"


class DeprecatedActionError(McpActionError):
    code = "deprecated_action"


class PolicyError(McpActionError):
    code = "policy_rejected"


class ConfirmationRequiredError(McpActionError):
    code = "confirmation_required"


class UnsupportedDryRunError(McpActionError):
    code = "unsupported_dry_run"


class ValidationError(McpActionError):
    code = "validation_error"


class VersionMismatchError(McpActionError):
    code = "version_mismatch"
