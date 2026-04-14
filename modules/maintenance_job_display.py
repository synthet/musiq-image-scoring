"""
Human-readable `jobs.input_path` values for maintenance / Tools runs.

The Runs UI lists runs by `input_path`; using stable "Tools: …" labels avoids the
opaque GLOBAL_MAINTENANCE placeholder.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Align with frontend `frontend/src/constants/pipelineTools.ts` (Pipeline Tools tab) where applicable.
_DEFAULT_TITLE_BY_ACTION: Dict[str, str] = {
    "reconcile": "Reconcile Finished Phases",
    "heal_thumbnails": "Heal Thumbnails",
    "backfill_exif": "Backfill EXIF Dates",
    "prune_missing": "Prune Missing Files",
    "backfill_index_meta": "Backfill Index/Meta Phase Status",
}


def _format_param_suffix(payload: Dict[str, Any]) -> str:
    parts: list[str] = []
    scope = payload.get("input_path") or payload.get("scope_path")
    if scope:
        s = str(scope).strip()
        if len(s) > 120:
            s = s[:117] + "..."
        parts.append(f"scope={s}")
    if payload.get("dry_run"):
        parts.append("dry_run=True")
    if "limit" in payload and payload["limit"] is not None:
        parts.append(f"limit={payload['limit']}")
    if "repair_limit" in payload and payload["repair_limit"] is not None:
        parts.append(f"repair_limit={payload['repair_limit']}")
    if "regen_limit" in payload and payload["regen_limit"] is not None:
        parts.append(f"regen_limit={payload['regen_limit']}")
    if "repair_all" in payload:
        parts.append(f"repair_all={bool(payload['repair_all'])}")
    return f" ({', '.join(parts)})" if parts else ""


def maintenance_job_input_path(
    action: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    job_name: Optional[str] = None,
    title_override: Optional[str] = None,
) -> str:
    """
    Build the persisted job label (`jobs.input_path`) for a maintenance run.

    Args:
        action: `queue_payload.action` value.
        payload: Queue payload dict (limits, dry_run, etc.).
        job_name: Optional UI-provided name (e.g. from Pipeline Tools tab copy in pipelineTools.ts).
        title_override: Explicit title when there is no `job_name` and the default
            map does not apply (e.g. API-only endpoints).
    """
    payload = dict(payload) if payload else {}
    raw_title = (job_name or "").strip() or (title_override or "").strip()
    if not raw_title:
        raw_title = _DEFAULT_TITLE_BY_ACTION.get((action or "").strip(), action or "maintenance")
    suffix = _format_param_suffix(payload)
    return f"Tools: {raw_title}{suffix}"
