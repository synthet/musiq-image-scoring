"""Operator approve/reject actions for agent cull recommendations."""

from __future__ import annotations

from typing import Any

from modules import audit, db
from modules.agent_cull.repository import list_recommendations_for_group, update_review_group

APPROVABLE_STATUSES = frozenset({"proposed", "agent_remove_candidate"})


def _filter_recommendations(
    group_id: int,
    recommendation_ids: list[int] | None,
) -> list[dict[str, Any]]:
    recs = list_recommendations_for_group(group_id)
    if recommendation_ids:
        wanted = {int(i) for i in recommendation_ids}
        recs = [r for r in recs if int(r["id"]) in wanted]
    return recs


def approve_recommendations(
    group_id: int,
    *,
    recommendation_ids: list[int] | None = None,
    actor: str = "operator",
    note: str | None = None,
) -> dict[str, Any]:
    recs = _filter_recommendations(group_id, recommendation_ids)
    updated = 0
    with audit.audit_context(source="agent_cull", phase_code="culling"):
        for rec in recs:
            if rec.get("final_decision") != "remove":
                continue
            status = str(rec.get("candidate_status") or "none")
            if status not in APPROVABLE_STATUSES:
                continue
            db.get_connector().execute(
                """
                UPDATE agent_cull_recommendations
                SET prior_candidate_status = candidate_status,
                    candidate_status = 'operator_approved',
                    operator_actor = ?,
                    operator_note = ?,
                    operator_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (actor, note, rec["id"]),
            )
            updated += 1
    if updated:
        update_review_group(group_id, applied_by=actor)
    return {"updated": updated, "group_id": group_id}


def reject_recommendations(
    group_id: int,
    *,
    recommendation_ids: list[int] | None = None,
    actor: str = "operator",
    note: str | None = None,
) -> dict[str, Any]:
    recs = _filter_recommendations(group_id, recommendation_ids)
    updated = 0
    with audit.audit_context(source="agent_cull", phase_code="culling"):
        for rec in recs:
            status = str(rec.get("candidate_status") or "none")
            if status in ("operator_rejected", "rolled_back"):
                continue
            if rec.get("final_decision") != "remove" and status not in APPROVABLE_STATUSES:
                continue
            db.get_connector().execute(
                """
                UPDATE agent_cull_recommendations
                SET prior_candidate_status = candidate_status,
                    candidate_status = 'operator_rejected',
                    operator_actor = ?,
                    operator_note = ?,
                    operator_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (actor, note, rec["id"]),
            )
            updated += 1
    return {"updated": updated, "group_id": group_id}
