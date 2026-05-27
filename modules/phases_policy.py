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


def explain_phase_run_decision(
    image_id: int,
    phase_code,
    current_executor_version=None,
    force_run: bool = False,
) -> Dict[str, Any]:
    """Return structured diagnostics for run/skip decision."""
    code = phase_code.value if hasattr(phase_code, "value") else str(phase_code)
    active_version = get_phase_executor_version(code, current_executor_version)
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
        decision["reason"] = "missing_phase_status"
        return decision

    status = (stored.get("status") or PhaseStatus.NOT_STARTED).strip()
    stored_version = stored.get("executor_version")
    decision["stored_status"] = status
    decision["stored_executor_version"] = stored_version

    if status in (PhaseStatus.NOT_STARTED, PhaseStatus.FAILED):
        decision["reason"] = f"status_{status}"
        return decision

    if status == PhaseStatus.RUNNING:
        decision["should_run"] = False
        decision["reason"] = "already_running"
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
        if not db.is_image_culling_complete(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_cull_decision"
            return decision
        if db.is_image_culling_similarity_artefacts_missing(image_id):
            decision["should_run"] = True
            decision["reason"] = "missing_similarity_artefacts"
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

