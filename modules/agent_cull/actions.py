"""High-level actions for agent cull REST and CLI."""

from __future__ import annotations

import logging
import os
from typing import Any

from modules import audit, db
from modules.agent_cull.apply import _coerce_dry_run, apply_agent_remove_candidates
from modules.agent_cull.config import load_agent_cull_config
from modules.agent_cull.discovery_db import (
    discover_eligible_units,
    inspect_review_unit_for_run,
    load_unit_rows,
)
from modules.agent_cull.fingerprint import check_group_staleness
from modules.agent_cull.operator import approve_recommendations, reject_recommendations
from modules.agent_cull.repository import get_latest_group_for_unit, list_recommendations_for_group
from modules.agent_cull.rollback import rollback_recommendation
from modules.agent_cull.service import run_agent_review_for_unit

logger = logging.getLogger(__name__)

#: Terminal status for a recommendation whose image+record were permanently deleted.
OPERATOR_DELETED_STATUS = "operator_deleted"


def _require_enabled() -> dict[str, Any] | None:
    if not load_agent_cull_config().enabled:
        return {"ok": False, "error": "agent_review_disabled"}
    return None


def discover_action(
    *,
    folder_path: str | None = None,
    folder_id: int | None = None,
    stack_id: int | None = None,
    sub_stack_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    cfg = load_agent_cull_config()
    units = discover_eligible_units(
        cfg,
        folder_path=folder_path,
        folder_id=folder_id,
        stack_id=stack_id,
        sub_stack_id=sub_stack_id,
        limit=limit,
    )
    return {
        "eligible_count": len(units),
        "units": [
            {
                "review_unit_key": u.review_unit_key,
                "stack_id": u.stack_id,
                "sub_stack_id": u.sub_stack_id,
                "picked": list(u.picked_ids),
                "rejected": list(u.rejected_ids),
                "image_count": len(u.image_ids),
            }
            for u in units
        ],
    }


def run_review_action(
    *,
    stack_id: int,
    sub_stack_id: int | None = None,
    dry_run: bool | None = None,
    force: bool = False,
    provider_override: str | None = None,
) -> dict[str, Any]:
    cfg = load_agent_cull_config()
    if not cfg.enabled:
        return {"ok": False, "error": "agent_review_disabled"}
    units = discover_eligible_units(
        cfg,
        stack_id=stack_id,
        sub_stack_id=sub_stack_id,
        limit=1 if sub_stack_id is not None else 50,
    )
    if sub_stack_id is not None:
        units = [u for u in units if u.sub_stack_id == sub_stack_id]
    elif len(units) > 1:
        units = [u for u in units if u.sub_stack_id is None] or units[:1]
    if not units:
        inspected = inspect_review_unit_for_run(
            cfg,
            stack_id=stack_id,
            sub_stack_id=sub_stack_id,
        )
        payload: dict[str, Any] = {"ok": False, "error": "no_eligible_unit"}
        if inspected is not None:
            payload["skip_reason"] = inspected.skip_reason or "ineligible"
            payload["counts"] = {
                "total": len(inspected.image_ids),
                "picked": len(inspected.picked_ids),
                "rejected": len(inspected.rejected_ids),
                "neutral": len(inspected.neutral_ids),
                "usable": len(inspected.usable_ids),
            }
        return payload
    unit = units[0]
    if not force:
        latest = get_latest_group_for_unit(unit.review_unit_key)
        if latest and latest.get("status") in ("proposed", "validated", "applied"):
            return {"ok": False, "error": "existing_review", "group_id": latest.get("id")}
    rows_by_id = load_unit_rows(unit)
    return run_agent_review_for_unit(
        unit,
        rows_by_id,
        cfg,
        dry_run=dry_run,
        provider_override=provider_override,
    )


def apply_candidates_action(
    group_id: int,
    *,
    applied_by: str = "operator",
    recommendation_ids: list[int] | None = None,
) -> dict[str, Any]:
    blocked = _require_enabled()
    if blocked:
        return blocked
    row = get_group_row(group_id)
    if row is None:
        return {"ok": False, "error": "group_not_found"}
    if check_group_staleness(group_id):
        return {"ok": False, "error": "stale_group_state"}
    return apply_agent_remove_candidates(
        group_id,
        applied_by=applied_by,
        recommendation_ids=recommendation_ids,
    )


def approve_action(
    group_id: int,
    *,
    recommendation_ids: list[int] | None = None,
    actor: str = "operator",
    note: str | None = None,
) -> dict[str, Any]:
    blocked = _require_enabled()
    if blocked:
        return blocked
    row = get_group_row(group_id)
    if row is None:
        return {"ok": False, "error": "group_not_found"}
    from modules.agent_cull.apply import _coerce_dry_run

    if _coerce_dry_run(row.get("dry_run")):
        return {"ok": False, "error": "dry_run_group"}
    if check_group_staleness(group_id):
        return {"ok": False, "error": "stale_group_state"}
    result = approve_recommendations(
        group_id,
        recommendation_ids=recommendation_ids,
        actor=actor,
        note=note,
    )
    return {"ok": True, **result}


def reject_action(
    group_id: int,
    *,
    recommendation_ids: list[int] | None = None,
    actor: str = "operator",
    note: str | None = None,
) -> dict[str, Any]:
    blocked = _require_enabled()
    if blocked:
        return blocked
    row = get_group_row(group_id)
    if row is None:
        return {"ok": False, "error": "group_not_found"}
    result = reject_recommendations(
        group_id,
        recommendation_ids=recommendation_ids,
        actor=actor,
        note=note,
    )
    return {"ok": True, **result}


def _mark_recommendation_deleted(recommendation_id: int, actor: str) -> None:
    db.get_connector().execute(
        """
        UPDATE agent_cull_recommendations
        SET prior_candidate_status = candidate_status,
            candidate_status = ?,
            operator_actor = ?,
            operator_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (OPERATOR_DELETED_STATUS, actor, recommendation_id),
    )


def delete_approved_action(
    group_id: int,
    *,
    actor: str = "operator",
) -> dict[str, Any]:
    """Permanently delete the FILE **and** DB record for every operator-approved remove candidate.

    IRREVERSIBLE. Only runs on a validated (non-dry-run) group whose live state still matches the
    review. Mirrors ``DELETE /images/{id}?delete_file=true``: ``db.delete_image`` removes the
    ``images`` row plus related rows and repairs the stack, then ``os.remove`` deletes the source
    file and thumbnails from disk. Each approved recommendation becomes ``operator_deleted``.
    """
    blocked = _require_enabled()
    if blocked:
        return blocked
    row = get_group_row(group_id)
    if row is None:
        return {"ok": False, "error": "group_not_found"}
    if _coerce_dry_run(row.get("dry_run")):
        return {"ok": False, "error": "dry_run_group"}
    if check_group_staleness(group_id):
        return {"ok": False, "error": "stale_group_state"}

    approved = [
        rec
        for rec in list_recommendations_for_group(group_id)
        if rec.get("candidate_status") == "operator_approved"
        and rec.get("final_decision") == "remove"
    ]
    if not approved:
        return {"ok": True, "deleted": [], "updated": 0, "group_id": group_id, "error": "no_approved_candidates"}

    deleted: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with audit.audit_context(source="agent_cull", phase_code="culling"):
        for rec in approved:
            image_id = int(rec["image_id"])
            img = db.get_connector().query_one(
                "SELECT file_path, thumbnail_path, thumbnail_path_win FROM images WHERE id = ?",
                (image_id,),
            )
            if not img:
                # Image already gone from the DB — mark the recommendation terminal and move on.
                _mark_recommendation_deleted(rec["id"], actor)
                deleted.append({"image_id": image_id, "file_path": None, "already_absent": True})
                continue

            file_path = img.get("file_path")
            success, msg = db.delete_image(file_path, delete_related=True)
            if not success:
                errors.append({"image_id": image_id, "error": msg})
                continue

            for path in (img.get("file_path"), img.get("thumbnail_path"), img.get("thumbnail_path_win")):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError as exc:
                        logger.warning("agent_cull delete: could not remove %s: %s", path, exc)

            _mark_recommendation_deleted(rec["id"], actor)
            deleted.append({"image_id": image_id, "file_path": file_path})

    result: dict[str, Any] = {
        "ok": not errors,
        "deleted": deleted,
        "updated": len(deleted),
        "group_id": group_id,
    }
    if errors:
        result["error"] = "delete_failed"
        result["errors"] = errors
    return result


def rollback_action(recommendation_id: int, *, actor: str = "operator") -> dict[str, Any]:
    blocked = _require_enabled()
    if blocked:
        return blocked
    ok = rollback_recommendation(recommendation_id, actor=actor)
    if not ok:
        return {"ok": False, "error": "recommendation_not_found"}
    return {"ok": True, "recommendation_id": recommendation_id}


def get_group_row(group_id: int) -> dict[str, Any] | None:
    from modules import db

    return db.get_connector().query_one(
        "SELECT * FROM agent_cull_review_groups WHERE id = ?",
        (group_id,),
    )
