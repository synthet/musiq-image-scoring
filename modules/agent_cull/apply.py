"""Apply and persist agent cull recommendations (metadata-only)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from modules.agent_cull.json_util import json_dumps

from modules import audit, db
from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.mode_profiles import resolve_prompt_template_version
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.repository import (
    insert_recommendation,
    insert_review_group,
    list_recommendations_for_group,
    update_review_group,
)
from modules.agent_cull.safety import SafetyResult

logger = logging.getLogger(__name__)


def _coerce_dry_run(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "t", "on")
    return bool(value)


def prompt_hash(packet: dict[str, Any]) -> str:
    blob = json_dumps(packet, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def candidate_status_for_decision(final_decision: str, *, dry_run: bool) -> str:
    if final_decision != "remove":
        return "none"
    return "proposed" if dry_run else "agent_remove_candidate"


PICK_QUALITY_ADVISORY_STATUS = "pick_quality_advisory"


def _persist_picked_advisories(
    *,
    group_id: int,
    validated: dict[str, Any],
    rows_by_id: dict[int, dict[str, Any]],
    picked_ids: set[int],
) -> int:
    """Persist picked-image quality advisories as advisory-only recommendations.

    Advisories never become remove candidates: they carry ``agent_decision``
    ``advisory`` / ``final_decision`` ``keep`` / ``candidate_status``
    ``pick_quality_advisory`` so the apply/remove gates always skip them.
    """
    inserted = 0
    for adv in validated.get("picked_image_advisories") or []:
        if not isinstance(adv, dict):
            continue
        try:
            adv_id = int(adv.get("image_id"))
        except (TypeError, ValueError):
            continue
        if adv_id not in picked_ids:
            continue
        row = rows_by_id.get(adv_id) or {}
        issue = str(adv.get("issue") or "other")
        reason = str(adv.get("reason") or "")
        try:
            adv_conf = float(adv["confidence"]) if adv.get("confidence") is not None else None
        except (TypeError, ValueError):
            adv_conf = None
        suggested: list[int] = []
        for alt in adv.get("suggested_alternatives") or []:
            try:
                suggested.append(int(alt))
            except (TypeError, ValueError):
                continue
        risk_flags = [str(r) for r in (adv.get("risk_flags") or [])]
        insert_recommendation(
            review_group_id=group_id,
            image_id=adv_id,
            agent_decision="advisory",
            final_decision="keep",
            confidence=adv_conf,
            reason=f"[{issue}] {reason}".strip(),
            better_alternatives=suggested,
            risk_flags=risk_flags,
            safety_overrides=[],
            candidate_status=PICK_QUALITY_ADVISORY_STATUS,
            prior_pick_status=row.get("pick_status"),
            prior_cull_decision=row.get("cull_decision"),
            prior_candidate_status="none",
        )
        inserted += 1
    return inserted


def persist_validated_review(
    *,
    unit: ReviewUnit,
    packet: dict[str, Any],
    validated: dict[str, Any],
    safety: SafetyResult,
    cfg: AgentCullConfig,
    dry_run: bool,
    rows_by_id: dict[int, dict[str, Any]],
    raw_response: str,
    provider_name: str,
    agent_model: str = "",
    agent_version: str = "",
    provider_supports_vision: bool,
) -> int:
    group_id = insert_review_group(
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        review_unit_key=unit.review_unit_key,
        dry_run=dry_run,
        status="validated",
        request_json=packet,
    )
    update_review_group(
        group_id,
        agent_name=provider_name,
        agent_model=agent_model or None,
        agent_version=agent_version or None,
        agent_supports_vision=provider_supports_vision,
        prompt_template_version=resolve_prompt_template_version(cfg),
        prompt_hash=prompt_hash(packet),
        response_raw=raw_response[:500_000],
        response_validated=validated,
        group_decision=validated.get("group_decision"),
        group_confidence=float(validated.get("confidence") or 0.0),
        summary=str(validated.get("summary") or "")[:4000],
        safety_overrides=[o.to_dict() for o in safety.overrides],
        status="proposed" if dry_run else "validated",
    )

    for decision in safety.image_decisions:
        row = rows_by_id.get(decision.image_id) or {}
        insert_recommendation(
            review_group_id=group_id,
            image_id=decision.image_id,
            agent_decision=decision.agent_decision,
            final_decision=decision.final_decision,
            confidence=decision.confidence,
            reason=decision.reason,
            better_alternatives=decision.better_alternatives,
            risk_flags=decision.risk_flags,
            safety_overrides=[o.to_dict() for o in decision.safety_overrides],
            candidate_status=candidate_status_for_decision(decision.final_decision, dry_run=dry_run),
            prior_pick_status=row.get("pick_status"),
            prior_cull_decision=row.get("cull_decision"),
            prior_candidate_status="none",
        )

    if cfg.review_picked_quality:
        _persist_picked_advisories(
            group_id=group_id,
            validated=validated,
            rows_by_id=rows_by_id,
            picked_ids=set(unit.picked_ids),
        )
    return group_id


def persist_failed_review(
    *,
    unit: ReviewUnit,
    packet: dict[str, Any] | None,
    dry_run: bool,
    error_code: str,
    error_message: str,
    raw_response: str | None = None,
    provider_name: str | None = None,
    agent_model: str | None = None,
    agent_version: str | None = None,
) -> int:
    group_id = insert_review_group(
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        review_unit_key=unit.review_unit_key,
        dry_run=dry_run,
        status="failed",
        request_json=packet,
    )
    update_review_group(
        group_id,
        response_raw=(raw_response or "")[:500_000],
        error_code=error_code,
        error_message=error_message[:4000],
        status="failed",
        agent_name=provider_name,
        agent_model=agent_model,
        agent_version=agent_version,
    )
    return group_id


def apply_agent_remove_candidates(
    group_id: int,
    *,
    applied_by: str = "system",
    recommendation_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Promote final remove recommendations to agent_remove_candidate. Never deletes files."""
    group = db.get_connector().query_one(
        "SELECT id, dry_run FROM agent_cull_review_groups WHERE id = ?",
        (group_id,),
    )
    if not group:
        return {"ok": False, "error": "group_not_found", "updated": 0}
    if _coerce_dry_run(group.get("dry_run")):
        return {"ok": False, "error": "dry_run_group", "updated": 0}

    recs = list_recommendations_for_group(group_id)
    if recommendation_ids:
        wanted = {int(i) for i in recommendation_ids}
        recs = [r for r in recs if int(r["id"]) in wanted]

    updated = 0
    with audit.audit_context(source="agent_cull", phase_code="culling"):
        for rec in recs:
            # Picked-quality advisories are informational only — never promote.
            if rec.get("candidate_status") == PICK_QUALITY_ADVISORY_STATUS:
                continue
            if rec.get("final_decision") != "remove":
                continue
            if rec.get("candidate_status") not in ("proposed", "none"):
                continue
            prior = rec.get("candidate_status") or "none"
            db.get_connector().execute(
                """
                UPDATE agent_cull_recommendations
                SET prior_candidate_status = ?,
                    candidate_status = 'agent_remove_candidate'
                WHERE id = ?
                """,
                (prior, rec["id"]),
            )
            updated += 1
    if updated:
        update_review_group(
            group_id,
            status="applied",
            applied_by=applied_by,
        )
    return {"ok": True, "updated": updated, "group_id": group_id}
