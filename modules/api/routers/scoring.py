"""API routes: scoring (extracted from modules.api)."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from modules import db
from modules.api_models import (
    ApiResponse,
    ScoringStartRequest,
    SingleImageRequest,
    StatusResponse,
)
from modules.job_description import (
    augment_queue_payload_for_audit,
    build_scoring_job_description,
)
from modules.run_manifest import (
    REASON_SOURCE_LEGACY_API,
    attach_run_reason,
    build_legacy_api_summary,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_scoring_router() -> APIRouter:
    router = APIRouter()
    # ========== Scoring Endpoints ==========
    
    @router.post(
        "/scoring/start",
        response_model=ApiResponse,
        summary="Start batch image scoring",
        description="""
        Initiates a batch image quality assessment job for all images in the specified directory.
        
        The scoring process uses a configurable ensemble of AI models, selected via the
        `scoring.models` registry. Current production models include:
        - **LIQE**: Learning Image Quality Evaluator (CLIP-based semantic quality)
        - **SPAQ**: Smartphone Photography Aesthetics Quality (MUSIQ)
        - **AVA**: Aesthetic Visual Analysis (MUSIQ)
        - **TOPIQ**: Top-down Image Quality (no-reference)

        Additional models run in shadow (stored but not fused) — e.g. **QPT V2** — and the
        active set is config-driven. See `GET /api/models` for the live registry and per-model
        shadow status.

        Results include:
        - Technical score (sharpness, noise, exposure)
        - Aesthetic score (composition, appeal)
        - General quality score (weighted combination)
        - Rating (1-5 stars) and color label (Red/Yellow/Green/Blue/Purple)
        
        The job runs asynchronously. Use GET /api/scoring/status to monitor progress.
        
        **Path Handling:**
        - Windows paths: `D:/Photos/2024` or `D:\\Photos\\2024`
        - WSL paths: `/mnt/d/Photos/2024`
        - Paths are automatically converted between formats when needed
        
        **Skip Logic:**
        - If `skip_existing=True`: Images with complete scores are skipped
        - If `force_rescore=True`: All images are re-scored regardless of existing data
        - Incomplete scores (missing models or metadata) are always completed
        
        **Example Request:**
        ```json
        {
            "input_path": "D:/Photos/2024",
            "skip_existing": true,
            "force_rescore": false
        }
        ```
        
        **Example Response:**
        ```json
        {
            "success": true,
            "message": "Scoring job started successfully",
            "data": {
                "job_id": 123,
                "input_path": "D:/Photos/2024"
            }
        }
        ```
        """,
        response_description="Job start confirmation with job_id",
        responses={
            200: {
                "description": "Job started successfully",
                "content": {
                    "application/json": {
                        "example": {
                            "success": True,
                            "message": "Scoring job started successfully",
                            "data": {"job_id": 123, "input_path": "D:/Photos/2024"}
                        }
                    }
                }
            },
            400: {"description": "Invalid input path or path not found"},
            503: {"description": "Scoring runner not available"}
        }
    )
    async def start_scoring(request: ScoringStartRequest):
        """
        Start a batch scoring job.

        Args:
            request: ScoringStartRequest with input_path and options

        Returns:
            ApiResponse with success status and job_id if started
        """
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("scoring_start")

        if _api_module()._scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")

        if not any([request.input_path, request.image_ids, request.image_paths, request.folder_ids, request.folder_paths]):
            raise HTTPException(status_code=400, detail="Provide input_path or at least one selector")

        selector_folder_paths = list(request.folder_paths or [])
        if request.input_path:
            if not os.path.exists(request.input_path):
                raise HTTPException(
                    status_code=400,
                    detail=f"Path not found: {request.input_path}"
                )
            selector_folder_paths.append(request.input_path)

        selector_result = {"resolved_image_ids": None}
        has_explicit_selectors = any([request.image_ids, request.image_paths, request.folder_ids, request.folder_paths])
        if has_explicit_selectors:
            import modules.api as api_mod

            selector_result = api_mod.resolve_selectors(
                image_ids=request.image_ids,
                image_paths=request.image_paths,
                folder_ids=request.folder_ids,
                folder_paths=selector_folder_paths,
                recursive=request.recursive,
                index_missing=True,
            )

        resolved_ids = selector_result.get("resolved_image_ids")
        resolved_count = len(resolved_ids or []) if resolved_ids is not None else None
        job_source = request.input_path or "SELECTOR_SCORING"
        skip_existing = not request.force_rescore if request.force_rescore else request.skip_existing
        queue_payload = {
            "skip_existing": skip_existing,
            "input_path": request.input_path,
            "resolved_image_ids": selector_result.get("resolved_image_ids"),
        }
        queue_payload = augment_queue_payload_for_audit(queue_payload, trigger="api", tool_id="scoring_start")
        extra = f"{resolved_count} resolved images." if resolved_count is not None else None
        queue_payload = attach_run_reason(
            queue_payload,
            source=REASON_SOURCE_LEGACY_API,
            summary=build_legacy_api_summary(
                job_kind="scoring", input_path=request.input_path, extra=extra
            ),
            trigger="api",
            tool_id="scoring_start",
            criteria={"resolved_count": resolved_count} if resolved_count is not None else None,
        )
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code="scoring",
            job_type="scoring",
            queue_payload=queue_payload,
            description=build_scoring_job_description(request.input_path, resolved_count=resolved_count),
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue scoring job")
        db.create_job_phases(job_id, ["indexing", "metadata", "scoring"], first_phase_state="queued")

        return ApiResponse(
            success=True,
            message="Scoring job queued",
            data={"job_id": job_id, "input_path": request.input_path, "resolved_count": resolved_count, "queue_position": queue_position}
        )
    
    @router.post(
        "/scoring/stop",
        response_model=ApiResponse,
        summary="Stop scoring job",
        description="""
        Sends a stop signal to the currently running scoring job.
        
        The job will finish processing the current image and then stop gracefully.
        Use GET /api/scoring/status to verify the job has stopped.
        
        **Note:** If no job is running, returns success=False with appropriate message.
        """,
        response_description="Stop confirmation"
    )
    async def stop_scoring():
        """Stop the currently running scoring job."""
        if _api_module()._scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not _api_module()._scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="No scoring job is currently running",
                data={"is_running": False}
            )
        
        _api_module()._scoring_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to scoring job",
            data={"is_running": _api_module()._scoring_runner.is_running}
        )
    
    @router.get(
        "/scoring/status",
        response_model=StatusResponse,
        summary="Get scoring status",
        description="""
        Returns the current status of the scoring job including:
        - Whether a job is currently running
        - Progress information (current/total images)
        - Status message
        - Full log output
        - Job type (scoring, fix_db, etc.)
        
        **Polling:** This endpoint can be polled periodically to monitor job progress.
        Recommended polling interval: 2-5 seconds.
        """,
        response_description="Current scoring job status"
    )
    async def get_scoring_status():
        """Get the current status of the scoring job."""
        if _api_module()._scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        result = _api_module()._scoring_runner.get_status()
        is_running, log_text, status_message, current, total = result[:5]
        
        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type=getattr(_api_module()._scoring_runner, 'job_type', None)
        )
    
    @router.post(
        "/scoring/fix-db",
        response_model=ApiResponse,
        summary="Fix database (re-score incomplete)",
        description="""
        Starts a database fix operation that re-scores images with incomplete data.
        
        This operation:
        - Finds images missing scores from one or more models
        - Finds images missing metadata (rating or label)
        - Re-runs scoring only for missing components
        - Updates database with complete scores
        
        Useful for:
        - Backfilling scores after adding new models
        - Fixing corrupted or incomplete records
        - Updating metadata for images scored before metadata features were added
        
        The operation runs asynchronously. Monitor progress with GET /api/scoring/status.

        Note: this endpoint starts immediately and intentionally bypasses the persisted queue.
        """,
        response_description="Fix operation start confirmation"
    )
    async def fix_database():
        """Start database fix operation (re-score incomplete records)."""
        if _api_module()._scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if _api_module()._scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="Scoring job is already running",
                data={"is_running": True}
            )
        
        job_id = db.create_job("DB_FIX_OPERATION")
        result = _api_module()._scoring_runner.start_fix_db(job_id)
        
        if result == "Started":
            return ApiResponse(
                success=True,
                message="Database fix operation started",
                data={"job_id": job_id}
            )
        else:
            return ApiResponse(
                success=False,
                message=result,
                data={"error": result}
            )
    
    @router.post(
        "/scoring/single",
        response_model=ApiResponse,
        summary="Score single image",
        description="""
        Scores a single image file using all available models.
        
        This is a blocking operation that runs the full scoring pipeline for one image.
        Use this for testing or when you need immediate results for a single file.
        
        For batch operations, use POST /api/scoring/start instead.
        
        **Supported formats:** JPG, JPEG, PNG, NEF, NRW, DNG, CR2, ARW, ORF, CR3, RW2
        """,
        response_description="Scoring result with success status and message"
    )
    async def score_single_image(request: SingleImageRequest):
        """Score a single image."""
        if _api_module()._scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _api_module()._scoring_runner.run_single_image(request.file_path)
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    

    return router
