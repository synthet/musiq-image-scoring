"""Just-in-time run planning: stale/missing image×phase work in scope."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from modules import db
from modules.phase_work_claims import count_claimed_by_other
from modules.phases_policy import explain_phase_run_decision

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


def _images_in_scope(scope_paths: list[str]) -> list[int]:
    return db._query_image_ids_by_condition_for_scope(scope_paths, "1=1")


def _apply_preflight(scope_paths: list[str]) -> dict[str, int]:
    actions = {"reconciled_rows": 0, "backfilled_index_meta": 0, "phantom_scores_finalized": 0}
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
    # Finalize phantom-scored images before the stage queues are built. Such an image has
    # per-model rows but a NULL ``images.score_general`` and a non-terminal scoring phase
    # row, which wedges auto-drive: the scoring predicate below reports no work (the model
    # rows exist) so the phase is dropped from the run, while the folder bucketer keeps
    # reading ``not_started`` and re-queues the folder — and culling then aborts with
    # "missing score_general". Finalizing here recomputes the composites from the stored
    # rows (no re-inference) and flips the phase, so the scope actually converges.
    try:
        from modules.phantom_score_finalize import finalize_phantom_scores

        for p in scope_paths or []:
            summary = finalize_phantom_scores(scope_path=p, dry_run=False)
            actions["phantom_scores_finalized"] += int(summary.get("composites_backfilled") or 0)
    except Exception:
        logger.exception("run_phase_planner: phantom score finalize failed")
    return actions


def _needs_work_for_phase(
    image_id: int,
    phase_code: str,
    *,
    prefetched_statuses: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    decision = explain_phase_run_decision(
        image_id,
        phase_code,
        force_run=False,
        prefetched_statuses=prefetched_statuses,
    )
    return bool(decision.get("should_run")), str(decision.get("reason") or "")


def _bulk_phase_status_enabled() -> bool:
    """Kill switch: ``auto_drive.bulk_phase_status`` (default True).

    Lets the per-image status fetch be restored without a redeploy if the bulk
    path ever diverges from :func:`db.get_image_phase_statuses`.
    """
    try:
        from modules.config import get_config_value

        return bool(get_config_value("auto_drive.bulk_phase_status", default=True))
    except Exception:
        return True


def plan_scope(
    scope_paths: list[str],
    stage_codes: list[str] | None = None,
    *,
    dry_run: bool = True,
    job_id: int | None = None,
    exclude_claimed: bool = True,
    include_stale_executor: bool = True,
) -> dict[str, Any]:
    """Build a scope plan with per-stage queues and reason counts."""
    selected = {_normalize_stage_code(str(s)) for s in (stage_codes or []) if str(s).strip()}
    if not selected:
        selected = set(DEFAULT_STAGES)

    actions = {
        "reconciled_rows": 0,
        "backfilled_index_meta": 0,
        "phantom_scores_finalized": 0,
        "scoring_fix_targets": 0,
    }
    if not dry_run:
        actions.update(_apply_preflight(scope_paths))

    image_ids = _images_in_scope(scope_paths)
    # Prefetch every image's phase-status map once for the whole scope so the
    # per-(image, stage) decision below is in-memory instead of an N+1 over the
    # folder. Gated so it can be turned off if the bulk path ever diverges.
    statuses_by_image: dict[int, dict[str, Any]] = {}
    if image_ids and _bulk_phase_status_enabled():
        try:
            statuses_by_image = db.get_image_phase_statuses_bulk(image_ids) or {}
        except Exception:
            logger.exception(
                "run_phase_planner: bulk phase-status prefetch failed; "
                "falling back to per-image lookups"
            )
            statuses_by_image = {}
    issue_counts: dict[str, int] = defaultdict(int)
    issue_counts_by_reason: dict[str, int] = defaultdict(int)
    ignored_counts: dict[str, int] = defaultdict(int)
    ignored_counts_by_reason: dict[str, int] = defaultdict(int)
    stage_queues: dict[str, list[int]] = {}

    for stage in sorted(selected):
        queue: list[int] = []
        for iid in image_ids:
            needs, reason = _needs_work_for_phase(
                iid, stage, prefetched_statuses=statuses_by_image.get(iid)
            )
            if not needs:
                continue
            bucket = _reason_bucket(reason)
            if bucket == "stale_executor" and not include_stale_executor:
                ignored_counts_by_reason[bucket] += 1
                ignored_counts[f"{stage}_{bucket}"] = ignored_counts.get(f"{stage}_{bucket}", 0) + 1
                continue
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

    unique_issue_ids: set[int] = set()
    for ids in stage_queues.values():
        unique_issue_ids.update(int(i) for i in ids)

    return {
        "issue_counts": dict(issue_counts),
        "issue_counts_by_reason": dict(issue_counts_by_reason),
        "ignored_counts": dict(ignored_counts),
        "ignored_counts_by_reason": dict(ignored_counts_by_reason),
        "stage_queues": stage_queues,
        "actions": actions,
        "issue_hits": int(sum(issue_counts_by_reason.values())),
        "repaired": (
            actions["reconciled_rows"]
            + actions["backfilled_index_meta"]
            + actions["phantom_scores_finalized"]
        )
        if not dry_run
        else 0,
        "skipped": len(unique_issue_ids) if dry_run else 0,
        "failed": 0,
        "dry_run": bool(dry_run),
    }


def plan_phase(
    scope_paths: list[str],
    phase_code: str,
    *,
    job_id: int | None = None,
    dry_run: bool = False,
    exclude_claimed: bool = True,
    include_stale_executor: bool = True,
) -> list[int]:
    stage = _normalize_stage_code(phase_code)
    plan = plan_scope(
        scope_paths,
        [stage],
        dry_run=dry_run,
        job_id=job_id,
        exclude_claimed=exclude_claimed,
        include_stale_executor=include_stale_executor,
    )
    return list(plan.get("stage_queues", {}).get(stage) or [])


def to_legacy_repair_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Shape compatible with historical validation-repair consumers."""
    out = dict(plan)
    legacy_counts: dict[str, int] = {}
    for stage, ids in (plan.get("stage_queues") or {}).items():
        if stage == "clustering":
            continue
        legacy_counts[f"{stage}_needs_work"] = len(ids or [])
    if "scoring" in (plan.get("stage_queues") or {}):
        legacy_counts["scoring_incomplete"] = len(plan["stage_queues"]["scoring"])
    out["issue_counts"] = {**legacy_counts, **(plan.get("issue_counts") or {})}
    return out
