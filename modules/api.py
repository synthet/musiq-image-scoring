"""
REST API layer for the Image Scoring WebUI.

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

    Public (read-only image JSON, same payloads as above where applicable):
        GET /public/api/images - Paginated list (page_size max 200)
        GET /public/api/images/by-uuid/{image_uuid}
        GET /public/api/images/by-hash/{image_hash}
        GET /public/api/images/{image_id}
        PATCH /api/images/{image_id} - Update image metadata (rating/label/title/description/keywords)
        DELETE /api/images/{image_id} - Remove image record from database
        GET /api/folders - Get flat folder listing
        GET /api/folders/tree - Get hierarchical folder tree (for Electron sidebar)
        GET /api/folders/phase-status - Get pipeline phase aggregate for a folder
        POST /api/gallery/export - Export filtered image set to JSON/CSV/XLSX
        GET /api/stacks - Get stacks listing
        GET /api/stacks/{stack_id}/images - Get images in a stack
        GET /api/stats - Get database statistics

    Pipeline:
        POST /api/pipeline/submit - Submit to processing pipeline

    General:
        GET /api/status - Get status of all runners
        GET /api/health - Health check endpoint

    Electron HTTP DB (optional, gated by config):
        POST /api/db/query - Parameterized SQL for local gallery ``engine: api`` mode (SELECT/WITH or writes)
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
import threading
from pathlib import Path
from modules.phases_policy import explain_phase_run_decision
from modules.selector_resolver import resolve_selectors
from modules.pipeline_selector_composer import (
    compose_selector_request,
    validate_and_preview,
    serialize_queue_payload,
)
from modules.run_modes import infer_run_mode, resolve_run_mode_flags

from modules.job_dispatcher import JobDispatcher
from modules import db

logger = logging.getLogger(__name__)


def _jobs_recent_json_default(o: Any) -> Any:
    """json.dumps default=... for GET /api/jobs/recent (driver-native / odd nested values)."""
    if o is None:
        return None
    if isinstance(o, (bytes, memoryview, bytearray)):
        return bytes(o).decode("utf-8", errors="replace")
    if isinstance(o, bool):
        return o
    if isinstance(o, int) and not isinstance(o, bool):
        return o
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return o
    if isinstance(o, str):
        return o
    if isinstance(o, Decimal):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, (datetime, date)):
        try:
            return o.isoformat()
        except Exception:
            pass
    if hasattr(o, "isoformat") and callable(getattr(o, "isoformat", None)):
        try:
            return o.isoformat()
        except Exception:
            pass
    try:
        return str(o)
    except Exception:
        return "<non-stringifiable>"


def _decode_db_row_blobs(d: dict) -> dict:
    """Shallow decode of BLOB / buffer columns from Firebird rows."""
    out = {}
    for k, v in dict(d).items():
        if isinstance(v, (bytes, memoryview, bytearray)):
            out[k] = bytes(v).decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


def _normalize_jobs_table_row(d: dict) -> dict:
    """jobs row: decode BLOBs, parse scope_paths / queue_payload JSON (API contract)."""
    out = _decode_db_row_blobs(d)
    if isinstance(out.get("scope_paths"), str):
        try:
            out["scope_paths"] = json.loads(out["scope_paths"]) if out["scope_paths"] else []
        except (json.JSONDecodeError, TypeError):
            out["scope_paths"] = []
    if out.get("scope_paths") is None:
        out["scope_paths"] = []
    if out.get("scope_type") is None and out.get("input_path"):
        out["scope_type"] = "folder_recursive"
        out["scope_paths"] = out["scope_paths"] or [out["input_path"]]
    qp = out.get("queue_payload")
    if isinstance(qp, str) and qp.strip():
        try:
            out["queue_payload"] = json.loads(qp)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def _json_response_db(data: Any, log_label: str) -> Response:
    """Encode DB-backed payloads without Pydantic Dict[str,Any] serialization (avoids pydantic_core URL bugs)."""
    try:
        body = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=_jobs_recent_json_default,
        )
    except (TypeError, ValueError) as e:
        logger.exception("%s: JSON serialization failed", log_label)
        raise HTTPException(
            status_code=500,
            detail=f"JSON serialization failed: {e!r}",
        ) from e
    return Response(content=body.encode("utf-8"), media_type="application/json")


def _synthetic_bird_species_job_phases(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One job_phases row for bird_species jobs when DB rows are missing or wrong template."""
    st = (job.get("status") or "queued").strip().lower()
    if st in ("pending", "queued"):
        pstate = "queued"
    elif st == "running":
        pstate = "running"
    elif st == "completed":
        pstate = "completed"
    elif st in ("failed", "interrupted"):
        pstate = st
    elif st in ("canceled", "cancelled"):
        pstate = "canceled"
    elif st == "paused":
        pstate = "paused"
    else:
        pstate = "pending"
    return [
        {
            "phase_order": 0,
            "phase_code": "bird_species",
            "state": pstate,
            "started_at": job.get("started_at"),
            "completed_at": job.get("finished_at") or job.get("completed_at"),
            "error_message": None,
        }
    ]


def _job_phases_for_run_display(
    job: Optional[Dict[str, Any]], phases: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Use real job_phases when they include bird_species; else synthesize for bird-only jobs."""
    if not job:
        return phases
    jt = (job.get("job_type") or "").strip().lower()
    if jt not in ("bird_species", "bird-species"):
        return phases
    codes = {(p.get("phase_code") or "").strip().lower() for p in (phases or [])}
    if "bird_species" in codes:
        return phases or []
    return _synthetic_bird_species_job_phases(job)


def _image_detail_payload(image_id: int) -> dict:
    """Full JSON for GET /api/images/{id} and uuid/hash lookups."""
    conn = db.get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM images WHERE id = ?", (image_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")

        data = row.to_dict()
        data["file_paths"] = db.get_all_paths(image_id)
        data["resolved_path"] = db.get_resolved_path(image_id, verified_only=False)
        data["phase_statuses"] = db.get_image_phase_statuses(image_id)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _images_list_payload(
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
    rating: Optional[str],
    label: Optional[str],
    keyword: Optional[str],
    min_score_general: float,
    min_score_aesthetic: float,
    min_score_technical: float,
    folder_path: Optional[str],
    stack_id: Optional[int],
) -> dict:
    """Paginated image rows as JSON (embeddings excluded). Used by /api/images and /public/api/images."""
    rating_filter = [int(r) for r in rating.split(",")] if rating else None
    label_filter = label.split(",") if label else None
    try:
        images, total_count = db.get_images_paginated_with_count(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order,
            rating_filter=rating_filter,
            label_filter=label_filter,
            keyword_filter=keyword,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            folder_path=folder_path,
            stack_id=stack_id,
        )
        return {
            "images": [img.to_dict(exclude_keys={"image_embedding"}) for img in images],
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _image_detail_for_uuid_str(image_uuid: str) -> dict:
    import uuid as uuid_stdlib

    key = (image_uuid or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="image_uuid is required")
    try:
        uuid_stdlib.UUID(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    image_id = db.find_image_id_by_uuid(key)
    if image_id is None:
        raise HTTPException(status_code=404, detail=f"Image not found: uuid={key}")
    return _image_detail_payload(image_id)


def _image_detail_for_hash_str(image_hash: str) -> dict:
    import re

    key = (image_hash or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="image_hash is required")
    if not re.fullmatch(r"[0-9a-fA-F]{32,128}", key):
        raise HTTPException(
            status_code=400,
            detail="image_hash must be a hex string of length 32–128",
        )
    row = db.get_image_by_hash(key)
    if not row:
        raise HTTPException(status_code=404, detail=f"Image not found: hash={key}")
    image_id = row.get("id")
    if image_id is None:
        raise HTTPException(status_code=404, detail=f"Image not found: hash={key}")
    return _image_detail_payload(int(image_id))


def create_public_api_router() -> APIRouter:
    """Read-only JSON API for image records (no job control or mutations).

    Mounted at ``/public/api``. Intended for integrations and scripts that only
    need database-backed image metadata and scores.
    """
    router = APIRouter(
        prefix="/public/api",
        tags=["Public Image API"],
        responses={
            400: {"description": "Bad Request"},
            404: {"description": "Not Found"},
            500: {"description": "Internal Server Error"},
        },
    )

    @router.get(
        "/images",
        summary="List images (public)",
        description="Read-only paginated image rows from the database; same filters as /api/images. "
        "page_size is capped at 200.",
    )
    async def public_list_images(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        sort_by: str = Query(
            "score",
            description="score, date, name, rating, score_general, score_aesthetic, score_technical",
        ),
        order: str = Query("desc", description="asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings"),
        label: Optional[str] = Query(None, description="Comma-separated labels"),
        keyword: Optional[str] = Query(None),
        min_score_general: float = Query(0, ge=0, le=1),
        min_score_aesthetic: float = Query(0, ge=0, le=1),
        min_score_technical: float = Query(0, ge=0, le=1),
        folder_path: Optional[str] = Query(None),
        stack_id: Optional[int] = Query(None),
    ):
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
            folder_path=folder_path,
            stack_id=stack_id,
        )

    @router.get(
        "/images/by-uuid/{image_uuid}",
        summary="Image by UUID (public)",
        description="Same JSON as GET /api/images/by-uuid/{image_uuid}.",
    )
    async def public_get_image_by_uuid(image_uuid: str):
        return _image_detail_for_uuid_str(image_uuid)

    @router.get(
        "/images/by-hash/{image_hash}",
        summary="Image by content hash (public)",
        description="Same JSON as GET /api/images/by-hash/{image_hash}.",
    )
    async def public_get_image_by_hash(image_hash: str):
        return _image_detail_for_hash_str(image_hash)

    @router.get(
        "/images/{image_id}",
        summary="Image by numeric id (public)",
        description="Same JSON as GET /api/images/{image_id}.",
    )
    async def public_get_image_by_id(image_id: int):
        return _image_detail_payload(image_id)

    return router


# Request/Response Models with comprehensive descriptions for LLM agents


class SelectorRequest(BaseModel):
    """Shared selector schema for batch operations."""

    image_ids: Optional[List[int]] = Field(
        None,
        description="Specific image IDs to process.",
        json_schema_extra={"example": [101, 102]}
    )
    image_paths: Optional[List[str]] = Field(
        None,
        description="Specific image file paths to process.",
        json_schema_extra={"example": ["D:/Photos/2024/img001.jpg"]}
    )
    folder_ids: Optional[List[int]] = Field(
        None,
        description="Folder IDs to process.",
        json_schema_extra={"example": [12]}
    )
    folder_paths: Optional[List[str]] = Field(
        None,
        description="Folder paths to process.",
        json_schema_extra={"example": ["D:/Photos/2024"]}
    )
    recursive: bool = Field(
        True,
        description="If True, include subfolders when folder selectors are used.",
        example=True
    )

class ScoringStartRequest(SelectorRequest):
    """Request model for starting a batch image scoring job.
    
    This endpoint initiates quality assessment of images using multiple AI models
    (SPAQ, AVA, KonIQ, PaQ2PiQ, LIQE) to generate technical, aesthetic, and general quality scores.
    
    Attributes:
        input_path: Directory path containing images to score. Supports Windows (D:\\...)
                   and WSL (/mnt/...) paths. Required.
        skip_existing: If True, skip images that already have complete scores in database. 
                      Default: True. Set to False to force re-scoring.
        force_rescore: If True, overwrite existing scores even if complete. 
                      Takes precedence over skip_existing. Default: False.
    
    Example:
        {
            "input_path": "D:/Photos/2024",
            "skip_existing": true,
            "force_rescore": false
        }
    """
    input_path: Optional[str] = Field(
        None,
        description="Directory path containing images to score. Supports Windows (D:\\...) and WSL (/mnt/...) paths.",
        json_schema_extra={"example": "D:/Photos/2024"}
    )
    skip_existing: bool = Field(
        True,
        description="If True, skip images that already have complete scores. Set to False to force re-scoring.",
        json_schema_extra={"example": True}
    )
    force_rescore: bool = Field(
        False,
        description="If True, overwrite existing scores even if complete. Takes precedence over skip_existing.",
        json_schema_extra={"example": False}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "input_path": "D:/Photos/2024",
            "skip_existing": True,
            "force_rescore": False
        }
    })


class TaggingStartRequest(SelectorRequest):
    """Request model for starting a batch image tagging/keyword extraction job.
    
    Uses CLIP (Contrastive Language-Image Pre-Training) to automatically tag images
    with relevant keywords and optionally generate captions using BLIP.
    
    Attributes:
        input_path: Optional directory path containing images to tag.
        custom_keywords: Optional list of custom keywords to use instead of default set.
                       If None, uses default keywords (landscape, portrait, urban, etc.).
        overwrite: If True, overwrite existing keywords in database. Default: False.
        generate_captions: If True, generate image captions using BLIP model. Default: False.
    
    Example:
        {
            "input_path": "D:/Photos/2024",
            "custom_keywords": ["landscape", "sunset", "nature"],
            "overwrite": false,
            "generate_captions": true
        }
    """
    input_path: Optional[str] = Field(
        None,
        description="Optional directory path containing images to tag.",
        example="D:/Photos/2024"
    )
    custom_keywords: Optional[List[str]] = Field(
        None,
        description="Optional list of custom keywords. If None, uses default keyword set.",
        example=["landscape", "sunset", "nature"]
    )
    overwrite: bool = Field(
        False,
        description="If True, overwrite existing keywords in database.",
        example=False
    )
    generate_captions: bool = Field(
        False,
        description="If True, generate image captions using BLIP model.",
        example=True
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "input_path": "D:/Photos/2024",
            "custom_keywords": ["landscape", "sunset"],
            "overwrite": False,
            "generate_captions": True
        }
    })


class BirdSpeciesStartRequest(SelectorRequest):
    """Request model for starting a bird species classification job.

    Only images that already have the 'birds' keyword are processed — all others are
    automatically skipped. Top predicted species are stored as 'species:Common Name'
    keywords using BioCLIP 2 (zero-shot, MIT license).

    Example:
        {
            "input_path": "D:/Photos/2024",
            "threshold": 0.1,
            "top_k": 3,
            "overwrite": false
        }
    """
    input_path: Optional[str] = Field(
        None,
        description="Directory path containing images to classify.",
        example="D:/Photos/2024"
    )
    candidate_species: Optional[List[str]] = Field(
        None,
        description="List of common species names to classify against. "
                    "If None, uses the bundled North American species list.",
        example=["American Robin", "Northern Cardinal", "Mallard"]
    )
    threshold: float = Field(
        0.1,
        description="Minimum softmax probability to store a species prediction.",
        example=0.1
    )
    top_k: int = Field(
        3,
        description="Maximum number of species to store per image.",
        example=3
    )
    overwrite: bool = Field(
        False,
        description="If True, re-classify images that already have species: keywords.",
        example=False
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "input_path": "D:/Photos/2024",
            "threshold": 0.1,
            "top_k": 3,
            "overwrite": False
        }
    })


class SingleImageRequest(BaseModel):
    """Request model for single image operations.

    Used for scoring or fixing metadata for a single image file.

    Attributes:
        file_path: Full path to the image file. Supports Windows and WSL paths.
    
    Example:
        {
            "file_path": "D:/Photos/2024/image.jpg"
        }
    """
    file_path: str = Field(
        ...,
        description="Full path to the image file. Supports Windows (D:\\...) and WSL (/mnt/...) paths.",
        example="D:/Photos/2024/image.jpg"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "file_path": "D:/Photos/2024/image.jpg"
        }
    })


class TaggingSingleRequest(BaseModel):
    """Request model for tagging a single image.
    
    Attributes:
        file_path: Full path to the image file.
        custom_keywords: Optional list of custom keywords. If None, uses default set.
        generate_captions: If True, generate caption for the image. Default: True.
    
    Example:
        {
            "file_path": "D:/Photos/2024/image.jpg",
            "custom_keywords": ["landscape"],
            "generate_captions": true
        }
    """
    file_path: str = Field(
        ...,
        description="Full path to the image file.",
        example="D:/Photos/2024/image.jpg"
    )
    custom_keywords: Optional[List[str]] = Field(
        None,
        description="Optional list of custom keywords. If None, uses default keyword set.",
        example=["landscape", "sunset"]
    )
    generate_captions: bool = Field(
        True,
        description="If True, generate caption for the image using BLIP model.",
        example=True
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "file_path": "D:/Photos/2024/image.jpg",
            "custom_keywords": ["landscape"],
            "generate_captions": True
        }
    })


class TagPropagationRequest(BaseModel):
    """Request model for tag propagation.
    
    Propagates keywords from tagged images to visually similar untagged images.
    
    Attributes:
        folder_path: Optional directory path to restrict propagation to.
        dry_run: If True, only returns candidates without writing to database. Default: True.
        k: Number of nearest neighbors to consider.
        min_similarity: Minimum cosine similarity to consider a neighbor.
        min_keyword_confidence: Minimum confidence score to apply a keyword.
        min_support_neighbors: Minimum number of neighbors that must have the keyword.
        write_mode: 'replace_missing_only' (default) or 'append'.
        max_keywords: Maximum keywords to propagate per image.
    """
    folder_path: Optional[str] = Field(
        None,
        description="Optional directory path to restrict propagation to.",
        example="D:/Photos/2024"
    )
    dry_run: bool = Field(
        True,
        description="If True, only returns candidates without writing to database.",
        example=True
    )
    k: Optional[int] = Field(
        None,
        description="Number of nearest neighbors to consider.",
        example=5
    )
    min_similarity: Optional[float] = Field(
        None,
        description="Minimum cosine similarity to consider a neighbor.",
        example=0.85
    )
    min_keyword_confidence: Optional[float] = Field(
        None,
        description="Minimum confidence score to apply a keyword.",
        example=0.6
    )
    min_support_neighbors: Optional[int] = Field(
        None,
        description="Minimum number of neighbors that must have the keyword.",
        example=2
    )
    write_mode: Optional[str] = Field(
        "replace_missing_only",
        description="'replace_missing_only' (default) or 'append'.",
        example="replace_missing_only"
    )
    max_keywords: Optional[int] = Field(
        None,
        description="Maximum keywords to propagate per image.",
        example=10
    )
    focus_image_id: Optional[int] = Field(
        None,
        description=(
            "When set with dry_run=True, include propagation preview for this image even if "
            "it already has keywords. Suggested keywords exclude ones already on the image."
        ),
        example=None,
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "folder_path": "D:/Photos/2024",
            "dry_run": True,
            "k": 5,
            "min_similarity": 0.85
        }
    })




class PhaseDecisionResponse(BaseModel):
    """Phase policy decision details for one image+phase."""
    image_id: int
    phase_code: str
    should_run: bool
    reason: str
    force_run: bool
    current_executor_version: Optional[str] = None
    stored_status: Optional[str] = None
    stored_executor_version: Optional[str] = None


class StatusResponse(BaseModel):
    """Response model for job status information.
    
    Provides real-time status of running or completed jobs including progress,
    logs, and current state.
    
    Attributes:
        is_running: True if job is currently running, False if idle or completed.
        status_message: Human-readable status message (e.g., "Running...", "Idle", "Done").
        progress: Dictionary with "current" and "total" counts of processed items.
        log: Full log output from the job (may be truncated for long logs).
        job_type: Type of job: "scoring", "fix_db", "tagging", or None if idle.
    
    Example:
        {
            "is_running": true,
            "status_message": "Running...",
            "progress": {"current": 45, "total": 100},
            "log": "Starting batch processing...\\nProcessing image 1...",
            "job_type": "scoring"
        }
    """
    is_running: bool = Field(
        ...,
        description="True if job is currently running, False if idle or completed.",
        example=True
    )
    status_message: str = Field(
        ...,
        description="Human-readable status message (e.g., 'Running...', 'Idle', 'Done').",
        example="Running..."
    )
    progress: Dict[str, int] = Field(
        ...,
        description="Dictionary with 'current' and 'total' counts of processed items.",
        example={"current": 45, "total": 100}
    )
    log: str = Field(
        ...,
        description="Full log output from the job. May be truncated for very long logs.",
        example="Starting batch processing...\nProcessing image 1..."
    )
    job_type: Optional[str] = Field(
        None,
        description="Type of job: 'scoring', 'fix_db', 'tagging', or None if idle.",
        example="scoring"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "is_running": True,
            "status_message": "Running...",
            "progress": {"current": 45, "total": 100},
            "log": "Starting batch processing...\nProcessing image 1...",
            "job_type": "scoring"
        }
    })


class HealthResponse(BaseModel):
    """Response model for health check endpoint.
    
    Indicates API availability and which runners are initialized.
    
    Attributes:
        status: Health status, typically "healthy".
        scoring_available: True if scoring runner is initialized and available.
        tagging_available: True if tagging runner is initialized and available.
    
    Example:
        {
            "status": "healthy",
            "scoring_available": true,
            "tagging_available": true
        }
    """
    status: str = Field(
        ...,
        description="Health status, typically 'healthy'.",
        example="healthy"
    )
    scoring_available: bool = Field(
        ...,
        description="True if scoring runner is initialized and available.",
        example=True
    )
    tagging_available: bool = Field(
        ...,
        description="True if tagging runner is initialized and available.",
        example=True
    )
    clustering_available: bool = Field(
        False,
        description="True if clustering runner is initialized and available.",
        example=True
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "healthy",
            "scoring_available": True,
            "clustering_available": True,
        }
    })


class DiagnosticsResponse(BaseModel):
    """Response model for diagnostics check endpoint."""
    timestamp: str = Field(..., description="ISO 8601 timestamp.")
    system: Dict[str, Any] = Field(..., description="System-level diagnostics (OS, Python, CPU, Memory).")
    database: Dict[str, Any] = Field(..., description="Database diagnostics (Path, Reachable, Size).")
    models: Dict[str, Any] = Field(..., description="Model and GPU diagnostics.")
    filesystem: Dict[str, Any] = Field(..., description="FileSystem diagnostics.")
    config: Dict[str, Any] = Field(..., description="Masked configuration summary.")
    runners: Dict[str, Any] = Field(..., description="Status of all runners.")


class FindDuplicatesRequest(BaseModel):
    """Request model for finding near-duplicate images."""
    threshold: Optional[float] = Field(
        None,
        description="Minimum cosine similarity threshold (default: 0.98).",
        example=0.98
    )
    folder_path: Optional[str] = Field(
        None,
        description="Optional folder path to restrict duplicate search to a specific directory.",
        example="D:/Photos/2024"
    )
    limit: Optional[int] = Field(
        None,
        description="Max number of duplicate pairs to return (defaults to configured duplicate_max_pairs).",
        example=5000
    )


class ClusteringStartRequest(SelectorRequest):
    """Request model for starting a clustering job.

    Clusters images in a folder based on visual similarity and temporal proximity.

    Attributes:
        input_path: Directory path containing images to cluster. If empty, clusters all unprocessed folders.
        threshold: Distance threshold for clustering (lower = stricter grouping).
        time_gap: Time gap in seconds for burst grouping.
        force_rescan: If True, re-cluster even if already processed.
    """
    input_path: Optional[str] = Field(
        None,
        description="Directory path containing images to cluster. None clusters all unprocessed.",
        example="D:/Photos/2024"
    )
    threshold: Optional[float] = Field(
        None,
        description="Distance threshold for clustering (lower = stricter).",
        example=0.15
    )
    time_gap: Optional[int] = Field(
        None,
        description="Time gap in seconds for burst grouping.",
        example=5
    )
    force_rescan: bool = Field(
        False,
        description="If True, re-cluster folders even if already processed.",
        example=False
    )


class ImportRegisterRequest(BaseModel):
    """Request model for registering images from a folder (import without scoring).

    Scans a folder for image files and adds them to the database.
    Supports Windows (D:\\...) and WSL (/mnt/...) paths.
    """
    folder_path: str = Field(
        ...,
        description="Directory path containing images to import.",
        example="D:/Photos/2024"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {"folder_path": "D:/Photos/2024"}
    })


class PipelineSubmitRequest(SelectorRequest):
    """Request model for submitting images/folders to the processing pipeline.

    Chains requested StageRuns sequentially (indexing/metadata/score/tag/cluster).

    Attributes:
        workspace_target: File or directory path to process.
        stage_codes: Ordered stage run codes to execute (indexing|metadata|score|tag|cluster).
        workflow_template: Logical template name for the run (e.g., full_ingest, metadata_only, re_tag).
    """
    workspace_target: Optional[str] = Field(
        None,
        description="WorkspaceTarget path to process (single file or folder). Optional when using selector fields.",
        example="D:/Photos/2024",
        validation_alias=AliasChoices("workspace_target", "input_path"),
        serialization_alias="workspace_target",
    )
    stage_codes: List[str] = Field(
        ["score", "tag"],
        description="Ordered StageRun codes. Valid values: 'indexing', 'metadata', 'score', 'tag', 'cluster'.",
        example=["indexing", "metadata", "score"],
        validation_alias=AliasChoices("stage_codes", "operations"),
        serialization_alias="stage_codes",
    )
    workflow_template: str = Field(
        "custom",
        description="WorkflowTemplate identifier that produced this stage sequence.",
        example="full_ingest",
    )
    skip_existing: bool = Field(
        True,
        description="Skip images that already have results for each operation.",
        example=True
    )
    custom_keywords: Optional[List[str]] = Field(
        None,
        description="Custom keywords for tagging (if 'tag' is in stage_codes)."
    )
    generate_captions: bool = Field(
        False,
        description="Generate captions during tagging.",
        example=False
    )
    clustering_threshold: Optional[float] = Field(
        None,
        description="Distance threshold for clustering (if 'cluster' is in stage_codes)."
    )
    clustering_time_gap: Optional[int] = Field(
        None,
        description="Time gap in seconds for clustering burst grouping (if 'cluster' is in stage_codes)."
    )
    clustering_force_rescan: bool = Field(
        False,
        description="If True, force re-clustering even when folder was already clustered."
    )
    exclude_image_paths: Optional[List[str]] = Field(
        None,
        description="Optional image paths to exclude from resolved selector targets."
    )


class PipelinePhaseControlRequest(BaseModel):
    """Request model for skip/retry controls on a pipeline phase."""
    input_path: str = Field(..., description="Folder path for phase control operation.")
    phase_code: str = Field(..., description="Phase code (e.g. scoring, culling, keywords).")
    reason: Optional[str] = Field(None, description="Skip reason when action=skip.")
    actor: Optional[str] = Field(None, description="Actor identifier who initiated action.")


class PipelineBackfillRequest(BaseModel):
    """Request model for backfill Index/Meta phase status."""
    input_path: str = Field(..., description="Folder path for backfill operation.")


class LifecycleControlRequest(BaseModel):
    """Generic lifecycle control request for workflow/stage/step runs."""
    reason: Optional[str] = Field(None, description="Optional reason for pause/cancel/restart request.")


class IpcBridgeRequest(BaseModel):
    """Generic IPC-style message wrapper for Electron -> FastAPI bridging."""
    channel: str = Field(
        ...,
        description="IPC channel name (e.g. 'pipeline:submit', 'tasks:active').",
        example="pipeline:submit",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Channel-specific payload; mirrors the endpoint body/query shape.",
    )


class IpcBridgeResponse(BaseModel):
    """Response envelope for IPC bridge requests."""
    channel: str = Field(..., description="Echoed IPC channel")
    ok: bool = Field(..., description="True when handler succeeded")
    data: Optional[Any] = Field(None, description="Handler result payload")


class PipelineRunControlRequest(BaseModel):
    """Request model for per-run pipeline controls."""
    input_path: Optional[str] = Field(None, description="Folder path used for restart/cancel scoping.")


class PipelineRestartFromStageRequest(BaseModel):
    """Request model for restarting a pipeline from a specific stage."""
    input_path: str = Field(..., description="Folder path.")
    phase_code: str = Field(..., description="Stage code to restart from (scoring|culling|keywords).")


class PipelineStepRerunRequest(BaseModel):
    """Request model for rerunning a failed idempotent step."""
    image_id: int = Field(..., description="Image ID for the step rerun target.")
    phase_code: str = Field(..., description="Step phase code.")


class ApiResponse(BaseModel):
    """Standard API response model for operation results.
    
    Used for all operation endpoints (start, stop, etc.) to provide consistent
    success/failure feedback.
    
    Attributes:
        success: True if operation succeeded, False otherwise.
        message: Human-readable message describing the result.
        data: Optional dictionary with additional result data (e.g., job_id, file_path).
    
    Example:
        {
            "success": true,
            "message": "Scoring job started successfully",
            "data": {"job_id": 123, "input_path": "D:/Photos/2024"}
        }
    """
    success: bool = Field(
        ...,
        description="True if operation succeeded, False otherwise.",
        example=True
    )
    message: str = Field(
        ...,
        description="Human-readable message describing the result.",
        example="Scoring job started successfully"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional dictionary with additional result data (e.g., job_id, file_path).",
        example={"job_id": 123, "input_path": "D:/Photos/2024"}
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Operation completed successfully",
            "data": {"job_id": 123}
        }
    })


class NeighborInfo(BaseModel):
    """Details for a nearest neighbor in outlier explanation."""
    image_id: int = Field(..., description="Unique image identifier.")
    file_path: str = Field(..., description="Full path to the neighbor image.")
    similarity: float = Field(..., description="Cosine similarity score.")

class OutlierInfo(BaseModel):
    """Detailed information for a detected visual outlier."""
    image_id: int = Field(..., description="Unique image identifier.")
    file_path: str = Field(..., description="Full path to the flagged image.")
    outlier_score: float = Field(..., description="Raw density/outlier score.")
    z_score: float = Field(..., description="Normalized z-score for the outlier.")
    nearest_neighbors: List[NeighborInfo] = Field(..., description="Explained neighbors.")

class OutlierResponse(BaseModel):
    """Response model for visual outlier detection."""
    outliers: List[OutlierInfo] = Field(..., description="List of detected outliers.")
    stats: Dict[str, Any] = Field(..., description="Summary statistics (mean, std, etc.).")
    skipped: List[Dict[str, Any]] = Field(..., description="Images skipped due to missing embeddings.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "outliers": [
                    {
                        "image_id": 42,
                        "z_score": -2.1,
                        "score": 0.18,
                    }
                ],
                "stats": {"total_images": 250, "outliers_found": 7},
                "skipped": [],
            }
        }
    )


class ImageUpdateRequest(BaseModel):
    """Request body for PATCH /api/images/{image_id}."""

    rating: Optional[int] = Field(None, ge=0, le=5, description="Star rating 0–5 (0 = unrated).")
    label: Optional[str] = Field(None, description="Color label: Red, Yellow, Green, Blue, Purple, or empty string to clear.")
    title: Optional[str] = Field(None, description="Image title.")
    description: Optional[str] = Field(None, description="Image description.")
    keywords: Optional[str] = Field(None, description="Comma-separated keywords string.")
    write_sidecar: bool = Field(True, description="If true, also write metadata to XMP sidecar / embedded tags via tagging runner.")


class ExportRequest(BaseModel):
    """Request body for POST /api/gallery/export."""

    format: str = Field("json", description="Export format: json, csv, or xlsx.")
    columns: Optional[List[str]] = Field(None, description="Subset of columns to include. Omit for all columns.")
    folder_path: Optional[str] = Field(None, description="Filter to a specific folder path.")
    rating: Optional[List[int]] = Field(None, description="Rating values to include (e.g. [3,4,5]).")
    label: Optional[List[str]] = Field(None, description="Label values to include (e.g. ['Green','Blue']).")
    keyword: Optional[str] = Field(None, description="Keyword substring to filter on.")
    min_score_general: float = Field(0.0, ge=0, le=1, description="Minimum general score.")
    min_score_aesthetic: float = Field(0.0, ge=0, le=1, description="Minimum aesthetic score.")
    min_score_technical: float = Field(0.0, ge=0, le=1, description="Minimum technical score.")
    date_from: Optional[str] = Field(None, description="Start date filter YYYY-MM-DD.")
    date_to: Optional[str] = Field(None, description="End date filter YYYY-MM-DD.")

# Global references to runners (set by webui.py)
_scoring_runner = None
_tagging_runner = None
_clustering_runner = None
_selection_runner = None
_bird_species_runner = None
_indexing_runner = None
_metadata_runner = None
_orchestrator = None
_job_dispatcher = JobDispatcher()


def _stop_runner_for_phase(phase: str) -> bool:
    phase_norm = (phase or "").strip().lower()
    if phase_norm == "scoring" and _scoring_runner is not None:
        _scoring_runner.stop()
        return True
    if phase_norm in ("keywords", "tagging") and _tagging_runner is not None:
        _tagging_runner.stop()
        return True
    if phase_norm in ("culling", "selection") and _selection_runner is not None:
        _selection_runner.stop()
        return True
    if phase_norm == "clustering" and _clustering_runner is not None:
        _clustering_runner.stop()
        return True
    if phase_norm == "indexing" and _indexing_runner is not None:
        _indexing_runner.stop()
        return True
    if phase_norm == "metadata" and _metadata_runner is not None:
        _metadata_runner.stop()
        return True
    if phase_norm in ("bird_species", "bird-species") and _bird_species_runner is not None:
        _bird_species_runner.stop()
        return True
    return False


def set_runners(scoring_runner, tagging_runner, clustering_runner=None, selection_runner=None, orchestrator=None, bird_species_runner=None, indexing_runner=None, metadata_runner=None):
    """Set the runner instances for API access."""
    global _scoring_runner, _tagging_runner, _clustering_runner, _selection_runner, _orchestrator, _job_dispatcher, _bird_species_runner, _indexing_runner, _metadata_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner
    _clustering_runner = clustering_runner
    _selection_runner = selection_runner
    _orchestrator = orchestrator
    _bird_species_runner = bird_species_runner
    _indexing_runner = indexing_runner
    _metadata_runner = metadata_runner
    _job_dispatcher.set_runners(
        scoring_runner, 
        tagging_runner, 
        clustering_runner, 
        selection_runner, 
        bird_species_runner=bird_species_runner,
        indexing_runner=indexing_runner,
        metadata_runner=metadata_runner,
    )
    _job_dispatcher.start()


def stop_dispatcher():
    """Stop background dispatcher thread, used during server shutdown."""
    try:
        _job_dispatcher.stop()
    except Exception as exc:
        logger.warning("Failed to stop JobDispatcher cleanly: %s", exc)


_graceful_shutdown_lock = threading.Lock()
_graceful_shutdown_done = False


def _map_job_row_to_dispatch_phase(job: Dict[str, Any]) -> str:
    """Map a jobs row to the phase key used by ``_stop_runner_for_phase``."""
    jt = (job.get("job_type") or "").strip().lower()
    cur = (job.get("current_phase") or "").strip().lower()
    if jt == "pipeline" and cur:
        return cur
    if jt in ("tag", "tagging", "keywords"):
        return "keywords"
    if jt in ("selection", "culling"):
        return "culling"
    if jt in ("cluster", "clustering"):
        return "clustering"
    if jt in ("bird_species", "bird-species"):
        return "bird_species"
    return jt or ""


def _stop_runner_for_job_row(job: Dict[str, Any]) -> bool:
    phase = _map_job_row_to_dispatch_phase(job)
    if not phase:
        return False
    if _stop_runner_for_phase(phase):
        return True
    for ph in (
        "indexing",
        "metadata",
        "scoring",
        "keywords",
        "tagging",
        "clustering",
        "selection",
        "culling",
        "bird_species",
    ):
        if _stop_runner_for_phase(ph):
            return True
    return False


def _join_runner_threads(per_thread_timeout: float = 2.0) -> None:
    """Wait for background runner threads to finish after ``stop()``."""
    runners = [
        _indexing_runner,
        _metadata_runner,
        _scoring_runner,
        _tagging_runner,
        _clustering_runner,
        _selection_runner,
        _bird_species_runner,
    ]
    for r in runners:
        if r is None:
            continue
        th = getattr(r, "_thread", None)
        if th is not None and th.is_alive():
            th.join(timeout=per_thread_timeout)


def _finalize_running_jobs_after_worker_stop(reason_log: str = "server_shutdown") -> None:
    """Move jobs still marked running to paused and reset in-flight image_phase_status rows."""
    try:
        rows = db.get_connector().query("SELECT id FROM jobs WHERE status = 'running'")
    except Exception:
        logger.exception("_finalize_running_jobs_after_worker_stop: query failed")
        return
    for r in rows or []:
        jid = r.get("id")
        if jid is None:
            continue
        try:
            db.update_job_status(int(jid), "paused", reason_log)
        except Exception as exc:
            logger.debug("finalize job %s to paused: %s", jid, exc)
        try:
            db.reconcile_stale_running_phases_for_jobs(
                [int(jid)],
                error_message=db.GRACEFUL_PAUSE_MSG,
                in_flight_to="not_started",
            )
        except Exception:
            logger.exception("reconcile in-flight rows for job %s", jid)


def graceful_shutdown_processing(reason: str = "server_shutdown") -> None:
    """Cooperatively stop runners, persist pausable job state, then stop the dispatcher."""
    global _graceful_shutdown_done
    with _graceful_shutdown_lock:
        if _graceful_shutdown_done:
            return
        _graceful_shutdown_done = True
    logger.info("Graceful shutdown: %s", reason)
    try:
        if _orchestrator is not None:
            _orchestrator.stop(mode="graceful")
    except Exception:
        logger.exception("orchestrator.stop(graceful) failed")
    for phase in (
        "indexing",
        "metadata",
        "scoring",
        "keywords",
        "clustering",
        "selection",
        "culling",
        "bird_species",
        "bird-species",
    ):
        try:
            _stop_runner_for_phase(phase)
        except Exception:
            logger.exception("stop runner phase %s", phase)
    _join_runner_threads(per_thread_timeout=3.0)
    try:
        _finalize_running_jobs_after_worker_stop(reason_log=reason)
    except Exception:
        logger.exception("_finalize_running_jobs_after_worker_stop failed")
    stop_dispatcher()


def create_api_router() -> APIRouter:
    """Create and configure the API router with comprehensive documentation.
    
    Returns:
        APIRouter: Configured FastAPI router with all API endpoints.
    """
    router = APIRouter(
        prefix="/api",
        tags=["Image Scoring API"],
        responses={
            400: {"description": "Bad Request - Invalid input parameters"},
            404: {"description": "Not Found - Resource not found"},
            500: {"description": "Internal Server Error"},
            503: {"description": "Service Unavailable - Runner not initialized"}
        }
    )
    
    @router.post(
        "/shutdown",
        summary="Graceful shutdown",
        description="Stop all runners, finalize jobs to paused state, and shutdown the dispatcher gracefully.",
    )
    async def shutdown_api():
        await asyncio.to_thread(graceful_shutdown_processing, "api_request")
        return {"success": True, "message": "Graceful shutdown initiated"}


    def _http_for_transition_error(exc: Exception):
        msg = str(exc)
        if "Invalid" in msg and "transition" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise exc

    def _control_job(job_id: int, target_status: str, reason: Optional[str] = None):
        job = db.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        try:
            db.update_job_status(job_id, target_status, log=reason)
            return db.get_job_by_id(job_id)
        except Exception as exc:
            _http_for_transition_error(exc)

    def _control_stage(job_id: int, phase_code: str, target_state: str, reason: Optional[str] = None):
        job = db.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        phases = db.get_job_phases(job_id)
        if not any((p.get("phase_code") or "").strip().lower() == phase_code.strip().lower() for p in phases):
            raise HTTPException(status_code=404, detail=f"Stage not found: {phase_code}")
        try:
            rows = db.set_job_phase_state(job_id, phase_code.strip().lower(), target_state, error_message=reason)
            return rows
        except Exception as exc:
            _http_for_transition_error(exc)

    def _control_step(image_id: int, phase_code: str, target_status: str, reason: Optional[str] = None):
        try:
            db.set_image_phase_status(image_id, phase_code.strip().lower(), target_status, error=reason)
            return db.get_image_phase_statuses(image_id)
        except Exception as exc:
            _http_for_transition_error(exc)

    # Add schema endpoint for LLM agents
    @router.get(
        "/schema",
        summary="Get API schema (LLM-optimized)",
        description="""
        Get API schema in a format optimized for LLM agents.
        
        Returns a simplified, readable schema description that LLM agents
        can easily parse and understand. This is a simplified version of
        the full OpenAPI schema available at /openapi.json.
        
        **Use Cases:**
        - LLM agent API discovery
        - Code generation
        - API understanding without parsing full OpenAPI spec
        
        **Note:** For complete OpenAPI 3.0 schema, use /openapi.json instead.
        """
    )
    async def get_api_schema():
        """Get API schema in a format optimized for LLM agents."""
        from fastapi.openapi.utils import get_openapi
        from fastapi import Request
        
        # This will be populated when the router is included in the main app
        # For now, return a structured description
        return {
            "api_name": "Image Scoring WebUI API",
            "version": "1.0.0",
            "base_url": "/api",
            "description": "REST API for image quality assessment and tagging operations",
            "endpoints": {
                "scoring": {
                    "start": {
                        "method": "POST",
                        "path": "/api/scoring/start",
                        "description": "Start batch image scoring job",
                        "request_body": {
                            "type": "object",
                            "required": ["input_path"],
                            "properties": {
                                "input_path": {"type": "string", "description": "Directory path containing images"},
                                "skip_existing": {"type": "boolean", "default": True},
                                "force_rescore": {"type": "boolean", "default": False}
                            }
                        },
                        "response": {
                            "type": "object",
                            "properties": {
                                "success": {"type": "boolean"},
                                "message": {"type": "string"},
                                "data": {"type": "object"}
                            }
                        }
                    },
                    "stop": {
                        "method": "POST",
                        "path": "/api/scoring/stop",
                        "description": "Stop running scoring job"
                    },
                    "status": {
                        "method": "GET",
                        "path": "/api/scoring/status",
                        "description": "Get current scoring job status",
                        "response": {
                            "type": "object",
                            "properties": {
                                "is_running": {"type": "boolean"},
                                "status_message": {"type": "string"},
                                "progress": {"type": "object"},
                                "log": {"type": "string"},
                                "job_type": {"type": "string"}
                            }
                        }
                    },
                    "fix-db": {
                        "method": "POST",
                        "path": "/api/scoring/fix-db",
                        "description": "Start database fix operation (re-score incomplete records)"
                    },
                    "single": {
                        "method": "POST",
                        "path": "/api/scoring/single",
                        "description": "Score a single image",
                        "request_body": {
                            "type": "object",
                            "required": ["file_path"],
                            "properties": {
                                "file_path": {"type": "string"}
                            }
                        }
                    },
                    "fix-image": {
                        "method": "POST",
                        "path": "/api/scoring/fix-image",
                        "description": "Fix metadata for a single image (recalculate from existing data)"
                    }
                },
                "tagging": {
                    "start": {
                        "method": "POST",
                        "path": "/api/tagging/start",
                        "description": "Start batch tagging job",
                        "request_body": {
                            "type": "object",
                            "properties": {
                                "input_path": {"type": "string"},
                                "custom_keywords": {"type": "array", "items": {"type": "string"}},
                                "overwrite": {"type": "boolean", "default": False},
                                "generate_captions": {"type": "boolean", "default": False}
                            }
                        }
                    },
                    "stop": {
                        "method": "POST",
                        "path": "/api/tagging/stop",
                        "description": "Stop running tagging job"
                    },
                    "status": {
                        "method": "GET",
                        "path": "/api/tagging/status",
                        "description": "Get current tagging job status"
                    },
                    "single": {
                        "method": "POST",
                        "path": "/api/tagging/single",
                        "description": "Tag a single image"
                    }
                },
                "clustering": {
                    "start": {
                        "method": "POST",
                        "path": "/api/clustering/start",
                        "description": "Start clustering job (group similar images into stacks)",
                        "request_body": {
                            "type": "object",
                            "properties": {
                                "input_path": {"type": "string", "description": "Folder path (null for all)"},
                                "threshold": {"type": "number"},
                                "time_gap": {"type": "integer"},
                                "force_rescan": {"type": "boolean", "default": False}
                            }
                        }
                    },
                    "stop": {
                        "method": "POST",
                        "path": "/api/clustering/stop",
                        "description": "Stop running clustering job"
                    },
                    "status": {
                        "method": "GET",
                        "path": "/api/clustering/status",
                        "description": "Get current clustering job status"
                    }
                },
                "data": {
                    "images": {
                        "method": "GET",
                        "path": "/api/images",
                        "description": "Query images with filters, sorting, and pagination",
                        "query_params": {
                            "page": {"type": "integer", "default": 1},
                            "page_size": {"type": "integer", "default": 50},
                            "sort_by": {"type": "string", "default": "score"},
                            "order": {"type": "string", "default": "desc"},
                            "rating": {"type": "string", "description": "Comma-separated ratings"},
                            "label": {"type": "string", "description": "Comma-separated labels"},
                            "keyword": {"type": "string"},
                            "folder_path": {"type": "string"},
                            "stack_id": {"type": "integer"},
                            "min_score_general": {"type": "number"},
                            "min_score_aesthetic": {"type": "number"},
                            "min_score_technical": {"type": "number"}
                        }
                    },
                    "image_details": {
                        "method": "GET",
                        "path": "/api/images/{image_id}",
                        "description": "Get full details for a single image"
                    },
                    "folders": {
                        "method": "GET",
                        "path": "/api/folders",
                        "description": "Get all folders in the database"
                    },
                    "stacks": {
                        "method": "GET",
                        "path": "/api/stacks",
                        "description": "Get stacks listing with cover images"
                    },
                    "stack_images": {
                        "method": "GET",
                        "path": "/api/stacks/{stack_id}/images",
                        "description": "Get all images in a stack"
                    },
                    "stats": {
                        "method": "GET",
                        "path": "/api/stats",
                        "description": "Get comprehensive database statistics"
                    }
                },
                "pipeline": {
                    "submit": {
                        "method": "POST",
                        "path": "/api/pipeline/submit",
                        "description": "Create a WorkflowRun for a WorkspaceTarget (indexing/metadata/score/tag/cluster StageRuns)",
                        "request_body": {
                            "type": "object",
                            "required": ["workspace_target"],
                            "properties": {
                                "workspace_target": {"type": "string"},
                                "stage_codes": {"type": "array", "items": {"type": "string"}, "default": ["score", "tag"]},
                                "workflow_template": {"type": "string", "default": "custom"},
                                "skip_existing": {"type": "boolean", "default": True},
                                "custom_keywords": {"type": "array", "items": {"type": "string"}},
                                "generate_captions": {"type": "boolean", "default": False},
                                "clustering_threshold": {"type": "number"},
                                "clustering_time_gap": {"type": "integer"},
                                "clustering_force_rescan": {"type": "boolean", "default": False}
                            }
                        }
                    }
                },
                "general": {
                    "status": {
                        "method": "GET",
                        "path": "/api/status",
                        "description": "Get status of all runners (scoring, tagging, clustering)"
                    },
                    "health": {
                        "method": "GET",
                        "path": "/api/health",
                        "description": "Health check endpoint"
                    },
                    "diagnostics": {
                        "method": "GET",
                        "path": "/api/diagnostics",
                        "description": "Comprehensive system diagnostics"
                    },
                    "jobs_recent": {
                        "method": "GET",
                        "path": "/api/jobs/recent",
                        "description": "Get recent job history",
                        "query_params": {
                            "limit": {"type": "integer", "default": 10}
                        }
                    },
                    "job_details": {
                        "method": "GET",
                        "path": "/api/jobs/{job_id}",
                        "description": "Get details for a specific job",
                        "path_params": {
                            "job_id": {"type": "integer"}
                        }
                    }
                }
            },
            "note": "For complete OpenAPI schema, visit /openapi.json or /docs"
        }
    
    # ========== Scoring Endpoints ==========
    
    @router.post(
        "/scoring/start",
        response_model=ApiResponse,
        summary="Start batch image scoring",
        description="""
        Initiates a batch image quality assessment job for all images in the specified directory.
        
        The scoring process uses multiple AI models to evaluate images:
        - **SPAQ**: Spatial Perception of Aesthetic Quality
        - **AVA**: Aesthetic Visual Analysis
        - **KonIQ**: Konstanz Image Quality
        - **PaQ2PiQ**: Perceptual Quality to Perceptual Image Quality
        - **LIQE**: Learning Image Quality Evaluator
        
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

        if _scoring_runner is None:
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
            selector_result = resolve_selectors(
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
        job_source = request.input_path or "SELECTOR_SCORING"
        skip_existing = not request.force_rescore if request.force_rescore else request.skip_existing
        queue_payload = {
            "skip_existing": skip_existing,
            "input_path": request.input_path,
            "resolved_image_ids": selector_result.get("resolved_image_ids"),
        }
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code="scoring",
            job_type="scoring",
            queue_payload=queue_payload,
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
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not _scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="No scoring job is currently running",
                data={"is_running": False}
            )
        
        _scoring_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to scoring job",
            data={"is_running": _scoring_runner.is_running}
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
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        result = _scoring_runner.get_status()
        is_running, log_text, status_message, current, total = result[:5]
        
        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type=getattr(_scoring_runner, 'job_type', None)
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
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if _scoring_runner.is_running:
            return ApiResponse(
                success=False,
                message="Scoring job is already running",
                data={"is_running": True}
            )
        
        from modules import db
        job_id = db.create_job("DB_FIX_OPERATION")
        result = _scoring_runner.start_fix_db(job_id)
        
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
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _scoring_runner.run_single_image(request.file_path)
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    
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

        if _tagging_runner is None:
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
            selector_result = resolve_selectors(
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
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code="keywords",
            job_type="tagging",
            queue_payload={
                "input_path": request.input_path,
                "custom_keywords": request.custom_keywords,
                "overwrite": request.overwrite,
                "generate_captions": request.generate_captions,
                "resolved_image_ids": selector_result.get("resolved_image_ids"),
            },
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue tagging job")
        db.create_job_phases(job_id, ["keywords"], first_phase_state="queued")

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
        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if not _tagging_runner.is_running:
            return ApiResponse(
                success=False,
                message="No tagging job is currently running",
                data={"is_running": False}
            )
        
        _tagging_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to tagging job",
            data={"is_running": _tagging_runner.is_running}
        )
    
    @router.get(
        "/tagging/status",
        response_model=StatusResponse,
        summary="Get tagging status",
        description="Returns the current status of the tagging job including progress and logs."
    )
    async def get_tagging_status():
        """Get the current status of the tagging job."""
        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        result = _tagging_runner.get_status()
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
        if _tagging_runner is None:
            raise HTTPException(status_code=503, detail="Tagging runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _tagging_runner.run_single_image(
            request.file_path,
            request.custom_keywords,
            request.generate_captions
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
    
    # ========== Bird Species Endpoints ==========

    @router.post(
        "/bird-species/start",
        response_model=ApiResponse,
        summary="Start bird species classification",
        description="""
        Classify bird species for images that already have the 'birds' keyword.

        Images **without** the 'birds' keyword are automatically skipped — no need to
        pre-filter. Top predictions are stored as 'species:Common Name' keywords using
        BioCLIP 2 (zero-shot, MIT license).

        The job runs asynchronously via the job queue. Monitor progress with
        GET /api/bird-species/status.

        **Requires:** `open_clip_torch` installed (`pip install open_clip_torch`).
        """
    )
    async def start_bird_species(request: BirdSpeciesStartRequest):
        """Start a bird species classification job."""
        if _bird_species_runner is None:
            raise HTTPException(status_code=503, detail="Bird species runner not available")

        if not any([request.input_path, request.image_ids, request.image_paths,
                    request.folder_ids, request.folder_paths]):
            raise HTTPException(
                status_code=400,
                detail="Provide input_path or at least one selector (image_ids, folder_paths, etc.)"
            )

        if request.input_path and not os.path.exists(request.input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.input_path}")

        selector_result = {"resolved_image_ids": None}
        has_explicit_selectors = any([
            request.image_ids, request.image_paths,
            request.folder_ids, request.folder_paths,
        ])
        if has_explicit_selectors:
            selector_result = resolve_selectors(
                image_ids=request.image_ids,
                image_paths=request.image_paths,
                folder_ids=request.folder_ids,
                folder_paths=request.folder_paths,
                recursive=request.recursive,
                index_missing=True,
            )

        resolved_ids = selector_result.get("resolved_image_ids")
        resolved_count = len(resolved_ids) if resolved_ids is not None else None
        job_source = request.input_path or "SELECTOR_BIRD_SPECIES"

        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code=None,
            job_type="bird_species",
            queue_payload={
                "input_path": request.input_path,
                "candidate_species": request.candidate_species,
                "threshold": request.threshold,
                "top_k": request.top_k,
                "overwrite": request.overwrite,
                "resolved_image_ids": resolved_ids,
            },
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue bird species job")

        await asyncio.to_thread(db.create_job_phases, job_id, ["bird_species"], "queued")

        return ApiResponse(
            success=True,
            message="Bird species classification job queued",
            data={
                "job_id": job_id,
                "input_path": request.input_path,
                "resolved_count": resolved_count,
                "queue_position": queue_position,
            }
        )

    @router.post(
        "/bird-species/stop",
        response_model=ApiResponse,
        summary="Stop bird species job",
        description="Send a stop signal to the running bird species classification job."
    )
    async def stop_bird_species():
        """Stop the running bird species classification job."""
        if _bird_species_runner is None:
            raise HTTPException(status_code=503, detail="Bird species runner not available")
        if not _bird_species_runner.is_running:
            return ApiResponse(
                success=False,
                message="No bird species job is currently running",
                data={"is_running": False}
            )
        _bird_species_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to bird species runner",
            data={"is_running": _bird_species_runner.is_running}
        )

    @router.get(
        "/bird-species/status",
        summary="Get bird species status",
        description="Get the current status of the bird species classification runner."
    )
    async def get_bird_species_status():
        """Get bird species runner status."""
        if _bird_species_runner is None:
            raise HTTPException(status_code=503, detail="Bird species runner not available")
        is_running, log_text, status_message, current, total = _bird_species_runner.get_status()
        return {
            "is_running": is_running,
            "status_message": status_message,
            "current": current,
            "total": total,
            "log": log_text,
            "job_type": "bird_species",
        }

    # ========== General Endpoints ==========

    @router.get(
        "/status",
        response_model=Dict[str, Any],
        summary="Get all runners status",
        description="""
        Returns the status of all runners (scoring and tagging) in a single response.
        
        Useful for monitoring the overall system state. Each runner's status includes:
        - Availability (whether runner is initialized)
        - Running state
        - Progress information
        - Status message
        - Recent log output (last 2000 characters)
        
        **Response Structure:**
        ```json
        {
            "scoring": {
                "available": true,
                "is_running": false,
                "status_message": "Idle",
                "progress": {"current": 0, "total": 0},
                "log": "",
                "job_type": null
            },
            "tagging": {
                "available": true,
                "is_running": false,
                "status_message": "Idle",
                "progress": {"current": 0, "total": 0},
                "log": ""
            }
        }
        ```
        """
    )
    async def get_all_status():
        """Get status of all runners."""
        status = {
            "scoring": {"available": False},
            "tagging": {"available": False},
            "clustering": {"available": False}
        }

        if _scoring_runner:
            try:
                result = _scoring_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["scoring"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else "",  # Last 2000 chars
                    "job_type": getattr(_scoring_runner, 'job_type', None)
                }
            except Exception as e:
                status["scoring"]["error"] = str(e)

        if _tagging_runner:
            try:
                result = _tagging_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["tagging"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else ""
                }
            except Exception as e:
                status["tagging"]["error"] = str(e)

        if _clustering_runner:
            try:
                result = _clustering_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["clustering"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else ""
                }
            except Exception as e:
                status["clustering"]["error"] = str(e)

        return status
    
    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="""
        Simple health check endpoint to verify API availability and runner initialization.
        
        Returns:
        - status: "healthy" if API is operational
        - scoring_available: True if scoring runner is initialized
        - tagging_available: True if tagging runner is initialized
        
        Use this endpoint for:
        - Health monitoring
        - Service discovery
        - Initial API capability detection
        """
    )
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            scoring_available=_scoring_runner is not None,
            tagging_available=_tagging_runner is not None,
            clustering_available=_clustering_runner is not None
        )

    class DbQueryRequest(BaseModel):
        """Body for POST /api/db/query (Electron ApiConnector)."""

        sql: str = Field(
            ...,
            description="SELECT/WITH (read) or INSERT/UPDATE/DELETE; Firebird-style ? placeholders",
        )
        params: List[Any] = Field(default_factory=list, description="Bound values for each ? in order")

    class DbQueryResponse(BaseModel):
        data: List[Dict[str, Any]]

    @router.post(
        "/db/query",
        response_model=DbQueryResponse,
        summary="SQL bridge for Electron API DB mode",
        description="""
        Executes parameterized SQL against the configured database engine (Firebird or PostgreSQL).
        Intended for the Electron gallery when ``database.engine`` is ``api`` and the app talks to this
        WebUI over HTTP. **Treat like direct DB access** — disable on untrusted networks via config.

        **Reads:** SQL must start with ``SELECT`` or ``WITH`` (``WITH``…``SELECT``). Row cap:
        ``database.api_db_query_max_rows`` (default 5000, max 50000).

        **Writes:** ``INSERT`` / ``UPDATE`` / ``DELETE`` (including Firebird ``UPDATE OR INSERT``) when
        ``database.api_db_allow_write_queries`` is true (default). DDL and ``DROP``/``TRUNCATE``/etc. are rejected.

        Uses Firebird-style ``?`` placeholders; translated when ``database.engine`` is ``postgres``.
        """,
    )
    async def api_db_query(request: DbQueryRequest):
        from modules import config as _cfg

        if not _cfg.get_config_value("database.enable_api_db_query", True):
            raise HTTPException(
                status_code=403,
                detail="POST /api/db/query is disabled (database.enable_api_db_query)",
            )
        max_rows = int(_cfg.get_config_value("database.api_db_query_max_rows", 5000))
        sql_text = (request.sql or "").strip()
        upper = sql_text.upper()
        is_read = upper.startswith("SELECT") or upper.startswith("WITH")
        try:
            if is_read:
                rows = db.execute_readonly_sql_for_api(
                    request.sql,
                    request.params,
                    max_rows=max_rows,
                )
            elif _cfg.get_config_value("database.api_db_allow_write_queries", True):
                rows = db.execute_write_sql_for_api(request.sql, request.params)
            else:
                raise HTTPException(
                    status_code=403,
                    detail="Write SQL is disabled (database.api_db_allow_write_queries)",
                )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("api_db_query failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return DbQueryResponse(data=rows)

    # ========== Debug / Profiling Endpoints ==========

    @router.get(
        "/debug/requests",
        summary="Request profiling dashboard",
        tags=["Debug"],
    )
    async def debug_requests():
        """In-flight requests, slow request history, and event loop health."""
        from modules.profiling import get_tracker, get_loop_monitor

        tracker = get_tracker()
        monitor = get_loop_monitor()
        if tracker is None:
            return {"error": "Profiling not initialized"}

        return {
            "request_stats": tracker.get_stats(),
            "in_flight": tracker.get_in_flight(),
            "slow_requests": tracker.get_slow_history(limit=30),
            "event_loop": monitor.get_stats() if monitor else {},
            "event_loop_recent": monitor.get_recent_lags(limit=30) if monitor else [],
        }

    @router.get(
        "/debug/loop-lag",
        summary="Current event loop lag",
        tags=["Debug"],
    )
    async def debug_loop_lag():
        """Quick event loop health check."""
        from modules.profiling import get_loop_monitor

        monitor = get_loop_monitor()
        if not monitor:
            return {"lag_ms": -1, "status": "monitor_not_running"}
        lag = monitor.current_lag_ms
        status = "healthy" if lag < 200 else "degraded" if lag < 1000 else "blocked"
        return {"lag_ms": round(lag, 1), "status": status}

    # ========== Utility Endpoints ==========

    @router.post(
        "/scoring/fix-image",
        response_model=ApiResponse,
        summary="Fix image metadata",
        description="""
        Recalculates scores and updates metadata for a single image without running neural networks.
        
        This operation:
        - Uses existing model scores from the database
        - Recalculates weighted scores (technical, aesthetic, general)
        - Updates rating and color label based on recalculated scores
        - Writes updated metadata to XMP sidecar and embedded metadata
        - Regenerates thumbnail if needed
        
        **Use Cases:**
        - Fixing metadata after score recalculation logic changes
        - Updating ratings/labels without re-running expensive model inference
        - Correcting corrupted metadata
        
        **Requirements:**
        - Image must exist in database
        - At least one model score must be present
        - If all scores missing, operation will fail
        
        This is much faster than full re-scoring as it doesn't run AI models.
        """
    )
    async def fix_image_metadata(request: SingleImageRequest):
        """Fix metadata for a single image (recalculate scores from existing data)."""
        if _scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = _scoring_runner.fix_image_metadata(request.file_path)
        
        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    
    @router.get(
        "/raw-preview",
        summary="Get RAW file preview",
        description="""
        Extracts or generates a JPEG preview for a RAW image file.
        
        This endpoint is optimized for performance:
        - Tries to extract embedded JPEG preview first (fastest)
        - Falls back to full RAW decode if needed
        - Caches generated previews
        - Returns a JPEG image directly
        
        **Query Parameters:**
        - path: Full path to the specific image file (URL encoded)
        """
    )
    async def get_raw_preview(path: str = Query(..., description="Full path to the image file")):
        """Get or generate a preview for a RAW file."""
        import urllib.parse
        from modules import thumbnails
        from modules import db
        
        decoded_path = urllib.parse.unquote(path)
        
        # specific handler for simple filenames (look up in DB)
        if not os.path.exists(decoded_path) and not os.path.isabs(decoded_path):
            try:
                # Try to find file in database by filename
                conn = db.get_db()
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT file_path FROM images WHERE file_name = ?", (decoded_path,))
                    row = cursor.fetchone()
                    if row:
                        decoded_path = row[0]
                except Exception as e:
                    print(f"Error looking up path for {decoded_path}: {e}")
                finally:
                    conn.close()
            except Exception:
                pass

        if not os.path.exists(decoded_path):
            # Try converting WSL path to Windows if running on Windows
            if decoded_path.startswith('/mnt/'):
                try:
                    parts = decoded_path.split('/')
                    if len(parts) > 2:
                        drive = parts[2].upper()
                        rest = os.sep.join(parts[3:])
                        win_path = f"{drive}:{os.sep}{rest}"
                        if os.path.exists(win_path):
                            decoded_path = win_path
                except (OSError, IndexError, ValueError):
                    pass

        if not os.path.exists(decoded_path):
             # Try appending to current working directory if just a relative path
             abs_path = os.path.abspath(decoded_path)
             if os.path.exists(abs_path):
                 decoded_path = abs_path
             else:
                 raise HTTPException(status_code=404, detail=f"File not found: {decoded_path}")

        try:
            preview_path = thumbnails.generate_preview(decoded_path)
            
            if preview_path and os.path.exists(preview_path):
                return FileResponse(preview_path, media_type="image/jpeg")
            else:
                 raise HTTPException(status_code=500, detail="Failed to generate preview")
                 
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/images/generate-thumbnail",
        summary="Generate thumbnail for an image",
        description="Generate and persist a thumbnail for an image that is missing one. "
                    "Updates the database with the new thumbnail path.",
    )
    async def generate_thumbnail_endpoint(request: SingleImageRequest):
        """Generate a thumbnail on demand for a single image."""
        import urllib.parse
        from modules import thumbnails
        from modules import db

        file_path = request.file_path
        decoded_path = urllib.parse.unquote(file_path)

        # --- path resolution (mirrors get_raw_preview) ---
        if not os.path.exists(decoded_path) and not os.path.isabs(decoded_path):
            try:
                conn = db.get_db()
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT file_path FROM images WHERE file_name = ?", (decoded_path,))
                    row = cursor.fetchone()
                    if row:
                        decoded_path = row[0]
                except Exception:
                    pass
                finally:
                    conn.close()
            except Exception:
                pass

        if not os.path.exists(decoded_path):
            if decoded_path.startswith('/mnt/'):
                try:
                    parts = decoded_path.split('/')
                    if len(parts) > 2:
                        drive = parts[2].upper()
                        rest = os.sep.join(parts[3:])
                        win_path = f"{drive}:{os.sep}{rest}"
                        if os.path.exists(win_path):
                            decoded_path = win_path
                except (OSError, IndexError, ValueError):
                    pass

        if not os.path.exists(decoded_path):
            abs_path = os.path.abspath(decoded_path)
            if os.path.exists(abs_path):
                decoded_path = abs_path
            else:
                raise HTTPException(status_code=404, detail=f"File not found: {decoded_path}")

        # --- generate thumbnail ---
        try:
            thumb_path = thumbnails.generate_thumbnail(decoded_path)
            if not thumb_path or not os.path.exists(thumb_path):
                raise HTTPException(status_code=500, detail="Thumbnail generation failed")

            thumb_win = thumbnails.thumb_path_to_win(thumb_path)

            # Update DB (normalized thumbnail_path / thumbnail_path_win)
            try:
                row = db.get_image_details(decoded_path) or db.get_image_details(decoded_path.replace("\\", "/"))
                if not row or not row.get("id"):
                    row = db.get_image_details(file_path)
                if row and row.get("id"):
                    db.update_image_thumbnail_paths(int(row["id"]), thumb_path, None)
                else:
                    conn = db.get_db()
                    cursor = conn.cursor()
                    try:
                        tp, tw = thumbnails.normalize_stored_thumbnail_pair(thumb_path, None)
                        if not tw and tp:
                            tw = thumbnails.thumb_path_to_win(tp)
                        cursor.execute(
                            "UPDATE images SET thumbnail_path=?, thumbnail_path_win=? WHERE file_path=?",
                            (tp, tw, file_path),
                        )
                        if cursor.rowcount == 0:
                            cursor.execute(
                                "UPDATE images SET thumbnail_path=?, thumbnail_path_win=? WHERE file_path=?",
                                (tp, tw, decoded_path),
                            )
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        print(f"Warning: thumbnail generated but DB update failed: {e}")
                    finally:
                        conn.close()
            except Exception as e:
                print(f"Warning: could not update DB with thumbnail path: {e}")

            return {
                "success": True,
                "thumbnail_path": thumb_win,
                "message": "Thumbnail generated successfully",
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ========== Tasks (Unified Active State) ==========

    @router.get(
        "/tasks/active",
        response_model=Dict[str, Any],
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
            if _scoring_runner:
                try:
                    result = _scoring_runner.get_status()
                    is_running, log, status_msg, current, total = result[:5]
                    runners["scoring"] = {
                        "available": True,
                        "is_running": is_running,
                        "status_message": status_msg,
                        "progress": {"current": current, "total": total},
                        "log": log[-2000:] if log else "",
                        "job_type": getattr(_scoring_runner, 'job_type', None)
                    }
                except Exception as e:
                    runners["scoring"]["error"] = str(e)
            if _tagging_runner:
                try:
                    result = _tagging_runner.get_status()
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
            if _clustering_runner:
                try:
                    result = _clustering_runner.get_status()
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
            state = _job_dispatcher.get_state()
            state["queue"] = db.get_queued_jobs(limit=limit)
            state["queue_size"] = len(state["queue"])
            dispatcher = state

            # Active job: first running job from recent jobs, or from active runner's job_id
            active_job = None
            active_runner = dispatcher.get("active_runner")
            if active_runner:
                # Try to get job_id from the active runner
                runner = None
                if active_runner == "scoring" and _scoring_runner:
                    runner = _scoring_runner
                elif active_runner == "tagging" and _tagging_runner:
                    runner = _tagging_runner
                elif active_runner == "clustering" and _clustering_runner:
                    runner = _clustering_runner
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
        """
    )
    async def get_recent_jobs(limit: int = 10):
        """Get recent job history."""
        from modules import db
        try:
            jobs = await asyncio.wait_for(
                asyncio.to_thread(db.get_jobs, limit),
                timeout=30.0,
            )
            result = [_normalize_jobs_table_row(dict(j)) for j in jobs]
            return _json_response_db(result, "GET /api/jobs/recent")
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
            state = _job_dispatcher.get_state()
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
            return _json_response_db(payload, f"GET /api/jobs/{job_id}")
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
        state = _control_job(job_id, "paused", request.reason)
        return ApiResponse(success=True, message="Workflow paused", data={"job": state})

    @router.post("/workflow-runs/{job_id}/resume", response_model=ApiResponse, summary="Resume workflow run")
    async def resume_workflow_run(job_id: int, request: LifecycleControlRequest):
        state = _control_job(job_id, "running", request.reason)
        return ApiResponse(success=True, message="Workflow resumed", data={"job": state})

    @router.post("/workflow-runs/{job_id}/restart", response_model=ApiResponse, summary="Restart workflow run")
    async def restart_workflow_run(job_id: int, request: LifecycleControlRequest):
        _control_job(job_id, "restarting", request.reason)
        state = _control_job(job_id, "queued", request.reason)
        return ApiResponse(success=True, message="Workflow restarting", data={"job": state})

    @router.post("/stage-runs/{job_id}/{phase_code}/pause", response_model=ApiResponse, summary="Pause stage run")
    async def pause_stage_run(job_id: int, phase_code: str, request: LifecycleControlRequest):
        rows = _control_stage(job_id, phase_code, "paused", request.reason)
        return ApiResponse(success=True, message="Stage paused", data={"phases": rows, "phase_code": phase_code})

    @router.post("/stage-runs/{job_id}/{phase_code}/resume", response_model=ApiResponse, summary="Resume stage run")
    async def resume_stage_run(job_id: int, phase_code: str, request: LifecycleControlRequest):
        rows = _control_stage(job_id, phase_code, "running", request.reason)
        return ApiResponse(success=True, message="Stage resumed", data={"phases": rows, "phase_code": phase_code})

    @router.post("/stage-runs/{job_id}/{phase_code}/restart", response_model=ApiResponse, summary="Restart stage run")
    async def restart_stage_run(job_id: int, phase_code: str, request: LifecycleControlRequest):
        _control_stage(job_id, phase_code, "restarting", request.reason)
        rows = _control_stage(job_id, phase_code, "queued", request.reason)
        return ApiResponse(success=True, message="Stage restarting", data={"phases": rows, "phase_code": phase_code})

    @router.post("/step-runs/{image_id}/{phase_code}/pause", response_model=ApiResponse, summary="Pause step run")
    async def pause_step_run(image_id: int, phase_code: str, request: LifecycleControlRequest):
        statuses = _control_step(image_id, phase_code, "paused", request.reason)
        return ApiResponse(success=True, message="Step paused", data={"image_id": image_id, "statuses": statuses})

    @router.post("/step-runs/{image_id}/{phase_code}/resume", response_model=ApiResponse, summary="Resume step run")
    async def resume_step_run(image_id: int, phase_code: str, request: LifecycleControlRequest):
        statuses = _control_step(image_id, phase_code, "running", request.reason)
        return ApiResponse(success=True, message="Step resumed", data={"image_id": image_id, "statuses": statuses})

    @router.post("/step-runs/{image_id}/{phase_code}/restart", response_model=ApiResponse, summary="Restart step run")
    async def restart_step_run(image_id: int, phase_code: str, request: LifecycleControlRequest):
        _control_step(image_id, phase_code, "restarting", request.reason)
        statuses = _control_step(image_id, phase_code, "queued", request.reason)
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
        )
        if isinstance(result, dict) and "error" in result:
            if "not found" in result["error"].lower():
                raise HTTPException(status_code=404, detail=result["error"])
            if "no embeddings" in result["error"].lower() or "clustering" in result["error"].lower():
                raise HTTPException(status_code=400, detail=result["error"])
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "query_image_id": image_id,
            "results": result,
            "count": len(result),
        }

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
    ):
        """Deprecated alias for similarity search."""
        return get_similar_images_similarity_namespace(
            image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
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


    # ========== Embedding Map Endpoint ==========

    @router.get(
        "/embedding_map",
        response_model=ApiResponse,
        summary="2D embedding map",
        description="""
        Project image embeddings to 2D coordinates for spatial visualisation.

        Uses UMAP (default) or t-SNE to reduce 1280-d MobileNetV2 embeddings to
        two dimensions.  Results are cached on disk; pass `refresh=true` to force
        recomputation.

        **Query Parameters:**
        - folder_path: Optional.  Scope projection to one folder; omit for all images.
        - method: `umap` (default) or `tsne`.
        - refresh: If true, ignore the on-disk cache and recompute.
        - sample_limit: Cap the number of images projected (default: config `embedding_map.max_points`).
        - n_neighbors: UMAP/t-SNE neighbourhood size (default: 30).
        - min_dist: UMAP min_dist (default: 0.1, ignored for t-SNE).

        **Returns:**
        - points: List of `{image_id, x, y, file_path, thumbnail_path, label, rating, score_general}`.
        - meta: `{count, method, computed_at, cache_key}`.
          When too few images are available `meta.error == "too_few_points"` and
          `points` is empty.
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
            )
            return ApiResponse(success=True, message="OK", data=result)
        except Exception as exc:
            logger.error("Error computing embedding map: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

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

        if _clustering_runner is None:
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
            selector_result = resolve_selectors(
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
        job_source = request.input_path or "SELECTOR_CLUSTERING"
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code="culling",
            job_type="clustering",
            queue_payload={
                "input_path": request.input_path,
                "threshold": request.threshold,
                "time_gap": request.time_gap,
                "force_rescan": request.force_rescan,
                "resolved_image_ids": selector_result.get("resolved_image_ids"),
            },
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue clustering job")

        db.create_job_phases(job_id, ["culling"], first_phase_state="queued")

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
        if _clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        if not _clustering_runner.is_running:
            return ApiResponse(
                success=False,
                message="No clustering job is currently running",
                data={"is_running": False}
            )

        _clustering_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to clustering job",
            data={"is_running": _clustering_runner.is_running}
        )

    @router.get(
        "/clustering/status",
        response_model=StatusResponse,
        summary="Get clustering status",
        description="Returns the current status of the clustering job including progress and logs."
    )
    async def get_clustering_status():
        """Get the current status of the clustering job."""
        if _clustering_runner is None:
            raise HTTPException(status_code=503, detail="Clustering runner not available")

        result = _clustering_runner.get_status()
        is_running, log_text, status_message, current, total = result[:5]

        return StatusResponse(
            is_running=is_running,
            status_message=status_message,
            progress={"current": current, "total": total},
            log=log_text,
            job_type="clustering"
        )

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
    async def query_images(
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        page_size: int = Query(50, ge=1, le=500, description="Items per page"),
        sort_by: str = Query("score", description="Sort field (score, date, name, rating, score_general, score_aesthetic, score_technical)"),
        order: str = Query("desc", description="Sort order: asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings to filter (e.g. '3,4,5')"),
        label: Optional[str] = Query(None, description="Comma-separated labels to filter (e.g. 'Green,Blue')"),
        keyword: Optional[str] = Query(None, description="Keyword to filter by (partial match)"),
        min_score_general: float = Query(0, ge=0, le=1, description="Minimum general score"),
        min_score_aesthetic: float = Query(0, ge=0, le=1, description="Minimum aesthetic score"),
        min_score_technical: float = Query(0, ge=0, le=1, description="Minimum technical score"),
        folder_path: Optional[str] = Query(None, description="Filter by folder path"),
        stack_id: Optional[int] = Query(None, description="Filter by stack ID"),
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
            folder_path=folder_path,
            stack_id=stack_id,
        )

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
    async def get_image_by_hash_param(image_hash: str):
        return _image_detail_for_hash_str(image_hash)

    @router.get(
        "/images/{image_id}",
        summary="Get image details by ID",
        description="Returns full details for a single image including all scores, metadata, and file paths."
    )
    async def get_image_by_id(image_id: int):
        """Get detailed information for a single image."""
        return _image_detail_payload(image_id)

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

    # ========== Import Register Endpoints ==========

    _IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".nef", ".arw", ".cr2", ".dng", ".heic", ".webp", ".tiff", ".tif", ".raw", ".orf", ".rw2"}

    def _resolve_import_path(raw_path: str) -> str:
        """Convert Windows path to WSL if needed, validate directory exists."""
        from modules import utils
        folder_path = raw_path
        try:
            if platform.system() == "Linux" and (":" in folder_path or "\\" in folder_path) and hasattr(utils, "convert_path_to_wsl"):
                folder_path = utils.convert_path_to_wsl(folder_path)
        except Exception:
            pass
        if not os.path.isdir(folder_path):
            raise HTTPException(status_code=400, detail=f"Path is not a directory or not found: {raw_path}")
        return folder_path

    def _import_folder_iter(folder_path: str):
        """Generator that yields progress/done/error dicts during folder import.

        Yields:
            {"type": "init", "total_files": int, "folder_path": str}
            {"type": "progress", "processed": int, "total": int, "added": int, "skipped": int, "current_file": str}
            {"type": "done", "success": bool, "added": int, "skipped": int, "total": int, "errors": list}
            {"type": "error", "message": str}
        """
        from modules import db
        from modules.exif_extractor import extract_exif
        from modules.indexing_runner import INDEXING_VERSION
        from modules.phases import PhaseCode, PhaseStatus
        from modules.version import APP_VERSION

        def _ensure_import_indexing_phase_done(image_id: int) -> None:
            """Backfill indexing (Discovery) done when import skips an already-registered image."""
            st = db.get_image_phase_status(image_id, PhaseCode.INDEXING)
            if st and st.get("status") == PhaseStatus.RUNNING:
                return
            if st and st.get("status") == PhaseStatus.DONE:
                return
            db.set_image_phase_status(
                image_id,
                PhaseCode.INDEXING,
                PhaseStatus.DONE,
                app_version=APP_VERSION,
                executor_version=INDEXING_VERSION,
            )

        folder_id = db.get_or_create_folder(folder_path)
        if not folder_id:
            yield {"type": "error", "message": "Failed to get or create folder"}
            return

        entries = os.listdir(folder_path)
        file_entries = [e for e in entries if os.path.isfile(os.path.join(folder_path, e))]
        total_files = len(file_entries)

        yield {"type": "init", "total_files": total_files, "folder_path": folder_path}

        added = 0
        skipped = 0
        processed = 0
        errors = []

        for name in file_entries:
            fp = os.path.join(folder_path, name)
            ext = os.path.splitext(name)[1].lower()

            if ext not in _IMPORT_IMAGE_EXTENSIONS:
                processed += 1
                if processed % 5 == 0 or processed == total_files:
                    yield {
                        "type": "progress",
                        "processed": processed,
                        "total": total_files,
                        "added": added,
                        "skipped": skipped,
                        "current_file": os.path.basename(name),
                    }
                continue

            file_name = os.path.basename(name)
            file_type = ext.lstrip(".") or "unknown"

            try:
                existing_by_path = db.find_image_id_by_path(fp)
                if existing_by_path:
                    _ensure_import_indexing_phase_done(int(existing_by_path))
                    skipped += 1
                else:
                    image_uuid = None
                    try:
                        exif_data = extract_exif(fp)
                        if exif_data:
                            uid = exif_data.get("image_unique_id")
                            if uid and isinstance(uid, str) and uid.strip():
                                image_uuid = uid.strip()
                                existing_by_uuid = db.find_image_id_by_uuid(image_uuid)
                                if existing_by_uuid:
                                    _ensure_import_indexing_phase_done(int(existing_by_uuid))
                                    skipped += 1
                                    image_uuid = "ALREADY_IN_DB"
                    except Exception:
                        pass

                    if image_uuid != "ALREADY_IN_DB":
                        if db.is_image_in_deleted_blocklist(fp, file_name, image_uuid):
                            skipped += 1
                            image_uuid = "ALREADY_IN_DB"
                    if image_uuid != "ALREADY_IN_DB":
                        image_id, was_new = db.register_image_for_import(fp, file_name, file_type, folder_id, image_uuid)
                        if image_id:
                            if was_new:
                                added += 1
                                db.set_image_phase_status(
                                    image_id,
                                    PhaseCode.INDEXING,
                                    PhaseStatus.DONE,
                                    app_version=APP_VERSION,
                                    executor_version=INDEXING_VERSION,
                                )
                            else:
                                _ensure_import_indexing_phase_done(int(image_id))
                                skipped += 1
                        else:
                            errors.append(f"{file_name}: insert failed")
            except Exception as e:
                errors.append(f"{file_name}: {str(e)}")

            processed += 1

            if processed % 5 == 0 or processed == total_files:
                yield {
                    "type": "progress",
                    "processed": processed,
                    "total": total_files,
                    "added": added,
                    "skipped": skipped,
                    "current_file": file_name,
                }

        yield {
            "type": "done",
            "success": True,
            "added": added,
            "skipped": skipped,
            "total": total_files,
            "errors": errors[:50],
        }

    @router.post(
        "/import/register",
        summary="Register images from folder",
        description="""
        Scans a folder for image files and registers them in the database.
        Returns a single JSON response when complete.
        Broadcasts real-time progress via WebSocket (event types:
        import_started, import_progress, import_completed).
        For streaming NDJSON progress, use /import/register/stream instead.
        """
    )
    async def import_register(request: ImportRegisterRequest):
        """Non-streaming image registration with WebSocket progress broadcasts."""
        from modules.ui.security import _check_rate_limit
        from modules.events import event_manager

        _check_rate_limit("import_register")
        folder_path = _resolve_import_path(request.folder_path)

        result = None
        for msg in _import_folder_iter(folder_path):
            msg_type = msg["type"]
            if msg_type == "init":
                event_manager.broadcast_threadsafe("import_started", {
                    "folder_path": msg["folder_path"],
                    "total_files": msg["total_files"],
                })
            elif msg_type == "progress":
                event_manager.broadcast_threadsafe("import_progress", {
                    "processed": msg["processed"],
                    "total": msg["total"],
                    "added": msg["added"],
                    "skipped": msg["skipped"],
                    "current_file": msg["current_file"],
                })
            elif msg_type == "done":
                result = msg
            elif msg_type == "error":
                event_manager.broadcast_threadsafe("import_completed", {
                    "added": 0, "skipped": 0, "total": 0, "errors": [msg["message"]],
                })
                raise HTTPException(status_code=500, detail=msg["message"])

        # Broadcast completion
        event_manager.broadcast_threadsafe("import_completed", {
            "added": result["added"],
            "skipped": result["skipped"],
            "total": result["total"],
            "errors": result["errors"],
        })

        errors = result["errors"]
        return {
            "success": len(errors) == 0 or result["added"] > 0,
            "message": f"Import complete: {result['added']} added, {result['skipped']} skipped"
                       + (f", {len(errors)} errors" if errors else ""),
            "data": {
                "added": result["added"],
                "skipped": result["skipped"],
                "errors": errors,
            },
        }

    @router.post(
        "/import/register/stream",
        summary="Register images from folder with streaming progress",
        description="""
        Returns a stream of JSON objects (NDJSON) providing real-time progress
        updates during the folder scan and registration process.
        For a single JSON response, use /import/register instead.
        """
    )
    async def import_register_stream(request: ImportRegisterRequest):
        """Streaming version of image registration (NDJSON)."""
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("import_register")
        folder_path = _resolve_import_path(request.folder_path)

        async def progress_generator():
            try:
                for msg in _import_folder_iter(folder_path):
                    yield json.dumps(msg) + "\n"
            except Exception as e:
                yield json.dumps({"type": "error", "message": f"Unexpected error during scan: {str(e)}"}) + "\n"

        return StreamingResponse(progress_generator(), media_type="application/x-ndjson")

    # ========== Pipeline Submit Endpoint ==========

    @router.post(
        "/pipeline/submit",
        response_model=ApiResponse,
        summary="Submit to processing pipeline",
        description="""
        Creates a WorkflowRun for sequential StageRuns on a WorkspaceTarget.

        StageRuns are executed in order based on stage_codes.
        For folder submissions, only the first applicable operation is queued immediately;
        subsequent operations should be triggered by the Electron app after the previous
        one completes (via status polling or WebSocket events).

        For single-file submissions, the first StageRun runs immediately.

        For single files, only 'score' and 'tag' StageRuns are supported.
        'cluster' requires a folder path.
        """
    )
    async def submit_pipeline(request: PipelineSubmitRequest):
        """Submit image/folder to the processing pipeline."""
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("pipeline_submit")

        wt = (request.workspace_target or "").strip()
        has_selector = any(
            [
                wt,
                request.image_ids,
                request.image_paths,
                request.folder_ids,
                request.folder_paths,
            ]
        )
        if not has_selector:
            raise HTTPException(status_code=400, detail="Provide workspace_target or at least one selector")

        selector_request = compose_selector_request(
            input_path=wt or None,
            image_ids_raw=request.image_ids,
            image_paths_raw=request.image_paths,
            folder_ids_raw=request.folder_ids,
            folder_paths_raw=request.folder_paths,
            exclude_image_paths_raw=request.exclude_image_paths,
            recursive=request.recursive,
        )
        preview = validate_and_preview(selector_request)
        resolved_count = int(preview.get("preview_count") or 0)
        if resolved_count <= 0:
            raise HTTPException(status_code=400, detail="No images matched selectors")

        if wt and not any([request.image_ids, request.image_paths, request.folder_ids, request.folder_paths]):
            if not os.path.exists(wt):
                raise HTTPException(status_code=400, detail=f"Path not found: {wt}")

        valid_ops = {"indexing", "metadata", "score", "tag", "cluster"}
        invalid_ops = [op for op in request.stage_codes if op not in valid_ops]
        if invalid_ops:
            raise HTTPException(status_code=400, detail=f"Invalid stage_codes: {invalid_ops}. Valid: {sorted(valid_ops)}")
        if not request.stage_codes:
            raise HTTPException(status_code=400, detail="At least one stage_code is required")

        is_file = bool(wt and os.path.isfile(wt))
        if is_file and "cluster" in request.stage_codes:
            raise HTTPException(status_code=400, detail="Clustering requires a folder path, not a single file")
        if "cluster" in request.stage_codes and not any([wt, request.folder_ids, request.folder_paths]):
            raise HTTPException(status_code=400, detail="Clustering requires a folder selector")

        queue_input_path = wt or "SELECTOR_PIPELINE"

        from modules import db
        first_op = request.stage_codes[0]

        def _normalize_stage_run_plan(rows: List[dict]) -> List[dict]:
            """Return semantic StageRun keys while preserving legacy phase aliases."""
            normalized: List[dict] = []
            for row in rows:
                stage_order = row.get("stage_order", row.get("phase_order"))
                stage_code = row.get("stage_code", row.get("phase_code"))
                item = dict(row)
                item["stage_order"] = stage_order
                item["stage_code"] = stage_code
                item.setdefault("phase_order", stage_order)
                item.setdefault("phase_code", stage_code)
                normalized.append(item)
            return normalized

        if is_file:
            if first_op == "score":
                if _scoring_runner is None:
                    raise HTTPException(status_code=503, detail="Scoring runner not available")
                if _scoring_runner.is_running:
                    return ApiResponse(success=False, message="Scoring runner is busy", data={"is_running": True})
                success, message = _scoring_runner.run_single_image(wt)
            elif first_op == "tag":
                if _tagging_runner is None:
                    raise HTTPException(status_code=503, detail="Tagging runner not available")
                if _tagging_runner.is_running:
                    return ApiResponse(success=False, message="Tagging runner is busy", data={"is_running": True})
                success, message = _tagging_runner.run_single_image(
                    wt,
                    request.custom_keywords,
                    request.generate_captions,
                )
            else:
                raise HTTPException(status_code=400, detail="Single-file pipeline supports score/tag only")

            stage_run_plan = _normalize_stage_run_plan([
                {"stage_order": i, "stage_code": op, "state": "completed" if i == 0 else "pending"}
                for i, op in enumerate(request.stage_codes)
            ])
            return ApiResponse(
                success=success,
                message=message,
                data={
                    "workflow_run_id": None,
                    "workspace_target": wt,
                    "input_path": wt,
                    "workflow_template": request.workflow_template,
                    "active_stage_run": None,
                    "active_operation": None,
                    "completed_stage_run": first_op,
                    "completed_operation": first_op,
                    "stage_run_plan": stage_run_plan,
                    "phase_plan": stage_run_plan,
                    "remaining_stage_runs": request.stage_codes[1:],
                    "remaining_operations": request.stage_codes[1:],
                },
            )

        # API operations map to persisted phase codes used by DB phase/status sync.
        op_to_phase_code = {
            "indexing": "indexing",
            "metadata": "metadata",
            "score": "scoring",
            "tag": "keywords",
            "cluster": "culling",
        }
        op_to_label = {
            "indexing": "indexing",
            "metadata": "metadata",
            "score": "scoring",
            "tag": "tagging",
            "cluster": "clustering",
        }
        phase_plan_codes = [op_to_phase_code.get(op, op) for op in request.stage_codes]

        if first_op == "indexing":
            if _indexing_runner is None:
                raise HTTPException(status_code=503, detail="Indexing runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="indexing",
                job_type="indexing",
                queue_payload=serialize_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "skip_existing": request.skip_existing,
                    },
                    preview,
                ),
            )
        elif first_op == "metadata":
            if _metadata_runner is None:
                raise HTTPException(status_code=503, detail="Metadata runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="metadata",
                job_type="metadata",
                queue_payload=serialize_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "skip_existing": request.skip_existing,
                    },
                    preview,
                ),
            )
        elif first_op == "score":
            if _scoring_runner is None:
                raise HTTPException(status_code=503, detail="Scoring runner not available")
            
            # Map operations to internal phase codes for the orchestrator
            target_phases = [op_to_phase_code.get(op) for op in request.stage_codes if op in ["indexing", "metadata", "score"]]
            
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="scoring",
                job_type="scoring",
                queue_payload=serialize_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "skip_existing": request.skip_existing,
                        "target_phases": target_phases,
                    },
                    preview,
                ),
            )
        elif first_op == "tag":
            if _tagging_runner is None:
                raise HTTPException(status_code=503, detail="Tagging runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="keywords",
                job_type="tagging",
                queue_payload=serialize_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "custom_keywords": request.custom_keywords,
                        "overwrite": not request.skip_existing,
                        "generate_captions": request.generate_captions,
                    },
                    preview,
                ),
            )
        else:
            if _clustering_runner is None:
                raise HTTPException(status_code=503, detail="Clustering runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="culling",
                job_type="clustering",
                queue_payload=serialize_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "threshold": request.clustering_threshold,
                        "time_gap": request.clustering_time_gap,
                        "force_rescan": request.clustering_force_rescan,
                    },
                    preview,
                ),
            )

        if job_id is None:
            raise HTTPException(status_code=500, detail=f"Failed to enqueue WorkflowRun for StageRun: {first_op}")

        phase_rows = db.create_job_phases(job_id, phase_plan_codes)
        stage_run_plan = _normalize_stage_run_plan(phase_rows)

        return ApiResponse(
            success=True,
            message=f"WorkflowRun queued: {op_to_label[first_op]}",
            data={
                "workflow_run_id": job_id,
                "job_id": job_id,
                "workspace_target": wt or queue_input_path,
                "input_path": wt or queue_input_path,
                "selector_source": queue_input_path,
                "workflow_template": request.workflow_template,
                "active_stage_run": first_op,
                "active_operation": first_op,
                "current_operation": first_op,
                "queue_position": queue_position,
                "stage_run_plan": stage_run_plan,
                "phase_plan": stage_run_plan,
                "remaining_stage_runs": request.stage_codes[1:],
                "remaining_operations": request.stage_codes[1:],
                "resolved_count": resolved_count,
                "warnings": preview.get("warnings") or [],
            },
        )


    @router.get(
        "/phases/decision",
        response_model=PhaseDecisionResponse,
        summary="Explain phase run/skip decision",
        description="Returns policy diagnostics describing why a phase would run or be skipped for an image."
    )
    async def get_phase_decision(
        image_id: int = Query(..., description="Image ID"),
        phase_code: str = Query(..., description="Phase code (scoring|culling|keywords|...)"),
        current_executor_version: Optional[str] = Query(None, description="Optional explicit executor version override"),
        force_run: bool = Query(False, description="If true, policy returns run decision as forced"),
    ):
        from modules import db
        from modules.phases import PhaseCode

        phase_code_normalized = (phase_code or "").strip().lower()
        valid_phase_codes = {code.value for code in PhaseCode}
        if phase_code_normalized not in valid_phase_codes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid phase_code: '{phase_code}'. Valid: {sorted(valid_phase_codes)}",
            )

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM images WHERE id = ?", (image_id,))
            if c.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
        finally:
            conn.close()

        return explain_phase_run_decision(
            image_id=image_id,
            phase_code=phase_code_normalized,
            current_executor_version=current_executor_version,
            force_run=force_run,
        )


    @router.post(
        "/pipeline/phase/skip",
        response_model=ApiResponse,
        summary="Skip a pipeline phase",
        description="Marks all images in a folder phase as skipped, storing reason and actor."
    )
    async def skip_pipeline_phase(request: PipelinePhaseControlRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_phase_skip")

        if not os.path.exists(request.input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.input_path}")

        updated = db.set_folder_phase_status(
            folder_path=request.input_path,
            phase_code=request.phase_code,
            status="skipped",
            reason=request.reason or "manual_skip",
            actor=request.actor or "api_user",
        )
        return ApiResponse(
            success=True,
            message=f"Phase '{request.phase_code}' marked as skipped",
            data={"updated_images": updated, "phase_code": request.phase_code}
        )

    @router.post(
        "/pipeline/phase/retry",
        response_model=ApiResponse,
        summary="Retry a skipped pipeline phase",
        description="Converts skipped statuses to running and starts the selected phase runner."
    )
    async def retry_pipeline_phase(request: PipelinePhaseControlRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_phase_retry")

        if not os.path.exists(request.input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.input_path}")

        updated = db.set_folder_phase_status(
            folder_path=request.input_path,
            phase_code=request.phase_code,
            status="running",
        )

        phase = request.phase_code.strip().lower()
        if phase == "scoring":
            if _scoring_runner is None:
                raise HTTPException(status_code=503, detail="Scoring runner not available")
            job_id = db.create_job(request.input_path, phase_code="scoring")
            result = _scoring_runner.start_batch(request.input_path, job_id, True)
        elif phase == "keywords":
            if _tagging_runner is None:
                raise HTTPException(status_code=503, detail="Tagging runner not available")
            job_id = db.create_job(request.input_path, phase_code="keywords")
            result = _tagging_runner.start_batch(request.input_path, job_id=job_id, overwrite=False, generate_captions=False)
        elif phase == "culling":
            culling_runner = _selection_runner or _clustering_runner
            if culling_runner is None:
                raise HTTPException(status_code=503, detail="Selection runner not available")
            job_id = db.create_job(request.input_path, phase_code="culling")
            result = culling_runner.start_batch(request.input_path, job_id=job_id, force_rescan=True)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported phase_code: {request.phase_code}")
        db.create_job_phases(job_id, [phase])  # immediate start

        return ApiResponse(
            success=(result == "Started"),
            message=f"Retry {request.phase_code}: {result}",
            data={"updated_images": updated, "phase_code": request.phase_code, "job_id": job_id}
        )

    @router.post("/pipeline/run/pause", response_model=ApiResponse, summary="Pause current run")
    async def pause_pipeline_run(request: PipelineRunControlRequest):
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("pipeline_run_pause")
        stopped = []
        for phase in ("indexing", "metadata", "scoring", "culling", "keywords"):
            if _stop_runner_for_phase(phase):
                stopped.append(phase)
        return ApiResponse(
            success=True,
            message="Pipeline run paused",
            data={
                "confirm_level": "soft",
                "stopped_phases": stopped,
                "rollback_guidance": "Resume with Run All Pending or retry a stage.",
            },
        )

    @router.post("/pipeline/run/cancel", response_model=ApiResponse, summary="Cancel current run")
    async def cancel_pipeline_run(request: PipelineRunControlRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_run_cancel")

        stopped = []
        for phase in ("indexing", "metadata", "scoring", "culling", "keywords"):
            if _stop_runner_for_phase(phase):
                stopped.append(phase)

        cancelled_jobs = []
        input_path = (request.input_path or "").strip()
        for job in db.get_queued_jobs(limit=1000):
            queued_path = str(job.get("input_path") or "")
            if input_path and not queued_path.startswith(input_path):
                continue
            res = db.request_cancel_job(job.get("id"))
            if res.get("success"):
                cancelled_jobs.append(job.get("id"))

        return ApiResponse(
            success=True,
            message="Pipeline run cancelled",
            data={
                "confirm_level": "strong",
                "stopped_phases": stopped,
                "cancelled_jobs": cancelled_jobs,
                "rollback_guidance": "Restart from stage to resume processing.",
            },
        )

    @router.post("/pipeline/run/restart", response_model=ApiResponse, summary="Restart run")
    async def restart_pipeline_run(request: PipelineRunControlRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_run_restart")
        input_path = (request.input_path or "").strip()
        if not input_path:
            raise HTTPException(status_code=400, detail="input_path is required")
        if not os.path.exists(input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {input_path}")

        for phase in ("indexing", "metadata", "scoring", "culling", "keywords"):
            _stop_runner_for_phase(phase)

        job_id, queue_position = db.enqueue_job(
            input_path,
            phase_code="indexing",
            job_type="indexing",
            queue_payload={"input_path": input_path, "skip_existing": False},
        )
        if job_id is not None:
            db.create_job_phases(
                job_id,
                ["indexing", "metadata", "scoring"],
                first_phase_state="queued",
            )
        return ApiResponse(
            success=job_id is not None,
            message="Pipeline run restart queued" if job_id is not None else "Failed to queue restart",
            data={
                "confirm_level": "strong",
                "job_id": job_id,
                "queue_position": queue_position,
                "rollback_guidance": "Use cancel if queued incorrectly, then re-submit with stage controls.",
            },
        )

    @router.post("/pipeline/phase/restart-from", response_model=ApiResponse, summary="Restart pipeline from stage")
    async def restart_pipeline_from_stage(request: PipelineRestartFromStageRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_phase_restart")

        if not os.path.exists(request.input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.input_path}")

        ordered = ["scoring", "culling", "keywords"]
        phase = (request.phase_code or "").strip().lower()
        if phase not in ordered:
            raise HTTPException(status_code=400, detail=f"Unsupported phase_code: {request.phase_code}")

        updated_total = 0
        start_idx = ordered.index(phase)
        for code in ordered[start_idx:]:
            updated_total += int(db.set_folder_phase_status(request.input_path, code, "running") or 0)

        if phase == "scoring":
            if _scoring_runner is None:
                raise HTTPException(status_code=503, detail="Scoring runner not available")
            job_id = db.create_job(request.input_path, phase_code="scoring")
            result = _scoring_runner.start_batch(request.input_path, job_id, True)
        elif phase == "culling":
            culling_runner = _selection_runner or _clustering_runner
            if culling_runner is None:
                raise HTTPException(status_code=503, detail="Selection runner not available")
            job_id = db.create_job(request.input_path, phase_code="culling")
            result = culling_runner.start_batch(request.input_path, job_id=job_id, force_rescan=True)
        else:
            if _tagging_runner is None:
                raise HTTPException(status_code=503, detail="Tagging runner not available")
            job_id = db.create_job(request.input_path, phase_code="keywords")
            result = _tagging_runner.start_batch(request.input_path, job_id=job_id, overwrite=True, generate_captions=False)
        restart_phases = ordered[start_idx:]  # e.g. ["scoring", "culling", "keywords"]
        db.create_job_phases(job_id, restart_phases)  # immediate start

        return ApiResponse(
            success=(result == "Started"),
            message=f"Restart from stage '{phase}': {result}",
            data={
                "phase_code": phase,
                "job_id": job_id,
                "updated_images": updated_total,
                "rollback_guidance": "Use skip with reason for non-actionable stage failures.",
            },
        )

    @router.post("/pipeline/step/rerun", response_model=ApiResponse, summary="Rerun failed idempotent step")
    async def rerun_pipeline_step(request: PipelineStepRerunRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_step_rerun")

        phase = (request.phase_code or "").strip().lower()
        idempotent_phases = {"metadata", "keywords", "culling"}
        if phase not in idempotent_phases:
            raise HTTPException(status_code=400, detail=f"Phase '{phase}' is not marked idempotent for step rerun")

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM images WHERE id = ?", (request.image_id,))
            if c.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Image not found: id={request.image_id}")
        finally:
            conn.close()

        statuses = db.get_image_phase_statuses(request.image_id) or []
        phase_row = next((row for row in statuses if str(row.get("phase_code") or "").lower() == phase), None)
        current_status = str((phase_row or {}).get("status") or "not_started").lower()
        if current_status != "failed":
            raise HTTPException(
                status_code=409,
                detail=f"Step rerun requires failed status. Current status for phase '{phase}' is '{current_status}'.",
            )

        db.set_image_phase_status(request.image_id, phase, "running")
        return ApiResponse(
            success=True,
            message=f"Step rerun requested for image {request.image_id} phase '{phase}'",
            data={
                "image_id": request.image_id,
                "phase_code": phase,
                "previous_status": current_status,
                "rollback_guidance": "If rerun fails again, skip stage with a reason and continue.",
            },
        )

    # ========== Electron Migration — Additional Endpoints ==========

    @router.get(
        "/folders/tree",
        summary="Get hierarchical folder tree",
        description="""
        Returns the folder list as a nested tree structure (rather than the flat list
        returned by GET /api/folders). Suitable for rendering a sidebar tree widget in
        Electron without the HTML generation done by the Gradio UI.

        Each node: `{name, path, children: [...]}`. Root nodes are returned as a top-level
        array. Platform path normalisation is applied (WSL↔Windows) the same way the
        Gradio folder tree does it.
        """
    )
    async def get_folder_tree():
        from modules import db, utils
        from modules.ui_tree import build_tree_dict
        import os

        try:
            raw_folders = db.get_all_folders()
            folders = []
            for p in raw_folders:
                local_p = utils.convert_path_to_local(p) if hasattr(utils, 'convert_path_to_local') else p
                if not local_p:
                    continue
                norm = os.path.normpath(local_p)
                if os.name == 'nt':
                    if len(norm) < 2 or norm[1] != ':':
                        continue
                    if norm.startswith('\\mnt') or norm == '\\':
                        continue
                else:
                    if local_p.startswith('\\'):
                        continue
                basename = os.path.basename(norm).lower()
                if basename in ['.tmp.drivedownload', '.tmp.driveupload', 'keywords_output', '.']:
                    continue
                folders.append(local_p)

            folders = list(set(folders))
            tree = build_tree_dict(folders)
            return {"tree": tree, "count": len(folders)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/folders/phase-status",
        summary="Get pipeline phase aggregate for a folder",
        description="""
        Returns per-phase completion counts for all images in the given folder (and its
        sub-folders). This is the JSON equivalent of the Pipeline tab stepper/phase cards.

        Uses the same cached `phase_agg_json` column as the Gradio UI. Pass
        `force_refresh=true` to bypass the cache and recompute live counts.

        **Query Parameters:**
        - `path` (required): Absolute folder path.
        - `force_refresh` (optional, default false): Bypass cache.
        """
    )
    async def get_folder_phase_status(
        path: str = Query(..., description="Absolute folder path to query."),
        force_refresh: bool = Query(False, description="Bypass cache and recompute live counts."),
    ):
        from modules import db
        try:
            phases = db.get_folder_phase_summary(path, force_refresh=force_refresh)
            return {"folder_path": path, "phases": phases}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.patch(
        "/images/{image_id}",
        summary="Update image metadata",
        description="""
        Updates writable metadata fields for an image: rating, label, title, description,
        and keywords. All fields are optional — only provided fields are updated.

        When `write_sidecar=true` (default), metadata is also written to the XMP sidecar
        file and embedded tags via the tagging runner, keeping file metadata in sync with
        the database.

        **IPC contract:** Column names match the `images` table schema; do not rename
        without also updating `electron/db.ts`.
        """
    )
    async def update_image(image_id: int, request: ImageUpdateRequest):
        from modules import db
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("image_update")

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT file_path, keywords, title, description, rating, label FROM images WHERE id = ?",
                (image_id,)
            )
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
            file_path = row[0]
            current_keywords = row[1] or ""
            current_title = row[2] or ""
            current_desc = row[3] or ""
            current_rating = row[4] or 0
            current_label = row[5] or ""
        finally:
            conn.close()

        new_keywords = request.keywords if request.keywords is not None else current_keywords
        new_title = request.title if request.title is not None else current_title
        new_desc = request.description if request.description is not None else current_desc
        new_rating = request.rating if request.rating is not None else current_rating
        new_label = request.label if request.label is not None else current_label

        try:
            success = db.update_image_metadata(file_path, new_keywords, new_title, new_desc, new_rating, new_label)
            if not success:
                raise HTTPException(status_code=500, detail="Database update failed")

            sidecar_ok = True
            if request.write_sidecar and _tagging_runner is not None:
                kw_list = [k.strip() for k in new_keywords.split(',') if k.strip()]
                sidecar_ok = _tagging_runner.write_metadata(file_path, kw_list, new_title, new_desc, new_rating, new_label)

            return ApiResponse(
                success=True,
                message=f"Updated image {image_id}",
                data={"image_id": image_id, "sidecar_written": sidecar_ok}
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete(
        "/images/{image_id}",
        summary="Delete image record from database",
        description="""
        Removes an image record from the database and cleans up related rows
        (culling picks, resolved paths, stack membership). The image file on disk is
        NOT deleted by default.

        Pass `delete_file=true` to also delete the source image file and its thumbnail
        from disk. Use with caution — this is irreversible.
        """
    )
    async def delete_image(image_id: int, delete_file: bool = Query(False, description="Also delete image file from disk.")):
        from modules import db
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("image_delete")

        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT file_path, thumbnail_path FROM images WHERE id = ?", (image_id,))
            row = c.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
            file_path = row[0]
            thumbnail_path = row[1]
        finally:
            conn.close()

        try:
            success, msg = db.delete_image(file_path, delete_related=True)
            if not success:
                raise HTTPException(status_code=500, detail=msg)

            deleted_files = []
            if delete_file:
                for path in [file_path, thumbnail_path]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                            deleted_files.append(path)
                        except OSError as exc:
                            logger.warning("Could not delete file %s: %s", path, exc)

            return ApiResponse(
                success=True,
                message=msg,
                data={"image_id": image_id, "deleted_files": deleted_files}
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/gallery/export",
        summary="Export gallery images to file",
        description="""
        Exports the image database (or a filtered subset) to JSON, CSV, or XLSX.
        The response is a file download. Filters mirror those available in the Gallery tab.

        **Formats:** `json` | `csv` | `xlsx`

        The file is written to `<app_root>/output/export_<timestamp>.<ext>` and served
        as an attachment.
        """
    )
    async def export_gallery(request: ExportRequest):
        from modules import db
        from modules.ui.security import _check_rate_limit
        import datetime
        _check_rate_limit("gallery_export")

        fmt = (request.format or "json").lower()
        if fmt not in ("json", "csv", "xlsx"):
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt!r}. Use json, csv, or xlsx.")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"export_{timestamp}.{fmt}")

        date_range = None
        if request.date_from or request.date_to:
            date_range = (request.date_from, request.date_to)

        try:
            if fmt == "json":
                success, msg = db.export_db_to_json(output_path)
            elif fmt == "csv":
                success, msg = db.export_db_to_csv(
                    output_path,
                    columns=request.columns,
                    rating_filter=request.rating,
                    label_filter=request.label,
                    keyword_filter=request.keyword,
                    folder_path=request.folder_path,
                    min_score_general=request.min_score_general,
                    min_score_aesthetic=request.min_score_aesthetic,
                    min_score_technical=request.min_score_technical,
                    date_range=date_range,
                )
            else:  # xlsx
                success, msg = db.export_db_to_excel(
                    output_path,
                    columns=request.columns,
                    rating_filter=request.rating,
                    label_filter=request.label,
                    keyword_filter=request.keyword,
                    folder_path=request.folder_path,
                    min_score_general=request.min_score_general,
                    min_score_aesthetic=request.min_score_aesthetic,
                    min_score_technical=request.min_score_technical,
                    date_range=date_range,
                )

            if not success:
                raise HTTPException(status_code=500, detail=msg)

            media_types = {"json": "application/json", "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            return FileResponse(
                output_path,
                media_type=media_types[fmt],
                filename=os.path.basename(output_path),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/config",
        summary="Get application configuration",
        description="""
        Returns the current `config.json` contents. Sections: `scoring`, `processing`,
        `culling`, `ui`, `tagging`. Used by the Settings tab; Electron should read this
        on startup and display values in its Settings pane.
        """
    )
    async def get_config():
        from modules.config import load_config
        try:
            return load_config()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/config/{section}",
        summary="Save a configuration section",
        description="""
        Persists a configuration section to `config.json`. Pass the section name as a
        path parameter (e.g. `scoring`, `ui`, `tagging`) and the section dict as the
        JSON body. Equivalent to clicking "Save All Configuration" in the Settings tab
        for a specific section.
        """
    )
    async def save_config(section: str, body: Dict[str, Any] = Body(...)):
        from modules.config import save_config_section
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("config_save")
        valid_sections = {"scoring", "processing", "culling", "ui", "tagging"}
        if section not in valid_sections:
            raise HTTPException(status_code=400, detail=f"Unknown config section: {section!r}. Valid: {sorted(valid_sections)}")
        try:
            save_config_section(section, body)
            return ApiResponse(success=True, message=f"Config section '{section}' saved.", data={})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─── New Runs API (React SPA) ────────────────────────────────────────────

    class RunSubmitRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")

        scope_type: str = "folder_recursive"  # file|folder|folder_recursive|path_list
        scope_paths: List[str]
        stages: Optional[List[str]] = None
        run_mode: Literal[
            "process_all_overwrite",
            "process_unprocessed_or_empty",
            "validate_and_repair",
        ] = "process_unprocessed_or_empty"
        # Deprecated compatibility fields. These are ignored when run_mode is present.
        skip_done: Optional[bool] = None
        force_rerun: Optional[bool] = None
        fix_incomplete_stages: Optional[bool] = None
        validation_repair_mode: bool = False
        validation_repair_dry_run: bool = False

        @model_validator(mode="after")
        def _normalize_run_mode_and_legacy_flags(self):
            if self.validation_repair_mode:
                return self
            self.run_mode = infer_run_mode(
                self.run_mode,
                run_mode_explicit=("run_mode" in self.model_fields_set),
                skip_done=self.skip_done,
                force_rerun=self.force_rerun,
                fix_incomplete_stages=self.fix_incomplete_stages,
            )
            return self

    class ValidationRepairPreviewRequest(BaseModel):
        scope_paths: List[str]
        stages: Optional[List[str]] = None

    @router.post("/runs/validation-repair/preview", summary="Preview validation-repair issues for scope")
    async def preview_validation_repair(request: ValidationRepairPreviewRequest):
        scope_paths = [_normalize_scope_path_input(p) for p in request.scope_paths]
        scope_paths = [p for p in scope_paths if p]
        if not scope_paths:
            raise HTTPException(status_code=400, detail="scope_paths must not be empty")
        try:
            result = await asyncio.to_thread(
                db.build_validation_repair_plan,
                scope_paths,
                request.stages or [],
                True,
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/runs/submit", summary="Submit a new Run")
    async def submit_run(request: RunSubmitRequest):
        from modules import db
        from modules.phases import PhaseCode, normalize_phase_codes, sort_phase_value_strings
        scope_paths = [_normalize_scope_path_input(p) for p in request.scope_paths]
        scope_paths = [p for p in scope_paths if p]
        if not scope_paths:
            raise HTTPException(status_code=400, detail="scope_paths must not be empty")
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

        mode_flags = resolve_run_mode_flags(request.run_mode)

        payload = {
            "scope_type": request.scope_type,
            "scope_paths": scope_paths,
            "input_path": primary_path,
            "run_mode": request.run_mode,
            "skip_done": mode_flags["skip_done"],
            "skip_existing": mode_flags["skip_existing"],
            "force_rerun": mode_flags["force_rerun"],
            "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
            "overwrite": mode_flags["overwrite"],
            "force_rescan": mode_flags["force_rescan"],
            "phases": phase_values,
            "target_phases": phase_values,
        }
        if request.validation_repair_mode:
            try:
                repair_plan = await asyncio.to_thread(
                    db.build_validation_repair_plan,
                    scope_paths,
                    phase_values or [],
                    bool(request.validation_repair_dry_run),
                )
                payload["validation_repair_summary"] = repair_plan
                payload["resolved_image_ids_by_stage"] = repair_plan.get("stage_queues", {})
                # Keep current runner contract for first phase as a fallback.
                if phase_values:
                    first = str(phase_values[0]).strip().lower()
                    first_ids = (repair_plan.get("stage_queues", {}) or {}).get(first)
                    if isinstance(first_ids, list):
                        payload["resolved_image_ids"] = first_ids
                payload["skip_existing"] = False
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"validation-repair planning failed: {e}") from e
        try:
            job_id, position = await asyncio.wait_for(
                asyncio.to_thread(
                    db.enqueue_job,
                    primary_path,
                    phase_code,
                    job_type,
                    payload,
                ),
                timeout=30.0,
            )
            await asyncio.to_thread(
                db.create_job_phases, job_id, phase_values, "queued",
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
            db.update_job_status(run_id, "paused", "user_pause")
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
                    payload = json.loads(payload)
            except Exception:
                payload = {}
            payload["skip_done"] = True
            db.update_job_payload(run_id, json.dumps(payload))

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
            if status == "queued":
                db.request_cancel_job(run_id)
            elif status in ("pending", "running", "paused", "interrupted", "cancel_requested", "restarting"):
                db.update_job_status(run_id, "canceled")
                # Stop the active runner when running (DB update alone doesn't stop the process)
                if status == "running":
                    state = _job_dispatcher.get_state()
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
            return {"success": True, "message": f"Run {run_id} canceled"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class ForceRunRequest(BaseModel):
        confirm: bool = Field(
            ..., description="Must be true to acknowledge this is a destructive operation"
        )

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

            # --- Helper: reset ghost is_running on all runners ----------------
            def _reset_ghost_runners() -> list:
                """Reset is_running on runners whose thread is no longer alive."""
                cleared = []
                for name, runner in [
                    ("scoring", _scoring_runner),
                    ("tagging", _tagging_runner),
                    ("clustering", _clustering_runner),
                    ("selection", _selection_runner),
                ]:
                    if runner is None:
                        continue
                    thread = getattr(runner, "_thread", None)
                    thread_alive = thread is not None and thread.is_alive()
                    # Selection runner uses is_running behind a lock
                    if name == "selection":
                        lock = getattr(runner, "_lock", None)
                        if lock:
                            with lock:
                                if runner.is_running and not thread_alive:
                                    runner.is_running = False
                                    cleared.append(name)
                    else:
                        if getattr(runner, "is_running", False) and not thread_alive:
                            runner.is_running = False
                            cleared.append(name)
                return cleared

            # --- Branch on status --------------------------------------------
            if status == "running":
                # Check if there's actually a live runner thread for this job
                state = _job_dispatcher.get_state()
                active_runner_name = state.get("active_runner")
                runner_map = {
                    "scoring": _scoring_runner,
                    "tagging": _tagging_runner,
                    "clustering": _clustering_runner,
                    "selection": _selection_runner,
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
                cleared = _reset_ghost_runners()
                if cleared:
                    actions_taken.append(f"reset ghost is_running on: {', '.join(cleared)}")

                # In-place resume: same job id back to queued
                _, pos = _resume_job_inplace(job)
                actions_taken.append(f"requeued run {run_id} (position {pos})")
                return {"success": True, "run_id": run_id, "queue_position": pos, "actions": actions_taken}

            elif status == "queued":
                # The job is queued but nothing is being dispatched —
                # likely ghost is_running on a runner is blocking the dispatcher.
                cleared = _reset_ghost_runners()
                if cleared:
                    actions_taken.append(f"reset ghost is_running on: {', '.join(cleared)}")
                else:
                    actions_taken.append("no ghost runners found — dispatcher should dequeue normally")
                return {"success": True, "run_id": run_id, "actions": actions_taken}

            elif status in ("paused", "interrupted"):
                # In-place resume: same job id
                _, pos = _resume_job_inplace(job)
                actions_taken.append(f"requeued run {run_id} (position {pos})")
                return {"success": True, "run_id": run_id, "queue_position": pos, "actions": actions_taken}

            elif status in ("completed", "failed", "canceled", "cancelled"):
                # Terminal — must create a new job (Retry semantics)
                new_id, pos = _reenqueue_job(job)
                actions_taken.append(f"retried as new job {new_id} (position {pos})")
                return {"success": True, "run_id": new_id, "queue_position": pos, "actions": actions_taken}

            else:
                raise HTTPException(status_code=400, detail=f"Unhandled status: {status}")

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("force_run failed for run_id=%s", run_id)
            raise HTTPException(status_code=500, detail=str(e))

    def _resume_job_inplace(job: dict) -> tuple:
        """Resume a job in-place: same id back to queued, phases preserved. Returns (job_id, position)."""
        from modules import db

        run_id = job["id"]
        payload_raw = job.get("queue_payload") or "{}"
        try:
            payload = json.loads(payload_raw)
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception:
            payload = {}
        payload["skip_done"] = True
        db.update_job_payload(run_id, json.dumps(payload))

        _, position = db.requeue_job(run_id)
        db.resume_job_phases(run_id)
        return run_id, position

    def _reenqueue_job(job: dict) -> tuple:
        """Re-enqueue a job with skip_done=True. Returns (new_job_id, position)."""
        from modules import db

        payload_raw = job.get("queue_payload") or "{}"
        try:
            payload = json.loads(payload_raw)
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception:
            payload = {}
        payload["skip_done"] = True

        orig_job_type = job.get("job_type", "indexing") # Safest default is indexing for new workflow
        _phase_code_map = {
            "indexing": "indexing",
            "metadata": "metadata",
            "scoring": "scoring",
            "tagging": "keywords",
            "clustering": "culling",
            "selection": "culling"
        }
        phase_code = _phase_code_map.get(orig_job_type, "indexing")

        new_job_id, position = db.enqueue_job(
            input_path=job.get("input_path", ""),
            phase_code=phase_code,
            job_type=orig_job_type,
            queue_payload=json.dumps(payload),
        )
        from modules.phases import sort_phase_value_strings

        orig_phases = db.get_job_phases(job["id"])
        if orig_phases:
            phase_codes = sort_phase_value_strings([p["phase_code"] for p in orig_phases])
        else:
            _defaults = {
                "indexing": ["indexing"],
                "metadata": ["metadata"],
                "tagging": ["keywords"], 
                "selection": ["culling", "metadata"], 
                "clustering": ["culling"]
            }
            phase_codes = sort_phase_value_strings(_defaults.get(orig_job_type, ["indexing", "metadata", "scoring"]))
        db.create_job_phases(new_job_id, phase_codes, first_phase_state="queued")
        return new_job_id, position

    @router.post("/runs/{run_id}/retry", summary="Retry a failed/canceled Run")
    async def retry_run(run_id: int):
        from modules import db
        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            payload_raw = job.get("queue_payload") or "{}"
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}
            payload["skip_done"] = True
            # Derive phase_code and job_type from original job
            orig_job_type = job.get("job_type", "scoring")
            _phase_code_map = {
                "indexing": "indexing",
                "metadata": "metadata",
                "scoring": "scoring",
                "tagging": "keywords",
                "clustering": "culling",
                "selection": "culling",
            }
            phase_code = _phase_code_map.get(orig_job_type, "scoring")
            new_job_id, position = db.enqueue_job(
                input_path=job.get("input_path", ""),
                phase_code=phase_code,
                job_type=orig_job_type,
                queue_payload=json.dumps(payload),
            )
            # Copy phases from original job, or default from job_type
            from modules.phases import sort_phase_value_strings

            orig_phases = db.get_job_phases(run_id)
            if orig_phases:
                phase_codes = sort_phase_value_strings([p["phase_code"] for p in orig_phases])
            else:
                _defaults = {"tagging": ["keywords"], "selection": ["culling", "metadata"], "clustering": ["culling"]}
                phase_codes = sort_phase_value_strings(_defaults.get(orig_job_type, ["indexing", "metadata", "scoring"]))
            db.create_job_phases(new_job_id, phase_codes, first_phase_state="queued")
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
            db.set_job_phase_state(run_id, stage_code, "pending")
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

    class ScopePreviewRequest(BaseModel):
        paths: List[str]
        recursive: bool = True

    def _normalize_scope_path_input(raw: str) -> str:
        """Trim and strip trailing slashes; keep Windows drive roots (e.g. D:\\) as directory paths."""
        s = (raw or "").strip()
        while len(s) > 1 and s[-1] in "/\\":
            prev = s[:-1]
            if len(prev) == 2 and prev[1] == ":":
                break
            s = prev
        return s

    def _scope_resolve_path(raw_path: str) -> str:
        """Map user path to an existing filesystem path for this OS (WSL /mnt/..., Windows, typos in slashes)."""
        from modules import utils
        path = _normalize_scope_path_input(raw_path)
        if not path:
            raise HTTPException(status_code=400, detail="Empty path")
        local_path, tried = utils.resolve_scope_input_path(path)
        if not local_path:
            sysname = platform.system()
            sl = path.replace("\\", "/")
            extra = ""
            if sysname == "Linux" and sl.startswith("/mnt/"):
                segs = [x for x in sl.split("/") if x]
                if len(segs) >= 2 and segs[0] == "mnt":
                    drv = segs[1]
                    mroot = f"/mnt/{drv}"
                    if not os.path.exists(mroot):
                        extra = (
                            f" {mroot}/ is not mounted here (WSL automount disabled, container without a host bind, "
                            "or this process is not WSL). Run the WebUI where that path exists, or bind-mount the folder."
                        )
            if utils.is_docker_runtime():
                extra += (
                    " Docker: only bind-mounted paths exist inside the container (besides `.:/app`). "
                    "`webui.volumes` uses ${PHOTOS_BIND_SOURCE:-/mnt/d/Photos}:/mnt/d/Photos — if `/mnt/d` is missing here, "
                    "you are likely on Docker Desktop for Windows: set PHOTOS_BIND_SOURCE to a Windows path in `.env` "
                    "(e.g. PHOTOS_BIND_SOURCE=D:/Photos), then `docker compose up -d --force-recreate webui`. "
                    "Using /mnt/d/... as the compose host source only works when the Docker engine runs inside WSL."
                )
            uniq_try = []
            for t in tried:
                if t not in uniq_try:
                    uniq_try.append(t)
            preview = ", ".join(repr(t) for t in uniq_try[:5])
            if len(uniq_try) > 5:
                preview += ", …"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Path not found: {raw_path}. Checked: {preview or '(no variants)'}. "
                    f"This server runs on {sysname}: use a path visible to that process "
                    f"(native Windows: D:\\Photos\\...; WSL/Linux: /mnt/d/Photos/... when drives are mounted)."
                    f"{extra}"
                ),
            )
        return local_path

    def _scope_count_images_on_disk(local_path: str, recursive: bool) -> tuple[int, int]:
        """Count images and folders on disk. Returns (image_count, folder_count)."""
        from modules.indexing_policy import discovery_extensions

        exts = discovery_extensions()
        if not os.path.isdir(local_path):
            return (0, 0)
        img_count = 0
        folder_count = 0
        if recursive:
            from modules.indexing_policy import path_is_indexing_excluded, prune_indexing_excluded_walk_dirs

            for root, dirs, files in os.walk(local_path):
                prune_indexing_excluded_walk_dirs(root, dirs)
                folder_count += 1
                for f in files:
                    fp = os.path.join(root, f)
                    if path_is_indexing_excluded(fp):
                        continue
                    if os.path.splitext(f)[1].lower() in exts:
                        img_count += 1
        else:
            folder_count = 1
            for f in os.listdir(local_path):
                fp = os.path.join(local_path, f)
                if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in exts:
                    img_count += 1
        return (img_count, folder_count)

    @router.post("/scope/preview", summary="Preview scope before submitting a Run")
    async def scope_preview(request: ScopePreviewRequest):
        """Returns image count and per-stage phase statuses for the given paths.
        When a folder has no images in the DB (not yet indexed), scans the filesystem to show actual counts."""
        from modules import db
        from modules.phases import PhaseCode
        preview_paths = [_normalize_scope_path_input(p) for p in request.paths]
        preview_paths = [p for p in preview_paths if p]
        if not preview_paths:
            raise HTTPException(status_code=400, detail="paths must not be empty")
        try:
            total_images = 0
            folder_count = 0
            stage_done: Dict[str, int] = {}
            stage_failed: Dict[str, int] = {}
            stage_skipped: Dict[str, int] = {}
            stage_total: Dict[str, int] = {}
            phase_codes = [p.value for p in PhaseCode]

            stage_running: Dict[str, int] = {}
            stage_queued: Dict[str, int] = {}
            for path in preview_paths:
                local_path = _scope_resolve_path(path)
                # Use the same resolved path the job/runner uses so folder_id / phase aggregates match.
                summary = db.get_folder_phase_summary(local_path, force_refresh=True)
                db_img_count = (summary[0].get("total_count", 0) if summary else 0)
                if summary and db_img_count > 0:
                    folder_count += 1
                    img_count = summary[0].get("total_count", 0) if summary else 0
                    total_images += img_count
                    for row in summary:
                        code = row.get("code", "")
                        stage_total[code] = stage_total.get(code, 0) + row.get("total_count", 0)
                        stage_done[code] = stage_done.get(code, 0) + row.get("done_count", 0)
                        stage_failed[code] = stage_failed.get(code, 0) + row.get("failed_count", 0)
                        stage_skipped[code] = stage_skipped.get(code, 0) + row.get("skipped_count", 0)
                        stage_running[code] = stage_running.get(code, 0) + int(row.get("running_count") or 0)
                        stage_queued[code] = stage_queued.get(code, 0) + int(row.get("queued_count") or 0)
                else:
                    img_count, n_folders = _scope_count_images_on_disk(local_path, request.recursive)
                    if img_count > 0 or n_folders > 0:
                        folder_count += n_folders
                        total_images += img_count
                        for code in phase_codes:
                            stage_total[code] = stage_total.get(code, 0) + img_count
                            stage_done[code] = stage_done.get(code, 0)
                            stage_failed[code] = stage_failed.get(code, 0)
                            stage_skipped[code] = stage_skipped.get(code, 0)

            stage_statuses = {}
            stage_counts = {}
            for code in phase_codes:
                total = stage_total.get(code, 0)
                done = stage_done.get(code, 0)
                failed = stage_failed.get(code, 0)
                skipped = stage_skipped.get(code, 0)
                running = stage_running.get(code, 0)
                queued = stage_queued.get(code, 0)
                if total == 0:
                    status = "not_started"
                elif running > 0:
                    status = "running"
                elif queued > 0:
                    status = "queued"
                elif failed > 0:
                    status = "failed"
                elif done == total:
                    status = "done"
                elif (done + skipped) == total and failed == 0:
                    # Optional phases (e.g. culling) can be "finished" via skip + done mix; mirror folder summary semantics.
                    status = "done"
                elif done > 0 or skipped > 0:
                    status = "partial"
                else:
                    status = "not_started"
                stage_statuses[code] = status
                stage_counts[code] = {
                    "done": done,
                    "failed": failed,
                    "skipped": skipped,
                    "total": total,
                    "running": running,
                    "queued": queued,
                }

            return {
                "image_count": total_images,
                "folder_count": folder_count,
                "stage_statuses": stage_statuses,
                "stage_counts": stage_counts,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def _build_scope_tree_sync(include_phase_status: bool = True):
        """Sync implementation run in thread pool to avoid blocking event loop."""
        from modules import db, utils
        from modules.ui_tree import build_tree_dict
        raw_folders = db.get_all_folders()
        folders = []
        for p in raw_folders:
            local_p = utils.convert_path_to_local(p) if hasattr(utils, 'convert_path_to_local') else p
            if not local_p:
                continue
            norm = os.path.normpath(local_p)
            basename = os.path.basename(norm).lower()
            if basename in ['.tmp.drivedownload', '.tmp.driveupload', 'keywords_output', '.']:
                continue
            folders.append(local_p)
        folders = list(set(folders))
        tree_dict = build_tree_dict(folders)

        if not include_phase_status:
            return tree_dict

        # Single bulk query — replaces N individual get_folder_phase_summary() calls
        bulk_cache = db.get_all_folder_phase_summaries_bulk()

        def enrich(nodes: List[Dict]) -> List[Dict]:
            result = []
            for node in nodes:
                path = node.get("path", "")
                if path:
                    summary = bulk_cache.get(os.path.normpath(path))
                    if summary:
                        node["phase_statuses"] = {
                            row["code"]: row.get("status", "not_started") for row in summary
                        }
                if "children" in node:
                    node["children"] = enrich(node["children"])
                result.append(node)
            return result

        return enrich(tree_dict)

    @router.get("/scope/tree", summary="Folder tree with phase status overlays")
    async def scope_tree(include_phase_status: bool = True):
        """Enhanced folder tree with per-folder phase status for the Scope Navigator sidebar."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_build_scope_tree_sync, include_phase_status),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Folder tree build timed out.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/queue", summary="Get the current Run Queue")
    async def get_run_queue(limit: int = 100):
        from modules import db
        try:
            queued = db.get_queued_jobs(limit=limit)
            return [
                {
                    "run_id": j.get("id"),
                    "position": j.get("queue_position"),
                    "input_path": j.get("input_path", ""),
                    "scope_paths": json.loads(j.get("scope_paths") or "[]") or [j.get("input_path", "")],
                    "created_at": j.get("created_at"),
                    "enqueued_at": j.get("enqueued_at"),
                }
                for j in (queued or [])
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class QueueReorderRequest(BaseModel):
        run_id: int
        new_position: int

    @router.post("/queue/reorder", summary="Reorder a queued Run")
    async def reorder_queue(request: QueueReorderRequest):
        from modules import db
        try:
            db.reorder_queued_job(request.run_id, request.new_position)
            return {"success": True}
        except AttributeError:
            raise HTTPException(status_code=501, detail="Queue reordering not yet implemented")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─── End new Runs API ────────────────────────────────────────────────────

    @router.post(
        "/pipeline/phase/backfill-index-meta",
        response_model=ApiResponse,
        summary="Backfill Index/Meta phase status",
        description="Sets INDEXING=DONE and METADATA=DONE for images that have SCORING=DONE but lack these statuses (repairs legacy or new-image backfill gap)."
    )
    async def backfill_index_meta(request: PipelineBackfillRequest):
        from modules.ui.security import _check_rate_limit
        from modules import db
        _check_rate_limit("pipeline_backfill")

        if not os.path.exists(request.input_path):
            raise HTTPException(status_code=400, detail=f"Path not found: {request.input_path}")

        updated = db.backfill_index_meta_for_folder(request.input_path)
        return ApiResponse(
            success=True,
            message=f"Backfilled Index/Meta for {updated} image(s)",
            data={"updated_images": updated}
        )

    @router.get(
        "/maintenance/stale-running-phases",
        summary="Diagnostic: image_phase_status rows stuck in running",
        description=(
            "Returns a count and sample of per-image phase rows still `running` older than "
            "`min_age_seconds`. Use before POST /api/maintenance/reconcile-terminal-job-phases."
        ),
        tags=["General API"],
    )
    async def get_stale_running_phases(
        min_age_seconds: int = Query(3600, ge=0, le=604800),
        limit: int = Query(50, ge=1, le=200),
    ):
        from modules import db

        result = db.list_stale_running_image_phase_rows(
            min_age_seconds=min_age_seconds,
            limit=limit,
        )
        result["reconcilable_count"] = db.count_reconcilable_terminal_job_phases()
        return result

    @router.post(
        "/maintenance/reconcile-terminal-job-phases",
        response_model=ApiResponse,
        summary="Reconcile stuck phases for finished jobs",
        description=(
            "Marks `image_phase_status` rows as failed when the parent job is already terminal "
            "(completed/failed/canceled) but a per-image row stayed `running`. "
            "Safe self-help for UI/badge drift after crashes or restarts."
        ),
        tags=["General API"],
    )
    async def reconcile_terminal_job_phases(
        limit: int = Query(5000, ge=1, le=50000),
    ):
        from modules.ui.security import _check_rate_limit
        from modules import db

        _check_rate_limit("maintenance_reconcile_terminal_phases")
        try:
            n = db.reconcile_stale_running_phases_for_terminal_jobs(limit=limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return ApiResponse(
            success=True,
            message=f"Reconciled {n} stuck phase row(s) tied to terminal jobs",
            data={"reconciled_rows": n},
        )

    @router.post(
        "/maintenance/backfill-index-meta",
        response_model=ApiResponse,
        summary="Global backfill Index/Meta phase status (batched)",
        description=(
            "Sets INDEXING=DONE and METADATA=DONE for up to `limit` images that have SCORING=DONE "
            "but lack those phase rows. Same semantics as backfill_index_meta_global; repeat to drain large DBs."
        ),
        tags=["General API"],
    )
    async def maintenance_backfill_index_meta(
        limit: int = Query(1000, ge=1, le=10000),
    ):
        from modules.ui.security import _check_rate_limit
        from modules import db

        _check_rate_limit("maintenance_backfill_index_meta")
        try:
            updated = db.backfill_index_meta_global(limit=limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return ApiResponse(
            success=True,
            message=f"Backfilled Index/Meta for {updated} image(s)",
            data={"updated_images": updated},
        )

    @router.post(
        "/maintenance/recalculate-status-from-data",
        response_model=ApiResponse,
        summary="Recalculate derivable per-image status and folder aggregates",
        description=(
            "Repairs derivable per-image phase status drift (index/meta, keywords, culling), "
            "then rebuilds folder phase aggregates and legacy flags. Supports all-db or selected-folder scope."
        ),
        tags=["General API"],
    )
    async def maintenance_recalculate_status_from_data(
        scope: str = Query("selected_folder", pattern="^(all|selected_folder)$"),
        scope_path: Optional[str] = Query(
            None,
            description="Required when scope=selected_folder. Uses folder + descendants.",
        ),
    ):
        from modules.ui.security import _check_rate_limit
        from modules import db, utils

        _check_rate_limit("maintenance_recalculate_status_from_data")

        selected_scope = (scope or "selected_folder").strip().lower()
        if selected_scope == "selected_folder" and not (scope_path and scope_path.strip()):
            raise HTTPException(status_code=400, detail="scope_path is required when scope=selected_folder")

        target_scope_path = None
        target_folder_paths: List[str] = []
        if selected_scope == "selected_folder":
            wsl_path = (
                utils.convert_path_to_wsl(scope_path.strip())
                if hasattr(utils, "convert_path_to_wsl")
                else scope_path.strip()
            )
            target_scope_path = wsl_path or scope_path.strip()
            target_folder_paths = db.list_folder_paths_under_scope(target_scope_path)
            if not target_folder_paths:
                row = db.get_connector().query_one("SELECT path FROM folders WHERE path = ?", (target_scope_path,))
                if row and row.get("path"):
                    target_folder_paths = [row["path"]]
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Scope folder not found in folders cache: {scope_path}",
                    )
        else:
            rows = db.get_connector().query("SELECT path FROM folders")
            target_folder_paths = [r["path"] for r in rows if r and r.get("path")]

        connector = db.get_connector()
        image_scope_sql = ""
        image_scope_params: List[Any] = []
        if selected_scope == "selected_folder":
            placeholders = ",".join(["?"] * len(target_folder_paths))
            image_scope_sql = f" AND i.folder_id IN (SELECT id FROM folders WHERE path IN ({placeholders}))"
            image_scope_params = list(target_folder_paths)

        before = {
            "missing_indexing_or_metadata_with_scoring_done": 0,
            "missing_keywords_status_with_keywords_data": 0,
            "culling_failed_with_data_present": 0,
        }
        after = dict(before)
        warnings: List[str] = []

        before_idx_meta_sql = (
            """
            SELECT COUNT(*) AS cnt
            FROM images i
            JOIN pipeline_phases p_score ON LOWER(TRIM(p_score.code)) = 'scoring'
            JOIN image_phase_status ips_score ON ips_score.image_id = i.id
                AND ips_score.phase_id = p_score.id
                AND LOWER(TRIM(ips_score.status)) = 'done'
            WHERE (
                NOT EXISTS (
                    SELECT 1 FROM image_phase_status ips_i
                    JOIN pipeline_phases p_i ON p_i.id = ips_i.phase_id
                    WHERE ips_i.image_id = i.id
                      AND LOWER(TRIM(p_i.code)) = 'indexing'
                      AND LOWER(TRIM(ips_i.status)) = 'done'
                )
                OR NOT EXISTS (
                    SELECT 1 FROM image_phase_status ips_m
                    JOIN pipeline_phases p_m ON p_m.id = ips_m.phase_id
                    WHERE ips_m.image_id = i.id
                      AND LOWER(TRIM(p_m.code)) = 'metadata'
                      AND LOWER(TRIM(ips_m.status)) = 'done'
                )
            )
            """
            + image_scope_sql
        )
        before["missing_indexing_or_metadata_with_scoring_done"] = int(
            (connector.query_one(before_idx_meta_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        kw_sql = (
            """
            SELECT COUNT(*) AS cnt
            FROM images i
            WHERE EXISTS (SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id)
              AND NOT EXISTS (
                SELECT 1 FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                WHERE ips.image_id = i.id
                  AND LOWER(TRIM(pp.code)) = 'keywords'
                  AND LOWER(TRIM(ips.status)) = 'done'
              )
            """
            + image_scope_sql
        )
        before["missing_keywords_status_with_keywords_data"] = int(
            (connector.query_one(kw_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        has_culling_data_expr = (
            "i.stack_id IS NOT NULL OR EXISTS (SELECT 1 FROM image_embeddings ie WHERE ie.image_id = i.id)"
            if getattr(connector, "type", "") == "postgres"
            else "i.stack_id IS NOT NULL OR i.image_embedding IS NOT NULL"
        )

        culling_sql = (
            """
            SELECT COUNT(*) AS cnt
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            JOIN images i ON i.id = ips.image_id
            WHERE LOWER(TRIM(pp.code)) = 'culling'
              AND LOWER(TRIM(ips.status)) = 'failed'
              AND (
            """
            + has_culling_data_expr
            + """
              )
            """
            + image_scope_sql
        )
        before["culling_failed_with_data_present"] = int(
            (connector.query_one(culling_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        if selected_scope == "selected_folder":
            idx_meta_changed = int(db.backfill_index_meta_for_folder(target_scope_path))
        else:
            idx_meta_changed = int(db.backfill_index_meta_global(limit=1_000_000))

        kw_rows = connector.query(
            (
                """
                SELECT DISTINCT i.id AS image_id
                FROM images i
                WHERE EXISTS (SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id)
                  AND NOT EXISTS (
                    SELECT 1 FROM image_phase_status ips
                    JOIN pipeline_phases pp ON pp.id = ips.phase_id
                    WHERE ips.image_id = i.id
                      AND LOWER(TRIM(pp.code)) = 'keywords'
                      AND LOWER(TRIM(ips.status)) = 'done'
                  )
                """
                + image_scope_sql
            ),
            tuple(image_scope_params),
        )
        kw_backfilled = 0
        for row in kw_rows:
            db.set_image_phase_status(int(row["image_id"]), "keywords", "done")
            kw_backfilled += 1

        culling_rows = connector.query(
            (
                """
                SELECT ips.id AS ips_id
                FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                JOIN images i ON i.id = ips.image_id
                WHERE LOWER(TRIM(pp.code)) = 'culling'
                  AND LOWER(TRIM(ips.status)) = 'failed'
                  AND (
                """
                + has_culling_data_expr
                + """
                  )
                """
                + image_scope_sql
            ),
            tuple(image_scope_params),
        )
        culling_ids = [int(r["ips_id"]) for r in culling_rows]
        if culling_ids:
            now = datetime.now()

            def _repair_culling_tx(tx):
                for ips_id in culling_ids:
                    tx.execute(
                        """
                        UPDATE image_phase_status
                        SET status = 'done',
                            last_error = NULL,
                            finished_at = COALESCE(finished_at, ?),
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, now, ips_id),
                    )

            connector.run_transaction(_repair_culling_tx)

        folders_recomputed = 0
        keywords_flag_updates = 0
        for path in target_folder_paths:
            try:
                db.invalidate_folder_phase_aggregates(folder_path=path)
                db.get_folder_phase_summary(path, force_refresh=True)
                folders_recomputed += 1
                if db.check_and_update_folder_keywords_status(path):
                    keywords_flag_updates += 1
            except Exception as folder_err:
                warnings.append(f"Folder aggregate rebuild failed for {path}: {folder_err}")

        if selected_scope == "all" and not target_folder_paths:
            warnings.append("No folders found; aggregate rebuild skipped.")
        warnings.append(
            "total_rows_changed_estimate is heuristic: index/meta assumes up to 2 per-image phase rows per repaired image."
        )

        after["missing_indexing_or_metadata_with_scoring_done"] = int(
            (connector.query_one(before_idx_meta_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )
        after["missing_keywords_status_with_keywords_data"] = int(
            (connector.query_one(kw_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )
        after["culling_failed_with_data_present"] = int(
            (connector.query_one(culling_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        target_images_row = connector.query_one(
            (
                "SELECT COUNT(*) AS cnt FROM images i WHERE 1=1"
                + image_scope_sql
            ),
            tuple(image_scope_params),
        )
        target_images = int((target_images_row or {}).get("cnt", 0))

        summary = {
            "scope": selected_scope,
            "scope_path": target_scope_path if selected_scope == "selected_folder" else None,
            "target_images": target_images,
            "per_image_changes": {
                "indexing_metadata_backfilled_images": idx_meta_changed,
                "keywords_phase_backfilled_rows": kw_backfilled,
                "culling_failed_to_done_rows": len(culling_ids),
                "total_rows_changed_estimate": (idx_meta_changed * 2) + kw_backfilled + len(culling_ids),
            },
            "folder_aggregate_changes": {
                "folders_recomputed": folders_recomputed,
                "folders_marked_keywords_processed": keywords_flag_updates,
            },
            "before": before,
            "after": after,
            "warnings": warnings,
        }

        return ApiResponse(
            success=True,
            message=(
                "Status recalculation finished: "
                f"{summary['per_image_changes']['total_rows_changed_estimate']} per-image row changes "
                f"(heuristic estimate), {folders_recomputed} folder aggregate(s) rebuilt."
            ),
            data={"summary": summary},
        )

    @router.post(
        "/maintenance/backfill-exif-dates",
        response_model=ApiResponse,
        summary="Re-extract EXIF dates for rows with NULL date_time_original",
        description=(
            "Repairs image_exif rows where date_time_original is NULL due to a prior "
            "timestamp parsing bug. Re-runs exiftool extraction and updates date columns. "
            "Safe to repeat; skips images whose files lack EXIF dates."
        ),
        tags=["General API"],
    )
    async def maintenance_backfill_exif_dates(
        limit: int = Query(1000, ge=1, le=10000),
    ):
        from modules.ui.security import _check_rate_limit
        from modules import exif_extractor

        _check_rate_limit("maintenance_backfill_exif_dates")
        try:
            stats = await asyncio.to_thread(exif_extractor.backfill_exif_dates, limit=limit)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return ApiResponse(
            success=True,
            message=f"Backfill EXIF dates: {stats['updated']} updated, {stats['skipped_no_file']} files missing, {stats['skipped_no_date']} no date tag, {stats['errors']} errors out of {stats['checked']} checked",
            data=stats,
        )

    @router.post(
        "/maintenance/regenerate-thumbnails",
        response_model=ApiResponse,
        summary="Regenerate missing thumbnails (global batch)",
        description=(
            "Regenerates up to 500 thumbnails globally where the DB path does not resolve to a file. "
            "May take several minutes on RAW-heavy libraries. Safe to repeat."
        ),
        tags=["General API"],
    )
    async def maintenance_regenerate_thumbnails():
        from modules.ui.security import _check_rate_limit
        from modules import thumbnail_maintenance

        _check_rate_limit("maintenance_regenerate_thumbnails")
        try:
            stats = thumbnail_maintenance.regenerate_missing_thumbnails_batch(limit=500)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return ApiResponse(
            success=True,
            message=(
                f"Thumbnail batch done: {stats['regenerated']} regenerated, "
                f"{stats['skipped_thumb_ok']} skipped (OK), "
                f"{stats['skipped_missing_original']} missing original, "
                f"{stats['failed']} failed"
            ),
            data=dict(stats),
        )

    @router.post(
        "/maintenance/repair-thumbnail-paths",
        response_model=ApiResponse,
        summary="Repair malformed thumbnail path columns (global batch)",
        description=(
            "Normalizes up to 1000 thumbnail_path / thumbnail_path_win row updates per call. "
            "Default (repair_all=false): Postgres scans only likely-bad rows (Docker /app paths, "
            "repo-relative fragments, single-column pairs). "
            "repair_all=true: full-table scan; normalizes any row where values change (slower). "
            "Does not regenerate image pixels. Safe to repeat."
        ),
        tags=["General API"],
    )
    async def maintenance_repair_thumbnail_paths(
        repair_all: bool = Query(
            False,
            description="Full scan: normalize every row where normalize_stored_thumbnail_pair changes values",
        ),
    ):
        from modules.ui.security import _check_rate_limit
        from modules import thumbnail_maintenance

        _check_rate_limit("maintenance_repair_thumbnail_paths")
        try:
            stats = thumbnail_maintenance.repair_thumbnail_paths_batch(
                limit=1000,
                repair_all_pairs=repair_all,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        parts = [
            f"{stats['repaired']} updated",
            f"{stats['unchanged']} unchanged",
            f"{stats['scanned']} rows scanned",
        ]
        if stats.get("used_candidate_filter"):
            parts.append("quick filter")
        msg = "Thumbnail path repair: " + ", ".join(parts)
        if not repair_all and stats["repaired"] == 0 and stats.get("used_candidate_filter") and stats["scanned"] == 0:
            msg += (
                ". No candidate rows (DB likely clean for common issues). "
                "Retry with repair_all=true for a deep normalize pass."
            )
        elif not repair_all and stats["repaired"] == 0 and stats["scanned"] > 0:
            msg += ". Candidate rows normalized with no changes; try repair_all=true if paths still look wrong."
        return ApiResponse(
            success=True,
            message=msg,
            data=dict(stats),
        )

    @router.post(
        "/maintenance/heal-thumbnails",
        response_model=ApiResponse,
        summary="Heal thumbnails (quick path repair + missing regeneration)",
        description=(
            "Runs quick thumbnail path normalization (up to 1000 row updates), then regenerates "
            "up to 500 missing thumbnail rasters. Order matters: normalize DB paths first, then decode pixels. "
            "Does not perform deep/full-table path repair; use POST /maintenance/repair-thumbnail-paths "
            "with repair_all=true when paths still look wrong after this."
        ),
        tags=["General API"],
    )
    async def maintenance_heal_thumbnails():
        from modules.ui.security import _check_rate_limit
        from modules import thumbnail_maintenance

        _check_rate_limit("maintenance_heal_thumbnails")
        try:
            result = thumbnail_maintenance.heal_thumbnails_batch()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        rep = result["repair"]
        reg = result["regenerate"]
        msg = (
            f"Heal thumbnails: path repair {rep['repaired']} updated / {rep['scanned']} scanned; "
            f"regenerate {reg['regenerated']} OK, {reg['skipped_thumb_ok']} skipped (thumb OK), "
            f"{reg['skipped_missing_original']} missing original, {reg['failed']} failed"
        )
        return ApiResponse(
            success=True,
            message=msg,
            data={"repair": dict(rep), "regenerate": dict(reg)},
        )

    @router.post(
        "/ipc/bridge",
        response_model=IpcBridgeResponse,
        summary="Electron IPC -> FastAPI bridge",
        description="""
        Bridges Electron-style IPC messages into FastAPI handlers so the desktop
        main process can forward a single contract to Python.

        Supported channels:
        - `pipeline:submit` -> POST /api/pipeline/submit
        - `pipeline:phase:skip` -> POST /api/pipeline/phase/skip
        - `pipeline:phase:retry` -> POST /api/pipeline/phase/retry
        - `tasks:active` -> GET /api/tasks/active
        - `jobs:queue` -> GET /api/jobs/queue
        - `folders:tree` -> GET /api/folders/tree
        - `folders:phase-status` -> GET /api/folders/phase-status
        """
    )
    async def ipc_bridge(request: IpcBridgeRequest):
        channel = (request.channel or "").strip()
        payload = request.payload or {}

        if channel == "pipeline:submit":
            result = await submit_pipeline(PipelineSubmitRequest(**payload))
            return IpcBridgeResponse(channel=channel, ok=True, data=result.model_dump())

        if channel == "pipeline:phase:skip":
            result = await skip_pipeline_phase(PipelinePhaseControlRequest(**payload))
            return IpcBridgeResponse(channel=channel, ok=True, data=result.model_dump())

        if channel == "pipeline:phase:retry":
            result = await retry_pipeline_phase(PipelinePhaseControlRequest(**payload))
            return IpcBridgeResponse(channel=channel, ok=True, data=result.model_dump())

        if channel == "tasks:active":
            limit = int(payload.get("limit", 200) or 200)
            result = await get_tasks_active(limit=limit)
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        if channel == "jobs:queue":
            limit = int(payload.get("limit", 200) or 200)
            result = await get_jobs_queue(limit=limit)
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        if channel == "folders:tree":
            result = await get_folder_tree()
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        if channel == "folders:phase-status":
            path = (payload.get("path") or payload.get("input_path") or "").strip()
            if not path:
                raise HTTPException(status_code=400, detail="payload.path is required for folders:phase-status")
            force_refresh = bool(payload.get("force_refresh", False))
            result = await get_folder_phase_status(path=path, force_refresh=force_refresh)
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Unsupported IPC channel: {channel}",
                "supported_channels": [
                    "pipeline:submit",
                    "pipeline:phase:skip",
                    "pipeline:phase:retry",
                    "tasks:active",
                    "jobs:queue",
                    "folders:tree",
                    "folders:phase-status",
                ],
            },
        )
    
    @router.get(
        "/diagnostics",
        response_model=DiagnosticsResponse,
        summary="Get comprehensive system diagnostics",
        description="""
        Returns detailed diagnostic information about the system, database, models, and runners.
        
        **Note:** Some fields may be omitted if dependencies (like psutil) are not installed.
        """,
        tags=["General API"]
    )
    async def get_diagnostics_endpoint():
        from modules.diagnostics import get_diagnostics
        diag = get_diagnostics()
        
        # Add runner status to the diagnostics payload
        diag["runners"] = {
            "scoring": "available" if _scoring_runner is not None else "unavailable",
            "tagging": "available" if _tagging_runner is not None else "unavailable",
            "clustering": "available" if _clustering_runner is not None else "unavailable",
            "selection": "available" if _selection_runner is not None else "unavailable",
            "bird_species": "available" if _bird_species_runner is not None else "unavailable",
            "indexing": "available" if _indexing_runner is not None else "unavailable",
            "metadata": "available" if _metadata_runner is not None else "unavailable",
            "orchestrator": "active" if _orchestrator and _orchestrator.get_status().get("active") else "idle"
        }
        
        return diag

    return router
