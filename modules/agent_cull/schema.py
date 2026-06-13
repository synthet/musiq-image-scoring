"""JSON schema validation for agent cull review responses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.agent_cull.config import RESPONSE_SCHEMA_VERSION

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional at runtime; required in tests via project deps
    jsonschema = None  # type: ignore[assignment]

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "technical"
    / "AGENT_CULL_REVIEW_SCHEMA.json"
)

ALLOWED_DECISIONS = frozenset({"remove", "keep", "uncertain"})
ALLOWED_GROUP_DECISIONS = frozenset({"apply_removals", "do_not_apply"})


@dataclass
class ValidationResult:
    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    errors: list[str] = field(default_factory=list)


def _load_schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def extract_json_object(raw: str) -> str:
    """Best-effort extraction of a JSON object from agent stdout."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty_response")
    if text.startswith("{") and text.endswith("}"):
        return text
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("no_json_object")


def parse_agent_response(raw: str) -> dict[str, Any]:
    payload = extract_json_object(raw)
    return json.loads(payload)


def validate_agent_response(
    data: dict[str, Any],
    *,
    stack_id: int,
    sub_stack_id: int | None,
    rejected_image_ids: set[int],
    picked_image_ids: set[int],
) -> ValidationResult:
    errors: list[str] = []

    if data.get("schema_version") != RESPONSE_SCHEMA_VERSION:
        errors.append(f"unsupported_schema_version:{data.get('schema_version')!r}")

    if int(data.get("stack_id", -1)) != int(stack_id):
        errors.append("stack_id_mismatch")

    resp_sub = data.get("sub_stack_id")
    if sub_stack_id is None:
        if resp_sub not in (None, 0):
            errors.append("sub_stack_id_mismatch")
    elif int(resp_sub or -1) != int(sub_stack_id):
        errors.append("sub_stack_id_mismatch")

    group_decision = data.get("group_decision")
    if group_decision not in ALLOWED_GROUP_DECISIONS:
        errors.append("invalid_group_decision")

    try:
        group_conf = float(data.get("confidence"))
        if not (0.0 <= group_conf <= 1.0):
            errors.append("group_confidence_out_of_range")
    except (TypeError, ValueError):
        errors.append("group_confidence_invalid")

    decisions = data.get("rejected_image_decisions")
    if not isinstance(decisions, list):
        errors.append("rejected_image_decisions_not_array")
        return ValidationResult(ok=False, error_code="schema_invalid", error_message="invalid decisions", errors=errors)

    if len(decisions) != len(rejected_image_ids):
        errors.append("rejected_decision_count_mismatch")

    seen: set[int] = set()
    for idx, item in enumerate(decisions):
        if not isinstance(item, dict):
            errors.append(f"decision_{idx}_not_object")
            continue
        image_id = item.get("image_id")
        try:
            iid = int(image_id)
        except (TypeError, ValueError):
            errors.append(f"decision_{idx}_invalid_image_id")
            continue
        if iid in seen:
            errors.append(f"duplicate_image_id:{iid}")
        seen.add(iid)
        if iid not in rejected_image_ids:
            errors.append(f"unknown_rejected_image_id:{iid}")
        decision = item.get("decision")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"decision_{idx}_invalid_decision")
        try:
            conf = float(item.get("confidence"))
            if not (0.0 <= conf <= 1.0):
                errors.append(f"decision_{idx}_confidence_out_of_range")
        except (TypeError, ValueError):
            errors.append(f"decision_{idx}_confidence_invalid")
        alts = item.get("better_alternatives")
        if not isinstance(alts, list):
            errors.append(f"decision_{idx}_alternatives_not_array")
        else:
            for alt in alts:
                try:
                    aid = int(alt)
                except (TypeError, ValueError):
                    errors.append(f"decision_{idx}_invalid_alternative")
                    break
                if aid not in picked_image_ids:
                    errors.append(f"decision_{idx}_alternative_not_picked:{aid}")

    if jsonschema is not None:
        try:
            jsonschema.validate(data, _load_schema())
        except jsonschema.ValidationError as exc:
            errors.append(f"jsonschema:{exc.message}")

    if errors:
        return ValidationResult(
            ok=False,
            error_code="schema_invalid",
            error_message="; ".join(errors[:8]),
            errors=errors,
        )
    return ValidationResult(ok=True, data=data)


def validate_raw_agent_response(
    raw: str,
    *,
    stack_id: int,
    sub_stack_id: int | None,
    rejected_image_ids: set[int],
    picked_image_ids: set[int],
) -> ValidationResult:
    try:
        data = parse_agent_response(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        return ValidationResult(
            ok=False,
            error_code="malformed_json",
            error_message=str(exc),
            errors=[str(exc)],
        )
    return validate_agent_response(
        data,
        stack_id=stack_id,
        sub_stack_id=sub_stack_id,
        rejected_image_ids=rejected_image_ids,
        picked_image_ids=picked_image_ids,
    )
