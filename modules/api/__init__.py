"""
REST API layer for the Vexlum Scoring WebUI.

Provides endpoints to trigger actions (start/stop/refresh/fetch) and retrieve
the status of running actions for scoring, tagging, and clustering operations.
Includes data query endpoints for Electron app integration.

Endpoints:
    Scoring:
        POST /api/scoring/start - Start batch scoring
        POST /api/scoring/stop - Stop running scoring job
        GET /api/scoring/status - Get scoring job status
        POST /api/scoring/fix-db - Start database fix operation
        POST /api/scoring/single - Score a single image

    Tagging:
        POST /api/tagging/start - Start batch tagging
        POST /api/tagging/stop - Stop running tagging job
        GET /api/tagging/status - Get tagging job status
        POST /api/tagging/single - Tag a single image

    Clustering:
        POST /api/clustering/start - Start clustering job
        POST /api/clustering/stop - Stop running clustering job
        GET /api/clustering/status - Get clustering job status

    Data Queries:
        GET /api/images - Query images with filters and pagination
        GET /api/images/by-uuid/{image_uuid} - Get single image details by image_uuid
        GET /api/images/by-hash/{image_hash} - Get single image details by content hash
        GET /api/images/{image_id} - Get single image details
        GET /api/images/{image_id}/exif - Cached EXIF row (image_exif)
        GET /api/images/{image_id}/xmp - Cached XMP row (image_xmp)
        POST /api/images/{image_id}/geocode/reverse - Reverse geocoding (GPS → address; Nominatim)
        POST /api/images/{image_id}/geocode/forward - Forward geocoding (address → GPS + image_exif)

    Public (read-only image JSON, same payloads as above where applicable):
        GET /public/api/images - Paginated list (page_size max 200)
        GET /public/api/images/by-uuid/{image_uuid}
        GET /public/api/images/by-hash/{image_hash}
        GET /public/api/images/{image_id}
        PATCH /api/images/{image_id} - Update image metadata (rating/label/title/description/keywords)
        DELETE /api/images/{image_id} - Remove image record from database
        GET /api/folders - Get flat folder listing
        GET /api/folders/{folder_id} - Get single folder by id (path, counts)
        GET /api/folders/tree - Get hierarchical folder tree (for Electron sidebar)
        GET /api/folders/phase-status - Get pipeline phase aggregate for a folder
        DELETE /api/folders/cache - Remove empty folder subtree from DB cache (no disk delete)
        POST /api/gallery/export - Export filtered image set to JSON/CSV/XLSX
        GET /api/stacks - Get stacks listing
        GET /api/stacks/{stack_id}/images - Get images in a stack
        GET /api/stats - Get database statistics
        GET /api/analytics/culling - Culling/stack analytics (library or folder scope)
        GET /api/analytics/culling/sessions/{session_id} - Culling session analytics
        GET /api/analytics/stacks/{stack_id} - Per-stack analytics drill-down

    Pipeline:
        POST /api/pipeline/submit - Submit to processing pipeline

    Maintenance:
        POST /api/maintenance/start - Start background maintenance job
        GET /api/maintenance/stale-running-phases - Diagnostic
        POST /api/maintenance/reconcile-terminal-job-phases - Queued reconcile
        POST /api/maintenance/backfill-exif-dates - Queued EXIF repair
        POST /api/maintenance/regenerate-thumbnails - Queued thumb repair
        POST /api/maintenance/prune-missing-files - Queued cleanup
        POST /api/maintenance/schedule-folder-quality-runs - Batch queue validate-and-repair runs per leaf folder

    General:
        GET /api/status - Get status of all runners
        GET /api/health - Health check endpoint
        GET /api/incidents - Paginated image incidents (failures / validations; PostgreSQL)
        GET /api/incidents/{incident_id} - Single incident row

    Electron HTTP DB (optional, gated by config):
        POST /api/db/query - See ``modules/api_db.py`` (SQL bridge for gallery ``engine: api`` mode)
"""

from fastapi import APIRouter, HTTPException, Body, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
import asyncio
import json
import math
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Dict, Any, Literal
import os
import platform
import logging
import time
import threading
from modules.phases_policy import explain_phase_run_decision
from modules.selector_resolver import resolve_selectors
from modules.pipeline_selector_composer import (
    compose_selector_request,
    validate_and_preview,
    serialize_queue_payload,
)
from modules.run_modes import CANONICAL_RUN_MODE, resolve_run_mode_flags

from modules.job_dispatcher import JobDispatcher
from modules.maintenance_job_display import maintenance_job_input_path, build_default_maintenance_description
from modules.job_description import (
    augment_queue_payload_for_audit,
    build_run_submit_description,
    build_scoring_job_description,
    build_clustering_job_description,
    build_tagging_job_description,
    build_bird_species_job_description,
    build_workflow_run_description,
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
from modules import db, config

logger = logging.getLogger(__name__)


from modules.api_helpers import (
    _jobs_recent_json_default,
    _decode_db_row_blobs,
    _normalize_jobs_table_row,
    _job_supports_execution_report,
    _normalize_incident_row,
    _json_response_db,
    _synthetic_bird_species_job_phases,
    _job_phases_for_run_display,
    _merge_model_scores_into,
    _parse_json_object_column,
    _image_detail_payload,
    _json_safe_metadata_row,
    _row_to_dict,
    _parse_rating_filter,
    _images_list_payload,
    _image_neighbors_payload,
    _image_detail_for_uuid_str,
    _image_detail_for_hash_str,
)
from modules.api_models import (
    SelectorRequest,
    ScoringStartRequest,
    TaggingStartRequest,
    BirdSpeciesStartRequest,
    SingleImageRequest,
    TaggingSingleRequest,
    TagPropagationRequest,
    PhaseDecisionResponse,
    StatusResponse,
    HealthResponse,
    ConfigResponse,
    DiagnosticsResponse,
    FindDuplicatesRequest,
    ClusteringStartRequest,
    ImportRegisterRequest,
    PipelineSubmitRequest,
    PipelinePhaseControlRequest,
    PipelineBackfillRequest,
    LifecycleControlRequest,
    IpcBridgeRequest,
    IpcBridgeResponse,
    PipelineRunControlRequest,
    PipelineRestartFromStageRequest,
    PipelineStepRerunRequest,
    MaintenanceStartRequest,
    HealPhaseRequest,
    GeocodeReverseRequest,
    GeocodeForwardRequest,
    ApiResponse,
    NeighborInfo,
    OutlierInfo,
    OutlierResponse,
    CullingAnalyticsResponse,
    ImageUpdateRequest,
    AgentCullDiscoverRequest,
    AgentCullRunRequest,
    AgentCullRecommendationIdsRequest,
    AgentCullDeleteApprovedRequest,
    AgentCullPickStatusRequest,
    ExportRequest,
)


from modules.pipeline_selector_composer import (
    compose_selector_request,
    serialize_queue_payload,
    validate_and_preview,
)
from modules.api.deps import control_job, control_stage, control_step, http_for_transition_error
from modules.api import state as _state
from modules.api.state import (
    graceful_shutdown_processing,
    stop_dispatcher,
    _join_runner_threads,
    _finalize_running_jobs_after_worker_stop,
)

# Test / monkeypatch compatibility (see tests/test_phase_reconcile.py)
_graceful_shutdown_done = False
from modules.api.routers.public import create_public_api_router
from modules.api.routers.shutdown_schema import create_shutdown_schema_router
from modules.api.routers.scoring import create_scoring_router
from modules.api.routers.tagging import create_tagging_router
from modules.api.routers.bird_species import create_bird_species_router
from modules.api.routers.general import create_general_router
from modules.api.routers.debug import create_debug_router
from modules.api.routers.utility import create_utility_router
from modules.api.routers.tasks import create_tasks_router
from modules.api.routers.geo import create_geo_router
from modules.api.routers.similar import create_similar_router
from modules.api.routers.duplicates import create_duplicates_router
from modules.api.routers.embedding import create_embedding_router
from modules.api.routers.clustering import create_clustering_router
from modules.api.routers.data_query import create_data_query_router
from modules.api.routers.agent_cull import create_agent_cull_router
from modules.api.routers.import_register import create_import_register_router
from modules.api.routers.pipeline_submit import create_pipeline_submit_router
from modules.api.routers.electron import create_electron_router
from modules.api.routers.maintenance import create_maintenance_router
from modules.api.routers.ipc_bridge import create_ipc_bridge_router

def create_api_router() -> APIRouter:
    """Create and configure the API router with comprehensive documentation."""
    router = APIRouter(
        prefix="/api",
        tags=["Vexlum Scoring API"],
        responses={
            400: {"description": "Bad Request - Invalid input parameters"},
            404: {"description": "Not Found - Resource not found"},
            500: {"description": "Internal Server Error"},
            503: {"description": "Service Unavailable - Runner not initialized"},
        },
    )
    router.include_router(create_shutdown_schema_router())
    router.include_router(create_scoring_router())
    router.include_router(create_tagging_router())
    router.include_router(create_bird_species_router())
    router.include_router(create_general_router())
    router.include_router(create_debug_router())
    router.include_router(create_utility_router())
    router.include_router(create_tasks_router())
    router.include_router(create_geo_router())
    router.include_router(create_similar_router())
    router.include_router(create_duplicates_router())
    router.include_router(create_embedding_router())
    router.include_router(create_clustering_router())
    router.include_router(create_data_query_router())
    router.include_router(create_agent_cull_router())
    router.include_router(create_import_register_router())
    router.include_router(create_pipeline_submit_router())
    router.include_router(create_electron_router())
    router.include_router(create_maintenance_router())
    router.include_router(create_ipc_bridge_router())
    return router


_RUNNER_ATTRS = frozenset({
    "_scoring_runner",
    "_tagging_runner",
    "_clustering_runner",
    "_selection_runner",
    "_bird_species_runner",
    "_indexing_runner",
    "_metadata_runner",
    "_maintenance_runner",
    "_orchestrator",
    "_job_dispatcher",
})


def __getattr__(name: str):
    if name in _RUNNER_ATTRS:
        return getattr(_state, name)
    if name == "set_runners":
        return set_runners
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def set_runners(
    scoring_runner,
    tagging_runner,
    clustering_runner=None,
    selection_runner=None,
    orchestrator=None,
    bird_species_runner=None,
    indexing_runner=None,
    metadata_runner=None,
    maintenance_runner=None,
):
    """Set runner instances for API access (delegates to state, syncs module attrs)."""
    _state.set_runners(
        scoring_runner,
        tagging_runner,
        clustering_runner=clustering_runner,
        selection_runner=selection_runner,
        orchestrator=orchestrator,
        bird_species_runner=bird_species_runner,
        indexing_runner=indexing_runner,
        metadata_runner=metadata_runner,
        maintenance_runner=maintenance_runner,
    )
    import sys

    mod = sys.modules[__name__]
    for attr in _RUNNER_ATTRS:
        mod.__dict__[attr] = getattr(_state, attr)
