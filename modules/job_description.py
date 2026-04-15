"""Human-readable ``jobs.description`` and structured ``queue_payload`` audit fields."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def augment_queue_payload_for_audit(
    payload: Optional[Dict[str, Any]],
    *,
    trigger: str = "api",
    tool_id: Optional[str] = None,
    ui_selected_scope_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge durable audit keys into queue_payload (does not remove existing keys)."""
    out = dict(payload) if payload else {}
    out.setdefault("trigger", trigger)
    if tool_id:
        out.setdefault("tool_id", tool_id)
    if ui_selected_scope_path and str(ui_selected_scope_path).strip():
        out.setdefault("ui_selected_scope_path", str(ui_selected_scope_path).strip())
    return out


def build_run_submit_description(
    *,
    scope_type: str,
    scope_paths: List[str],
    run_mode: str,
    validation_repair_mode: bool,
    phase_values: Optional[List[str]] = None,
    client_description: Optional[str] = None,
) -> str:
    """Default jobs.description for POST /runs/submit when the client omits one."""
    if client_description and str(client_description).strip():
        return str(client_description).strip()
    primary = scope_paths[0] if scope_paths else ""
    parts = [
        f"Pipeline run (run_mode={run_mode}, scope_type={scope_type}).",
        f"Primary path: {primary}.",
    ]
    if len(scope_paths) > 1:
        parts.append(f"Multiple roots: {len(scope_paths)} path(s).")
    if validation_repair_mode:
        parts.append("Validation-repair: scan for stage-specific issues and apply minimal repairs.")
    if phase_values:
        parts.append(f"Stages: {', '.join(phase_values)}.")
    return " ".join(parts)


def build_scoring_job_description(
    input_path: Optional[str],
    *,
    resolved_count: Optional[int] = None,
) -> str:
    """jobs.description for legacy POST /scoring/start style enqueue."""
    base = (input_path or "selector").strip() or "selector"
    if resolved_count is not None:
        return f"Scoring job queued from API. Input: {base}. Resolved images: {resolved_count}."
    return f"Scoring job queued from API. Input: {base}."


def build_clustering_job_description(
    input_path: Optional[str],
    *,
    force_rescan: bool = False,
    resolved_count: Optional[int] = None,
) -> str:
    base = (input_path or "selector").strip() or "selector"
    extra = "force_rescan=True. " if force_rescan else ""
    rc = f" Resolved images: {resolved_count}." if resolved_count is not None else ""
    return f"Clustering job from API. {extra}Input: {base}.{rc}"


def build_tagging_job_description(input_path: Optional[str]) -> str:
    base = (input_path or "selector").strip() or "selector"
    return f"Tagging job queued from API. Input: {base}."


def build_bird_species_job_description(input_path: Optional[str]) -> str:
    base = (input_path or "selector").strip() or "selector"
    return f"Bird species job queued from API. Input: {base}."


def build_workflow_run_description(
    first_op: str,
    workspace_target: Optional[str],
    stage_codes: List[str],
) -> str:
    wt = (workspace_target or "").strip() or "(default)"
    stages = ", ".join(stage_codes) if stage_codes else first_op
    return f"Workflow run from API: first stage {first_op!r}. Workspace: {wt}. Plan: {stages}."
