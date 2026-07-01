"""API routes: shutdown_schema (extracted from modules.api)."""

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



def create_shutdown_schema_router() -> APIRouter:
    router = APIRouter()
    @router.post(
        "/shutdown",
        summary="Graceful shutdown",
        description="Stop all runners, finalize jobs to paused state, and shutdown the dispatcher gracefully.",
    )
    async def shutdown_api():
        await asyncio.to_thread(state.graceful_shutdown_processing, "api_request")
        return {"success": True, "message": "Graceful shutdown initiated"}

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
        # This will be populated when the router is included in the main app
        # For now, return a structured description
        return {
            "api_name": "Vexlum Scoring WebUI API",
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
                                "generate_captions": {"type": "boolean", "default": False},
                                "generate_accessibility": {"type": "boolean", "default": False}
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
                                "generate_accessibility": {"type": "boolean", "default": False},
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
                    },
                    "incidents": {
                        "method": "GET",
                        "path": "/api/incidents",
                        "description": "Paginated image incidents (PostgreSQL)"
                    },
                    "incident_detail": {
                        "method": "GET",
                        "path": "/api/incidents/{incident_id}",
                        "description": "Single incident by id"
                    }
                }
            },
            "note": "For complete OpenAPI schema, visit /openapi.json or /docs"
        }
    

    return router
