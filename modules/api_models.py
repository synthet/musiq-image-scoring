"""Pydantic request/response models for the REST API (extracted from modules.api)."""

from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
    
    This endpoint initiates quality assessment of images using a configurable ensemble of
    AI models selected via the scoring.models registry (LIQE, MUSIQ variants such as SPAQ/AVA,
    and TOPIQ; QPT V2 runs in shadow) to generate technical, aesthetic, and general quality
    scores. See GET /api/models for the live set and per-model shadow status.
    
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
        generate_accessibility: If True, generate IPTC accessibility alt/extended text via CLIP.
    
    Example:
        {
            "input_path": "D:/Photos/2024",
            "custom_keywords": ["landscape", "sunset", "nature"],
            "overwrite": false,
            "generate_captions": true,
            "generate_accessibility": true
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
    generate_accessibility: bool = Field(
        False,
        description="If True, generate IPTC Alt Text and Extended Description via CLIP prompt ranking.",
        example=False
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "input_path": "D:/Photos/2024",
            "custom_keywords": ["landscape", "sunset"],
            "overwrite": False,
            "generate_captions": True,
            "generate_accessibility": False
        }
    })


class BirdSpeciesStartRequest(SelectorRequest):
    """Request model for starting a bird species classification job.

    Only images that already have the 'birds' keyword are processed — all others are
    automatically skipped. The single highest-scoring species (BioCLIP 2 argmax) is
    stored as a 'species:Common Name' keyword (zero-shot, MIT license). Pass top_k > 1
    to store multiple candidates instead.

    Example:
        {
            "input_path": "D:/Photos/2024",
            "threshold": 0.1,
            "top_k": 1,
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
        1,
        description="Maximum number of species to store per image. Default 1 keeps "
                    "only the highest-scoring species (BioCLIP argmax).",
        example=1
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
            "top_k": 1,
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
        generate_accessibility: If True, generate IPTC accessibility metadata via CLIP.
    
    Example:
        {
            "file_path": "D:/Photos/2024/image.jpg",
            "custom_keywords": ["landscape"],
            "generate_captions": true,
            "generate_accessibility": false
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
    generate_accessibility: bool = Field(
        False,
        description="If True, generate IPTC Alt Text and Extended Description via CLIP.",
        example=False
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "file_path": "D:/Photos/2024/image.jpg",
            "custom_keywords": ["landscape"],
            "generate_captions": True,
            "generate_accessibility": False
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


class ConfigResponse(BaseModel):
    """Response model for public configuration flags.
    
    Exposes a safe subset of configuration values to the frontend.
    """
    enable_culling: bool = Field(
        False, 
        description="True if the experimental culling feature should be visible and accessible."
    )
    embedding_map_enabled: bool = Field(
        False,
        description="True if the embedding map feature is enabled."
    )
    db_explorer_enabled: bool = Field(
        True,
        description="True if the React DB Explorer (/ui/db) should be visible.",
    )
    scoring_models: Dict[str, Dict[str, bool]] = Field(
        default_factory=dict,
        description="scoring.models membership map: {model_name: {enabled, shadow}}. "
                    "Lets the UI show known models (and which are active vs. disabled).",
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "enable_culling": False,
            "embedding_map_enabled": True,
            "scoring_models": {
                "topiq": {"enabled": False, "shadow": False},
                "cursor": {"enabled": False, "shadow": False},
                "claude": {"enabled": False, "shadow": False}
            }
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
    generate_accessibility: bool = Field(
        False,
        description="Generate IPTC accessibility alt/extended description during tagging.",
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
    """Request model for backfilling Index/Meta phase status on a folder."""
    input_path: str = Field(..., description="Folder path to backfill INDEXING/METADATA statuses for.")




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


class MaintenanceStartRequest(BaseModel):
    """Request model for starting a background maintenance run."""
    action: str = Field(..., description="Maintenance action to perform (heal_thumbnails, backfill_exif, prune_missing, reconcile, backfill_index_meta).")
    input_path: Optional[str] = Field(None, description="Optional folder path to narrow the scope.")
    limit: Optional[int] = Field(None, description="Maximum items to process in this run.")
    dry_run: bool = Field(False, description="Whether to simulate changes.")
    job_name: Optional[str] = Field(
        None,
        description="Optional UI display name for this run (e.g. Tools tab label); stored as jobs.input_path.",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable reason for this run (jobs.description). Server fills a default if omitted.",
    )
    trigger: str = Field(
        "api",
        description="Audit: who queued the job (e.g. runs_tools_tab, api). Stored in queue_payload.trigger.",
    )
    tool_id: Optional[str] = Field(
        None,
        description="Optional stable id for the UI control (queue_payload.tool_id).",
    )
    ui_selected_scope_path: Optional[str] = Field(
        None,
        description="Scope navigator selection when relevant (queue_payload.ui_selected_scope_path).",
    )




class HealPhaseRequest(BaseModel):
    """Request parameters for workflow healing per phase."""

    root_path: Optional[str] = Field(
        None,
        description=(
            "Scope restriction. Accepts a folder path, a file path (parent folder is used), "
            "or a /ui/images/<id> URL (resolved to the image's folder)."
        ),
    )
    dry_run: bool = False
    budget: int = Field(
        10,
        ge=1,
        le=100,
        description="Schedules at most max(0, budget - active_running_or_queued_jobs) folder runs.",
    )


class GeocodeReverseRequest(BaseModel):
    """Reverse geocoding: GPS in EXIF → human-readable location (Nominatim by default)."""

    force: bool = Field(False, description="Re-resolve even if location_resolved is already set.")
    dry_run: bool = Field(False, description="Return provider result without writing to DB or files.")
    write_embedded: bool = Field(
        False,
        description="If true, also write City/State/Country/GPS to embedded metadata via exiftool.",
    )
    write_sidecar: bool = Field(
        False,
        description="If true and a .xmp sidecar exists, also write the same tags to it.",
    )


class GeocodeForwardRequest(BaseModel):
    """Forward geocoding: address string → coordinates; updates image_exif and optional file tags."""

    query: str = Field(..., min_length=1, description="Address or place name.")
    dry_run: bool = Field(False, description="Return coordinates without writing to DB or files.")
    write_embedded: bool = Field(
        True,
        description="If true, write GPS and location text to embedded metadata via exiftool.",
    )
    write_sidecar: bool = Field(
        True,
        description="If true and a .xmp sidecar exists, write the same tags to it.",
    )


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


class CullingAnalyticsResponse(BaseModel):
    """Culling and stack analytics payload (library, folder, session, or stack scope)."""

    scope: str = Field(..., description="library | session | stack")
    generated_at: Optional[str] = None
    folder_id: Optional[int] = None
    folder_path: Optional[str] = None
    session_id: Optional[int] = None
    stack_id: Optional[int] = None
    error: Optional[str] = None
    stack_size: Optional[Dict[str, Any]] = None
    flags: Optional[Dict[str, Any]] = None
    scores: Optional[Dict[str, Any]] = None
    exposure: Optional[Dict[str, Any]] = None
    labels: Optional[Dict[str, Any]] = None
    gps: Optional[Dict[str, Any]] = None
    keywords: Optional[Dict[str, Any]] = None
    embeddings: Optional[Dict[str, Any]] = None
    composite: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None

    model_config = ConfigDict(extra="allow")


class ImageUpdateRequest(BaseModel):
    """Request body for PATCH /api/images/{image_id}."""

    rating: Optional[int] = Field(None, ge=0, le=5, description="Star rating 0–5 (0 = unrated).")
    label: Optional[str] = Field(None, description="Color label: Red, Yellow, Green, Blue, Purple, or empty string to clear.")
    title: Optional[str] = Field(None, description="Image title.")
    description: Optional[str] = Field(None, description="Image description.")
    keywords: Optional[str] = Field(None, description="Comma-separated keywords string.")
    pick_status: Optional[int] = Field(
        None,
        ge=-1,
        le=1,
        description=(
            "Culling pick: 1 = picked, -1 = rejected, 0 = unflagged. When provided "
            "without explicit rating/label, the server mirrors the pick to "
            "rating + label so legacy gallery filters keep working."
        ),
    )
    write_sidecar: bool = Field(True, description="If true, also write metadata to XMP sidecar / embedded tags via tagging runner.")


class AgentCullDiscoverRequest(BaseModel):
    folder_path: Optional[str] = None
    folder_id: Optional[int] = None
    stack_id: Optional[int] = None
    sub_stack_id: Optional[int] = None
    limit: int = Field(50, ge=1, le=200)


class AgentCullRunRequest(BaseModel):
    stack_id: int
    sub_stack_id: Optional[int] = None
    dry_run: Optional[bool] = None
    force: bool = False
    agent: Optional[str] = None


class AgentCullRecommendationIdsRequest(BaseModel):
    recommendation_ids: Optional[List[int]] = None
    actor: str = "operator"
    note: Optional[str] = None


class AgentCullDeleteApprovedRequest(BaseModel):
    actor: str = "operator"
    #: Server-side safety: callers must pass true to perform the irreversible delete.
    confirm: bool = False


class AgentCullPickStatusRequest(BaseModel):
    pick_status: int = Field(..., ge=-1, le=1)


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


class DeleteFolderCacheRequest(BaseModel):
    """Remove a folder subtree from the folders cache when no images reference it."""

    path: str = Field(..., description="Absolute folder path matching a cached folders.path.")
