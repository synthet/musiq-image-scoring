#!/usr/bin/env python3
"""One-shot mechanical split of modules/api/__init__.py into domain routers.

Run from repo root:
  python scripts/refactor/extract_api_routers.py

Idempotent only before first run; re-run will fail if routers already exist.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INIT = ROOT / "modules" / "api" / "__init__.py"
ROUTERS_DIR = ROOT / "modules" / "api" / "routers"

# (module_name, start_line, end_line_inclusive) — lines inside create_api_router body
SECTIONS: list[tuple[str, int, int]] = [
    ("shutdown_schema", 529, 843),
    ("scoring", 844, 1153),
    ("tagging", 1154, 1395),
    ("bird_species", 1396, 1543),
    ("general", 1544, 1676),
    ("debug", 1677, 1716),
    ("utility", 1717, 1957),
    ("tasks", 1958, 2368),
    ("geo", 2369, 2561),
    ("similar", 2562, 2812),
    ("duplicates", 2813, 2971),
    ("embedding", 2972, 3100),
    ("clustering", 3101, 3255),
    ("data_query", 3256, 3713),
    ("agent_cull", 3714, 4011),
    ("import_register", 4012, 4248),
    ("pipeline_submit", 4249, 4883),
    ("electron", 4884, 6581),
    ("maintenance", 6582, 7356),
]

ROUTER_HEADER = '''\
"""API routes: {name} (extracted from modules.api)."""

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

# Runner / dispatcher aliases (module-level state)
_scoring_runner = state._scoring_runner
_tagging_runner = state._tagging_runner
_clustering_runner = state._clustering_runner
_selection_runner = state._selection_runner
_bird_species_runner = state._bird_species_runner
_indexing_runner = state._indexing_runner
_metadata_runner = state._metadata_runner
_maintenance_runner = state._maintenance_runner
_orchestrator = state._orchestrator
_job_dispatcher = state._job_dispatcher

_control_job = deps.control_job
_control_stage = deps.control_stage
_control_step = deps.control_step
_http_for_transition_error = deps.http_for_transition_error
graceful_shutdown_processing = state.graceful_shutdown_processing


def create_{name}_router() -> APIRouter:
    router = APIRouter()
'''

STATE_BLOCK_START = 317
STATE_BLOCK_END = 510
PUBLIC_START = 196
PUBLIC_END = 315
DEPS_LINES = (539, 573)
CREATE_ROUTER_START = 512
CREATE_ROUTER_BODY_START = 528


def read_lines() -> list[str]:
    return INIT.read_text(encoding="utf-8").splitlines(keepends=True)


def write_state_and_public(lines: list[str]) -> None:
    ROUTERS_DIR.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / "modules" / "api" / "state.py"
    state_content = "".join(lines[STATE_BLOCK_START - 1 : STATE_BLOCK_END])
    state_path.write_text(
        '"""Runner globals, dispatcher, and graceful shutdown for the REST API."""\n\n'
        + state_content,
        encoding="utf-8",
    )

    public_body = ''.join(lines[PUBLIC_START : PUBLIC_END])
    public_path = ROUTERS_DIR / "public.py"
    public_path.write_text(
        textwrap.dedent(
            '''\
            """Read-only public image API routes."""

            from __future__ import annotations

            from typing import Optional

            from fastapi import APIRouter, Query

            from modules.api_helpers import (
                _image_detail_for_hash_str,
                _image_detail_for_uuid_str,
                _image_detail_payload,
                _image_neighbors_payload,
                _images_list_payload,
            )


            '''
        )
        + public_body,
        encoding="utf-8",
    )

    deps_path = ROOT / "modules" / "api" / "deps.py"
    raw_deps = "".join(lines[DEPS_LINES[0] - 1 : DEPS_LINES[1]])
    dedented = textwrap.dedent(raw_deps)
    deps_path.write_text(
        '"""Shared route helpers for job/stage/step lifecycle control."""\n\n'
        "from typing import Optional\n\n"
        "from fastapi import HTTPException\n\n"
        "from modules import db\n\n"
        + dedented.replace("def _http_for_transition_error", "def http_for_transition_error")
        .replace("def _control_job", "def control_job")
        .replace("def _control_stage", "def control_stage")
        .replace("def _control_step", "def control_step")
        .replace("_http_for_transition_error(", "http_for_transition_error("),
        encoding="utf-8",
    )


def extract_section(lines: list[str], start: int, end: int) -> str:
    chunk = lines[start - 1 : end]
    return "".join(chunk)


def strip_helper_defs(body: str) -> str:
    """Remove nested helper defs that moved to deps.py (shutdown_schema section only)."""
    if "def _http_for_transition_error" not in body:
        return body
    return re.sub(
        r"\n    def _http_for_transition_error.*?def _control_step.*?\n",
        "\n",
        body,
        count=1,
        flags=re.DOTALL,
    )


def write_routers(lines: list[str]) -> list[str]:
    ROUTERS_DIR.mkdir(parents=True, exist_ok=True)
    (ROUTERS_DIR / "__init__.py").write_text(
        '"""Domain-specific APIRouter factories."""\n', encoding="utf-8"
    )
    factory_names: list[str] = []
    for name, start, end in SECTIONS:
        body = extract_section(lines, start, end)
        if name == "shutdown_schema":
            body = strip_helper_defs(body)
        path = ROUTERS_DIR / f"{name}.py"
        path.write_text(
            ROUTER_HEADER.format(name=name) + body + "\n    return router\n",
            encoding="utf-8",
        )
        factory_names.append(f"create_{name}_router")
    return factory_names


def rebuild_init(lines: list[str], factory_names: list[str]) -> None:
    header_end = PUBLIC_START - 1
    header = "".join(lines[:header_end])

    imports_block = """
from modules.api.deps import control_job, control_stage, control_step, http_for_transition_error
from modules.api.state import (
    graceful_shutdown_processing,
    set_runners,
    stop_dispatcher,
)
from modules.api.routers.public import create_public_api_router
"""
    for name, _, _ in SECTIONS:
        imports_block += f"from modules.api.routers.{name} import create_{name}_router\n"

    composer = '''
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
'''
    for name, _, _ in SECTIONS:
        composer += f"    router.include_router(create_{name}_router())\n"
    composer += "    return router\n"

    # Re-export state helpers at package level for backward compat
    reexports = '''
# Backward-compatible re-exports (webui.py, tests import these from modules.api)
from modules.api.state import (  # noqa: E402
    _bird_species_runner,
    _clustering_runner,
    _indexing_runner,
    _job_dispatcher,
    _maintenance_runner,
    _metadata_runner,
    _orchestrator,
    _scoring_runner,
    _selection_runner,
    _tagging_runner,
    graceful_shutdown_processing,
    set_runners,
    stop_dispatcher,
)
'''

    INIT.write_text(header + imports_block + composer + reexports, encoding="utf-8")


def main() -> None:
    lines = read_lines()
    write_state_and_public(lines)
    factories = write_routers(lines)
    rebuild_init(lines, factories)
    print(f"Extracted {len(SECTIONS)} routers into {ROUTERS_DIR}")


if __name__ == "__main__":
    main()
