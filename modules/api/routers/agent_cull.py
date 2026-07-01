"""API routes: agent_cull (extracted from modules.api)."""

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



def create_agent_cull_router() -> APIRouter:
    router = APIRouter()
    # ========== Agent-assisted cull review (read-only MVP endpoints) ==========

    @router.get(
        "/culling/agent-review/groups",
        summary="List agent cull review groups",
        description="Postgres-only. Metadata-only removal candidate reviews for stack/substack units.",
    )
    async def list_agent_cull_groups(
        stack_id: Optional[int] = None,
        sub_stack_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ):
        from modules.agent_cull.api_helpers import list_groups
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            return {"groups": list_groups(
                stack_id=stack_id,
                sub_stack_id=sub_stack_id,
                status=status,
                limit=min(max(limit, 1), 200),
                offset=max(offset, 0),
            )}
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except Exception as e:
            logger.exception("list_agent_cull_groups failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/culling/agent-review/groups/{group_id}",
        summary="Get agent cull review group with recommendations",
    )
    async def get_agent_cull_group(group_id: int):
        from modules.agent_cull.api_helpers import get_group
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            result = get_group(group_id)
            if result is None:
                raise HTTPException(status_code=404, detail="Review group not found")
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_agent_cull_group failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/culling/agent-review/schema",
        summary="Agent cull review response schema metadata",
    )
    async def get_agent_cull_schema():
        from modules.agent_cull.config import PROMPT_TEMPLATE_VERSION, RESPONSE_SCHEMA_VERSION
        from modules.agent_cull.vocab import output_vocabulary

        return {
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "output_vocabulary": output_vocabulary(),
        }

    @router.post(
        "/culling/agent-review/discover",
        summary="Discover eligible agent cull review units",
    )
    async def discover_agent_cull_units(request: AgentCullDiscoverRequest):
        from modules.agent_cull.actions import discover_action
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            return discover_action(
                folder_path=request.folder_path,
                folder_id=request.folder_id,
                stack_id=request.stack_id,
                sub_stack_id=request.sub_stack_id,
                limit=request.limit,
            )
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except Exception as e:
            logger.exception("discover_agent_cull_units failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/culling/agent-review/run",
        summary="Run agent cull review for one stack/substack unit",
    )
    async def run_agent_cull_review(request: AgentCullRunRequest):
        from modules.agent_cull.actions import run_review_action
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            result = await asyncio.to_thread(
                run_review_action,
                stack_id=request.stack_id,
                sub_stack_id=request.sub_stack_id,
                dry_run=request.dry_run,
                force=request.force,
                provider_override=request.agent,
            )
            if not result.get("ok") and result.get("error") == "agent_review_disabled":
                raise HTTPException(status_code=403, detail=result["error"])
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("run_agent_cull_review failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/culling/agent-review/groups/{group_id}/apply-candidates",
        summary="Mark safe remove recommendations as agent_remove_candidate (metadata only)",
    )
    async def apply_agent_cull_candidates(group_id: int, request: AgentCullRecommendationIdsRequest):
        from modules.agent_cull.actions import apply_candidates_action
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            result = apply_candidates_action(
                group_id,
                applied_by=request.actor,
                recommendation_ids=request.recommendation_ids,
            )
            if not result.get("ok"):
                err = result.get("error")
                if err == "group_not_found":
                    code = 404
                elif err == "agent_review_disabled":
                    code = 403
                elif err == "dry_run_group":
                    code = 409
                elif err == "stale_group_state":
                    code = 409
                else:
                    code = 400
                raise HTTPException(status_code=code, detail=err)
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("apply_agent_cull_candidates failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/culling/agent-review/groups/{group_id}/approve",
        summary="Operator approve agent removal recommendations",
    )
    async def approve_agent_cull_group(group_id: int, request: AgentCullRecommendationIdsRequest):
        from modules.agent_cull.actions import approve_action
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            result = approve_action(
                group_id,
                recommendation_ids=request.recommendation_ids,
                actor=request.actor,
                note=request.note,
            )
            if not result.get("ok"):
                err = result.get("error")
                if err == "group_not_found":
                    code = 404
                elif err == "agent_review_disabled":
                    code = 403
                elif err == "dry_run_group":
                    code = 409
                elif err == "stale_group_state":
                    code = 409
                else:
                    code = 400
                raise HTTPException(status_code=code, detail=err)
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("approve_agent_cull_group failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/culling/agent-review/groups/{group_id}/reject",
        summary="Operator reject agent removal recommendations",
    )
    async def reject_agent_cull_group(group_id: int, request: AgentCullRecommendationIdsRequest):
        from modules.agent_cull.actions import reject_action
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            result = reject_action(
                group_id,
                recommendation_ids=request.recommendation_ids,
                actor=request.actor,
                note=request.note,
            )
            if not result.get("ok"):
                err = result.get("error")
                if err == "group_not_found":
                    code = 404
                elif err == "agent_review_disabled":
                    code = 403
                else:
                    code = 400
                raise HTTPException(status_code=code, detail=err)
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("reject_agent_cull_group failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/culling/agent-review/groups/{group_id}/delete-approved",
        summary="Permanently delete files + DB records for operator-approved removals",
    )
    async def delete_approved_agent_cull_group(group_id: int, request: AgentCullDeleteApprovedRequest):
        """IRREVERSIBLE. Deletes the source file, thumbnails, and DB record for every
        operator-approved remove candidate in a validated group. Requires ``confirm: true``."""
        from modules.agent_cull.actions import delete_approved_action
        from modules.culling_analytics._common import require_postgres

        if not request.confirm:
            raise HTTPException(status_code=400, detail="confirmation_required")
        try:
            require_postgres()
            result = delete_approved_action(group_id, actor=request.actor)
            if not result.get("ok"):
                err = result.get("error")
                if err == "group_not_found":
                    code = 404
                elif err == "agent_review_disabled":
                    code = 403
                elif err in ("dry_run_group", "stale_group_state"):
                    code = 409
                elif err == "delete_failed":
                    code = 500
                else:
                    code = 400
                raise HTTPException(status_code=code, detail=err)
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("delete_approved_agent_cull_group failed")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/culling/agent-review/recommendations/{recommendation_id}/rollback",
        summary="Rollback recommendation candidate status",
    )
    async def rollback_agent_cull_recommendation(
        recommendation_id: int,
        request: AgentCullRecommendationIdsRequest,
    ):
        from modules.agent_cull.actions import rollback_action
        from modules.culling_analytics._common import require_postgres

        try:
            require_postgres()
            result = rollback_action(recommendation_id, actor=request.actor)
            if not result.get("ok"):
                err = result.get("error")
                if err == "recommendation_not_found":
                    code = 404
                elif err == "agent_review_disabled":
                    code = 403
                else:
                    code = 400
                raise HTTPException(status_code=code, detail=err)
            return result
        except ValueError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("rollback_agent_cull_recommendation failed")
            raise HTTPException(status_code=500, detail=str(e))


    return router
