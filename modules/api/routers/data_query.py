"""API routes: data_query (extracted from modules.api)."""

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



def create_data_query_router() -> APIRouter:
    router = APIRouter()
    # ========== Data Query Endpoints (for Electron integration) ==========

    @router.get(
        "/images",
        summary="Query images with filters",
        description="""
        Returns a paginated list of images with optional filtering by rating, label,
        keyword, score ranges, folder, and stack. Supports sorting and pagination.

        This endpoint replaces direct DB access from the Electron app.
        """
    )
    def query_images(
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(50, ge=1, le=500, description="Items per page"),
        sort_by: str = Query("score", description="Sort field (score, date, name, rating, score_general, score_aesthetic, score_technical, phases, embeddings)"),
        order: str = Query("desc", description="Sort order: asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings to filter (e.g. '3,4,5')"),
        label: Optional[str] = Query(None, description="Comma-separated labels to filter (e.g. 'Green,Blue')"),
        keyword: Optional[str] = Query(None, description="Keyword to filter by (partial match)"),
        keyword_exact: bool = Query(False, description="When true, match the keyword exactly instead of a substring (e.g. tag-cloud clicks)"),
        min_score_general: float = Query(0, ge=0, le=1, description="Minimum general score"),
        min_score_aesthetic: float = Query(0, ge=0, le=1, description="Minimum aesthetic score"),
        min_score_technical: float = Query(0, ge=0, le=1, description="Minimum technical score"),
        min_clip_quality_v0: float = Query(0, ge=0, le=1, description="Minimum CLIP quality score (clip_quality_v0)"),
        folder_path: Optional[str] = Query(None, description="Filter by folder path"),
        stack_id: Optional[int] = Query(None, description="Filter by stack ID"),
        phase_status: Optional[str] = Query(
            None,
            description="Filter by image_phase_status as phase_code:status (e.g. keywords:not_started)",
        ),
        unscored_only: bool = Query(
            False,
            description="When true, only images with score_general null or <= 0",
        ),
        data_gap: Optional[str] = Query(
            None,
            description="Phase marked done/skipped but data missing (e.g. keywords)",
        ),
    ):
        """Query images with filtering, sorting, and pagination."""
        return _images_list_payload(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order,
            rating=rating,
            label=label,
            keyword=keyword,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            min_clip_quality_v0=min_clip_quality_v0,
            folder_path=folder_path,
            stack_id=stack_id,
            phase_status_filter=phase_status,
            unscored_only=unscored_only,
            data_gap=data_gap,
            keyword_exact=keyword_exact,
        )

    @router.get(
        "/images/{image_id}/auditlog",
        summary="Audit trail for image phase status changes",
        description="Recent auditlog rows for image_phase_status (record_id = image_id).",
    )
    async def get_image_auditlog(
        image_id: int,
        limit: int = Query(50, ge=1, le=200),
    ):
        if not db.image_exists_by_id(image_id):
            raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
        return {"image_id": image_id, "items": db.get_image_auditlog(image_id, limit=limit)}

    @router.get(
        "/images/by-uuid/{image_uuid}",
        summary="Get image details by image_uuid",
        description="Resolves images.image_uuid to the same payload as GET /api/images/{image_id}.",
    )
    async def get_image_by_uuid(image_uuid: str):
        return _image_detail_for_uuid_str(image_uuid)

    @router.get(
        "/images/by-hash/{image_hash}",
        summary="Get image details by content hash",
        description="Looks up images.image_hash; returns the same payload as GET /api/images/{image_id}.",
    )
    async def get_image_by_hash_param(
        image_hash: str,
        hash_version: Optional[int] = Query(None, description="images.hash_version (1=full file, 2=preview)"),
    ):
        return _image_detail_for_hash_str(image_hash, hash_version=hash_version)

    @router.get(
        "/images/{image_id}/exif",
        summary="Get cached EXIF row for an image",
        description="Returns columns from image_exif for inspector UIs. Empty object when no cached row exists.",
    )
    async def get_image_exif_row(image_id: int):
        row = db.get_image_exif(image_id)
        return _json_safe_metadata_row(row)

    @router.get(
        "/images/{image_id}/xmp",
        summary="Get cached XMP row for an image",
        description="Returns columns from image_xmp for inspector UIs. Empty object when no cached row exists.",
    )
    async def get_image_xmp_row(image_id: int):
        row = db.get_image_xmp(image_id)
        return _json_safe_metadata_row(row)

    @router.post(
        "/images/{image_id}/geocode/reverse",
        summary="Reverse geocoding for an image (coordinates → address)",
        description="Requires geocoding.enabled and geocoding.user_agent. Uses cached GPS in image_exif or reads from the file.",
    )
    async def post_geocode_reverse(
        image_id: int,
        request: Optional[GeocodeReverseRequest] = Body(default=None),
    ):
        from modules.geocoding import image_service

        req = request or GeocodeReverseRequest()
        return await asyncio.to_thread(
            image_service.geocode_image_reverse,
            image_id,
            force=req.force,
            dry_run=req.dry_run,
            write_embedded=req.write_embedded,
            write_sidecar=req.write_sidecar,
        )

    @router.post(
        "/images/{image_id}/geocode/forward",
        summary="Forward geocoding (address → coordinates) and update EXIF",
        description="Resolves the query via the configured provider, updates image_exif, and optionally writes tags with exiftool.",
    )
    async def post_geocode_forward(image_id: int, request: GeocodeForwardRequest):
        from modules.geocoding import image_service

        return await asyncio.to_thread(
            image_service.geocode_image_forward,
            image_id,
            request.query,
            dry_run=request.dry_run,
            write_embedded=request.write_embedded,
            write_sidecar=request.write_sidecar,
        )

    @router.get(
        "/images/{image_id}",
        summary="Get image details by ID",
        description="Returns full details for a single image including all scores, metadata, and file paths."
    )
    async def get_image_by_id(image_id: int):
        """Get detailed information for a single image."""
        return _image_detail_payload(image_id)

    @router.get(
        "/images/{image_id}/neighbors",
        summary="Get image neighbors",
        description="Find previous and next image IDs for navigation within a sorted/filtered sequence.",
    )
    async def get_image_neighbors(
        image_id: int,
        sort_by: str = Query("score", description="Sort field"),
        order: str = Query("desc", description="Sort order: asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings"),
        label: Optional[str] = Query(None, description="Comma-separated labels"),
        keyword: Optional[str] = Query(None, description="Keyword filter"),
        min_score_general: float = Query(0, ge=0, le=1),
        min_score_aesthetic: float = Query(0, ge=0, le=1),
        min_score_technical: float = Query(0, ge=0, le=1),
        min_clip_quality_v0: float = Query(0, ge=0, le=1),
        folder_path: Optional[str] = Query(None),
        stack_id: Optional[int] = Query(None),
    ):
        return _image_neighbors_payload(
            image_id=image_id,
            sort_by=sort_by,
            order=order,
            rating=rating,
            label=label,
            keyword=keyword,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            min_clip_quality_v0=min_clip_quality_v0,
            folder_path=folder_path,
            stack_id=stack_id,
        )

    @router.get(
        "/images/{image_id}/similar",
        summary="k-NN visually-similar images for a single image",
        description="""
        Returns the top-k visually similar images to ``{image_id}`` using
        embedding cosine similarity. RESTful path-parameter form of
        `GET /api/similarity/search?image_id=...`.

        Note: do **not** confuse with `/images/{image_id}/neighbors`, which
        returns prev/next IDs for sorted-list navigation.

        **Path parameters:**
        - image_id: ID of the query image.

        **Query parameters:**
        - limit: Max results (default 20).
        - folder_path: Restrict to a folder.
        - min_similarity: Minimum cosine-similarity threshold (default 0.80).
        - embedding_space: Optional embedding-space code (default
          `mobilenet_v2_imagenet_gap`). Non-default codes require PostgreSQL.
        """,
        tags=["Similarity"],
    )
    async def get_image_similar(
        image_id: int,
        limit: int = Query(20, ge=1, le=100, description="Max results"),
        folder_path: Optional[str] = Query(None, description="Scope search to folder"),
        min_similarity: Optional[float] = Query(
            0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"
        ),
        embedding_space: Optional[str] = Query(
            None, description="Embedding-space code (default: mobilenet_v2_imagenet_gap)"
        ),
    ):
        from modules import similar_search, db

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM images WHERE id = ?", (image_id,))
            if c.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
        finally:
            conn.close()

        result = similar_search.search_similar_images(
            example_image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
            embedding_space=embedding_space,
        )
        if isinstance(result, dict) and "error" in result:
            err = result["error"].lower()
            if "not found" in err:
                raise HTTPException(status_code=404, detail=result["error"])
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "query_image_id": image_id,
            "results": result,
            "count": len(result),
            "embedding_space": embedding_space,
        }

    @router.get(
        "/folders",
        summary="Get folder list",
        description="Returns all folders in the database with their paths. Use folder_path query param on /api/images to browse folder contents."
    )
    async def get_folders():
        """Get all folders in the database."""
        from modules import db
        try:
            folders = db.get_all_folders()
            return {"folders": folders, "count": len(folders)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/folders/rebuild",
        summary="Rebuild folder cache",
        description="Scans images in the database and rebuilds the folder tree. Use when the Pipeline tab shows no folders."
    )
    async def rebuild_folders():
        """Rebuild folder cache from images table."""
        from modules import db
        try:
            db.rebuild_folder_cache()
            folders = db.get_all_folders()
            return {"success": True, "folders": folders, "count": len(folders)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stacks",
        summary="Get stacks listing",
        description="Returns stacks (image groups) with cover images and metadata. Optionally filter by folder."
    )
    async def get_stacks(
        folder_path: Optional[str] = Query(None, description="Filter stacks by folder path"),
        sort_by: str = Query("score_general", description="Sort field for cover image selection"),
        order: str = Query("desc", description="Sort order: asc or desc"),
    ):
        """Get stacks with cover images for display."""
        from modules import db
        try:
            stacks = db.get_stacks_for_display(
                folder_path=folder_path,
                sort_by=sort_by,
                order=order
            )
            return {
                "stacks": [dict(s) if hasattr(s, 'keys') else s for s in stacks],
                "count": len(stacks),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stacks/{stack_id}/images",
        summary="Get images in a stack",
        description="Returns all images belonging to a specific stack, sorted by general score descending."
    )
    async def get_stack_images(stack_id: int):
        """Get all images in a stack."""
        from modules import db
        try:
            images = db.get_images_in_stack(stack_id)
            return {
                "images": [dict(img) for img in images],
                "count": len(images),
                "stack_id": stack_id,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stacks/{stack_id}/substacks",
        summary="Get sub-stacks for a root stack",
        description=(
            "Returns persisted leaf sub-stacks from two-level culling "
            "(visual then semantic clustering). Empty when two-level culling "
            "has not run or is disabled."
        ),
    )
    async def get_stack_substacks(stack_id: int):
        """Get sub-stacks belonging to a root stack."""
        from modules import db
        try:
            substacks = db.get_substacks_for_stack(stack_id)
            return {
                "substacks": [dict(s) if hasattr(s, "keys") else s for s in substacks],
                "count": len(substacks),
                "stack_id": stack_id,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/substacks/{sub_stack_id}/images",
        summary="Get images in a sub-stack",
        description="Returns images belonging to a two-level culling sub-stack.",
    )
    async def get_substack_images(sub_stack_id: int):
        """Get all images in a sub-stack."""
        from modules import db
        try:
            images = db.get_images_in_substack(sub_stack_id)
            return {
                "images": [dict(img) for img in images],
                "count": len(images),
                "sub_stack_id": sub_stack_id,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/stats",
        summary="Get database statistics",
        description="""
        Returns comprehensive database statistics including total counts,
        score distributions, averages by rating/label, folder and stack counts.
        """
    )
    async def get_stats():
        """Get comprehensive database statistics."""
        from modules.mcp_server import get_database_stats
        try:
            stats = get_database_stats()
            return stats
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/analytics/culling",
        response_model=CullingAnalyticsResponse,
        summary="Culling and stack analytics (library or folder)",
        description=(
            "Aggregates stack size, pick/reject flags (images.pick_status), scores, "
            "EXIF exposure consistency, labels, GPS, keywords, and embedding coverage. "
            "PostgreSQL only. Optional folder_path or folder_id filter."
        ),
    )
    async def get_culling_analytics(
        folder_path: Optional[str] = Query(None, description="Filter to exact folder path"),
        folder_id: Optional[int] = Query(None, description="Filter to folder id"),
        per_stack_limit: int = Query(50, ge=0, le=200),
        per_stack_offset: int = Query(0, ge=0),
    ):
        from modules.culling_analytics.service import get_library_analytics

        try:
            return get_library_analytics(
                folder_path=folder_path,
                folder_id=folder_id,
                per_stack_limit=per_stack_limit,
                per_stack_offset=per_stack_offset,
            )
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except Exception as e:
            logger.exception("get_culling_analytics failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/analytics/culling/sessions/{session_id}",
        response_model=CullingAnalyticsResponse,
        summary="Culling session analytics",
    )
    async def get_culling_session_analytics(session_id: int):
        from modules.culling_analytics.service import get_session_analytics

        try:
            result = get_session_analytics(session_id)
            if result.get("error") == "session_not_found":
                raise HTTPException(status_code=404, detail="Session not found")
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_culling_session_analytics failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/analytics/stacks/{stack_id}",
        response_model=CullingAnalyticsResponse,
        summary="Per-stack culling analytics",
    )
    async def get_stack_analytics_endpoint(stack_id: int):
        from modules.culling_analytics.service import get_stack_analytics

        try:
            result = get_stack_analytics(stack_id)
            if result.get("error") == "stack_not_found":
                raise HTTPException(status_code=404, detail="Stack not found")
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_stack_analytics failed")
            raise HTTPException(status_code=500, detail=str(e))


    return router
