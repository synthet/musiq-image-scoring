"""API routes: duplicates (extracted from modules.api)."""

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
from modules.api.handler_registry import get_handler
from modules.selector_resolver import resolve_selectors

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_duplicates_router() -> APIRouter:
    router = APIRouter()
    # ========== Find Duplicates Endpoints ==========

    @router.post(
        "/duplicates/find", 
        response_model=ApiResponse,
        summary="[DEPRECATED] Find near-duplicate images",
        description="DEPRECATED: Use POST /api/similarity/duplicates instead.",
        deprecated=True,
    )
    def find_duplicates_legacy(req: FindDuplicatesRequest = Body(...)):
        """Deprecated legacy duplicate detection."""
        return post_duplicates_similarity_namespace(req)

    @router.post(
        "/similarity/duplicates", 
        response_model=ApiResponse,
        summary="Find near-duplicate images",
        description="Detect likely duplicate image pairs using embedding cosine similarity.",
        tags=["Similarity"]
    )
    def post_duplicates_similarity_namespace(req: FindDuplicatesRequest = Body(...)):
        """Find near-duplicate image pairs in the database (similarity namespace)."""
        try:
            from modules import similar_search
            results = similar_search.find_near_duplicates(
                threshold=req.threshold,
                folder_path=req.folder_path,
                limit=req.limit
            )
            return ApiResponse(
                success=True, 
                message=f"Found {len(results)} near-duplicate pairs",
                data={"duplicates": results}
            )
        except Exception as e:
            return ApiResponse(success=False, message=str(e))

    @router.get(
        "/similarity/similar",
        summary="[DEPRECATED] Find similar images",
        description="DEPRECATED: Use GET /api/similarity/search instead.",
        deprecated=True,
    )
    def get_similar_images_alias(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: Optional[str] = Query(None, description="Scope search to folder"),
        min_similarity: Optional[float] = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
        embedding_space: Optional[str] = Query(
            None, description="Embedding-space code (default: mobilenet_v2_imagenet_gap)"
        ),
    ):
        """Deprecated alias for similarity search."""
        return get_handler("get_similar_images_similarity_namespace")(
            image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
            embedding_space=embedding_space,
        )

    @router.get(
        "/similarity/duplicates",
        summary="Find near-duplicate images (similarity namespace)",
        description="Detect likely duplicate image pairs using embedding cosine similarity.",
    )
    def get_duplicates_similarity_namespace(
        threshold: Optional[float] = Query(
            None,
            ge=0.0,
            le=1.0,
            description="Similarity threshold. Uses config default when omitted.",
        ),
        folder_path: Optional[str] = Query(None, description="Restrict duplicate detection to a folder"),
        limit: int = Query(1000, ge=1, le=10000, description="Maximum duplicate pairs to return"),
    ):
        """GET alias for duplicate detection under /api/similarity namespace."""
        from modules import similar_search

        try:
            duplicates = similar_search.find_near_duplicates(
                threshold=threshold,
                folder_path=folder_path,
                limit=limit,
            )
            return {
                "duplicates": duplicates,
                "count": len(duplicates),
            }
        except Exception as exc:
            logger.error("Error in get_duplicates_similarity_namespace: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get(
        "/outliers",
        response_model=OutlierResponse,
        summary="[DEPRECATED] Find visual outliers in a folder",
        description="DEPRECATED: Use GET /api/similarity/outliers instead.",
        deprecated=True,
    )
    def get_outliers_legacy(
        folder_path: str = Query(..., description="Folder path to analyze"),
        z_threshold: Optional[float] = Query(None, ge=0.0, description="Outlier z-score threshold"),
        k: Optional[int] = Query(None, ge=1, description="Top-K neighbors used for local density"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum outlier results to return"),
    ):
        """Deprecated legacy outlier search."""
        return get_outliers_similarity_namespace(
            folder_path=folder_path,
            z_threshold=z_threshold,
            k=k,
            limit=limit,
        )

    @router.get(
        "/similarity/outliers",
        response_model=OutlierResponse,
        summary="Find visual outliers",
        description="""
        Identify visually atypical images inside a folder using embedding-based similarity analysis.

        **Query Parameters:**
        - folder_path: Required. Restrict analysis to this folder.
        - z_threshold: Optional z-score cutoff (default from config).
        - k: Optional number of nearest neighbors used per image (default from config).
        - limit: Maximum number of outliers to return (default: 100).

        **Returns:**
        - outliers: List of flagged images with outlier scores, z-scores, and nearest-neighbor explainability.
        - stats: Folder-level summary statistics used during detection.
        - skipped: Images skipped due to missing embeddings.
        """,
        tags=["Similarity"]
    )
    def get_outliers_similarity_namespace(
        folder_path: str = Query(..., description="Folder path to analyze"),
        z_threshold: Optional[float] = Query(None, ge=0.0, description="Outlier z-score threshold"),
        k: Optional[int] = Query(None, ge=1, description="Top-K neighbors used for local density"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum outlier results to return"),
    ):
        """Find statistically atypical images based on embedding similarity (similarity namespace)."""
        from modules import similar_search
        try:
            result = similar_search.find_outliers(
                folder_path=folder_path,
                z_threshold=z_threshold,
                k=k,
                limit=limit,
            )
            if isinstance(result, dict) and "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Error in get_outliers for %s: %s", folder_path, exc)
            raise HTTPException(status_code=500, detail=str(exc))



    return router
