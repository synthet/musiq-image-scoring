"""
Schedule /api/runs/submit jobs for leaf folders with data-quality issues.

Mirrors ``scripts/maintenance/schedule_folder_quality_fix_runs.py`` for use from the Web UI.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

from modules import db
from modules.maintenance_job_display import maintenance_job_input_path
from modules.phases import PhaseCode, normalize_phase_codes, sort_phase_value_strings
from modules.run_modes import resolve_run_mode_flags

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_folder_quality_report():
    """Load ``scripts/maintenance/folder_data_quality_report.py`` as a module."""
    path = _PROJECT_ROOT / "scripts" / "maintenance" / "folder_data_quality_report.py"
    spec = importlib.util.spec_from_file_location("folder_data_quality_report", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load folder quality report from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PHASE_ORDER = ["indexing", "metadata", "scoring", "culling", "keywords", "bird_species"]


def stages_for_quality_row(row: dict[str, Any]) -> list[str]:
    """Ordered pipeline stages needed to address non-zero issue columns."""
    si = int(row.get("scoring_incomplete") or 0)
    tm = int(row.get("thumb_missing") or 0)
    br = int(row.get("bird_missing_species") or 0)
    st = int(row.get("stack_issue") or 0)

    need: set[str] = set()
    if si > 0 or tm > 0 or st > 0:
        need.update(["indexing", "metadata", "scoring"])
    if st > 0:
        need.add("culling")
    if br > 0:
        need.update(["keywords", "bird_species"])

    return [p for p in PHASE_ORDER if p in need]


def _enqueue_pipeline_run(
    scope_paths: list[str],
    stages: list[str],
    *,
    run_mode: str = "validate_and_repair",
) -> tuple[int, int]:
    """
    Enqueue one pipeline run (same contract as POST /api/runs/submit).
    Returns (job_id, queue_position).
    """
    if not scope_paths or not str(scope_paths[0]).strip():
        raise ValueError("scope_paths required")
    primary_path = str(scope_paths[0]).strip()

    raw_stages = list(stages)
    want_bird_species = "bird_species" in raw_stages
    pipeline_stages = [s for s in raw_stages if s != "bird_species"]

    phases = normalize_phase_codes(pipeline_stages) if pipeline_stages else None
    phase_values = [p.value for p in phases] if phases else None

    phase_code = "scoring"
    job_type = "scoring"
    if phases:
        first_p = phases[0]
        if first_p == PhaseCode.INDEXING:
            phase_code = "indexing"
            job_type = "indexing"
        elif first_p == PhaseCode.METADATA:
            phase_code = "metadata"
            job_type = "metadata"
        elif first_p == PhaseCode.SCORING:
            phase_code = "scoring"
            job_type = "scoring"
        elif first_p == PhaseCode.KEYWORDS:
            phase_code = "keywords"
            job_type = "tagging"
        elif first_p == PhaseCode.CULLING:
            phase_code = "culling"
            job_type = "selection"
    elif want_bird_species:
        phase_code = "bird_species"
        job_type = "bird_species"
        phase_values = ["bird_species"]

    if not phase_values:
        if job_type == "tagging":
            phase_values = [PhaseCode.KEYWORDS.value]
        elif job_type == "selection":
            phase_values = [PhaseCode.CULLING.value, PhaseCode.METADATA.value]
        else:
            phase_values = [
                PhaseCode.INDEXING.value,
                PhaseCode.METADATA.value,
                PhaseCode.SCORING.value,
            ]

    if want_bird_species and phase_values and "bird_species" not in phase_values:
        phase_values = list(phase_values) + ["bird_species"]
    if phase_values:
        phase_values = sort_phase_value_strings(phase_values)

    mode_flags = resolve_run_mode_flags(run_mode)

    payload = {
        "scope_type": "folder_recursive",
        "scope_paths": scope_paths,
        "input_path": primary_path,
        "run_mode": run_mode,
        "skip_done": mode_flags["skip_done"],
        "skip_existing": mode_flags["skip_existing"],
        "force_rerun": mode_flags["force_rerun"],
        "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
        "overwrite": mode_flags["overwrite"],
        "force_rescan": mode_flags["force_rescan"],
        "phases": phase_values,
        "target_phases": phase_values,
    }

    job_id, position = db.enqueue_job(
        primary_path,
        phase_code,
        job_type,
        payload,
    )
    db.create_job_phases(job_id, phase_values, "queued")
    return job_id, position


def _maybe_queue_global_thumbnail_heal() -> int | None:
    """Enqueue global heal_thumbnails maintenance job; returns new job id or None."""
    queue_payload = {
        "action": "heal_thumbnails",
        "limit": 500,
    }
    job_id, _ = db.enqueue_job(
        maintenance_job_input_path("heal_thumbnails", queue_payload),
        None,
        job_type="maintenance",
        queue_payload=queue_payload,
    )
    return job_id


def schedule_folder_quality_runs(
    *,
    root_path: str | None = None,
    stack_after_culling_only: bool = False,
    budget: int = 10,
    run_mode: str = "validate_and_repair",
    dry_run: bool = False,
    heal_thumbnails_global: bool = False,
) -> dict[str, Any]:
    """
    For up to ``max(0, budget - len(active_jobs))`` folders (issue-sorted), enqueue one run each.

    ``active_jobs`` = jobs with status running or queued and non-empty input_path (same as CLI).
    """
    fqr = _load_folder_quality_report()
    conn = db.get_connector()

    active_jobs = fqr._active_jobs_snapshot(conn)
    active_count = len(active_jobs)
    capacity = max(0, int(budget) - active_count)

    all_rows = fqr.fetch_folder_quality_rows(
        conn,
        root_path=root_path,
        stack_after_culling_only=stack_after_culling_only,
        exclude_active_runs=True,
        include_clean_folders=False,
    )
    total_folders = len(all_rows)
    to_schedule = all_rows[:capacity]

    scheduled_detail: list[dict[str, Any]] = []
    errors: list[str] = []
    thumb_heal_run_id: int | None = None

    any_thumb = bool(
        heal_thumbnails_global
        and any(int(r.get("thumb_missing") or 0) > 0 for r in to_schedule)
    )
    if any_thumb and not dry_run:
        thumb_heal_run_id = _maybe_queue_global_thumbnail_heal()

    for row in to_schedule:
        path = str(row.get("folder_path") or "").strip()
        if not path:
            continue
        st_list = stages_for_quality_row(row)
        if not st_list:
            errors.append(f"No stages derived for {path}")
            continue
        if dry_run:
            scheduled_detail.append(
                {
                    "folder_path": path,
                    "stages": st_list,
                    "run_id": None,
                    "queue_position": None,
                }
            )
            continue
        try:
            job_id, pos = _enqueue_pipeline_run([path], st_list, run_mode=run_mode)
            scheduled_detail.append(
                {
                    "folder_path": path,
                    "stages": st_list,
                    "run_id": job_id,
                    "queue_position": pos,
                }
            )
        except Exception as e:
            logger.exception("schedule_folder_quality_runs: failed for %s", path)
            errors.append(f"{path}: {e}")

    scheduled_n = len(scheduled_detail)
    remaining = max(0, total_folders - scheduled_n)

    return {
        "budget": int(budget),
        "active_jobs": active_count,
        "capacity_slots": capacity,
        "folders_total_needing_work": total_folders,
        "scheduled_this_round": scheduled_n,
        "folders_remaining_after": remaining,
        "scheduled": scheduled_detail,
        "errors": errors,
        "global_thumbnail_heal_run_id": thumb_heal_run_id,
        "dry_run": dry_run,
    }
