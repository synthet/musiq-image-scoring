"""
Workflow Healing Service — Identify and repair incomplete processing phases.

This module provides logic to:
1. Find images where a phase status is marked 'done' but required data is missing.
   For ``culling``, this includes similarity-clustering staleness (done + pick/reject +
   clustered eligibility but no ``stack_id`` and no default-space Mobilenet embeddings),
   and **time-cohesive unstacked folders**: 2+ images, none in a stack, embeddings present,
   capture-time span ``<= (n-1) * clustering.default_time_gap`` (see
   ``get_phase_incomplete_sql('culling')``, ``culling_cohesion_folders_aggregate_sql``,
   and ``clustering.heal_folder_cohesion_candidates``). Heal scans compute that folder set
   once via a ``cohesion_folders`` CTE instead of re-aggregating per image row.
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
from modules.phases import PhaseCode, sort_phase_value_strings
from modules.phases_policy import get_phase_executor_version
from modules.job_description import augment_queue_payload_for_audit, build_run_submit_description
from modules.pipeline_tool_folder_touch import upsert_pipeline_tool_folder_touch
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
    heal_touch_tool_key = f"heal_workflow_{phase_code}"
    use_touch_rr = db._get_db_engine() == "postgres"

    # Resolve active executor version for version-aware phases.
    current_executor_version: Optional[str] = None
    if phase_code == PhaseCode.BIRD_SPECIES.value:
        current_executor_version = get_phase_executor_version(PhaseCode.BIRD_SPECIES.value)
        if not current_executor_version:
            try:
                from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

                current_executor_version = str(BIRD_SPECIES_RUNNER_VERSION)
            except Exception:
                current_executor_version = None

    # Culling heal: evaluate time-cohesion folder aggregate once (CTE) instead of
    # re-aggregating per image row; keeps semantics identical to get_phase_incomplete_sql.
    heal_sql_prefix = ""
    if phase_code == PhaseCode.CULLING.value:
        from modules.config import get_config_section

        clustering_cfg = get_config_section("clustering") or {}
        if bool(clustering_cfg.get("heal_folder_cohesion_candidates", True)):
            heal_sql_prefix = (
                "WITH cohesion_folders AS (\n"
                + db.culling_cohesion_folders_aggregate_sql().strip()
                + "\n)\n"
            )
            incomplete_sql = db.get_culling_incomplete_predicate_sql(
                "i",
                cohesion_folders_expr="SELECT folder_id FROM cohesion_folders",
            )
        else:
            incomplete_sql = db.get_culling_incomplete_predicate_sql(
                "i",
                include_folder_cohesion=False,
            )
    else:
        incomplete_sql = db.get_phase_incomplete_sql(phase_code, table_alias="i")

    # 1. Identify "False Positives" (Done but missing data)
    # -----------------------------------------------------------------------
    reset_query = f"""{heal_sql_prefix}
        SELECT i.id
        FROM images i
        JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = ?
        LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
        WHERE LOWER(TRIM(ips.status)) = 'done'
          AND ({incomplete_sql})
          AND (ips.updated_at IS NULL OR ips.updated_at < (CURRENT_TIMESTAMP - INTERVAL '1 minute'))
    """
    
    if phase_code == PhaseCode.BIRD_SPECIES.value:
        # For bird_species, "done with no species predictions" is terminal for the
        # current executor version, so these are not false positives to reset.
        false_positive_ids: List[int] = []
    else:
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

    touch_join = ""
    if use_touch_rr:
        touch_join = (
            "\n        LEFT JOIN pipeline_tool_folder_last_touch pt "
            "ON pt.folder_id = f.id AND pt.tool_key = ?\n"
        )
    sel_cols = (
        "f.id, f.path, COUNT(*) AS image_count"
        if use_touch_rr
        else "f.path, COUNT(*) AS image_count"
    )
    grp_order = (
        " GROUP BY f.id, f.path "
        "ORDER BY MAX(pt.last_touched_at) NULLS FIRST, COUNT(*) DESC, f.path ASC"
        if use_touch_rr
        else " GROUP BY f.path ORDER BY image_count DESC"
    )

    if phase_code == PhaseCode.CULLING.value:
        # Apply incomplete predicate first so the planner can narrow rows before joins;
        # status filter still excludes only running/skipped (same as before).
        folder_query = f"""{heal_sql_prefix}
        SELECT {sel_cols}
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = ?{touch_join}
        LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
        WHERE ({incomplete_sql})
          AND (ips.status IS NULL OR LOWER(TRIM(ips.status)) IN ('not_started', 'failed', 'partial', 'done'))
    """
    else:
        folder_query = f"""
        SELECT {sel_cols}
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = ?{touch_join}
        LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
        WHERE (ips.status IS NULL OR LOWER(TRIM(ips.status)) IN ('not_started', 'failed', 'partial', 'done'))
          AND ({incomplete_sql})
    """
    params = [phase_code]
    if use_touch_rr:
        params.append(heal_touch_tool_key)
    if phase_code == PhaseCode.BIRD_SPECIES.value:
        folder_query = f"""
            SELECT {sel_cols}
            FROM images i
            JOIN folders f ON f.id = i.folder_id
            JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = ?{touch_join}
            LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
            WHERE ({incomplete_sql})
              AND (
                  ips.status IS NULL
                  OR LOWER(TRIM(ips.status)) IN ('not_started', 'failed', 'partial', 'running')
                  OR (
                      LOWER(TRIM(ips.status)) IN ('done', 'skipped')
                      AND (? IS NULL OR COALESCE(TRIM(ips.executor_version), '') <> ?)
                  )
              )
        """
        params.extend([current_executor_version, current_executor_version])

    if root_path:
        rp = root_path.rstrip("/\\")
        folder_query += " AND (f.path = ? OR f.path LIKE ?)"
        params.extend([rp, rp + "/%"])

    folder_query += grp_order

    with db.connection() as conn:
        c = conn.cursor()
        c.execute(folder_query, tuple(params))
        rows = c.fetchall()
        if use_touch_rr:
            folders_needing_work = [
                {"folder_id": int(row[0]), "folder_path": row[1], "image_count": int(row[2])}
                for row in rows
            ]
        else:
            folders_needing_work = [{"folder_path": row[0], "image_count": row[1]} for row in rows]
    
    if folders_needing_work:
        logger.info(
            "Heal [%s]: Found %s folders needing work. Top candidate: %s (%s images)",
            phase_code,
            len(folders_needing_work),
            folders_needing_work[0]["folder_path"],
            folders_needing_work[0]["image_count"],
        )
    
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
    skipped_detail = []
    if not dry_run:
        for folder in to_schedule:
            try:
                result = _enqueue_heal_run(folder["folder_path"], phase_code, run_mode=run_mode)
                if result is None:
                    continue
                job_id, pos = result
                if isinstance(pos, dict):
                    # Structured skip (e.g., missing prerequisites). Surface to caller.
                    skipped_detail.append({
                        "folder_path": folder["folder_path"],
                        "skipped": True,
                        **pos,
                    })
                    continue
                if job_id is None:
                    continue  # missing on disk; logged inside
                scheduled_detail.append({
                    "folder_path": folder["folder_path"],
                    "job_id": job_id,
                    "queue_position": pos,
                })
                fid = folder.get("folder_id")
                if fid is not None:
                    upsert_pipeline_tool_folder_touch(heal_touch_tool_key, int(fid))
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
        "skipped": skipped_detail if not dry_run else [],
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

def _enqueue_heal_run(folder_path: str, phase_code: str, run_mode: str = "validate_and_repair"):
    """Enqueue a targeted pipeline run for a folder and phase.

    Returns ``(job_id, queue_position)`` on success, ``(None, None)`` when the
    folder is missing on disk, or ``(None, {"missing": {...}})`` when the
    phase's prerequisites aren't satisfied for the folder. Callers should
    interpret a dict in slot 1 as a structured "skipped, missing prereqs"
    result rather than a real queue position.
    """
    import os
    from modules.phases import assert_prereqs_for_scope
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

    # Prereq gate: skip folders whose phases-of-interest can't run yet.
    prereq_miss = assert_prereqs_for_scope(phase_values, [folder_path])
    if prereq_miss:
        logger.info(
            "Heal skip (missing prerequisites): %s phase=%s missing=%s",
            folder_path, phase_code, prereq_miss,
        )
        return None, {"missing_prerequisites": prereq_miss}

    # Canonical pipeline order (e.g. metadata before culling)
    phase_values = sort_phase_value_strings(phase_values)

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
    
    job_id, pos = db.enqueue_job_with_phases(
        folder_path,
        phase_code,
        job_type,
        payload,
        description,
        phase_codes=phase_values,
        first_phase_state="queued",
    )
    return job_id, pos
