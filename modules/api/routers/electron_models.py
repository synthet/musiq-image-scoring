"""Pydantic request models for electron API routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: str = "folder_recursive"  # file|folder|folder_recursive|path_list
    scope_paths: list[str]
    stages: list[str] | None = None
    run_mode: Literal["process_stale_or_missing"] = "process_stale_or_missing"
    plan_dry_run: bool = Field(
        False,
        description="When true, run the stale/missing planner only and return the plan without enqueueing a job.",
    )
    description: str | None = Field(
        None,
        description="Human-readable reason/scope for this run (stored on jobs.description).",
    )
    post_run_audit: bool | None = Field(
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
    scope_paths: list[str]
    stages: list[str] | None = None
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

    root_path: str | None = Field(
        None,
        description="Optional root folder restriction for the bucket planner.",
    )
    folder_paths: list[str] | None = Field(
        None,
        description="Optional explicit folder paths to queue; used by per-row Queue actions.",
    )
    target_phases: list[str] | None = Field(
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

    root_path: str | None = Field(
        None,
        description="Optional root folder restriction; omit to drive the whole library.",
    )
    limit: int = Field(50, ge=1, le=500, description="Max folder runs queued per drive tick.")
    target_phases: list[str] | None = Field(
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
    paths: list[str]
    recursive: bool = True


class QueueReorderRequest(BaseModel):
    run_id: int
    new_position: int
