"""API routes: embedding (extracted from modules.api)."""

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



def create_embedding_router() -> APIRouter:
    router = APIRouter()
    # ========== Embedding Map Endpoint ==========

    @router.get(
        "/embedding_map",
        response_model=ApiResponse,
        summary="2D embedding map",
        description="""
        Project image embeddings to 2D coordinates for spatial visualisation.

        Uses UMAP (default) or t-SNE to reduce embeddings to two dimensions.
        Defaults to the 1280-d MobileNetV2 space; pass `space_code` to project
        a non-default space (e.g. `clip_vit_b32_image`, `blip_vit_b16_image`,
        `bioclip_2_image`). Results are cached on disk per
        `(folder_path, method, sample_limit, n_neighbors, min_dist, space_code, pca_dim)`;
        pass `refresh=true` to force recomputation.

        **Query Parameters:**
        - folder_path: Optional.  Scope projection to one folder; omit for all images.
        - method: `umap` (default) or `tsne`.
        - refresh: If true, ignore the on-disk cache and recompute.
        - sample_limit: Cap the number of images projected (default: config `embedding_map.max_points`).
        - n_neighbors: UMAP/t-SNE neighbourhood size (default: 30).
        - min_dist: UMAP min_dist (default: 0.1, ignored for t-SNE).
        - space_code: Embedding-space code (default: `mobilenet_v2_imagenet_gap`).
          Non-default spaces require PostgreSQL.
        - pca_dim: Optional PCA pre-step target dimension. Omit for auto
          (50 when source dim >= 1280, off otherwise). `0` disables PCA.

        **Returns:**
        - points: List of `{image_id, x, y, file_path, thumbnail_path, label, rating, score_general}`.
        - meta: `{count, method, computed_at, cache_key, embedding_space, pca_dim}`.
          When too few images are available `meta.error == "too_few_points"` and
          `points` is empty. Unknown `space_code` returns
          `meta.error == "unknown_embedding_space"`.
        """,
        tags=["Similarity"],
    )
    def get_embedding_map(
        folder_path: Optional[str] = Query(None, description="Scope to folder path"),
        method: str = Query("umap", description="Projection method: umap or tsne"),
        refresh: bool = Query(False, description="Force recomputation, ignoring cache"),
        sample_limit: Optional[int] = Query(None, ge=1, le=50000, description="Max images to project"),
        n_neighbors: int = Query(30, ge=2, le=200, description="UMAP/t-SNE neighbourhood size"),
        min_dist: float = Query(0.1, ge=0.0, le=1.0, description="UMAP min_dist parameter"),
        space_code: Optional[str] = Query(
            None,
            description="Embedding-space code (default: mobilenet_v2_imagenet_gap)",
        ),
        pca_dim: Optional[int] = Query(
            None,
            ge=0,
            le=512,
            description="PCA target dim before UMAP/t-SNE; omit=auto, 0=off",
        ),
    ):
        """Return 2D projection of image embeddings."""
        if method not in ("umap", "tsne"):
            raise HTTPException(status_code=422, detail="method must be 'umap' or 'tsne'")
        from modules import projections
        try:
            result = projections.compute_embedding_map(
                folder_path=folder_path,
                method=method,
                refresh=refresh,
                sample_limit=sample_limit,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                embedding_space=space_code,
                pca_dim=pca_dim,
            )
            return ApiResponse(success=True, message="OK", data=result)
        except Exception as exc:
            logger.error("Error computing embedding map: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get(
        "/embedding_spaces",
        response_model=ApiResponse,
        summary="List embedding spaces",
        description=(
            "Return the registry of active embedding spaces (for UI dropdowns "
            "and `space_code` selection on /embedding_map and /similarity/*). "
            "On Postgres reads from `embedding_spaces`; on Firebird falls back "
            "to the static registry in modules.embedding_spaces."
        ),
        tags=["Similarity"],
    )
    def list_embedding_spaces():
        """Return active embedding-space registry rows."""
        from modules import db
        from modules.embedding_spaces import (
            DEFAULT_EMBEDDING_SPACE_CODE,
            SPACE_DIMS,
        )

        engine = db._get_db_engine()
        spaces: list[dict] = []
        if engine == "postgres":
            from modules import db_postgres
            rows = db_postgres.execute_select(
                "SELECT code, dim, description, active "
                "FROM embedding_spaces "
                "WHERE COALESCE(active, 1) = 1 "
                "ORDER BY id"
            )
            for r in rows:
                spaces.append({
                    "code": r["code"],
                    "dim": int(r["dim"]),
                    "description": r.get("description"),
                    "active": bool(r.get("active", 1)),
                    "is_default": r["code"] == DEFAULT_EMBEDDING_SPACE_CODE,
                })
        else:
            for code, dim in SPACE_DIMS.items():
                spaces.append({
                    "code": code,
                    "dim": dim,
                    "description": None,
                    "active": True,
                    "is_default": code == DEFAULT_EMBEDDING_SPACE_CODE,
                })

        data = {
            "spaces": spaces,
            "meta": {"default_code": DEFAULT_EMBEDDING_SPACE_CODE, "engine": engine},
        }
        return ApiResponse(success=True, message="OK", data=data)


    return router
