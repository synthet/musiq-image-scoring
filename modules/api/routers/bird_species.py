"""API routes: bird_species (extracted from modules.api)."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException

from modules import db
from modules.api_models import (
    ApiResponse,
    BirdSpeciesStartRequest,
)
from modules.job_description import (
    augment_queue_payload_for_audit,
    build_bird_species_job_description,
)
from modules.run_manifest import (
    REASON_SOURCE_LEGACY_API,
    attach_run_reason,
    build_legacy_api_summary,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_bird_species_router() -> APIRouter:
    router = APIRouter()
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
        if _api_module()._bird_species_runner is None:
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
            import modules.api as api_mod

            selector_result = api_mod.resolve_selectors(
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

        bs_payload_body: dict = {
            "input_path": request.input_path,
            "candidate_species": request.candidate_species,
            "threshold": request.threshold,
            "top_k": request.top_k,
            "overwrite": request.overwrite,
            "resolved_image_ids": resolved_ids,
        }
        if resolved_ids is not None:
            bs_payload_body["resolved_image_ids_by_stage"] = {
                "bird_species": list(resolved_ids),
            }
        if request.folder_paths:
            bs_payload_body["scope_paths"] = list(request.folder_paths)
        bs_payload = augment_queue_payload_for_audit(
            bs_payload_body,
            trigger="api",
            tool_id="bird_species_start",
        )
        bs_extra = f"{resolved_count} resolved images." if resolved_count is not None else None
        bs_payload = attach_run_reason(
            bs_payload,
            source=REASON_SOURCE_LEGACY_API,
            summary=build_legacy_api_summary(
                job_kind="bird species", input_path=request.input_path, extra=bs_extra
            ),
            trigger="api",
            tool_id="bird_species_start",
            criteria={"resolved_count": resolved_count} if resolved_count is not None else None,
        )
        job_id, queue_position = db.enqueue_job(
            job_source,
            phase_code=None,
            job_type="bird_species",
            queue_payload=bs_payload,
            description=build_bird_species_job_description(request.input_path),
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
        if _api_module()._bird_species_runner is None:
            raise HTTPException(status_code=503, detail="Bird species runner not available")
        if not _api_module()._bird_species_runner.is_running:
            return ApiResponse(
                success=False,
                message="No bird species job is currently running",
                data={"is_running": False}
            )
        _api_module()._bird_species_runner.stop()
        return ApiResponse(
            success=True,
            message="Stop signal sent to bird species runner",
            data={"is_running": _api_module()._bird_species_runner.is_running}
        )

    @router.get(
        "/bird-species/status",
        summary="Get bird species status",
        description="Get the current status of the bird species classification runner."
    )
    async def get_bird_species_status():
        """Get bird species runner status."""
        if _api_module()._bird_species_runner is None:
            raise HTTPException(status_code=503, detail="Bird species runner not available")
        is_running, log_text, status_message, current, total = _api_module()._bird_species_runner.get_status()
        return {
            "is_running": is_running,
            "status_message": status_message,
            "current": current,
            "total": total,
            "log": log_text,
            "job_type": "bird_species",
        }


    return router
