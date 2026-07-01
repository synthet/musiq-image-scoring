"""API routes: tagging (extracted from modules.api)."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import platform
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from modules import config, db
from modules.api import deps, state
from modules.api_helpers import (
    _decode_db_row_blobs,
    _image_detail_for_hash_str,
    _image_detail_for_uuid_str,
    _image_detail_payload,
    _image_neighbors_payload,
    _images_list_payload,
    _job_phases_for_run_display,
    _job_supports_execution_report,
    _jobs_recent_json_default,
    _json_response_db,
    _json_safe_metadata_row,
    _merge_model_scores_into,
    _normalize_incident_row,
    _normalize_jobs_table_row,
    _parse_json_object_column,
    _parse_rating_filter,
    _row_to_dict,
    _synthetic_bird_species_job_phases,
)
from modules.api_models import (
    AgentCullDeleteApprovedRequest,
    AgentCullDiscoverRequest,
    AgentCullPickStatusRequest,
    AgentCullRecommendationIdsRequest,
    AgentCullRunRequest,
    ApiResponse,
    BirdSpeciesStartRequest,
    ClusteringStartRequest,
    ConfigResponse,
    CullingAnalyticsResponse,
    DiagnosticsResponse,
    ExportRequest,
    FindDuplicatesRequest,
    GeocodeForwardRequest,
    GeocodeReverseRequest,
    HealPhaseRequest,
    HealthResponse,
    ImageUpdateRequest,
    ImportRegisterRequest,
    IpcBridgeRequest,
    IpcBridgeResponse,
    LifecycleControlRequest,
    MaintenanceStartRequest,
    NeighborInfo,
    OutlierInfo,
    OutlierResponse,
    PhaseDecisionResponse,
    PipelineBackfillRequest,
    PipelinePhaseControlRequest,
    PipelineRestartFromStageRequest,
    PipelineRunControlRequest,
    PipelineStepRerunRequest,
    PipelineSubmitRequest,
    ScoringStartRequest,
    SelectorRequest,
    SingleImageRequest,
    StatusResponse,
    TaggingSingleRequest,
    TaggingStartRequest,
    TagPropagationRequest,
)
from modules.job_description import (
    augment_queue_payload_for_audit,
    build_bird_species_job_description,
    build_clustering_job_description,
    build_run_submit_description,
    build_scoring_job_description,
    build_tagging_job_description,
    build_workflow_run_description,
)
from modules.job_dispatcher import JobDispatcher
from modules.maintenance_job_display import (
    build_default_maintenance_description,
    maintenance_job_input_path,
)
from modules.phases_policy import explain_phase_run_decision
from modules.pipeline_selector_composer import (
    compose_selector_request,
    serialize_queue_payload,
    validate_and_preview,
)
from modules.run_manifest import (
    REASON_SOURCE_FORCE_RUN,
    REASON_SOURCE_LEGACY_API,
    REASON_SOURCE_MAINTENANCE,
    REASON_SOURCE_MANUAL_SUBMIT,
    REASON_SOURCE_PIPELINE_SUBMIT,
    REASON_SOURCE_RETRY,
    attach_run_reason,
    build_legacy_api_summary,
    build_maintenance_summary,
    build_manual_submit_summary,
    build_retry_summary,
)
from modules.run_modes import CANONICAL_RUN_MODE, resolve_run_mode_flags
from modules.selector_resolver import resolve_selectors

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_tagging_router() -> APIRouter:
    router = APIRouter()
    # ========== Tagging Endpoints ==========
    
    @router.post(
        "/tagging/start",
        response_model=ApiResponse,
        summary="Start batch tagging",
        description="""
        Initiates a batch image tagging job using CLIP (Contrastive Language-Image Pre-Training).
        
        The tagging process:
        - Extracts relevant keywords from images using zero-shot classification
        - Optionally generates captions using BLIP (Bootstrapping Language-Image Pre-training)
        - Writes metadata to XMP sidecar files and embedded metadata
        - Updates database with keywords, title, and description
        
        **Keyword Extraction:**
        - Uses default keyword set if custom_keywords not provided
        - Default keywords: landscape, portrait, urban, cityscape, nature, wildlife, etc.
        - Returns top 5 most relevant keywords per image
        
        **Caption Generation:**
        - Enabled with generate_captions=True
        - Uses BLIP model to generate natural language descriptions
        - Title is auto-generated from caption (first 50 chars)
        
        **Path Handling:**
        - Provide input_path and/or selectors (image_ids, image_paths, folder_ids, folder_paths)
        - Directory path processes images in that folder and subfolders
        - Paths are automatically converted between Windows/WSL formats
        
        The job runs asynchronously. Use GET /api/tagging/status to monitor progress.
        """,
        response_description="Tagging job start confirmation"
    )
    async def start_tagging(request: TaggingStartRequest):
        """Start a batch tagging job."""
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("tagging_start")

        if _api_module()._tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
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

        from modules import db
        resolved_ids = selector_result.get("resolved_image_ids")
        resolved_count = len(resolved_ids or []) if resolved_ids is not None else None
        job_source = request.input_path or "SELECTOR_TAGGING"
        t_payload = augment_queue_payload_for_audit(
            {
                "input_path": request.input_path,
                "custom_keywords": request.custom_keywords,
                "overwrite": request.overwrite,
                "generate_captions": request.generate_captions,
                "generate_accessibility": request.generate_accessibility,
                "resolved_image_ids": selector_result.get("resolved_image_ids"),
            },
            trigger="api",
            tool_id="tagging_start",
        )
        t_extra = f"{resolved_count} resolved images." if resolved_count is not None else None
        t_payload = attach_run_reason(
            t_payload,
            source=REASON_SOURCE_LEGACY_API,
            summary=build_legacy_api_summary(
                job_kind="tagging", input_path=request.input_path, extra=t_extra
            ),
            trigger="api",
            tool_id="tagging_start",
            criteria={"resolved_count": resolved_count} if resolved_count is not None else None,
        )
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code="keywords",
            job_type="tagging",
            queue_payload=t_payload,
            description=build_tagging_job_description(request.input_path),
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue tagging job")
        # Enqueue the full dependency prefix (indexing→metadata→scoring→keywords)
        # so tagging can never run ahead of scoring; already-satisfied phases
        # no-op in the JIT planner. Mirrors start_scoring's prefix expansion.
        from modules.phases import pipeline_prefix_through
        db.create_job_phases(
            job_id, pipeline_prefix_through("keywords"), first_phase_state="queued"
        )

        return ApiResponse(
            success=True,
            message="Tagging job queued",
            data={
                "job_id": job_id,
                "input_path": request.input_path,
                "resolved_count": resolved_count,
                "queue_position": queue_position,
            }
        )
    
    @router.post(
        "/tagging/stop",
        response_model=ApiResponse,
        summary="Stop tagging job",
        description="Sends a stop signal to the currently running tagging job."
    )
    async def stop_tagging():
        """Stop the currently running tagging job."""
        if _api_module()._tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if not _api_module()._tagging_runner.is_running:
            return ApiResponse(
                success=False,
                message="No tagging job is currently running",
                data={"is_running": False}
            )
        
        _api_module()._tagging_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to tagging job",
            data={"is_running": _api_module()._tagging_runner.is_running}
        )
    
    @router.get(
        "/tagging/status",
        response_model=StatusResponse,
        summary="Get tagging status",
        description="Returns the current status of the tagging job including progress and logs."
    )
    async def get_tagging_status():
        """Get the current status of the tagging job."""
        if _api_module()._tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        result = _api_module()._tagging_runner.get_status()
        is_running, log_text, status_message, current, total = result[:5]
        
        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type="tagging"
        )
    
    @router.post(
        "/tagging/single",
        response_model=ApiResponse,
        summary="Tag single image",
        description="""
        Tags a single image file with keywords and optionally generates a caption.
        
        This is a blocking operation that processes one image immediately.
        For batch operations, use POST /api/tagging/start instead.
        """
    )
    async def tag_single_image(request: TaggingSingleRequest):
        """Tag a single image."""
        if _api_module()._tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _api_module()._tagging_runner.run_single_image(
            request.file_path,
            request.custom_keywords,
            request.generate_captions,
            request.generate_accessibility,
        )
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )

    @router.post(
        "/tagging/propagate",
        summary="Propagate tags",
        description="""
        Propagates keywords from tagged images to visually similar untagged images.
        
        This operation uses image embeddings to find nearest neighbors and applies
        tags based on similarity-weighted voting.
        
        **Use Cases:**
        - Automatically tagging large datasets from a small set of manually tagged examples
        - Ensuring consistent tagging across similar bursts or shots
        - Quickly organizing imported photo collections
        """
    )
    async def tag_propagation(request: TagPropagationRequest):
        """Propagate keywords from tagged images to untagged neighbors."""
        from modules.tagging import propagate_tags
        try:
            result = propagate_tags(
                folder_path=request.folder_path,
                dry_run=request.dry_run,
                k=request.k,
                min_similarity=request.min_similarity,
                min_keyword_confidence=request.min_keyword_confidence,
                min_support_neighbors=request.min_support_neighbors,
                write_mode=request.write_mode,
                max_keywords=request.max_keywords,
                focus_image_id=request.focus_image_id,
            )
            return {
                "success": True,
                "message": f"Tag propagation completed ({'dry run' if request.dry_run else 'live'})",
                "data": result
            }
        except Exception as e:
            logger.error(f"Tag propagation failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    

    return router
