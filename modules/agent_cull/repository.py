"""Persistence helpers for agent cull review groups and recommendations."""

from __future__ import annotations

import json
from typing import Any

from modules import db


def insert_review_group(
    *,
    stack_id: int,
    sub_stack_id: int | None,
    review_unit_key: str,
    dry_run: bool,
    status: str = "discovered",
    request_json: dict[str, Any] | None = None,
) -> int:
    rows = db.get_connector().execute_returning(
        """
        INSERT INTO agent_cull_review_groups (
            stack_id, sub_stack_id, review_unit_key, status, dry_run, request_json
        ) VALUES (?, ?, ?, ?, ?, ?::jsonb)
        RETURNING id
        """,
        (
            stack_id,
            sub_stack_id,
            review_unit_key,
            status,
            dry_run,
            json.dumps(request_json) if request_json is not None else None,
        ),
    )
    if not rows:
        raise RuntimeError("insert_review_group: INSERT returned no row")
    return int(rows[0]["id"])


def update_review_group(group_id: int, **fields: Any) -> None:
    allowed = {
        "status",
        "agent_name",
        "agent_model",
        "agent_version",
        "agent_supports_vision",
        "prompt_template_version",
        "prompt_hash",
        "request_json",
        "response_raw",
        "response_validated",
        "group_decision",
        "group_confidence",
        "summary",
        "safety_overrides",
        "error_code",
        "error_message",
        "applied_at",
        "applied_by",
    }
    sets: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in ("request_json", "response_validated", "safety_overrides") and value is not None:
            sets.append(f"{key} = ?::jsonb")
            params.append(json.dumps(value))
        else:
            sets.append(f"{key} = ?")
            params.append(value)
    if not sets:
        return
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(group_id)
    db.get_connector().execute(
        f"UPDATE agent_cull_review_groups SET {', '.join(sets)} WHERE id = ?",
        tuple(params),
    )


def insert_recommendation(
    *,
    review_group_id: int,
    image_id: int,
    agent_decision: str,
    final_decision: str,
    confidence: float | None,
    reason: str,
    better_alternatives: list[int],
    risk_flags: list[str],
    safety_overrides: list[dict[str, Any]],
    candidate_status: str,
    prior_pick_status: int | None,
    prior_cull_decision: str | None,
    prior_candidate_status: str | None = None,
) -> int:
    rows = db.get_connector().execute_returning(
        """
        INSERT INTO agent_cull_recommendations (
            review_group_id, image_id, agent_decision, final_decision, confidence,
            reason, better_alternatives, risk_flags, safety_overrides, candidate_status,
            prior_pick_status, prior_cull_decision, prior_candidate_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?::jsonb, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            review_group_id,
            image_id,
            agent_decision,
            final_decision,
            confidence,
            reason[:4000] if reason else None,
            json.dumps(better_alternatives),
            json.dumps(risk_flags),
            json.dumps(safety_overrides),
            candidate_status,
            prior_pick_status,
            prior_cull_decision,
            prior_candidate_status,
        ),
    )
    if not rows:
        raise RuntimeError("insert_recommendation: INSERT returned no row")
    return int(rows[0]["id"])


def get_latest_group_for_unit(review_unit_key: str) -> dict[str, Any] | None:
    return db.get_connector().query_one(
        """
        SELECT * FROM agent_cull_review_groups
        WHERE review_unit_key = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (review_unit_key,),
    )


def list_recommendations_for_group(group_id: int) -> list[dict[str, Any]]:
    return db.get_connector().query(
        "SELECT * FROM agent_cull_recommendations WHERE review_group_id = ? ORDER BY id",
        (group_id,),
    ) or []
