"""API routes: clustering (extracted from modules.api)."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from modules import db
from modules.api_models import (
    ApiResponse,
    ClusteringStartRequest,
    StatusResponse,
)
from modules.job_description import (
    augment_queue_payload_for_audit,
    build_clustering_job_description,
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



def create_clustering_router() -> APIRouter:
    router = APIRouter()
    # ========== Clustering Endpoints ==========

    @router.post(
        "/clustering/start",
        response_model=ApiResponse,
        summary="Start clustering job",
        description="""
        Starts a clustering job that groups visually similar images into stacks.

        Uses MobileNetV2 embeddings and cosine similarity to find groups of related images.
        Optionally uses EXIF timestamps for burst detection.

        The job runs asynchronously. Use GET /api/clustering/status to monitor progress.
        """
    )
    async def start_clustering(request: ClusteringStartRequest):
        """Start a batch clustering job."""
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("clustering_start")

        if _api_module()._clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

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
        job_source = request.input_path or "SELECTOR_CLUSTERING"
        cl_payload = augment_queue_payload_for_audit(
            {
                "input_path": request.input_path,
                "threshold": request.threshold,
                "time_gap": request.time_gap,
                "force_rescan": request.force_rescan,
                "resolved_image_ids": selector_result.get("resolved_image_ids"),
            },
            trigger="api",
            tool_id="clustering_start",
        )
        cl_extra = f"{resolved_count} resolved images." if resolved_count is not None else None
        if request.force_rescan:
            cl_extra = (cl_extra or "") + " force_rescan=True."
        cl_payload = attach_run_reason(
            cl_payload,
            source=REASON_SOURCE_LEGACY_API,
            summary=build_legacy_api_summary(
                job_kind="clustering", input_path=request.input_path, extra=cl_extra
            ),
            trigger="api",
            tool_id="clustering_start",
            criteria={
                "resolved_count": resolved_count,
                "force_rescan": bool(request.force_rescan),
            }
            if resolved_count is not None or request.force_rescan
            else None,
        )
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code="culling",
            job_type="clustering",
            queue_payload=cl_payload,
            description=build_clustering_job_description(
                request.input_path,
                force_rescan=bool(request.force_rescan),
                resolved_count=resolved_count,
            ),
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue clustering job")

        # Enqueue the full dependency prefix (indexing→metadata→scoring→culling)
        # so clustering can never run ahead of scoring; already-satisfied phases
        # no-op in the JIT planner. Mirrors start_scoring's prefix expansion.
        from modules.phases import pipeline_prefix_through
        db.create_job_phases(
            job_id, pipeline_prefix_through("culling"), first_phase_state="queued"
        )

        return ApiResponse(
            success=True,
            message="Clustering job queued",
            data={"job_id": job_id, "input_path": request.input_path, "resolved_count": resolved_count, "queue_position": queue_position}
        )

    @router.post(
        "/clustering/stop",
        response_model=ApiResponse,
        summary="Stop clustering job",
        description="Sends a stop signal to the currently running clustering job."
    )
    async def stop_clustering():
        """Stop the currently running clustering job."""
        if _api_module()._clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        if not _api_module()._clustering_runner.is_running:
            return ApiResponse(
                success=False,
                message="No clustering job is currently running",
                data={"is_running": False}
            )

        _api_module()._clustering_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to clustering job",
            data={"is_running": _api_module()._clustering_runner.is_running}
        )

    @router.get(
        "/clustering/status",
        response_model=StatusResponse,
        summary="Get clustering status",
        description="Returns the current status of the clustering job including progress and logs."
    )
    async def get_clustering_status():
        """Get the current status of the clustering job."""
        if _api_module()._clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        result = _api_module()._clustering_runner.get_status()
        is_running, log_text, status_message, current, total = result[:5]

        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type="clustering"
        )


    return router
