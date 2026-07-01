"""API routes: electron (extracted from modules.api)."""

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
    DeleteFolderCacheRequest,
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


_control_job = deps.control_job
_control_stage = deps.control_stage
_control_step = deps.control_step
_http_for_transition_error = deps.http_for_transition_error
graceful_shutdown_processing = state.graceful_shutdown_processing




class RunSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: str = "folder_recursive"  # file|folder|folder_recursive|path_list
    scope_paths: List[str]
    stages: Optional[List[str]] = None
    run_mode: Literal["process_stale_or_missing"] = "process_stale_or_missing"
    plan_dry_run: bool = Field(
        False,
        description="When true, run the stale/missing planner only and return the plan without enqueueing a job.",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable reason/scope for this run (stored on jobs.description).",
    )
    post_run_audit: Optional[bool] = Field(
        None,
        description="When true, force post-completion data-quality audit (see processing.post_run_data_quality_audit).",
    )
    generate_captions: bool = Field(
        True,
        description="Generate BLIP captions for title/description during the keywords phase.",
    )
    generate_accessibility: bool = Field(
        False,
        description="Generate IPTC accessibility alt/extended description during the keywords phase.",
    )

    @model_validator(mode="after")
    def _normalize_run_mode(self):
        from modules.run_modes import normalize_run_mode

        self.run_mode = normalize_run_mode(self.run_mode)
        return self


class ValidationRepairPreviewRequest(BaseModel):
    scope_paths: List[str]
    stages: Optional[List[str]] = None
    include_stale_executor: bool = Field(
        True,
        description=(
            "When false, exclude executor-version-only drift from stage_queues "
            "(same as auto-drive enqueue)."
        ),
    )
    align_auto_drive: bool = Field(
        False,
        description="When true, forces include_stale_executor=false for this preview.",
    )


class RunsAutoDriveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_path: Optional[str] = Field(
        None,
        description="Optional root folder restriction for the bucket planner.",
    )
    folder_paths: Optional[List[str]] = Field(
        None,
        description="Optional explicit folder paths to queue; used by per-row Queue actions.",
    )
    target_phases: Optional[List[str]] = Field(
        None,
        description="Pipeline phases the auto-driver should consider. Defaults to the full pipeline.",
    )
    limit: int = Field(50, ge=1, le=500, description="Maximum folder runs to queue in this drive tick.")
    dry_run: bool = Field(False, description="When true, return the proposed queue operations without writing jobs.")
    max_repeats: int = Field(
        2,
        ge=1,
        le=20,
        description="Skip a folder/phase plan after this many prior terminal auto-drive attempts.",
    )
    generate_captions: bool = Field(
        True,
        description="Generate captions during keywords runs.",
    )
    force: bool = Field(
        False,
        description=(
            "When true with explicit folder_paths, bypass the loop guard for a "
            "manual per-folder queue (Drive batch still respects max_repeats)."
        ),
    )


class RunsDriveStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_path: Optional[str] = Field(
        None,
        description="Optional root folder restriction; omit to drive the whole library.",
    )
    limit: int = Field(50, ge=1, le=500, description="Max folder runs queued per drive tick.")
    target_phases: Optional[List[str]] = Field(
        None,
        description="Phases to drive. Defaults to the full pipeline including bird_species.",
    )
    generate_captions: bool = Field(True, description="Generate captions during keywords runs.")
    max_repeats: int = Field(
        2,
        ge=1,
        le=20,
        description="Skip a folder/phase plan after this many prior terminal attempts.",
    )


class ForceRunRequest(BaseModel):
    confirm: bool = Field(
        ..., description="Must be true to acknowledge this is a destructive operation"
    )


class ScopePreviewRequest(BaseModel):
    paths: List[str]
    recursive: bool = True


class QueueReorderRequest(BaseModel):
    run_id: int
    new_position: int



def create_electron_router() -> APIRouter:
    router = APIRouter()
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

    @router.delete(
        "/folders/cache",
        summary="Remove empty folder subtree from DB cache",
        description=(
            "Deletes the subtree rooted at ``path`` only when ``COUNT(images.folder_id ∈ subtree)==0``. "
            "Does not delete files on disk. Descendant rows are cleared via FK cascade."
        ),
    )
    async def delete_empty_folder_cache_route(request: DeleteFolderCacheRequest = Body(...)):
        try:
            res = await asyncio.to_thread(db.delete_empty_folder_cache_subtree, (request.path or "").strip())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        reason = res.get("reason")
        if reason == "invalid":
            raise HTTPException(status_code=400, detail=res.get("message") or "Invalid folder path.")
        if reason == "not_found":
            raise HTTPException(status_code=404, detail=res.get("message") or "Folder not found.")
        if reason == "not_empty":
            raise HTTPException(status_code=409, detail=res.get("message") or "Folder is not empty.")
        if reason == "error" or not res.get("success"):
            raise HTTPException(status_code=500, detail=res.get("message") or "Delete failed.")

        return {
            "success": True,
            "message": res.get("message"),
            "deleted_folders": int(res.get("deleted_folders") or 0),
        }

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

    @router.get(
        "/folders/{folder_id}",
        summary="Get folder by id",
        description=(
            "Returns a single folder row: id, path, parent_id, is_fully_scored, created_at, "
            "and a live image_count from images.folder_id (not the deprecated folders.image_count column)."
        ),
    )
    async def get_folder_by_id_endpoint(folder_id: int):
        from modules import db
        try:
            row = db.get_folder_detail_by_id(folder_id)
            if not row:
                raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
            created = row.get("created_at")
            return {
                "id": row["id"],
                "path": row["path"],
                "parent_id": row.get("parent_id"),
                "is_fully_scored": bool(row.get("is_fully_scored")),
                "image_count": int(row.get("image_count") or 0),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
            }
        except HTTPException:
            raise
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
    async def update_image(image_id: int, request: ImageUpdateRequest = Body(...)):
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
            current_keywords = db.get_resolved_image_keywords(
                image_id, legacy_fallback=row[1] or ""
            )
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

        # Pick-status mirror: when caller sets pick_status without an explicit
        # rating/label, project the pick onto Adobe-compatible rating + label so
        # Lightroom and existing gallery filters see it.
        if request.pick_status is not None:
            if request.pick_status == 1:
                if request.rating is None:
                    new_rating = 4
                if request.label is None:
                    new_label = "Green"
            elif request.pick_status == -1:
                if request.rating is None:
                    new_rating = 1
                if request.label is None:
                    new_label = "Red"
            else:  # 0
                if request.rating is None:
                    new_rating = 0
                if request.label is None:
                    new_label = ""

        try:
            success = db.update_image_metadata(file_path, new_keywords, new_title, new_desc, new_rating, new_label)
            if not success:
                raise HTTPException(status_code=500, detail="Database update failed")

            if request.pick_status is not None:
                db.update_image_pick_status(image_id, request.pick_status)

            sidecar_ok = True
            if request.write_sidecar and _api_module()._tagging_runner is not None:
                kw_list = [k.strip() for k in new_keywords.split(',') if k.strip()]
                sidecar_ok = _api_module()._tagging_runner.write_metadata(file_path, kw_list, new_title, new_desc, new_rating, new_label)

            return ApiResponse(
                success=True,
                message=f"Updated image {image_id}",
                data={
                    "image_id": image_id,
                    "sidecar_written": sidecar_ok,
                    "pick_status": request.pick_status,
                    "rating": new_rating,
                    "label": new_label,
                },
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
    async def export_gallery(request: ExportRequest = Body(...)):
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
        "/config/full",
        summary="Get full application configuration",
        description="""
        Returns merged `config.json` + `environment.json` contents for Settings integrations
        and Electron. Prefer `GET /api/config` for the React SPA feature-flag subset.
        Passwords and tokens may be present; callers should not expose this response publicly.
        """
    )
    async def get_config_full():
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

    @router.post("/runs/plan/preview", summary="Preview stale/missing work for scope")
    @router.post("/runs/validation-repair/preview", summary="Preview stale/missing work for scope (alias)")
    async def preview_validation_repair(request: ValidationRepairPreviewRequest = Body(...)):
        scope_paths = [_normalize_scope_path_input(p) for p in request.scope_paths]
        scope_paths = [p for p in scope_paths if p]
        if not scope_paths:
            raise HTTPException(status_code=400, detail="scope_paths must not be empty")
        include_stale = request.include_stale_executor
        if request.align_auto_drive:
            include_stale = False
        try:
            result = await asyncio.to_thread(
                db.build_validation_repair_plan,
                scope_paths,
                request.stages or [],
                True,
                include_stale_executor=include_stale,
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/runs/folder-buckets", summary="Paginated folder buckets for Runs auto-queue")
    async def get_run_folder_buckets(
        root_path: Optional[str] = None,
        q: Optional[str] = None,
        bucket: Optional[str] = None,
        limit: int = Query(25, ge=1, le=200),
        offset: int = Query(0, ge=0),
        include_complete: bool = False,
        refresh_dirty_limit: int = Query(
            100,
            ge=0,
            le=500,
            description=(
                "Max folder phase summaries to force-refresh when bulk cache is missing "
                "or phase_agg_dirty=1 (0 = only refresh missing cache entries)."
            ),
        ),
        planner_preview_limit: int = Query(
            0,
            ge=0,
            le=100,
            description=(
                "Max folder-bucket rows on this page to compute JIT planner_next_phases "
                "(default 0; opt in for accurate enqueue preview, but each row runs a "
                "per-image plan_scope and can be slow on folders with many images)."
            ),
        ),
        planner_preview_max_images: int = Query(
            500,
            ge=0,
            le=100000,
            description=(
                "Skip planner preview on folders larger than this image count "
                "(0 disables the cap)."
            ),
        ),
    ):
        try:
            from modules import runs_autodrive

            return await asyncio.to_thread(
                runs_autodrive.build_folder_buckets,
                root_path=root_path,
                q=q,
                bucket=bucket,
                limit=limit,
                offset=offset,
                include_complete=include_complete,
                refresh_dirty_limit=refresh_dirty_limit,
                planner_preview_limit=planner_preview_limit,
                planner_preview_max_images=planner_preview_max_images,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/auto-drive", summary="Auto-queue folder runs from bucket planner")
    async def auto_drive_runs(request: RunsAutoDriveRequest = Body(...)):
        try:
            from modules import runs_autodrive

            return await asyncio.to_thread(
                runs_autodrive.auto_drive_runs,
                root_path=request.root_path,
                folder_paths=request.folder_paths,
                limit=request.limit,
                dry_run=request.dry_run,
                target_phases=request.target_phases,
                max_repeats=request.max_repeats,
                generate_captions=request.generate_captions,
                force=request.force,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/drive/start", summary="Start the durable auto-drive loop")
    async def start_runs_drive(request: RunsDriveStartRequest = Body(...)):
        try:
            from modules import runs_autodrive

            return await asyncio.to_thread(
                lambda: {
                    "state": runs_autodrive.arm_drive(
                        root_path=request.root_path,
                        limit=request.limit,
                        target_phases=request.target_phases,
                        generate_captions=request.generate_captions,
                        max_repeats=request.max_repeats,
                    ),
                    "batch": runs_autodrive.kick_drive_batch_async(force=True),
                },
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/drive/stop", summary="Stop the durable auto-drive loop")
    async def stop_runs_drive():
        from modules import runs_autodrive

        return {"state": await asyncio.to_thread(runs_autodrive.stop_drive, "manual")}

    @router.get("/runs/drive/status", summary="Auto-drive loop status + outstanding work")
    async def runs_drive_status():
        from modules import runs_autodrive

        return await asyncio.to_thread(runs_autodrive.get_drive_status_with_outstanding)

    @router.post("/runs/submit", summary="Submit a new Run")
    async def submit_run(request: RunSubmitRequest = Body(...)):
        from modules import db
        from modules.phases import (
            PhaseCode,
            assert_prereqs_for_scope,
            normalize_phase_codes,
            sort_phase_value_strings,
        )
        scope_paths = [_normalize_scope_path_input(p) for p in request.scope_paths]
        scope_paths = [p for p in scope_paths if p]
        if not scope_paths:
            raise HTTPException(status_code=400, detail="scope_paths must not be empty")
        # Resolve each scope path to a local OS path (e.g. WSL /mnt/d/... → D:/ on Windows)
        # so the job dispatcher and runners see paths that actually exist on this host.
        scope_paths = [_scope_resolve_path(p) for p in scope_paths]
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

        try:
            prereq_miss = await asyncio.to_thread(
                assert_prereqs_for_scope,
                phase_values or [],
                scope_paths,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"scope prerequisite check failed: {e}") from e

        if prereq_miss:
            raise HTTPException(
                status_code=400,
                detail={"code": "missing_prerequisites", "missing": prereq_miss},
            )

        requested_phases = list(phase_values) if phase_values else None

        if phase_values and not request.plan_dry_run:
            from modules.runs_autodrive import phases_with_work_from_repair_plan

            try:
                narrowed = await asyncio.to_thread(
                    phases_with_work_from_repair_plan,
                    scope_paths,
                    requested_phases,
                    dry_run=True,
                    include_stale_executor=True,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"run planning failed: {e}") from e
            if not narrowed:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "nothing_to_queue",
                        "message": "No stale or missing work for the requested stages in this scope.",
                        "requested_phases": requested_phases,
                    },
                )
            phase_values = narrowed
            phases = normalize_phase_codes(phase_values)
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
            elif first_p == PhaseCode.BIRD_SPECIES:
                phase_code = "bird_species"
                job_type = "bird_species"

        mode_flags = resolve_run_mode_flags(CANONICAL_RUN_MODE)

        payload = {
            "scope_type": request.scope_type,
            "scope_paths": scope_paths,
            "input_path": primary_path,
            "run_mode": CANONICAL_RUN_MODE,
            "skip_done": mode_flags["skip_done"],
            "skip_existing": mode_flags["skip_existing"],
            "force_rerun": mode_flags["force_rerun"],
            "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
            "overwrite": mode_flags["overwrite"],
            "force_rescan": mode_flags["force_rescan"],
            "phases": phase_values,
            "target_phases": phase_values,
            "generate_captions": bool(request.generate_captions),
            "generate_accessibility": bool(request.generate_accessibility),
            "post_run_audit": True,
        }
        payload = augment_queue_payload_for_audit(payload, trigger="api", tool_id="run_submit")
        run_description = build_run_submit_description(
            scope_type=request.scope_type,
            scope_paths=scope_paths,
            run_mode=CANONICAL_RUN_MODE,
            phase_values=phase_values,
            client_description=request.description,
        )
        if request.post_run_audit is not None:
            payload["post_run_audit"] = bool(request.post_run_audit)
        try:
            repair_plan = await asyncio.to_thread(
                db.build_validation_repair_plan,
                scope_paths,
                phase_values or [],
                bool(request.plan_dry_run),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"run planning failed: {e}") from e

        if request.plan_dry_run:
            return {"success": True, "plan": repair_plan, "dry_run": True}

        payload["repair_plan_summary"] = repair_plan
        payload["resolved_image_ids_by_stage"] = repair_plan.get("stage_queues", {})
        if phase_values:
            first = str(phase_values[0]).strip().lower()
            first_ids = (repair_plan.get("stage_queues", {}) or {}).get(first)
            if isinstance(first_ids, list):
                payload["resolved_image_ids"] = first_ids
        payload["skip_existing"] = False
        reason_summary, reason_criteria = build_manual_submit_summary(
            scope_paths=scope_paths,
            enqueued_phases=phase_values or [],
            requested_phases=requested_phases,
            repair_plan=repair_plan,
        )
        reason_criteria["run_mode"] = CANONICAL_RUN_MODE
        payload = attach_run_reason(
            payload,
            source=REASON_SOURCE_MANUAL_SUBMIT,
            summary=reason_summary,
            criteria=reason_criteria,
            trigger="api",
            tool_id="run_submit",
        )
        try:
            job_id, position = await asyncio.wait_for(
                asyncio.to_thread(
                    db.enqueue_job_with_phases,
                    primary_path,
                    phase_code,
                    job_type,
                    payload,
                    run_description,
                    phase_values,
                    "queued",
                ),
                timeout=30.0,
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
            try:
                db.update_job_status(run_id, "paused", "user_pause")
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))
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
                    logger.warning("resume_run: double-encoded queue_payload detected on run_id=%s; decoding again", run_id)
                    payload = json.loads(payload)
            except Exception:
                payload = {}
            payload["skip_done"] = True
            db.update_job_payload(run_id, json.dumps(payload))

            # Verify job has a phase plan before requeuing
            phases = db.get_job_phases(run_id)
            if not phases:
                raise HTTPException(status_code=409, detail=f"Run {run_id} has no phase plan — cannot resume. Use retry instead.")

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
            cancel_method = None
            if status == "queued":
                result = db.request_cancel_job(run_id)
                if not result.get("success"):
                    raise HTTPException(status_code=409, detail=f"Could not cancel run {run_id}: {result.get('reason')}")
                cancel_method = "cancel_requested"
            elif status in ("pending", "running", "paused", "interrupted", "cancel_requested", "restarting"):
                db.update_job_status(run_id, "cancelled")
                cancel_method = "update_status"
                # Stop the active runner when running (DB update alone doesn't stop the process)
                if status == "running":
                    state = _api_module()._job_dispatcher.get_state()
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
            return {"success": True, "message": f"Run {run_id} canceled", "method": cancel_method}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
                    ("scoring", _api_module()._scoring_runner),
                    ("tagging", _api_module()._tagging_runner),
                    ("clustering", _api_module()._clustering_runner),
                    ("selection", _api_module()._selection_runner),
                    ("indexing", _api_module()._indexing_runner),
                    ("metadata", _api_module()._metadata_runner),
                    ("bird_species", _api_module()._bird_species_runner),
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
                state = _api_module()._job_dispatcher.get_state()
                active_runner_name = state.get("active_runner")
                runner_map = {
                    "scoring": _api_module()._scoring_runner,
                    "tagging": _api_module()._tagging_runner,
                    "clustering": _api_module()._clustering_runner,
                    "selection": _api_module()._selection_runner,
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
                new_id, pos = _create_retry_job(job, "force_run")
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
                logger.warning("_resume_job_inplace: double-encoded queue_payload detected on run_id=%s; decoding again", run_id)
                payload = json.loads(payload)
        except Exception:
            payload = {}
        payload["skip_done"] = True
        db.update_job_payload(run_id, json.dumps(payload))

        # Verify job has a phase plan before requeuing
        phases = db.get_job_phases(run_id)
        if not phases:
            raise HTTPException(status_code=409, detail=f"Run {run_id} has no phase plan — cannot resume. Use retry instead.")

        _, position = db.requeue_job(run_id)
        db.resume_job_phases(run_id)
        return run_id, position

    def _create_retry_job(original_job: dict, source: str) -> tuple:
        """Shared helper: create a retry job from an original job.

        Args:
            original_job: job dict from db.get_job()
            source: "retry_run" or "force_run" to determine description suffix

        Returns:
            (new_job_id, queue_position)
        """
        from modules import db
        from modules.phases import sort_phase_value_strings

        payload_raw = original_job.get("queue_payload") or "{}"
        try:
            payload = json.loads(payload_raw)
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception:
            payload = {}
        payload["skip_done"] = True

        orig_job_type = original_job.get("job_type", "scoring")
        _phase_code_map = {
            "indexing": "indexing",
            "metadata": "metadata",
            "scoring": "scoring",
            "tagging": "keywords",
            "clustering": "culling",
            "selection": "culling",
        }
        phase_code = _phase_code_map.get(orig_job_type, "scoring")

        prior = original_job.get("description")
        _retry_ui = "(retry from Runs UI)"
        _force_q = "(re-queued via force_run)"

        def _with_suffix(base: str, suffix: str) -> str:
            p = (base or "").strip()
            if not p:
                return ""
            return p if p.endswith(suffix) else f"{p} {suffix}"

        if source == "force_run":
            retry_desc = (
                _with_suffix(str(prior).strip() if prior else "", _force_q)
                if prior and str(prior).strip()
                else f"Retry via force_run of job #{original_job.get('id')} ({orig_job_type}) for {original_job.get('input_path') or ''}."
            )
        else:  # "retry_run"
            retry_desc = (
                _with_suffix(str(prior).strip() if prior else "", _retry_ui)
                if prior and str(prior).strip()
                else f"Retry of run #{original_job.get('id')} ({orig_job_type}) for {original_job.get('input_path') or ''}."
            )

        orig_phases = db.get_job_phases(original_job["id"])
        if orig_phases:
            phase_codes = sort_phase_value_strings([p["phase_code"] for p in orig_phases])
        else:
            _defaults = {"tagging": ["keywords"], "selection": ["culling", "metadata"], "clustering": ["culling"]}
            phase_codes = sort_phase_value_strings(_defaults.get(orig_job_type, ["indexing", "metadata", "scoring"]))

        reason_source = REASON_SOURCE_FORCE_RUN if source == "force_run" else REASON_SOURCE_RETRY
        payload = attach_run_reason(
            payload,
            source=reason_source,
            summary=build_retry_summary(
                source=reason_source,
                original_run_id=int(original_job.get("id") or 0),
                job_type=str(orig_job_type),
                input_path=original_job.get("input_path"),
            ),
            criteria={
                "retried_from_run_id": original_job.get("id"),
                "enqueued_phases": phase_codes,
                "original_job_type": orig_job_type,
            },
            trigger=str(payload.get("trigger") or "api"),
            tool_id=str(payload.get("tool_id") or source),
        )

        new_job_id, position = db.enqueue_job_with_phases(
            input_path=original_job.get("input_path", ""),
            phase_code=phase_code,
            job_type=orig_job_type,
            queue_payload=json.dumps(payload),
            description=retry_desc,
            phase_codes=phase_codes,
            first_phase_state="queued",
        )
        return new_job_id, position

    @router.post("/runs/{run_id}/retry", summary="Retry a failed/canceled Run")
    async def retry_run(run_id: int):
        from modules import db
        try:
            job = db.get_job(run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            TERMINAL_STATUSES = {"failed", "interrupted", "canceled", "cancelled", "completed"}
            if job.get("status", "").lower() not in TERMINAL_STATUSES:
                raise HTTPException(status_code=409, detail=f"Run {run_id} cannot be retried (status={job.get('status')})")
            new_job_id, position = _create_retry_job(job, "retry_run")
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
            db.force_reset_job_phase_to_queued(run_id, stage_code)
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

    @router.get(
        "/runs/{run_id}/diagnostics",
        summary="Run diagnostics (post-run audit + per-phase image_phase_status counts)",
        description="""
        Returns ``post_run_audit`` from the job queue_payload (when present) and aggregated
        ``image_phase_status`` counts for this run. Use with ``GET .../stages/{stage_code}/items``
        for per-image details.
        """,
    )
    async def get_run_diagnostics(run_id: int):
        from modules import db
        try:
            out = await asyncio.to_thread(db.get_run_diagnostics, run_id)
            if out.get("error") == "job_not_found":
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            return out
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/runs/{run_id}/report",
        summary="Get job execution report",
        description="Returns the structured execution report (report_json) for a completed job.",
    )
    async def get_run_report(run_id: int):
        from modules import db
        try:
            job = await asyncio.to_thread(db.get_job_by_id, run_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            phases = await asyncio.to_thread(db.get_job_phases, run_id)
            phase_codes = [str((p or {}).get("phase_code") or "") for p in (phases or [])]
            if not _job_supports_execution_report(dict(job), phase_codes):
                return {
                    "available": False,
                    "reason": "unsupported_run_type",
                    "message": "Execution report is not available for this run type.",
                    "run_type": str(job.get("job_type") or ""),
                }
            report = await asyncio.to_thread(db.get_job_report, run_id)
            if report is None:
                raise HTTPException(status_code=404, detail=f"No execution report for run {run_id}")
            return {
                "available": True,
                "report": report,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/runs/{run_id}/report/images",
        summary="Get per-image execution actions",
        description=(
            "Paginated per-image action log with before/after score snapshots. "
            "Filter by phase_code and/or action (processed, skipped, failed, unchanged)."
        ),
    )
    async def get_run_report_images(
        run_id: int,
        phase_code: Optional[str] = None,
        action: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ):
        from modules import db
        try:
            return await asyncio.to_thread(
                db.get_job_image_actions, run_id, phase_code, action, offset, limit
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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

    def _compute_scope_preview_for_resolved_paths(
        resolved_paths: List[str],
        recursive: bool,
    ) -> Dict[str, Any]:
        """Aggregate scope preview for paths already resolved via ``_scope_resolve_path``."""
        from modules import db
        from modules.phases import PhaseCode

        total_images = 0
        folder_count = 0
        stage_done: Dict[str, int] = {}
        stage_failed: Dict[str, int] = {}
        stage_skipped: Dict[str, int] = {}
        stage_total: Dict[str, int] = {}
        phase_codes = [p.value for p in PhaseCode]

        stage_running: Dict[str, int] = {}
        stage_queued: Dict[str, int] = {}
        for local_path in resolved_paths:
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
                img_count, n_folders = _scope_count_images_on_disk(local_path, recursive)
                if img_count > 0 or n_folders > 0:
                    folder_count += n_folders
                    total_images += img_count
                    for code in phase_codes:
                        stage_total[code] = stage_total.get(code, 0) + img_count
                        stage_done[code] = stage_done.get(code, 0)
                        stage_failed[code] = stage_failed.get(code, 0)
                        stage_skipped[code] = stage_skipped.get(code, 0)

        stage_statuses: Dict[str, str] = {}
        stage_counts: Dict[str, Any] = {}
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

    @router.post("/scope/preview", summary="Preview scope before submitting a Run")
    async def scope_preview(request: ScopePreviewRequest = Body(...)):
        """Returns image count and per-stage phase statuses for the given paths.
        When a folder has no images in the DB (not yet indexed), scans the filesystem to show actual counts."""
        preview_paths = [_normalize_scope_path_input(p) for p in request.paths]
        preview_paths = [p for p in preview_paths if p]
        if not preview_paths:
            raise HTTPException(status_code=400, detail="paths must not be empty")
        try:
            resolved: List[str] = []
            for path in preview_paths:
                resolved.append(_scope_resolve_path(path))
            return _compute_scope_preview_for_resolved_paths(resolved, request.recursive)
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

        dc_map = db.get_folder_direct_image_counts_by_local_path_norm()

        def rollup_image_counts(node: Dict) -> int:
            """Set ``node["image_count"]`` to subtree image total (gallery ``total_image_count`` semantics)."""
            pkey = os.path.normpath(node.get("path") or "")
            meta = dc_map.get(pkey) or {}
            direct = int(meta.get("direct_count") or 0)
            children = node.get("children") or []
            under = sum(rollup_image_counts(ch) for ch in children)
            total = direct + under
            node["image_count"] = total
            return total

        for root in tree_dict:
            rollup_image_counts(root)

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

    @router.post("/queue/reorder", summary="Reorder a queued Run")
    async def reorder_queue(request: QueueReorderRequest = Body(...)):
        from modules import db
        try:
            db.reorder_queued_job(request.run_id, request.new_position)
            return {"success": True}
        except AttributeError:
            raise HTTPException(status_code=501, detail="Queue reordering not yet implemented")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─── End new Runs API ────────────────────────────────────────────────────



    from modules.api.handler_registry import register_handlers

    register_handlers(
        {
            "get_folder_tree": get_folder_tree,
            "get_folder_phase_status": get_folder_phase_status,
        }
    )

    return router
