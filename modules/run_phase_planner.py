"""Just-in-time run planning: stale/missing image×phase work in scope."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from modules import db
from modules.phases import PhaseCode
from modules.phases_policy import explain_phase_run_decision
from modules.phase_work_claims import count_claimed_by_other

logger = logging.getLogger(__name__)

DEFAULT_STAGES = (
    "indexing",
    "metadata",
    "scoring",
    "keywords",
    "culling",
    "bird_species",
)

_PHASE_ALIASES = {
    "clustering": "culling",
    "selection": "culling",
    "tagging": "keywords",
    "tag": "keywords",
    "score": "scoring",
    "bird-species": "bird_species",
}


def _normalize_stage_code(code: str) -> str:
    c = (code or "").strip().lower()
    return _PHASE_ALIASES.get(c, c)


def _reason_bucket(policy_reason: str) -> str:
    r = (policy_reason or "").strip().lower()
    if r in ("missing_phase_status",):
        return "missing_row"
    if r.startswith("status_not_started"):
        return "not_started"
    if r.startswith("status_failed"):
        return "failed"
    if r in ("executor_version_changed",):
        return "stale_executor"
    if r in ("already_running",):
        return "stale_running"
    if r.startswith("missing_") or "incomplete" in r:
        return "missing_data"
    if r in ("already_done_current_executor",):
        return "current"
    return "invalid_data"


def _images_in_scope(scope_paths: List[str]) -> List[int]:
    return db._query_image_ids_by_condition_for_scope(scope_paths, "1=1")


def _apply_preflight(scope_paths: List[str]) -> Dict[str, int]:
    actions = {"reconciled_rows": 0, "backfilled_index_meta": 0}
    try:
        actions["reconciled_rows"] = int(
            db.reconcile_stale_running_phases_for_terminal_jobs(limit=5000)
        )
    except Exception:
        logger.exception("run_phase_planner: reconcile terminal phases failed")
    try:
        for p in scope_paths or []:
            actions["backfilled_index_meta"] += int(db.backfill_index_meta_for_folder(p))
    except Exception:
        logger.exception("run_phase_planner: backfill index/meta failed")
    return actions


def _needs_work_for_phase(image_id: int, phase_code: str) -> tuple[bool, str]:
    decision = explain_phase_run_decision(image_id, phase_code, force_run=False)
    return bool(decision.get("should_run")), str(decision.get("reason") or "")


def plan_scope(
    scope_paths: List[str],
    stage_codes: Optional[List[str]] = None,
    *,
    dry_run: bool = True,
    job_id: Optional[int] = None,
    exclude_claimed: bool = True,
) -> Dict[str, Any]:
    """Build a scope plan with per-stage queues and reason counts."""
    selected = {_normalize_stage_code(str(s)) for s in (stage_codes or []) if str(s).strip()}
    if not selected:
        selected = set(DEFAULT_STAGES)

    actions = {"reconciled_rows": 0, "backfilled_index_meta": 0, "scoring_fix_targets": 0}
    if not dry_run:
        actions.update(_apply_preflight(scope_paths))

    image_ids = _images_in_scope(scope_paths)
    issue_counts: Dict[str, int] = defaultdict(int)
    issue_counts_by_reason: Dict[str, int] = defaultdict(int)
    stage_queues: Dict[str, List[int]] = {}

    for stage in sorted(selected):
        queue: List[int] = []
        for iid in image_ids:
            needs, reason = _needs_work_for_phase(iid, stage)
            if not needs:
                continue
            bucket = _reason_bucket(reason)
            issue_counts_by_reason[bucket] += 1
            issue_counts[f"{stage}_{bucket}"] = issue_counts.get(f"{stage}_{bucket}", 0) + 1
            if (
                exclude_claimed
                and job_id is not None
                and count_claimed_by_other(job_id, stage, [iid]) > 0
            ):
                issue_counts_by_reason["claimed_by_active_run"] += 1
                continue
            queue.append(iid)
        stage_queues[stage] = queue
        if stage == "culling":
            stage_queues["clustering"] = list(queue)
        if stage == "scoring":
            actions["scoring_fix_targets"] = len(queue)

    unique_issue_ids: Set[int] = set()
    for ids in stage_queues.values():
        unique_issue_ids.update(int(i) for i in ids)

    return {
        "issue_counts": dict(issue_counts),
        "issue_counts_by_reason": dict(issue_counts_by_reason),
        "stage_queues": stage_queues,
        "actions": actions,
        "issue_hits": int(sum(issue_counts_by_reason.values())),
        "repaired": actions["reconciled_rows"] + actions["backfilled_index_meta"] if not dry_run else 0,
        "skipped": len(unique_issue_ids) if dry_run else 0,
        "failed": 0,
        "dry_run": bool(dry_run),
    }


def plan_phase(
    scope_paths: List[str],
    phase_code: str,
    *,
    job_id: Optional[int] = None,
    dry_run: bool = False,
    exclude_claimed: bool = True,
) -> List[int]:
    stage = _normalize_stage_code(phase_code)
    plan = plan_scope(
        scope_paths,
        [stage],
        dry_run=dry_run,
        job_id=job_id,
        exclude_claimed=exclude_claimed,
    )
    return list(plan.get("stage_queues", {}).get(stage) or [])


def to_legacy_repair_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Shape compatible with historical validation-repair consumers."""
    out = dict(plan)
    legacy_counts: Dict[str, int] = {}
    for stage, ids in (plan.get("stage_queues") or {}).items():
        if stage == "clustering":
            continue
        legacy_counts[f"{stage}_needs_work"] = len(ids or [])
    if "scoring" in (plan.get("stage_queues") or {}):
        legacy_counts["scoring_incomplete"] = len(plan["stage_queues"]["scoring"])
    out["issue_counts"] = {**legacy_counts, **(plan.get("issue_counts") or {})}
    return out
