"""API routes: pipeline_submit (extracted from modules.api)."""

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



def create_pipeline_submit_router() -> APIRouter:
    router = APIRouter()
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
    def submit_pipeline(request: PipelineSubmitRequest):
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
            return ApiResponse(success=False, message="Invalid submission parameters: Provide workspace_target or at least one selector")

        import modules.api as api_mod

        selector_request = api_mod.compose_selector_request(
            input_path=wt or None,
            image_ids_raw=request.image_ids,
            image_paths_raw=request.image_paths,
            folder_ids_raw=request.folder_ids,
            folder_paths_raw=request.folder_paths,
            exclude_image_paths_raw=request.exclude_image_paths,
            recursive=request.recursive,
        )
        valid_ops = {"indexing", "metadata", "score", "tag", "cluster"}
        invalid_ops = [op for op in request.stage_codes if op not in valid_ops]
        if invalid_ops:
            return ApiResponse(success=False, message=f"Invalid submission parameters: Invalid stage_codes: {invalid_ops}. Valid: {sorted(valid_ops)}")
        if not request.stage_codes:
            return ApiResponse(success=False, message="Invalid submission parameters: At least one stage_code is required")

        first_op = request.stage_codes[0]

        preview = api_mod.validate_and_preview(selector_request)
        resolved_count = int(preview.get("preview_count") or 0)
        if resolved_count <= 0 and first_op != "indexing":
            return ApiResponse(success=False, message="Invalid submission parameters: No images matched selectors")

        if wt and not any([request.image_ids, request.image_paths, request.folder_ids, request.folder_paths]):
            if not os.path.exists(wt):
                return ApiResponse(success=False, message=f"Invalid submission parameters: Path not found: {wt}")

        is_file = bool(wt and os.path.isfile(wt))
        if is_file and "cluster" in request.stage_codes:
            return ApiResponse(success=False, message="Invalid submission parameters: Clustering requires a folder path, not a single file")
        if "cluster" in request.stage_codes and not any([wt, request.folder_ids, request.folder_paths]):
            return ApiResponse(success=False, message="Invalid submission parameters: Clustering requires a folder selector")

        queue_input_path = wt or "SELECTOR_PIPELINE"

        from modules import db

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
                if _api_module()._scoring_runner is None:
                    return ApiResponse(success=False, message="Orchestrator unavailable: Scoring runner not available")
                if _api_module()._scoring_runner.is_running:
                    return ApiResponse(success=False, message="Orchestrator busy: Scoring runner is busy", data={"is_running": True})
                success, message = _api_module()._scoring_runner.run_single_image(wt)
            elif first_op == "tag":
                if _api_module()._tagging_runner is None:
                    return ApiResponse(success=False, message="Orchestrator unavailable: Tagging runner not available")
                if _api_module()._tagging_runner.is_running:
                    return ApiResponse(success=False, message="Orchestrator busy: Tagging runner is busy", data={"is_running": True})
                success, message = _api_module()._tagging_runner.run_single_image(
                    wt,
                    request.custom_keywords,
                    request.generate_captions,
                )
            else:
                return ApiResponse(success=False, message="Invalid submission parameters: Single-file pipeline supports score/tag only")

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

        wf_desc = build_workflow_run_description(first_op, wt or queue_input_path, list(request.stage_codes))

        def _pipeline_queue_payload(base: dict) -> dict:
            payload = augment_queue_payload_for_audit(
                serialize_queue_payload(base, preview),
                trigger="api",
                tool_id="pipeline_submit",
            )
            return attach_run_reason(
                payload,
                source=REASON_SOURCE_PIPELINE_SUBMIT,
                summary=(
                    f"Workflow pipeline queued starting at {first_op!r} "
                    f"for {queue_input_path or wt or 'workspace'}."
                ),
                trigger="api",
                tool_id="pipeline_submit",
                criteria={
                    "stage_codes": list(base.get("stage_codes") or request.stage_codes or []),
                    "first_op": first_op,
                    "workspace_target": wt or None,
                },
            )

        if first_op == "indexing":
            if _api_module()._indexing_runner is None:
                return ApiResponse(success=False, message="Orchestrator unavailable: Indexing runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="indexing",
                job_type="indexing",
                queue_payload=_pipeline_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "skip_existing": request.skip_existing,
                    },
                ),
                description=wf_desc,
            )
        elif first_op == "metadata":
            if _api_module()._metadata_runner is None:
                return ApiResponse(success=False, message="Orchestrator unavailable: Metadata runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="metadata",
                job_type="metadata",
                queue_payload=_pipeline_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "skip_existing": request.skip_existing,
                    },
                ),
                description=wf_desc,
            )
        elif first_op == "score":
            if _api_module()._scoring_runner is None:
                return ApiResponse(success=False, message="Orchestrator unavailable: Scoring runner not available")
            
            # Map operations to internal phase codes for the orchestrator
            target_phases = [op_to_phase_code.get(op) for op in request.stage_codes if op in ["indexing", "metadata", "score"]]
            
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="scoring",
                job_type="scoring",
                queue_payload=_pipeline_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "skip_existing": request.skip_existing,
                        "target_phases": target_phases,
                    },
                ),
                description=wf_desc,
            )
        elif first_op == "tag":
            if _api_module()._tagging_runner is None:
                return ApiResponse(success=False, message="Orchestrator unavailable: Tagging runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="keywords",
                job_type="tagging",
                queue_payload=_pipeline_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "custom_keywords": request.custom_keywords,
                        "overwrite": not request.skip_existing,
                        "generate_captions": request.generate_captions,
                        "generate_accessibility": request.generate_accessibility,
                    },
                ),
                description=wf_desc,
            )
        else:
            if _api_module()._clustering_runner is None:
                return ApiResponse(success=False, message="Orchestrator unavailable: Clustering runner not available")
            job_id, queue_position = db.enqueue_job(
                queue_input_path,
                phase_code="culling",
                job_type="clustering",
                queue_payload=_pipeline_queue_payload(
                    {
                        "input_path": wt or None,
                        "workspace_target": wt or None,
                        "workflow_template": request.workflow_template,
                        "stage_codes": request.stage_codes,
                        "threshold": request.clustering_threshold,
                        "time_gap": request.clustering_time_gap,
                        "force_rescan": request.clustering_force_rescan,
                    },
                ),
                description=wf_desc,
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
            if _api_module()._scoring_runner is None:
                raise HTTPException(status_code=503, detail="Scoring runner not available")
            job_id = db.create_job(request.input_path, phase_code="scoring")
            result = _api_module()._scoring_runner.start_batch(request.input_path, job_id, True)
        elif phase == "keywords":
            if _api_module()._tagging_runner is None:
                raise HTTPException(status_code=503, detail="Tagging runner not available")
            job_id = db.create_job(request.input_path, phase_code="keywords")
            generate_captions = config.get_config_section('tagging').get('captions_default', True)
            result = _api_module()._tagging_runner.start_batch(request.input_path, job_id=job_id, overwrite=False, generate_captions=generate_captions)
        elif phase == "culling":
            culling_runner = _api_module()._selection_runner or _api_module()._clustering_runner
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

    @router.post(
        "/pipeline/phase/backfill-index-meta",
        response_model=ApiResponse,
        summary="Backfill Index/Meta phase status",
        description=(
            "Sets INDEXING=DONE and METADATA=DONE for images that have "
            "SCORING=DONE but lack these statuses in the given folder."
        ),
        tags=["General API"],
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
            data={"updated_images": updated},
        )

    @router.post("/pipeline/run/pause", response_model=ApiResponse, summary="Pause current run")
    async def pause_pipeline_run(request: PipelineRunControlRequest):
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("pipeline_run_pause")
        stopped = []
        for phase in ("indexing", "metadata", "scoring", "culling", "keywords"):
            if state._stop_runner_for_phase(phase):
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
            if state._stop_runner_for_phase(phase):
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
            state._stop_runner_for_phase(phase)

        rp = attach_run_reason(
            augment_queue_payload_for_audit(
                {"input_path": input_path, "skip_existing": False},
                trigger="api",
                tool_id="pipeline_run_restart",
            ),
            source=REASON_SOURCE_LEGACY_API,
            summary=(
                f"Pipeline restart queued full Discovery→Inspection→Quality for {input_path}."
            ),
            trigger="api",
            tool_id="pipeline_run_restart",
            criteria={"enqueued_phases": ["indexing", "metadata", "scoring"], "input_path": input_path},
        )
        job_id, queue_position = db.enqueue_job(
            input_path,
            phase_code="indexing",
            job_type="indexing",
            queue_payload=rp,
            description=f"Pipeline restart from API: full Discovery→Inspection→Quality for {input_path}.",
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
            if _api_module()._scoring_runner is None:
                raise HTTPException(status_code=503, detail="Scoring runner not available")
            job_id = db.create_job(request.input_path, phase_code="scoring")
            result = _api_module()._scoring_runner.start_batch(request.input_path, job_id, True)
        elif phase == "culling":
            culling_runner = _api_module()._selection_runner or _api_module()._clustering_runner
            if culling_runner is None:
                raise HTTPException(status_code=503, detail="Selection runner not available")
            job_id = db.create_job(request.input_path, phase_code="culling")
            result = culling_runner.start_batch(request.input_path, job_id=job_id, force_rescan=True)
        else:
            if _api_module()._tagging_runner is None:
                raise HTTPException(status_code=503, detail="Tagging runner not available")
            job_id = db.create_job(request.input_path, phase_code="keywords")
            generate_captions = config.get_config_section('tagging').get('captions_default', True)
            result = _api_module()._tagging_runner.start_batch(request.input_path, job_id=job_id, overwrite=True, generate_captions=generate_captions)
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


    from modules.api.handler_registry import register_handlers

    register_handlers(
        {
            "submit_pipeline": submit_pipeline,
            "skip_pipeline_phase": skip_pipeline_phase,
            "retry_pipeline_phase": retry_pipeline_phase,
        }
    )

    return router
