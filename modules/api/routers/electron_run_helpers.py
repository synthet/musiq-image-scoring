"""Run lifecycle helpers for electron runs API routes."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException

from modules.api.routers.electron_helpers import api_module
from modules.run_manifest import (
    REASON_SOURCE_FORCE_RUN,
    REASON_SOURCE_RETRY,
    attach_run_reason,
    build_retry_summary,
)

logger = logging.getLogger(__name__)


def reset_ghost_runners() -> list[str]:
    """Reset is_running on runners whose thread is no longer alive."""
    cleared = []
    for name, runner in [
        ("scoring", api_module()._scoring_runner),
        ("tagging", api_module()._tagging_runner),
        ("clustering", api_module()._clustering_runner),
        ("selection", api_module()._selection_runner),
        ("indexing", api_module()._indexing_runner),
        ("metadata", api_module()._metadata_runner),
        ("bird_species", api_module()._bird_species_runner),
    ]:
        if runner is None:
            continue
        thread = getattr(runner, "_thread", None)
        thread_alive = thread is not None and thread.is_alive()
        if name == "selection":
            lock = getattr(runner, "_lock", None)
            if lock:
                with lock:
                    if runner.is_running and not thread_alive:
                        runner.is_running = False
                        cleared.append(name)
        elif getattr(runner, "is_running", False) and not thread_alive:
            runner.is_running = False
            cleared.append(name)
    return cleared


def resume_job_inplace(job: dict) -> tuple[int, int]:
    """Resume a job in-place: same id back to queued, phases preserved. Returns (job_id, position)."""
    from modules import db

    run_id = job["id"]
    payload_raw = job.get("queue_payload") or "{}"
    try:
        payload = json.loads(payload_raw)
        if isinstance(payload, str):
            logger.warning(
                "resume_job_inplace: double-encoded queue_payload detected on run_id=%s; decoding again",
                run_id,
            )
            payload = json.loads(payload)
    except Exception:
        payload = {}
    payload["skip_done"] = True
    db.update_job_payload(run_id, json.dumps(payload))

    phases = db.get_job_phases(run_id)
    if not phases:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} has no phase plan — cannot resume. Use retry instead.",
        )

    _, position = db.requeue_job(run_id)
    db.resume_job_phases(run_id)
    return run_id, position


def create_retry_job(original_job: dict, source: str) -> tuple[int, int]:
    """Create a retry job from an original job. Returns (new_job_id, queue_position)."""
    from modules import db
    from modules.phases import sort_phase_value_strings

    payload_raw = original_job.get("queue_payload") or "{}"
    try:
        payload = json.loads(payload_raw)
        if isinstance(payload, str):
            payload = json.loads(payload)
    except Exception:
        payload = {}
    payload["skip_done"] = True

    orig_job_type = original_job.get("job_type", "scoring")
    _phase_code_map = {
        "indexing": "indexing",
        "metadata": "metadata",
        "scoring": "scoring",
        "tagging": "keywords",
        "clustering": "culling",
        "selection": "culling",
    }
    phase_code = _phase_code_map.get(orig_job_type, "scoring")

    prior = original_job.get("description")
    _retry_ui = "(retry from Runs UI)"
    _force_q = "(re-queued via force_run)"

    def _with_suffix(base: str, suffix: str) -> str:
        p = (base or "").strip()
        if not p:
            return ""
        return p if p.endswith(suffix) else f"{p} {suffix}"

    if source == "force_run":
        retry_desc = (
            _with_suffix(str(prior).strip() if prior else "", _force_q)
            if prior and str(prior).strip()
            else (
                f"Retry via force_run of job #{original_job.get('id')} ({orig_job_type}) "
                f"for {original_job.get('input_path') or ''}."
            )
        )
    else:
        retry_desc = (
            _with_suffix(str(prior).strip() if prior else "", _retry_ui)
            if prior and str(prior).strip()
            else (
                f"Retry of run #{original_job.get('id')} ({orig_job_type}) "
                f"for {original_job.get('input_path') or ''}."
            )
        )

    orig_phases = db.get_job_phases(original_job["id"])
    if orig_phases:
        phase_codes = sort_phase_value_strings([p["phase_code"] for p in orig_phases])
    else:
        _defaults = {
            "tagging": ["keywords"],
            "selection": ["culling", "metadata"],
            "clustering": ["culling"],
        }
        phase_codes = sort_phase_value_strings(
            _defaults.get(orig_job_type, ["indexing", "metadata", "scoring"])
        )

    reason_source = REASON_SOURCE_FORCE_RUN if source == "force_run" else REASON_SOURCE_RETRY
    payload = attach_run_reason(
        payload,
        source=reason_source,
        summary=build_retry_summary(
            source=reason_source,
            original_run_id=int(original_job.get("id") or 0),
            job_type=str(orig_job_type),
            input_path=original_job.get("input_path"),
        ),
        criteria={
            "retried_from_run_id": original_job.get("id"),
            "enqueued_phases": phase_codes,
            "original_job_type": orig_job_type,
        },
        trigger=str(payload.get("trigger") or "api"),
        tool_id=str(payload.get("tool_id") or source),
    )

    new_job_id, position = db.enqueue_job_with_phases(
        input_path=original_job.get("input_path", ""),
        phase_code=phase_code,
        job_type=orig_job_type,
        queue_payload=json.dumps(payload),
        description=retry_desc,
        phase_codes=phase_codes,
        first_phase_state="queued",
    )
    return new_job_id, position
