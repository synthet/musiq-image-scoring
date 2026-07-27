"""API routes: tasks (extracted from modules.api)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from modules import db
from modules.api import deps
from modules.api_helpers import (
    _decode_db_row_blobs,
    _job_supports_execution_report,
    _json_response_db,
    _normalize_incident_row,
    _normalize_jobs_table_row,
)
from modules.api_models import (
    ApiResponse,
    LifecycleControlRequest,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_tasks_router() -> APIRouter:
    router = APIRouter()
    # ========== Tasks (Unified Active State) ==========

    @router.get(
        "/tasks/active",
        response_model=dict[str, Any],
        summary="Get active tasks (unified)",
        description="""
        Returns a unified view of active tasks, workers, and jobs in a single response.
        Combines runner status, dispatcher state, and the currently running job.

        **Response Structure:**
        - runners: Status of scoring, tagging, clustering runners (is_running, progress, log)
        - dispatcher: Queue state (queue, queue_size, active_runner, is_dispatcher_running)
        - active_job: The currently running job if any, or null
        """
    )
    async def get_tasks_active(limit: int = 200):
        """Get unified active tasks, workers, and jobs."""
        from modules import db
        try:
            # Runners status (same logic as get_all_status)
            runners = {
                "scoring": {"available": False},
                "tagging": {"available": False},
                "clustering": {"available": False}
            }
            if _api_module()._scoring_runner:
                try:
                    result = _api_module()._scoring_runner.get_status()
                    is_running, log, status_msg, current, total = result[:5]
                    runners["scoring"] = {
                        "available": True,
                        "is_running": is_running,
                        "status_message": status_msg,
                        "progress": {"current": current, "total": total},
                        "log": log[-2000:] if log else "",
                        "job_type": getattr(_api_module()._scoring_runner, 'job_type', None)
                    }
                except Exception as e:
                    runners["scoring"]["error"] = str(e)
            if _api_module()._tagging_runner:
                try:
                    result = _api_module()._tagging_runner.get_status()
                    is_running, log, status_msg, current, total = result[:5]
                    runners["tagging"] = {
                        "available": True,
                        "is_running": is_running,
                        "status_message": status_msg,
                        "progress": {"current": current, "total": total},
                        "log": log[-2000:] if log else ""
                    }
                except Exception as e:
                    runners["tagging"]["error"] = str(e)
            if _api_module()._clustering_runner:
                try:
                    result = _api_module()._clustering_runner.get_status()
                    is_running, log, status_msg, current, total = result[:5]
                    runners["clustering"] = {
                        "available": True,
                        "is_running": is_running,
                        "status_message": status_msg,
                        "progress": {"current": current, "total": total},
                        "log": log[-2000:] if log else ""
                    }
                except Exception as e:
                    runners["clustering"]["error"] = str(e)

            # Dispatcher state
            state = _api_module()._job_dispatcher.get_state()
            state["queue"] = db.get_queued_jobs(limit=limit)
            state["queue_size"] = len(state["queue"])
            dispatcher = state

            # Active job: first running job from recent jobs, or from active runner's job_id
            active_job = None
            active_runner = dispatcher.get("active_runner")
            if active_runner:
                # Try to get job_id from the active runner
                runner = None
                if active_runner == "scoring" and _api_module()._scoring_runner:
                    runner = _api_module()._scoring_runner
                elif active_runner == "tagging" and _api_module()._tagging_runner:
                    runner = _api_module()._tagging_runner
                elif active_runner == "clustering" and _api_module()._clustering_runner:
                    runner = _api_module()._clustering_runner
                job_id = getattr(runner, "job_id", None) if runner else None
                if job_id:
                    active_job = db.get_job_by_id(job_id)
            if not active_job:
                # Fallback: first running job from recent jobs
                recent = db.get_jobs(limit=20)
                for j in recent:
                    if (j.get("status") or "").lower() == "running":
                        active_job = j
                        break

            return {
                "runners": runners,
                "dispatcher": dispatcher,
                "active_job": active_job
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/jobs/recent",
        summary="Get recent jobs",
        description="""
        Returns a list of recent job history entries.
        
        Jobs are ordered by creation time (most recent first).
        Each job entry includes:
        - id: Unique job identifier
        - input_path: Path that was processed
        - status: Job status (pending, running, completed, failed, canceled, interrupted)
        - created_at: Job creation timestamp
        - current_phase / next_phase_index / runner_state: Persisted execution cursor fields
        - log: Job log output (if available)
        
        **Query Parameters:**
        - limit: Maximum number of jobs to return (default: 10, max: 1000)
        - offset: Skip this many jobs (newest-first order; default 0)
        - history: When true, only terminal statuses (completed/failed/canceled/interrupted);
          response is JSON `{"runs":[...],"total":N}` for pagination (default response remains a JSON array).
        """
    )
    async def get_recent_jobs(
        limit: int = 10,
        offset: int = 0,
        history: bool = Query(
            False,
            description="Terminal jobs only; JSON object with runs + total for pagination.",
        ),
        status: str = Query(
            None,
            description="Comma-separated status filter (e.g. 'running,paused,queued').",
        ),
    ):
        """Get recent job history."""
        from modules import db
        try:

            def _fetch_recent():
                status_filter = None
                if status:
                    status_filter = [s.strip().lower() for s in status.split(",")]
                if history:
                    rows = db.get_jobs(limit, offset, history_only=True, status_filter=status_filter)
                    total = db.count_jobs(history_only=True, status_filter=status_filter)
                    return rows, total
                rows = db.get_jobs(limit, offset, history_only=False, status_filter=status_filter)
                return rows, None

            jobs, total = await asyncio.wait_for(
                asyncio.to_thread(_fetch_recent),
                timeout=30.0,
            )
            result = [_normalize_jobs_table_row(dict(j)) for j in jobs]
            if history:
                return _json_response_db(
                    {"runs": result, "jobs": result, "total": int(total or 0)},
                    "GET /api/jobs/recent",
                )
            return _json_response_db({"runs": result, "jobs": result}, "GET /api/jobs/recent")
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Database operation timed out.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/jobs/queue",
        summary="Get queue state",
        description="Returns dispatcher state and currently queued jobs."
    )
    async def get_jobs_queue(limit: int = 200):
        from modules import db
        try:
            state = _api_module()._job_dispatcher.get_state()
            raw_queue = db.get_queued_jobs(limit=limit)
            state["queue"] = [_normalize_jobs_table_row(dict(x)) for x in raw_queue]
            state["queue_size"] = len(state["queue"])
            return _json_response_db(state, "GET /api/jobs/queue")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/jobs/{job_id}",
        summary="Get job details",
        description="""
        Returns detailed information for a specific job by ID.
        
        **Path Parameters:**
        - job_id: Integer job identifier
        
        **Returns:**
        - Full job record including status, timestamps, logs, etc.
        - 404 if job not found
        """
    )
    async def get_job_details(job_id: int):
        """Get details for a specific job."""
        from modules import db
        try:
            job = db.get_job_by_id(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            payload = _normalize_jobs_table_row(dict(job))
            payload["phases"] = [
                _decode_db_row_blobs(dict(p)) for p in db.get_job_phases(job_id)
            ]
            phase_codes = [str(p.get("phase_code") or "") for p in payload["phases"]]
            payload["capabilities"] = {
                "execution_report": _job_supports_execution_report(payload, phase_codes),
            }
            return _json_response_db(payload, f"GET /api/jobs/{job_id}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/incidents",
        summary="List image incidents",
        description="""
        Paginated append-only incidents (phase failures, validation, etc.) linked to images.
        PostgreSQL only; returns empty items when the engine is not PostgreSQL.

        Query: limit, offset, folder_id, job_id, phase_code, kind, since (ISO-8601).
        """,
    )
    async def list_incidents(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        folder_id: int | None = None,
        job_id: int | None = None,
        phase_code: str | None = None,
        kind: str | None = None,
        since: str | None = Query(
            None,
            description="ISO-8601 datetime; return rows with created_at >= since",
        ),
    ):
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid since: {e}") from e
        try:
            raw = db.list_image_incidents(
                limit=limit,
                offset=offset,
                folder_id=folder_id,
                job_id=job_id,
                phase_code=phase_code,
                kind=kind,
                since=since_dt,
            )
            items = [_normalize_incident_row(dict(x)) for x in raw.get("items") or []]
            return _json_response_db(
                {"items": items, "total": int(raw.get("total") or 0)},
                "GET /api/incidents",
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/incidents/{incident_id}",
        summary="Get one image incident",
        description="Returns a single incident by id with file_path and phase_code.",
    )
    async def get_incident(incident_id: int):
        try:
            row = db.get_image_incident(incident_id)
            if not row:
                raise HTTPException(status_code=404, detail="Incident not found")
            return _json_response_db(
                _normalize_incident_row(dict(row)),
                f"GET /api/incidents/{incident_id}",
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/jobs/{job_id}/cancel",
        response_model=ApiResponse,
        summary="Cancel a queued job",
        description="Cancels queued jobs. Running jobs currently return running_not_supported."
    )
    async def cancel_job(job_id: int):
        from modules import db
        try:
            result = db.request_cancel_job(job_id)
            if not result.get("success"):
                if result.get("reason") == "not_found":
                    raise HTTPException(status_code=404, detail="Job not found")
                if result.get("reason") == "running_not_supported":
                    return ApiResponse(success=False, message="Running job cancellation is not supported yet", data=result)
                return ApiResponse(success=False, message="Job cannot be cancelled", data=result)
            return ApiResponse(success=True, message="Cancellation requested", data={"job_id": job_id, **result})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


    @router.post("/workflow-runs/{job_id}/pause", response_model=ApiResponse, summary="Pause workflow run")
    async def pause_workflow_run(job_id: int, request: LifecycleControlRequest):
        state = deps.control_job(job_id, "paused", request.reason)
        return ApiResponse(success=True, message="Workflow paused", data={"job": state})

    @router.post("/workflow-runs/{job_id}/resume", response_model=ApiResponse, summary="Resume workflow run")
    async def resume_workflow_run(job_id: int, request: LifecycleControlRequest):
        state = deps.control_job(job_id, "running", request.reason)
        return ApiResponse(success=True, message="Workflow resumed", data={"job": state})

    @router.post("/workflow-runs/{job_id}/restart", response_model=ApiResponse, summary="Restart workflow run")
    async def restart_workflow_run(job_id: int, request: LifecycleControlRequest):
        deps.control_job(job_id, "restarting", request.reason)
        state = deps.control_job(job_id, "queued", request.reason)
        return ApiResponse(success=True, message="Workflow restarting", data={"job": state})

    @router.post("/stage-runs/{job_id}/{phase_code}/pause", response_model=ApiResponse, summary="Pause stage run")
    async def pause_stage_run(job_id: int, phase_code: str, request: LifecycleControlRequest):
        rows = deps.control_stage(job_id, phase_code, "paused", request.reason)
        return ApiResponse(success=True, message="Stage paused", data={"phases": rows, "phase_code": phase_code})

    @router.post("/stage-runs/{job_id}/{phase_code}/resume", response_model=ApiResponse, summary="Resume stage run")
    async def resume_stage_run(job_id: int, phase_code: str, request: LifecycleControlRequest):
        rows = deps.control_stage(job_id, phase_code, "running", request.reason)
        return ApiResponse(success=True, message="Stage resumed", data={"phases": rows, "phase_code": phase_code})

    @router.post("/stage-runs/{job_id}/{phase_code}/restart", response_model=ApiResponse, summary="Restart stage run")
    async def restart_stage_run(job_id: int, phase_code: str, request: LifecycleControlRequest):
        deps.control_stage(job_id, phase_code, "restarting", request.reason)
        rows = deps.control_stage(job_id, phase_code, "queued", request.reason)
        return ApiResponse(success=True, message="Stage restarting", data={"phases": rows, "phase_code": phase_code})

    @router.post("/step-runs/{image_id}/{phase_code}/pause", response_model=ApiResponse, summary="Pause step run")
    async def pause_step_run(image_id: int, phase_code: str, request: LifecycleControlRequest):
        statuses = deps.control_step(image_id, phase_code, "paused", request.reason)
        return ApiResponse(success=True, message="Step paused", data={"image_id": image_id, "statuses": statuses})

    @router.post("/step-runs/{image_id}/{phase_code}/resume", response_model=ApiResponse, summary="Resume step run")
    async def resume_step_run(image_id: int, phase_code: str, request: LifecycleControlRequest):
        statuses = deps.control_step(image_id, phase_code, "running", request.reason)
        return ApiResponse(success=True, message="Step resumed", data={"image_id": image_id, "statuses": statuses})

    @router.post("/step-runs/{image_id}/{phase_code}/restart", response_model=ApiResponse, summary="Restart step run")
    async def restart_step_run(image_id: int, phase_code: str, request: LifecycleControlRequest):
        deps.control_step(image_id, phase_code, "restarting", request.reason)
        statuses = deps.control_step(image_id, phase_code, "queued", request.reason)
        return ApiResponse(success=True, message="Step restarting", data={"image_id": image_id, "statuses": statuses})

    @router.post(
        "/jobs/{job_id}/pause",
        response_model=ApiResponse,
        summary="Pause a queued job",
        description="Moves a queued job to paused state.",
    )
    async def pause_job(job_id: int):
        from modules import db
        try:
            result = db.pause_queue_job(job_id)
            if not result.get("success"):
                return ApiResponse(success=False, message="Job could not be paused", data={"job_id": job_id, **result})
            return ApiResponse(success=True, message="Job paused", data={"job_id": job_id, **result})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/jobs/{job_id}/restart",
        response_model=ApiResponse,
        summary="Restart a failed job",
        description="Re-queues a failed job and increments retry count.",
    )
    async def restart_job(job_id: int):
        from modules import db
        try:
            result = db.restart_failed_job(job_id)
            if not result.get("success"):
                return ApiResponse(success=False, message="Job could not be restarted", data={"job_id": job_id, **result})
            return ApiResponse(success=True, message="Job restarted", data={"job_id": job_id, **result})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/jobs/{job_id}/priority",
        response_model=ApiResponse,
        summary="Adjust job priority",
        description="Bumps queued/paused job priority by delta (default: 10).",
    )
    async def bump_priority(job_id: int, delta: int = 10):
        from modules import db
        try:
            result = db.bump_job_priority(job_id, delta=delta)
            if not result.get("success"):
                return ApiResponse(success=False, message="Priority not updated", data={"job_id": job_id, **result})
            return ApiResponse(success=True, message="Priority updated", data={"job_id": job_id, **result})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


    from modules.api.handler_registry import register_handlers

    register_handlers(
        {
            "get_tasks_active": get_tasks_active,
            "get_jobs_queue": get_jobs_queue,
        }
    )

    return router
