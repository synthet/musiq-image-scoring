"""
Workflow Healing Service — Identify and repair incomplete processing phases.

This module provides logic to:
1. Find images where a phase status is marked 'done' but required data is missing.
2. Reset those statuses (healing false-positives).
3. Identify folders with any images needing the specified phase.
4. Spawn targeted pipeline runs for those folders.
"""

from __future__ import annotations
import logging
import os
import re
from typing import Any, List, Dict, Optional
from urllib.parse import urlparse

from modules import db
from modules.phases import PhaseCode
from modules.job_description import augment_queue_payload_for_audit, build_run_submit_description
from modules.run_modes import resolve_run_mode_flags

logger = logging.getLogger(__name__)

_UI_IMAGE_ID_RE = re.compile(r"/(?:ui/)?images/(\d+)(?:/|$)")


def _resolve_image_id_to_path(image_id: int) -> Optional[str]:
    with db.connection() as conn:
        c = conn.cursor()
        c.execute("SELECT file_path FROM images WHERE id = ?", (image_id,))
        row = c.fetchone()
    return row[0] if row and row[0] else None


def normalize_heal_root(root: Optional[str]) -> Optional[str]:
    """Accept folder path, file path, or /ui/images/<id> URL; return folder path.

    Why: heal is folder-scoped, but callers often hand over a file path or a UI
    link. Coerce to the parent folder so the SQL filter still hits.
    """
    if not root:
        return None
    s = str(root).strip()
    if not s:
        return None

    # UI URL form: http://host/ui/images/<id> or path-only /ui/images/<id>
    url_candidate = s if s.startswith(("http://", "https://")) else None
    path_part = urlparse(url_candidate).path if url_candidate else s
    m = _UI_IMAGE_ID_RE.search(path_part)
    if m:
        try:
            resolved = _resolve_image_id_to_path(int(m.group(1)))
        except Exception:
            logger.exception("heal: failed resolving image id from %s", s)
            resolved = None
        if not resolved:
            logger.info("heal: could not resolve image id in %s", s)
            return None
        s = resolved

    # File path → parent folder; folder path → itself
    if os.path.isfile(s):
        s = os.path.dirname(s)
    return s.rstrip("/\\") or None

def heal_phase_data(
    phase_code: str,
    *,
    root_path: Optional[str] = None,
    dry_run: bool = False,
    budget: int = 10,
    run_mode: str = "validate_and_repair",
) -> Dict[str, Any]:
    """
    Perform a healing pass for a specific pipeline phase.
    
    Args:
        phase_code: The phase to heal (e.g., 'scoring', 'keywords').
        root_path: Optional root path to restrict the scope.
        dry_run: If True, only report issues without making changes.
        budget: Maximum number of folders to schedule runs for.
        run_mode: The run mode for spawned jobs (default: validate_and_repair).
        
    Returns:
        Summary of identified issues, resets, and scheduled runs.
    """
    phase_code = phase_code.lower().strip()
    root_path = normalize_heal_root(root_path)

    # 1. Identify "False Positives" (Done but missing data)
    # -----------------------------------------------------------------------
    incomplete_sql = db.get_phase_incomplete_sql(phase_code, table_alias="i")
    
    reset_query = f"""
        SELECT i.id
        FROM images i
        JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = ?
        LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
        WHERE LOWER(TRIM(ips.status)) = 'done'
          AND ({incomplete_sql})
          AND (ips.updated_at IS NULL OR ips.updated_at < (CURRENT_TIMESTAMP - INTERVAL '1 minute'))
    """
    
    with db.connection() as conn:
        c = conn.cursor()
        c.execute(reset_query, (phase_code,))
        false_positive_ids = [row[0] for row in c.fetchall()]
    
    resets_performed = 0
    if not dry_run and false_positive_ids:
        resets_performed = db.reset_image_phase_status(false_positive_ids, phase_code)
        logger.info("Heal [%s]: Reset status for %s images", phase_code, resets_performed)

    # 2. Identify Folders needing work for this phase
    # -----------------------------------------------------------------------
    # Folders where at least one image is NOT 'done' (or was just reset)
    # but has the missing data criteria.
    # Note: after reset, images have status 'not_started'.
    
    folder_query = f"""
        SELECT f.path, COUNT(*) as image_count
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = ?
        LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
        WHERE (ips.status IS NULL OR LOWER(TRIM(ips.status)) IN ('not_started', 'failed', 'partial', 'done'))
          AND ({incomplete_sql})
    """
    params: List[Any] = [phase_code]
    
    if root_path:
        rp = root_path.rstrip("/\\")
        folder_query += " AND (f.path = ? OR f.path LIKE ?)"
        params.extend([rp, rp + "/%"])
        
    folder_query += " GROUP BY f.path ORDER BY image_count DESC"
    
    with db.connection() as conn:
        c = conn.cursor()
        c.execute(folder_query, tuple(params))
        folders_needing_work = [{"folder_path": row[0], "image_count": row[1]} for row in c.fetchall()]
    
    # Filter out folders already being processed (active/queued runs)
    active_jobs = _get_active_jobs_snapshot()
    active_paths = {str(j.get("input_path")).strip().lower() for j in active_jobs if j.get("input_path")}
    
    def is_under_active_run(folder_path: str) -> bool:
        fp = folder_path.strip().lower()
        for active in active_paths:
            if fp == active or fp.startswith(active + "/") or fp.startswith(active + "\\"):
                return True
        return False
        
    eligible_folders = [f for f in folders_needing_work if not is_under_active_run(f["folder_path"])]
    
    # 3. Spawn Runs (Up to budget)
    # -----------------------------------------------------------------------
    capacity = max(0, budget - len(active_jobs))
    to_schedule = eligible_folders[:capacity]
    
    scheduled_detail = []
    if not dry_run:
        for folder in to_schedule:
            try:
                result = _enqueue_heal_run(folder["folder_path"], phase_code, run_mode=run_mode)
                if result is None or result[0] is None:
                    continue  # missing on disk; logged inside
                job_id, pos = result
                scheduled_detail.append({
                    "folder_path": folder["folder_path"],
                    "job_id": job_id,
                    "queue_position": pos
                })
            except Exception:
                logger.exception("Heal [%s]: Failed to schedule for %s", phase_code, folder["folder_path"])
    
    return {
        "phase_code": phase_code,
        "dry_run": dry_run,
        "false_positives_found": len(false_positive_ids),
        "resets_performed": resets_performed,
        "folders_needing_work": len(folders_needing_work),
        "eligible_folders": len(eligible_folders),
        "capacity_slots": capacity,
        "scheduled": scheduled_detail if not dry_run else to_schedule,
        "budget": budget
    }

def _get_active_jobs_snapshot() -> List[Dict[str, Any]]:
    """Retrieve currently active or queued jobs with input paths."""
    with db.connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, input_path, status FROM jobs "
            "WHERE LOWER(TRIM(status)) IN ('running', 'queued') "
            "AND input_path IS NOT NULL AND input_path <> ''"
        )
        rows = c.fetchall()
    return [{"id": r[0], "input_path": r[1], "status": r[2]} for r in rows]

def _enqueue_heal_run(folder_path: str, phase_code: str, run_mode: str = "validate_and_repair") -> tuple[int, int]:
    """Enqueue a targeted pipeline run for a folder and phase."""
    import os
    if not os.path.isdir(folder_path):
        logger.info("Heal skip (missing on disk): %s", folder_path)
        return None, None

    # Mapping phase codes to job types (same as schedule_folder_quality_runs)
    job_type_map = {
        "indexing": "indexing",
        "metadata": "metadata",
        "scoring": "scoring",
        "keywords": "tagging",
        "culling": "selection",
        "bird_species": "bird_species"
    }
    
    job_type = job_type_map.get(phase_code, "scoring")
    
    # Prepare phases list
    if phase_code == "bird_species":
        phase_values = ["bird_species"]
    elif phase_code == "keywords":
        phase_values = [PhaseCode.KEYWORDS.value]
    elif phase_code == "culling":
        # Usually metadata is needed for XMP writing if it hasn't run
        phase_values = [PhaseCode.CULLING.value, PhaseCode.METADATA.value]
    else:
        # Default for index/meta/score
        phase_values = [PhaseCode(phase_code).value]

    mode_flags = resolve_run_mode_flags(run_mode)
    
    payload = {
        "scope_type": "folder_recursive",
        "scope_paths": [folder_path],
        "input_path": folder_path,
        "run_mode": run_mode,
        "skip_done": mode_flags["skip_done"],
        "skip_existing": mode_flags["skip_existing"],
        "force_rerun": mode_flags["force_rerun"],
        "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
        "overwrite": mode_flags["overwrite"],
        "phases": phase_values,
        "target_phases": phase_values,
    }
    
    payload = augment_queue_payload_for_audit(payload, trigger="api", tool_id=f"heal_workflow_{phase_code}")
    
    description = build_run_submit_description(
        scope_type="folder_recursive",
        scope_paths=[folder_path],
        run_mode=run_mode,
        validation_repair_mode=(run_mode == "validate_and_repair"),
        phase_values=phase_values,
        client_description=f"Automated workflow healing for phase: {phase_code}",
    )
    
    job_id, pos = db.enqueue_job(
        folder_path,
        phase_code,
        job_type,
        payload,
        description
    )
    
    db.create_job_phases(job_id, phase_values, "queued")
    return job_id, pos
