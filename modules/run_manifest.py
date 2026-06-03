"""Structured ``queue_payload.reason`` for run/job manifests at enqueue time."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

# Documented source literals for queue_payload.reason.source
REASON_SOURCE_MANUAL_SUBMIT = "manual_submit"
REASON_SOURCE_AUTO_DRIVE = "auto_drive"
REASON_SOURCE_WORKFLOW_HEALING = "workflow_healing"
REASON_SOURCE_PHASE_FOLLOWUP = "phase_followup"
REASON_SOURCE_RETRY = "retry"
REASON_SOURCE_FORCE_RUN = "force_run"
REASON_SOURCE_LEGACY_API = "legacy_api"
REASON_SOURCE_MAINTENANCE = "maintenance"
REASON_SOURCE_WEBSOCKET = "websocket"
REASON_SOURCE_MCP = "mcp"
REASON_SOURCE_PIPELINE_SUBMIT = "pipeline_submit"
REASON_SOURCE_IMPORT = "import"

_PHASE_LABELS = {
    "indexing": "discovery",
    "metadata": "inspection",
    "scoring": "scoring",
    "culling": "culling",
    "keywords": "tagging",
    "bird_species": "bird species",
}


def _basename(path: str) -> str:
    p = str(path or "").strip().replace("\\", "/")
    if not p:
        return "(scope)"
    return p.rstrip("/").split("/")[-1] or p


def _phase_phrase(phases: Sequence[str]) -> str:
    codes = [str(p).strip().lower() for p in phases if str(p).strip()]
    if not codes:
        return "pipeline work"
    if len(codes) == 1:
        return _PHASE_LABELS.get(codes[0], codes[0])
    labels = [_PHASE_LABELS.get(c, c) for c in codes]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _format_reason_counts(counts: Mapping[str, int], *, limit: int = 4) -> str:
    if not counts:
        return ""
    items = sorted(
        ((k, int(v)) for k, v in counts.items() if int(v) > 0),
        key=lambda kv: (-kv[1], kv[0]),
    )
    if not items:
        return ""
    shown = items[:limit]
    parts = [f"{k}={v}" for k, v in shown]
    if len(items) > limit:
        parts.append(f"+{len(items) - limit} more")
    return "Work: " + ", ".join(parts) + "."


def summarize_planner_reasons(
    repair_plan: Optional[Mapping[str, Any]],
    *,
    enqueued_phases: Optional[Sequence[str]] = None,
    requested_phases: Optional[Sequence[str]] = None,
) -> tuple[str, Dict[str, int]]:
    """Build summary fragment and ``planner_reason_counts`` from a repair plan."""
    plan = repair_plan or {}
    raw_counts = plan.get("issue_counts_by_reason") or {}
    planner_reason_counts: Dict[str, int] = {}
    if isinstance(raw_counts, Mapping):
        for key, val in raw_counts.items():
            try:
                n = int(val)
            except (TypeError, ValueError):
                continue
            if n > 0:
                planner_reason_counts[str(key)] = n

    work_fragment = _format_reason_counts(planner_reason_counts)
    enqueued = [str(p) for p in (enqueued_phases or []) if str(p).strip()]
    requested = [str(p) for p in (requested_phases or []) if str(p).strip()]
    dropped = [p for p in requested if p not in enqueued]
    narrow_fragment = ""
    if dropped and enqueued:
        narrow_fragment = (
            f" JIT narrowed from {len(requested)} requested stage(s) to "
            f"{_phase_phrase(enqueued)}."
        )
    elif enqueued and not requested:
        narrow_fragment = f" Stages: {_phase_phrase(enqueued)}."

    summary_bits = [b for b in (narrow_fragment.strip(), work_fragment) if b]
    return " ".join(summary_bits).strip(), planner_reason_counts


def build_run_reason(
    *,
    source: str,
    summary: str,
    criteria: Optional[Dict[str, Any]] = None,
    trigger: Optional[str] = None,
    tool_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the structured ``reason`` object stored on ``queue_payload``."""
    out: Dict[str, Any] = {
        "source": str(source or "").strip() or REASON_SOURCE_LEGACY_API,
        "summary": str(summary or "").strip() or "Run queued.",
    }
    if trigger:
        out["trigger"] = str(trigger).strip()
    if tool_id:
        out["tool_id"] = str(tool_id).strip()
    crit = dict(criteria) if criteria else {}
    if crit:
        out["criteria"] = crit
    return out


def build_manual_submit_summary(
    *,
    scope_paths: Sequence[str],
    enqueued_phases: Sequence[str],
    requested_phases: Optional[Sequence[str]] = None,
    repair_plan: Optional[Mapping[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    primary = scope_paths[0] if scope_paths else ""
    folder = _basename(primary)
    plan_fragment, planner_counts = summarize_planner_reasons(
        repair_plan,
        enqueued_phases=enqueued_phases,
        requested_phases=requested_phases,
    )
    summary = f"Manual run queued {_phase_phrase(enqueued_phases)} for {folder}."
    if plan_fragment:
        summary = f"{summary} {plan_fragment}"
    criteria: Dict[str, Any] = {
        "enqueued_phases": list(enqueued_phases),
    }
    if requested_phases:
        criteria["requested_phases"] = list(requested_phases)
    if scope_paths:
        criteria["scope_paths"] = list(scope_paths)
    if planner_counts:
        criteria["planner_reason_counts"] = planner_counts
    return summary, criteria


def build_auto_drive_summary(
    *,
    scope_paths: Sequence[str],
    enqueued_phases: Sequence[str],
    requested_phases: Optional[Sequence[str]] = None,
    auto_drive_bucket: Optional[str] = None,
    auto_drive_overall_percent: Optional[int] = None,
    auto_drive_plan_key: Optional[str] = None,
    repair_plan: Optional[Mapping[str, Any]] = None,
    run_mode: Optional[str] = None,
    folder_created_at: Optional[str] = None,
    is_newly_imported: Optional[bool] = None,
) -> tuple[str, Dict[str, Any]]:
    primary = scope_paths[0] if scope_paths else ""
    folder = _basename(primary)
    bucket = str(auto_drive_bucket or "").strip()
    bucket_fragment = f" (bucket: {bucket})" if bucket else ""
    plan_fragment, planner_counts = summarize_planner_reasons(
        repair_plan,
        enqueued_phases=enqueued_phases,
        requested_phases=requested_phases,
    )
    summary = (
        f"Auto-drive queued {_phase_phrase(enqueued_phases)} for leaf folder {folder}"
        f"{bucket_fragment}."
    )
    if plan_fragment:
        summary = f"{summary} {plan_fragment}"
    criteria: Dict[str, Any] = {
        "enqueued_phases": list(enqueued_phases),
        "include_stale_executor": False,
    }
    if requested_phases:
        criteria["requested_phases"] = list(requested_phases)
    if scope_paths:
        criteria["scope_paths"] = list(scope_paths)
    if run_mode:
        criteria["run_mode"] = run_mode
    if bucket:
        criteria["auto_drive_bucket"] = bucket
    if auto_drive_overall_percent is not None:
        try:
            criteria["auto_drive_overall_percent"] = int(auto_drive_overall_percent)
        except (TypeError, ValueError):
            pass
    if auto_drive_plan_key:
        criteria["auto_drive_plan_key"] = str(auto_drive_plan_key)
    if folder_created_at:
        criteria["folder_created_at"] = str(folder_created_at)
    if is_newly_imported is not None:
        criteria["is_newly_imported"] = bool(is_newly_imported)
    if planner_counts:
        criteria["planner_reason_counts"] = planner_counts
    return summary, criteria


def build_legacy_api_summary(
    *,
    job_kind: str,
    input_path: Optional[str] = None,
    extra: Optional[str] = None,
) -> str:
    base = _basename(str(input_path or "selector"))
    kind = str(job_kind or "job").replace("_", " ")
    msg = f"Legacy API queued {kind} for {base}."
    if extra:
        msg = f"{msg} {extra.strip()}"
    return msg


def build_maintenance_summary(*, action: str, input_path: Optional[str] = None) -> str:
    base = _basename(str(input_path or "library"))
    return f"Maintenance job ({action}) queued for {base}."


def build_retry_summary(
    *,
    source: str,
    original_run_id: int,
    job_type: str,
    input_path: Optional[str] = None,
) -> str:
    base = _basename(str(input_path or ""))
    if source == REASON_SOURCE_FORCE_RUN:
        return f"Force re-queue of run #{original_run_id} ({job_type}) for {base}."
    return f"Retry of run #{original_run_id} ({job_type}) for {base}."


def attach_run_reason(
    payload: Optional[Dict[str, Any]],
    *,
    source: str,
    summary: str,
    criteria: Optional[Dict[str, Any]] = None,
    trigger: Optional[str] = None,
    tool_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Set ``payload['reason']`` (always overwrites). Returns the payload dict."""
    out = dict(payload) if payload else {}
    out["reason"] = build_run_reason(
        source=source,
        summary=summary,
        criteria=criteria,
        trigger=trigger or out.get("trigger"),
        tool_id=tool_id or out.get("tool_id"),
    )
    return out
