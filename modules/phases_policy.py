"""Phase execution policy helpers.

Centralizes decision making for whether a phase should execute for an image
based on stored IMAGE_PHASE_STATUS and registered PhaseRegistry executor
versions.
"""

from __future__ import annotations

from typing import Any, Dict

from modules import db
from modules.phases import PhaseRegistry, PhaseStatus


def get_phase_executor_version(phase_code, current_executor_version=None) -> str | None:
    """Resolve current executor version from explicit input or PhaseRegistry."""
    if current_executor_version:
        return str(current_executor_version)

    code = phase_code.value if hasattr(phase_code, "value") else str(phase_code)
    executor = PhaseRegistry.get(code)
    if executor and executor.executor_version:
        return str(executor.executor_version)
    return None


def _phase_data_complete(image_id: int, code: str) -> bool | None:
    """Return True/False if the phase has a data-completeness checker, else None."""
    from modules.phases import PhaseCode
    if code == PhaseCode.SCORING.value:
        return bool(db.is_image_scoring_complete(image_id))
    if code == PhaseCode.KEYWORDS.value:
        return bool(db.is_image_keywords_complete(image_id))
    if code == PhaseCode.METADATA.value:
        if db.get_image_metadata_asset_gap_reason(image_id):
            return False
        return bool(db.is_image_metadata_complete(image_id))
    if code == PhaseCode.INDEXING.value:
        return bool(db.is_image_indexing_complete(image_id))
    if code == PhaseCode.BIRD_SPECIES.value:
        return bool(db.is_image_bird_species_complete(image_id))
    if code == PhaseCode.CULLING.value:
        return bool(db.is_image_culling_work_complete(image_id))
    return None


def explain_phase_run_decision(
    image_id: int,
    phase_code,
    current_executor_version=None,
    force_run: bool = False,
    prefetched_statuses: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return structured diagnostics for run/skip decision.

    ``prefetched_statuses`` is an optional per-image phase-status map (same shape
    as :func:`db.get_image_phase_statuses`). When provided, it is used instead of
    issuing a per-image query — set-based callers (e.g. the run planner) pass a
    bulk-fetched slice to avoid an N+1 over a whole folder.
    """
    code = phase_code.value if hasattr(phase_code, "value") else str(phase_code)
    active_version = get_phase_executor_version(code, current_executor_version)
    if prefetched_statuses is not None:
        statuses = prefetched_statuses
    else:
        statuses = db.get_image_phase_statuses(image_id) or {}
    stored = statuses.get(code)

    decision = {
        "image_id": image_id,
        "phase_code": code,
        "should_run": True,
        "reason": "not_started",
        "force_run": bool(force_run),
        "current_executor_version": active_version,
        "stored_status": None,
        "stored_executor_version": None,
    }

    if force_run:
        decision["reason"] = "force_run_requested"
        return decision

    if not stored:
        # No phase_status row. Before queueing, check whether the underlying
        # data is already present (e.g. backfilled via image_model_scores)
        # so we don't re-run completed work when the row was never written.
        if _phase_data_complete(image_id, code) is True:
            decision["should_run"] = False
            decision["reason"] = "data_complete_missing_phase_status"
            return decision
        decision["reason"] = "missing_phase_status"
        return decision

    status = (stored.get("status") or PhaseStatus.NOT_STARTED).strip()
    stored_version = stored.get("executor_version")
    decision["stored_status"] = status
    decision["stored_executor_version"] = stored_version

    if status in (PhaseStatus.NOT_STARTED, PhaseStatus.FAILED):
        # phase_status says not_started/failed, but a previous run may have
        # populated the data anyway (interrupted commit, manual backfill,
        # legacy migration). Skip the rerun when the data is complete.
        if _phase_data_complete(image_id, code) is True:
            decision["should_run"] = False
            decision["reason"] = f"data_complete_status_{status}"
            return decision
        decision["reason"] = f"status_{status}"
        return decision

    if status == PhaseStatus.RUNNING:
        decision["should_run"] = False
        decision["reason"] = "already_running"
        return decision

    if status == PhaseStatus.SKIPPED:
        # Terminal, like the rest of the codebase treats it (see
        # ``runs_autodrive.COMPLETE_PHASE_STATUSES`` and the ``NOT IN ('done','skipped')``
        # incomplete-work predicates). A skip means the executor deliberately produced no
        # work product (e.g. the tagger's "no tags produced"), so the data-validation below
        # would always find the data missing and re-queue the image forever. Only a new
        # executor version justifies another attempt.
        if active_version and stored_version and stored_version != active_version:
            decision["reason"] = "executor_version_changed"
            return decision
        decision["should_run"] = False
        decision["reason"] = "already_skipped_current_executor"
        return decision

    # status == done (or unknown terminal): compare versions when both are known.
    # Legacy rows often have executor_version=NULL; treat as unknown and fall through
    # to data-validation instead of forcing executor_version_changed.
    if active_version and stored_version and stored_version != active_version:
        decision["reason"] = "executor_version_changed"
        return decision

    # DATA VALIDATION: Even if status is 'done', check if the actual data is present.
    # This addresses the 'falsely done' state where status is 'done' but data is missing.
    from modules.phases import PhaseCode
    if code == PhaseCode.SCORING.value:
        if not db.is_image_scoring_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_scoring_data"
            return decision
    elif code == PhaseCode.KEYWORDS.value:
        if not db.is_image_keywords_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_keyword_data"
            return decision
    elif code == PhaseCode.METADATA.value:
        asset_gap = db.get_image_metadata_asset_gap_reason(image_id)
        if asset_gap:
            decision["should_run"] = True
            decision["reason"] = asset_gap
            return decision
        if not db.is_image_metadata_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_metadata"
            return decision
    elif code == PhaseCode.INDEXING.value:
        if not db.is_image_indexing_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_indexing_data"
            return decision
    elif code == PhaseCode.BIRD_SPECIES.value:
        if not db.is_image_bird_species_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_bird_species_data"
            return decision
    elif code == PhaseCode.CULLING.value:
        if not db.is_image_culling_work_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_culling_work"
            return decision

    decision["should_run"] = False
    decision["reason"] = "already_done_current_executor"
    return decision


def should_run_phase(image_id: int, phase_code, current_executor_version=None, force_run: bool = False) -> bool:
    """Policy predicate used by runners before phase execution."""
    return explain_phase_run_decision(
        image_id=image_id,
        phase_code=phase_code,
        current_executor_version=current_executor_version,
        force_run=force_run,
    )["should_run"]

