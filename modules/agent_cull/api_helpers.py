"""REST serialization helpers for agent cull review."""

from __future__ import annotations

import json
from typing import Any

from modules import db
from modules.agent_cull.repository import list_recommendations_for_group


def _json_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def serialize_group(row: dict[str, Any], *, include_recommendations: bool = False) -> dict[str, Any]:
    out = {
        "id": row.get("id"),
        "stack_id": row.get("stack_id"),
        "sub_stack_id": row.get("sub_stack_id"),
        "review_unit_key": row.get("review_unit_key"),
        "status": row.get("status"),
        "dry_run": row.get("dry_run"),
        "agent_name": row.get("agent_name"),
        "agent_model": row.get("agent_model"),
        "agent_version": row.get("agent_version"),
        "agent_supports_vision": row.get("agent_supports_vision"),
        "prompt_template_version": row.get("prompt_template_version"),
        "prompt_hash": row.get("prompt_hash"),
        "group_decision": row.get("group_decision"),
        "group_confidence": row.get("group_confidence"),
        "summary": row.get("summary"),
        "safety_overrides": _json_field(row.get("safety_overrides")),
        "error_code": row.get("error_code"),
        "error_message": row.get("error_message"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "applied_at": row.get("applied_at"),
        "applied_by": row.get("applied_by"),
    }
    if include_recommendations:
        recs = list_recommendations_for_group(int(row["id"]))
        out["recommendations"] = [serialize_recommendation(r) for r in recs]
    return out


def serialize_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "review_group_id": row.get("review_group_id"),
        "image_id": row.get("image_id"),
        "agent_decision": row.get("agent_decision"),
        "final_decision": row.get("final_decision"),
        "confidence": row.get("confidence"),
        "reason": row.get("reason"),
        "better_alternatives": _json_field(row.get("better_alternatives")),
        "risk_flags": _json_field(row.get("risk_flags")),
        "safety_overrides": _json_field(row.get("safety_overrides")),
        "candidate_status": row.get("candidate_status"),
        "operator_actor": row.get("operator_actor"),
        "operator_at": row.get("operator_at"),
    }


def list_groups(
    *,
    stack_id: int | None = None,
    sub_stack_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if stack_id is not None:
        clauses.append("stack_id = ?")
        params.append(stack_id)
    if sub_stack_id is not None:
        clauses.append("sub_stack_id = ?")
        params.append(sub_stack_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    params.extend([limit, offset])
    rows = db.get_connector().query(
        f"""
        SELECT * FROM agent_cull_review_groups
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    ) or []
    return [serialize_group(r) for r in rows]


def get_group(group_id: int) -> dict[str, Any] | None:
    row = db.get_connector().query_one(
        "SELECT * FROM agent_cull_review_groups WHERE id = ?",
        (group_id,),
    )
    if not row:
        return None
    payload = serialize_group(row, include_recommendations=True)
    payload["request_json"] = _json_field(row.get("request_json"))
    payload["response_validated"] = _json_field(row.get("response_validated"))
    return payload
