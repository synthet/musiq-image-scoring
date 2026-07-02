"""API routes: similar (extracted from modules.api)."""

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



def create_similar_router() -> APIRouter:
    router = APIRouter()
    # ========== Similar Images Endpoint ==========

    @router.get(
        "/similar",
        summary="[DEPRECATED] Find similar images",
        description="DEPRECATED: Use GET /api/similarity/search instead.",
        deprecated=True,
    )
    def get_similar_images_legacy(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: Optional[str] = Query(None, description="Scope search to folder"),
        min_similarity: Optional[float] = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
    ):
        """Deprecated legacy similarity search."""
        return get_similar_images_similarity_namespace(
            image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
        )

    @router.get(
        "/similarity/search",
        summary="Find similar images",
        description="""
        Find images visually similar to a given image using embedding-based cosine similarity.

        **Query Parameters:**
        - image_id: Required. Integer ID of the query image.
        - limit: Maximum number of results (default: 20).
        - folder_path: Optional. Scope search to a specific folder path.
        - min_similarity: Minimum similarity threshold 0.0-1.0 (default: 0.80).
        - embedding_space: Optional embedding-space code. Defaults to the
          1280-d MobileNet space. Non-default codes (e.g.
          `clip_vit_b32_image`) require PostgreSQL.

        **Returns:**
        - query_image_id: ID of the query image
        - results: List of {image_id, file_path, similarity}
        - count: Number of results returned
        """,
        tags=["Similarity"]
    )
    def get_similar_images_similarity_namespace(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: Optional[str] = Query(None, description="Scope search to folder"),
        min_similarity: Optional[float] = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
        embedding_space: Optional[str] = Query(
            None,
            description="Embedding-space code (default: mobilenet_v2_imagenet_gap)",
        ),
    ):
        """Find images similar to the given image by ID (new similarity namespace)."""
        from modules import similar_search, db
        # Verify image exists before searching
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
            if "not found" in result["error"].lower():
                raise HTTPException(status_code=404, detail=result["error"])
            if "no embeddings" in result["error"].lower() or "clustering" in result["error"].lower():
                raise HTTPException(status_code=400, detail=result["error"])
            raise HTTPException(status_code=400, detail=result["error"])
        payload = {
            "query_image_id": image_id,
            "results": result,
            "count": len(result),
        }
        if embedding_space is not None:
            payload["embedding_space"] = embedding_space
        return payload

    @router.get(
        "/similarity/text-search",
        summary="Search images by text query",
        description="""
        Find images semantically matching a free-text query using CLIP text-to-image
        similarity.

        Encodes the query with the CLIP ViT-B/32 text tower and searches against
        stored `clip_vit_b32_image` embeddings via pgvector cosine distance.
        Requires PostgreSQL and at least some images with CLIP embeddings
        (produced during tagging).

        **Query Parameters:**
        - query: Required. Free-text search query (e.g. "sunset over mountains").
        - limit: Maximum number of results (default: 20, max: 100).
        - folder_path: Optional. Scope search to a specific folder path.
        - min_similarity: Minimum similarity threshold 0.0-1.0 (default: none).

        **Returns:**
        - query: The original query string
        - results: List of {image_id, file_path, similarity}
        - count: Number of results returned
        - embedding_space: Always "clip_vit_b32_image"
        """,
        tags=["Similarity"],
    )
    async def search_images_by_text(
        query: str = Query(..., min_length=1, max_length=500, description="Free-text search query"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: Optional[str] = Query(None, description="Scope search to folder (ignored if folder_ids set)"),
        folder_ids: Optional[List[int]] = Query(None, description="Scope search to folder IDs (includes subfolders when expanded client-side)"),
        min_similarity: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum similarity threshold"),
        min_rating: Optional[int] = Query(None, ge=0, le=5, description="Minimum star rating"),
        color_label: Optional[str] = Query(None, description="Filter by color label (Red, Yellow, Green, Blue, Purple)"),
        keyword: Optional[str] = Query(None, description="Also require normalized keyword match (AND filter)"),
        captured_date: Optional[str] = Query(None, description="Filter by capture date (YYYY-MM-DD)"),
        sort_by: Optional[str] = Query(None, description="Secondary sort after relevance (capture_date, created_at, rating, score_general, ...)"),
        order: Optional[str] = Query("DESC", description="Secondary sort direction (ASC or DESC)"),
    ):
        """Search images by free-text query using CLIP text-to-image similarity."""
        from modules import similar_search

        def _run():
            return similar_search.search_by_text(
                query=query,
                limit=limit,
                folder_path=folder_path,
                min_similarity=min_similarity,
                folder_ids=folder_ids,
                min_rating=min_rating,
                color_label=color_label,
                keyword=keyword,
                captured_date=captured_date,
                sort_by=sort_by,
                order=order,
            )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_run),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Text search timed out (model loading may take a while on first call).",
            )
        except Exception as e:
            import traceback
            logger.error(f"Unexpected error in text search endpoint: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

        if isinstance(result, dict):
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            raise HTTPException(status_code=500, detail="Unexpected text search result shape.")
        if not isinstance(result, list):
            raise HTTPException(status_code=500, detail="Unexpected text search result type.")

        return {
            "query": query,
            "results": result,
            "count": len(result),
            "embedding_space": "clip_vit_b32_image",
        }

    @router.get(
        "/similarity/example-queries",
        summary="Suggested text-search queries from library keywords",
        description="""
        Returns up to ``limit`` display strings derived from ranked keywords in the catalog
        (``keywords_dim`` / ``image_keywords``), optionally scoped to a folder path.
        Used by the Semantic Search UI for rotating example chips.

        Always returns HTTP 200; on failure or empty catalog, ``queries`` is an empty list.
        """,
        tags=["Similarity"],
    )
    def get_similarity_example_queries(
        limit: int = Query(48, ge=1, le=100, description="Maximum keyword phrases to return"),
        folder_path: Optional[str] = Query(None, description="Scope keywords to images under this folder path"),
    ):
        """Top keywords from the catalog as suggestion strings for text search."""
        from modules.keyword_discovery import get_top_keywords

        def _min_display_len(val: Optional[str]) -> bool:
            s = (val or "").strip()
            return len(s) >= 2

        try:
            rows = get_top_keywords(limit=limit, folder_path=folder_path) or []
        except Exception as e:
            logger.warning("example-queries failed: %s", e)
            return {"queries": [], "source": "keywords"}

        out: List[str] = []
        seen = set()
        for r in rows:
            disp = r.get("keyword_display")
            norm = r.get("keyword_norm")
            text = (disp if (disp and str(disp).strip()) else norm) or ""
            text = str(text).strip()
            if not _min_display_len(text):
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)

        return {"queries": out, "source": "keywords"}

    @router.get(
        "/keywords/cloud",
        summary="Keyword tag cloud (counts by keyword)",
        description="""
        Returns keywords with usage counts for a tag-cloud UI, ordered by count desc.

        ``kind=species`` returns only ``species:*`` keywords (Birds page); ``kind=general``
        returns all non-species keywords (Keywords page). Optionally scope to a folder path.

        Each entry: ``{keyword_norm, keyword_display, count}``. Always HTTP 200; on failure
        or empty catalog, ``keywords`` is an empty list.
        """,
        tags=["Keywords"],
    )
    def get_keyword_cloud_endpoint(
        kind: str = Query("general", description="species | general"),
        limit: int = Query(200, ge=1, le=1000, description="Maximum keywords to return"),
        folder_path: Optional[str] = Query(None, description="Scope keywords to images under this folder path"),
    ):
        """Keyword usage counts for the Birds / Keywords tag clouds."""
        from modules.keyword_discovery import get_keyword_cloud

        kind_norm = (kind or "general").strip().lower()
        if kind_norm not in ("species", "general"):
            raise HTTPException(status_code=400, detail="kind must be 'species' or 'general'")
        try:
            rows = get_keyword_cloud(kind=kind_norm, limit=limit, folder_path=folder_path) or []
        except Exception as e:
            logger.warning("keyword cloud failed: %s", e)
            return {"keywords": [], "kind": kind_norm}
        return {"keywords": rows, "kind": kind_norm}

    from modules.api.handler_registry import register_handlers

    register_handlers(
        {"get_similar_images_similarity_namespace": get_similar_images_similarity_namespace}
    )

    return router
