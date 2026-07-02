"""API routes: utility (extracted from modules.api)."""

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



def create_utility_router() -> APIRouter:
    router = APIRouter()
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
        if _api_module()._scoring_runner is None:
            raise HTTPException(status_code=503, detail="Scoring runner not available")
        
        if not os.path.exists(request.file_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {request.file_path}"
            )
        
        success, message = await asyncio.to_thread(
            _api_module()._scoring_runner.fix_image_metadata,
            request.file_path,
        )

        return ApiResponse(
            success=success,
            message=message,
            data={"file_path": request.file_path}
        )
    
    @router.get(
        "/raw-preview",
        response_model=None,
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
        """,
        responses={
            200: {
                "description": "JPEG preview bytes",
                "content": {"image/jpeg": {}},
            },
            400: {"description": "Bad Request - Invalid input parameters"},
            404: {"description": "Not Found - Resource not found"},
            500: {"description": "Internal Server Error"},
        },
    )
    def get_raw_preview(path: str = Query(..., description="Full path to the image file")):
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
                 
        except HTTPException:
            raise
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


    return router
