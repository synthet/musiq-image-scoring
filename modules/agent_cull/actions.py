"""High-level actions for agent cull REST and CLI."""

from __future__ import annotations

from typing import Any

from modules.agent_cull.apply import apply_agent_remove_candidates
from modules.agent_cull.config import load_agent_cull_config
from modules.agent_cull.discovery_db import (
    discover_eligible_units,
    inspect_review_unit_for_run,
    load_unit_rows,
)
from modules.agent_cull.fingerprint import check_group_staleness
from modules.agent_cull.operator import approve_recommendations, reject_recommendations
from modules.agent_cull.repository import get_latest_group_for_unit
from modules.agent_cull.rollback import rollback_recommendation
from modules.agent_cull.service import run_agent_review_for_unit


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
