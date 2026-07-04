"""API routes: electron runs lifecycle (extracted from electron.py)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from modules import db
from modules.api.routers.electron_helpers import (
    api_module,
    logger,
    _join_runner_threads,
    _stop_runner_for_job_row,
    _stop_runner_for_phase,
)
from modules.api.routers.electron_models import ForceRunRequest, RunSubmitRequest
from modules.api.routers.electron_run_helpers import (
    create_retry_job,
    reset_ghost_runners,
    resume_job_inplace,
)
from modules.api.routers.electron_scope_helpers import (
    normalize_scope_path_input,
    scope_resolve_path,
)
from modules.api_helpers import _job_phases_for_run_display, _job_supports_execution_report
from modules.job_description import augment_queue_payload_for_audit, build_run_submit_description
from modules.run_manifest import REASON_SOURCE_MANUAL_SUBMIT, attach_run_reason, build_manual_submit_summary
from modules.run_modes import CANONICAL_RUN_MODE, resolve_run_mode_flags

def create_electron_runs_lifecycle_router() -> APIRouter:
    router = APIRouter()

    @router.post("/runs/submit", summary="Submit a new Run")
    async def submit_run(request: RunSubmitRequest = Body(...)):
        from modules import db
        from modules.phases import (
            PhaseCode,
            assert_prereqs_for_scope,
            normalize_phase_codes,
            sort_phase_value_strings,
        )
        scope_paths = [normalize_scope_path_input(p) for p in request.scope_paths]
        scope_paths = [p for p in scope_paths if p]
        if not scope_paths:
            raise HTTPException(status_code=400, detail="scope_paths must not be empty")
        # Resolve each scope path to a local OS path (e.g. WSL /mnt/d/... → D:/ on Windows)
        # so the job dispatcher and runners see paths that actually exist on this host.
        scope_paths = [scope_resolve_path(p) for p in scope_paths]
        primary_path = scope_paths[0]

        # bird_species is not a pipeline PhaseCode — handle it before normalize_phase_codes.
        raw_stages = list(request.stages or [])
        want_bird_species = "bird_species" in raw_stages
        pipeline_stages = [s for s in raw_stages if s != "bird_species"]

        phases = normalize_phase_codes(pipeline_stages) if pipeline_stages else None
        phase_values = [p.value for p in phases] if phases else None

        # Derive job_type and phase_code from stages so JobDispatcher can route the job.
        # Routing:
        # - indexing -> IndexingRunner
        # - metadata -> MetadataRunner
        # - score    -> ScoringRunner
        # - keywords -> TaggingRunner
        # - culling  -> SelectionRunner
        
        phase_code = "scoring"
        job_type = "scoring"
        if phases:
            # We use the first phase in the requested set to determine the entry runner
            # (Subsequent phases are handled by the PipelineOrchestrator)
            first_p = phases[0]
            if first_p == PhaseCode.INDEXING:
                phase_code = "indexing"
                job_type = "indexing"
            elif first_p == PhaseCode.METADATA:
                phase_code = "metadata"
                job_type = "metadata"
            elif first_p == PhaseCode.SCORING:
                phase_code = "scoring"
                job_type = "scoring"
            elif first_p == PhaseCode.KEYWORDS:
                phase_code = "keywords"
                job_type = "tagging"
            elif first_p == PhaseCode.CULLING:
                phase_code = "culling"
                job_type = "selection"
        elif want_bird_species:
            # bird_species is the only requested stage
            phase_code = "bird_species"
            job_type = "bird_species"
            phase_values = ["bird_species"]

        # SPA workflow expects job_phases rows; clients may omit `stages` (or send []).
        if not phase_values:
            if job_type == "tagging":
                phase_values = [PhaseCode.KEYWORDS.value]
            elif job_type == "selection":
                # For selection, we want clustering/selection logic + metadata (XMP writing)
                phase_values = [PhaseCode.CULLING.value, PhaseCode.METADATA.value]
            else:
                phase_values = [
                    PhaseCode.INDEXING.value,
                    PhaseCode.METADATA.value,
                    PhaseCode.SCORING.value,
                ]

        if want_bird_species and phase_values and "bird_species" not in phase_values:
            phase_values = list(phase_values) + ["bird_species"]
        if phase_values:
            phase_values = sort_phase_value_strings(phase_values)

        try:
            prereq_miss = await asyncio.to_thread(
                assert_prereqs_for_scope,
                phase_values or [],
                scope_paths,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"scope prerequisite check failed: {e}") from e

        if prereq_miss:
            raise HTTPException(
                status_code=400,
                detail={"code": "missing_prerequisites", "missing": prereq_miss},
            )

        requested_phases = list(phase_values) if phase_values else None

        if phase_values and not request.plan_dry_run:
            from modules.runs_autodrive import phases_with_work_from_repair_plan

            try:
                narrowed = await asyncio.to_thread(
                    phases_with_work_from_repair_plan,
                    scope_paths,
                    requested_phases,
                    dry_run=True,
                    include_stale_executor=True,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"run planning failed: {e}") from e
            if not narrowed:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "nothing_to_queue",
                        "message": "No stale or missing work for the requested stages in this scope.",
                        "requested_phases": requested_phases,
                    },
                )
            phase_values = narrowed
            phases = normalize_phase_codes(phase_values)
            first_p = phases[0]
            if first_p == PhaseCode.INDEXING:
                phase_code = "indexing"
                job_type = "indexing"
            elif first_p == PhaseCode.METADATA:
                phase_code = "metadata"
                job_type = "metadata"
            elif first_p == PhaseCode.SCORING:
                phase_code = "scoring"
                job_type = "scoring"
            elif first_p == PhaseCode.KEYWORDS:
                phase_code = "keywords"
                job_type = "tagging"
            elif first_p == PhaseCode.CULLING:
                phase_code = "culling"
                job_type = "selection"
            elif first_p == PhaseCode.BIRD_SPECIES:
                phase_code = "bird_species"
                job_type = "bird_species"

        mode_flags = resolve_run_mode_flags(CANONICAL_RUN_MODE)

        payload = {
            "scope_type": request.scope_type,
            "scope_paths": scope_paths,
            "input_path": primary_path,
            "run_mode": CANONICAL_RUN_MODE,
            "skip_done": mode_flags["skip_done"],
            "skip_existing": mode_flags["skip_existing"],
            "force_rerun": mode_flags["force_rerun"],
            "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
            "overwrite": mode_flags["overwrite"],
            "force_rescan": mode_flags["force_rescan"],
            "phases": phase_values,
            "target_phases": phase_values,
            "generate_captions": bool(request.generate_captions),
            "generate_accessibility": bool(request.generate_accessibility),
            "post_run_audit": True,
        }
        payload = augment_queue_payload_for_audit(payload, trigger="api", tool_id="run_submit")
        run_description = build_run_submit_description(
            scope_type=request.scope_type,
            scope_paths=scope_paths,
            run_mode=CANONICAL_RUN_MODE,
            phase_values=phase_values,
            client_description=request.description,
        )
        if request.post_run_audit is not None:
            payload["post_run_audit"] = bool(request.post_run_audit)
        try:
            repair_plan = await asyncio.to_thread(
                db.build_validation_repair_plan,
                scope_paths,
                phase_values or [],
                bool(request.plan_dry_run),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"run planning failed: {e}") from e

        if request.plan_dry_run:
            return {"success": True, "plan": repair_plan, "dry_run": True}

        payload["repair_plan_summary"] = repair_plan
        payload["resolved_image_ids_by_stage"] = repair_plan.get("stage_queues", {})
        if phase_values:
            first = str(phase_values[0]).strip().lower()
            first_ids = (repair_plan.get("stage_queues", {}) or {}).get(first)
            if isinstance(first_ids, list):
                payload["resolved_image_ids"] = first_ids
        payload["skip_existing"] = False
        reason_summary, reason_criteria = build_manual_submit_summary(
            scope_paths=scope_paths,
            enqueued_phases=phase_values or [],
            requested_phases=requested_phases,
            repair_plan=repair_plan,
        )
        reason_criteria["run_mode"] = CANONICAL_RUN_MODE
        payload = attach_run_reason(
            payload,
            source=REASON_SOURCE_MANUAL_SUBMIT,
            summary=reason_summary,
            criteria=reason_criteria,
            trigger="api",
            tool_id="run_submit",
        )
        try:
            job_id, position = await asyncio.wait_for(
                asyncio.to_thread(
                    db.enqueue_job_with_phases,
                    primary_path,
                    phase_code,
                    job_type,
                    payload,
                    run_description,
                    phase_values,
                    "queued",
                ),
                timeout=30.0,
            )
            return {"run_id": job_id, "queue_position": position, "success": True}
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Database operation timed out. The database may be busy or unreachable.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/{run_id}/pause", summary="Soft-pause a running Run")
    async def pause_run(run_id: int):
        """Pause: mark job paused, stop the runner, wait for the batch thread, reconcile in-flight images."""

        def _sync_pause() -> dict:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            if job.get("status") != "running":
                raise HTTPException(
                    status_code=400,
                    detail=f"Run {run_id} is not running (status={job.get('status')})",
                )
            try:
                db.update_job_status(run_id, "paused", "user_pause")
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
            _stop_runner_for_job_row(job)
            _join_runner_threads(per_thread_timeout=4.0)
            try:
                db.reconcile_stale_running_phases_for_jobs(
                    [run_id],
                    error_message=db.GRACEFUL_PAUSE_MSG,
                    in_flight_to="not_started",
                )
            except Exception:
                logger.exception("pause_run: reconcile failed for run_id=%s", run_id)
            return {"success": True, "message": f"Run {run_id} paused"}

        try:
            return await asyncio.to_thread(_sync_pause)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/{run_id}/resume", summary="Resume a paused Run")
    async def resume_run(run_id: int):
        """Resume a paused/interrupted run in-place (same run_id).

        Requeues the same job row. Completed/skipped phases are preserved;
        incomplete phases are reset so the dispatcher picks them up.
        """
        from modules import db
        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            if job.get("status") not in ("paused", "interrupted"):
                raise HTTPException(status_code=400, detail=f"Run {run_id} cannot be resumed (status={job.get('status')})")

            # Update payload to skip_done=True
            payload_raw = job.get("queue_payload") or "{}"
            try:
                payload = json.loads(payload_raw)
                if isinstance(payload, str):
                    logger.warning("resume_run: double-encoded queue_payload detected on run_id=%s; decoding again", run_id)
                    payload = json.loads(payload)
            except Exception:
                payload = {}
            payload["skip_done"] = True
            db.update_job_payload(run_id, json.dumps(payload))

            # Verify job has a phase plan before requeuing
            phases = db.get_job_phases(run_id)
            if not phases:
                raise HTTPException(status_code=409, detail=f"Run {run_id} has no phase plan — cannot resume. Use retry instead.")

            # Requeue the same row
            _, position = db.requeue_job(run_id)

            # Preserve completed/skipped phases; reset incomplete ones
            db.resume_job_phases(run_id)

            return {"success": True, "run_id": run_id, "queue_position": position}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/{run_id}/cancel", summary="Cancel a Run")
    async def cancel_run(run_id: int):
        from modules import db
        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            status = str(job.get("status") or "").strip().lower()
            cancel_method = None
            if status == "queued":
                result = db.request_cancel_job(run_id)
                if not result.get("success"):
                    raise HTTPException(status_code=409, detail=f"Could not cancel run {run_id}: {result.get('reason')}")
                cancel_method = "cancel_requested"
            elif status in ("pending", "running", "paused", "interrupted", "cancel_requested", "restarting"):
                db.update_job_status(run_id, "cancelled")
                cancel_method = "update_status"
                # Stop the active runner when running (DB update alone doesn't stop the process)
                if status == "running":
                    state = api_module()._job_dispatcher.get_state()
                    active = state.get("active_runner")
                    stopped = _stop_runner_for_phase(active) if active else False
                    if not stopped:
                        for ph in (
                            "indexing",
                            "metadata",
                            "scoring",
                            "tagging",
                            "clustering",
                            "selection",
                            "bird_species",
                        ):
                            if _stop_runner_for_phase(ph):
                                break
            else:
                raise HTTPException(status_code=400, detail=f"Cannot cancel run with status={status}")
            return {"success": True, "message": f"Run {run_id} canceled", "method": cancel_method}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/{run_id}/force", summary="Force-start a stuck Run")
    async def force_run(run_id: int, body: ForceRunRequest):
        """Force-unstick a run that the normal Resume/Retry flow cannot handle.

        Branches on current status:
        - **running** (ghost — no live runner thread): marks interrupted, then re-enqueues.
        - **queued**: resets the dispatcher's ghost is_running flag if no runner thread
          is actually alive, so the dispatcher can dequeue again.
        - **paused/interrupted**: delegates to the normal resume flow.
        - Terminal states: delegates to the normal retry flow.

        Requires ``confirm: true`` in the request body.
        """
        from modules import db

        if not body.confirm:
            raise HTTPException(status_code=400, detail="Set confirm=true to proceed")

        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

            status = (job.get("status") or "").strip().lower()
            actions_taken = []

            # --- Branch on status --------------------------------------------
            if status == "running":
                # Check if there's actually a live runner thread for this job
                state = api_module()._job_dispatcher.get_state()
                active_runner_name = state.get("active_runner")
                runner_map = {
                    "scoring": api_module()._scoring_runner,
                    "tagging": api_module()._tagging_runner,
                    "clustering": api_module()._clustering_runner,
                    "selection": api_module()._selection_runner,
                }
                runner = runner_map.get(active_runner_name) if active_runner_name else None
                thread = getattr(runner, "_thread", None) if runner else None
                thread_alive = thread is not None and thread.is_alive()

                if thread_alive:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Run {run_id} has a live runner thread ({active_runner_name}). "
                               "Use Cancel first, then Retry.",
                    )

                # Ghost running — mark interrupted, clear runners, resume in-place
                db.update_job_status(run_id, "interrupted", log="Force-interrupted (ghost running)")
                actions_taken.append(f"marked {run_id} interrupted")
                cleared = reset_ghost_runners()
                if cleared:
                    actions_taken.append(f"reset ghost is_running on: {', '.join(cleared)}")

                # In-place resume: same job id back to queued
                _, pos = resume_job_inplace(job)
                actions_taken.append(f"requeued run {run_id} (position {pos})")
                return {"success": True, "run_id": run_id, "queue_position": pos, "actions": actions_taken}

            elif status == "queued":
                # The job is queued but nothing is being dispatched —
                # likely ghost is_running on a runner is blocking the dispatcher.
                cleared = reset_ghost_runners()
                if cleared:
                    actions_taken.append(f"reset ghost is_running on: {', '.join(cleared)}")
                else:
                    actions_taken.append("no ghost runners found — dispatcher should dequeue normally")
                return {"success": True, "run_id": run_id, "actions": actions_taken}

            elif status in ("paused", "interrupted"):
                # In-place resume: same job id
                _, pos = resume_job_inplace(job)
                actions_taken.append(f"requeued run {run_id} (position {pos})")
                return {"success": True, "run_id": run_id, "queue_position": pos, "actions": actions_taken}

            elif status in ("completed", "failed", "canceled", "cancelled"):
                # Terminal — must create a new job (Retry semantics)
                new_id, pos = create_retry_job(job, "force_run")
                actions_taken.append(f"retried as new job {new_id} (position {pos})")
                return {"success": True, "run_id": new_id, "queue_position": pos, "actions": actions_taken}

            else:
                raise HTTPException(status_code=400, detail=f"Unhandled status: {status}")

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("force_run failed for run_id=%s", run_id)
            raise HTTPException(status_code=500, detail=str(e))
    @router.post("/runs/{run_id}/retry", summary="Retry a failed/canceled Run")
    async def retry_run(run_id: int):
        from modules import db
        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            TERMINAL_STATUSES = {"failed", "interrupted", "canceled", "cancelled", "completed"}
            if job.get("status", "").lower() not in TERMINAL_STATUSES:
                raise HTTPException(status_code=409, detail=f"Run {run_id} cannot be retried (status={job.get('status')})")
            new_job_id, position = create_retry_job(job, "retry_run")
            return {"success": True, "run_id": new_job_id, "queue_position": position}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/runs/{run_id}/stages", summary="Get all stages for a Run")
    async def get_run_stages(run_id: int):
        from modules import db
        from modules.phases import sort_job_phase_rows_for_display

        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            phases = db.get_job_phases(run_id)
            phases = _job_phases_for_run_display(job, phases)
            if not phases:
                return []
            return sort_job_phase_rows_for_display(phases)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/{run_id}/stages/{stage_code}/retry", summary="Retry a specific stage")
    async def retry_run_stage(run_id: int, stage_code: str):
        from modules import db
        try:
            db.force_reset_job_phase_to_queued(run_id, stage_code)
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/{run_id}/stages/{stage_code}/skip", summary="Skip a specific stage")
    async def skip_run_stage(run_id: int, stage_code: str):
        from modules import db
        try:
            db.set_job_phase_state(run_id, stage_code, "skipped")
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/runs/{run_id}/stages/{stage_code}/steps", summary="Get steps for a stage")
    async def get_stage_steps(run_id: int, stage_code: str):
        """Returns step-level telemetry for a stage (e.g. individual ML model runs)."""
        from modules import db
        try:
            steps = db.get_job_steps(run_id, stage_code)
            return steps or []
        except AttributeError:
            return []  # get_job_steps not yet implemented — return empty
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/runs/{run_id}/stages/{stage_code}/items", summary="Get work items for a stage")
    async def get_stage_work_items(
        run_id: int,
        stage_code: str,
        offset: int = 0,
        limit: int = 50,
    ):
        """Returns individual images and their processing status for a stage."""
        from modules import db
        try:
            items_data = db.get_job_stage_images(run_id, stage_code, offset=offset, limit=limit)
            if items_data is None:
                return {"items": [], "total": 0}
            return items_data
        except AttributeError:
            return {"items": [], "total": 0}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/runs/{run_id}/diagnostics",
        summary="Run diagnostics (post-run audit + per-phase image_phase_status counts)",
        description="""
        Returns ``post_run_audit`` from the job queue_payload (when present) and aggregated
        ``image_phase_status`` counts for this run. Use with ``GET .../stages/{stage_code}/items``
        for per-image details.
        """,
    )
    async def get_run_diagnostics(run_id: int):
        from modules import db
        try:
            out = await asyncio.to_thread(db.get_run_diagnostics, run_id)
            if out.get("error") == "job_not_found":
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            return out
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/runs/{run_id}/report",
        summary="Get job execution report",
        description="Returns the structured execution report (report_json) for a completed job.",
    )
    async def get_run_report(run_id: int):
        from modules import db
        try:
            job = await asyncio.to_thread(db.get_job_by_id, run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            phases = await asyncio.to_thread(db.get_job_phases, run_id)
            phase_codes = [str((p or {}).get("phase_code") or "") for p in (phases or [])]
            if not _job_supports_execution_report(dict(job), phase_codes):
                return {
                    "available": False,
                    "reason": "unsupported_run_type",
                    "message": "Execution report is not available for this run type.",
                    "run_type": str(job.get("job_type") or ""),
                }
            report = await asyncio.to_thread(db.get_job_report, run_id)
            if report is None:
                raise HTTPException(status_code=404, detail=f"No execution report for run {run_id}")
            return {
                "available": True,
                "report": report,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/runs/{run_id}/report/images",
        summary="Get per-image execution actions",
        description=(
            "Paginated per-image action log with before/after score snapshots. "
            "Filter by phase_code and/or action (processed, skipped, failed, unchanged)."
        ),
    )
    async def get_run_report_images(
        run_id: int,
        phase_code: Optional[str] = None,
        action: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ):
        from modules import db
        try:
            return await asyncio.to_thread(
                db.get_job_image_actions, run_id, phase_code, action, offset, limit
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return router
