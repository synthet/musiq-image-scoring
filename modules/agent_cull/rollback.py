"""Rollback agent cull recommendation candidate status."""

from __future__ import annotations

from modules import audit, db
from modules.agent_cull.repository import update_review_group


def rollback_recommendation(recommendation_id: int, *, actor: str = "operator") -> bool:
    row = db.get_connector().query_one(
        "SELECT * FROM agent_cull_recommendations WHERE id = ?",
        (recommendation_id,),
    )
    if not row:
        return False
    prior = row.get("prior_candidate_status")
    if prior is None:
        prior = "none"
    with audit.audit_context(source="agent_cull", phase_code="culling"):
        db.get_connector().execute(
            """
            UPDATE agent_cull_recommendations
            SET candidate_status = ?, operator_actor = ?, operator_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (prior, actor, recommendation_id),
        )
    group_id = row.get("review_group_id")
    if group_id is not None:
        update_review_group(int(group_id), status="rolled_back", applied_by=actor)
    return True
