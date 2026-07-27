"""API routes: maintenance (extracted from modules.api)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from modules import db
from modules.api_models import (
    ApiResponse,
    DiagnosticsResponse,
    HealPhaseRequest,
    MaintenanceStartRequest,
)
from modules.job_description import (
    augment_queue_payload_for_audit,
)
from modules.maintenance_job_display import (
    build_default_maintenance_description,
    maintenance_job_input_path,
)
from modules.run_manifest import (
    REASON_SOURCE_MAINTENANCE,
    attach_run_reason,
    build_maintenance_summary,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_maintenance_router() -> APIRouter:
    router = APIRouter()
    @router.post(
        "/maintenance/heal/{phase_code}",
        response_model=ApiResponse,
        summary="Heal workflow phase: identify false completions, reset, and queue repair runs",
        description=(
            "1. Identifies images marked 'done' for the phase but missing underlying data. "
            "2. Resets those statuses to 'not_started' (healing false-positives). "
            "3. Identifies folders with images needing the phase. "
            "4. Spawns targeted pipeline runs for those folders (capacity-aware)."
        ),
        tags=["General API"],
    )
    async def maintenance_heal_phase(phase_code: str, request: HealPhaseRequest):
        from modules import workflow_healing
        from modules.ui.security import _check_rate_limit

        _check_rate_limit(f"maintenance_heal_phase_{phase_code}")
        try:
            data = await asyncio.to_thread(
                workflow_healing.heal_phase_data,
                phase_code=phase_code,
                root_path=request.root_path,
                dry_run=request.dry_run,
                budget=request.budget,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        n_scheduled = data.get("scheduled", [])
        n = len(n_scheduled) if isinstance(n_scheduled, list) else int(n_scheduled or 0)
        fnw = int(data.get("folders_needing_work") or 0)
        eligible = int(data.get("eligible_folders") or 0)
        msg = (
            f"Scheduled {n} folder run(s). "
            f"This scan found {fnw} folder(s) with incomplete images; "
            f"{eligible} were eligible to schedule (capacity and in-flight runs)."
            if not request.dry_run
            else (
                f"Dry run: would schedule {n} folder run(s). "
                f"Would detect {fnw} folder(s) with incomplete images; "
                f"{eligible} eligible under capacity / in-flight rules."
            )
        )
        return ApiResponse(success=True, message=msg, data=data)

    @router.post(
        "/maintenance/recalculate-status-from-data",
        response_model=ApiResponse,
        summary="Recalculate derivable per-image status and folder aggregates",
        description=(
            "Repairs derivable per-image phase status drift (index/meta, keywords, culling), "
            "then rebuilds folder phase aggregates and legacy flags. Supports all-db or selected-folder scope."
        ),
        tags=["General API"],
    )
    async def maintenance_recalculate_status_from_data(
        scope: str = Query("selected_folder", pattern="^(all|selected_folder)$"),
        scope_path: str | None = Query(
            None,
            description="Required when scope=selected_folder. Uses folder + descendants.",
        ),
    ):
        from modules import db, utils
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("maintenance_recalculate_status_from_data")
        summary: dict[str, Any] = {}

        selected_scope = (scope or "selected_folder").strip().lower()
        if selected_scope == "selected_folder" and not (scope_path and scope_path.strip()):
            raise HTTPException(status_code=400, detail="scope_path is required when scope=selected_folder")

        target_scope_path = None
        target_folder_paths: list[str] = []
        if selected_scope == "selected_folder":
            wsl_path = (
                utils.convert_path_to_wsl(scope_path.strip())
                if hasattr(utils, "convert_path_to_wsl")
                else scope_path.strip()
            )
            target_scope_path = wsl_path or scope_path.strip()
            target_folder_paths = db.list_folder_paths_under_scope(target_scope_path)
            if not target_folder_paths:
                row = db.get_connector().query_one("SELECT path FROM folders WHERE path = ?", (target_scope_path,))
                if row and row.get("path"):
                    target_folder_paths = [row["path"]]
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Scope folder not found in folders cache: {scope_path}",
                    )
        else:
            rows = db.get_connector().query("SELECT path FROM folders")
            target_folder_paths = [r["path"] for r in rows if r and r.get("path")]

        connector = db.get_connector()
        image_scope_sql = ""
        image_scope_params: list[Any] = []
        if selected_scope == "selected_folder":
            placeholders = ",".join(["?"] * len(target_folder_paths))
            image_scope_sql = f" AND i.folder_id IN (SELECT id FROM folders WHERE path IN ({placeholders}))"
            image_scope_params = list(target_folder_paths)

        before = {
            "missing_indexing_or_metadata_with_scoring_done": 0,
            "missing_keywords_status_with_keywords_data": 0,
            "culling_failed_with_data_present": 0,
        }
        after = dict(before)
        warnings: list[str] = []

        before_idx_meta_sql = (
            """
            SELECT COUNT(*) AS cnt
            FROM images i
            JOIN pipeline_phases p_score ON LOWER(TRIM(p_score.code)) = 'scoring'
            JOIN image_phase_status ips_score ON ips_score.image_id = i.id
                AND ips_score.phase_id = p_score.id
                AND LOWER(TRIM(ips_score.status)) = 'done'
            WHERE (
                NOT EXISTS (
                    SELECT 1 FROM image_phase_status ips_i
                    JOIN pipeline_phases p_i ON p_i.id = ips_i.phase_id
                    WHERE ips_i.image_id = i.id
                      AND LOWER(TRIM(p_i.code)) = 'indexing'
                      AND LOWER(TRIM(ips_i.status)) = 'done'
                )
                OR NOT EXISTS (
                    SELECT 1 FROM image_phase_status ips_m
                    JOIN pipeline_phases p_m ON p_m.id = ips_m.phase_id
                    WHERE ips_m.image_id = i.id
                      AND LOWER(TRIM(p_m.code)) = 'metadata'
                      AND LOWER(TRIM(ips_m.status)) = 'done'
                )
            )
            """
            + image_scope_sql
        )
        before["missing_indexing_or_metadata_with_scoring_done"] = int(
            (connector.query_one(before_idx_meta_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        kw_sql = (
            """
            SELECT COUNT(*) AS cnt
            FROM images i
            WHERE EXISTS (SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id)
              AND NOT EXISTS (
                SELECT 1 FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                WHERE ips.image_id = i.id
                  AND LOWER(TRIM(pp.code)) = 'keywords'
                  AND LOWER(TRIM(ips.status)) = 'done'
              )
            """
            + image_scope_sql
        )
        before["missing_keywords_status_with_keywords_data"] = int(
            (connector.query_one(kw_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        if getattr(connector, "type", "") == "postgres":
            has_culling_data_expr = (
                f"i.stack_id IS NOT NULL OR ({db._postgres_has_default_embedding_sql('i')})"
            )
        else:
            has_culling_data_expr = (
                "i.stack_id IS NOT NULL OR i.image_embedding IS NOT NULL"
            )

        culling_sql = (
            """
            SELECT COUNT(*) AS cnt
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            JOIN images i ON i.id = ips.image_id
            WHERE LOWER(TRIM(pp.code)) = 'culling'
              AND LOWER(TRIM(ips.status)) = 'failed'
              AND (
            """
            + has_culling_data_expr
            + """
              )
            """
            + image_scope_sql
        )
        before["culling_failed_with_data_present"] = int(
            (connector.query_one(culling_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        if selected_scope == "selected_folder":
            idx_meta_changed = int(db.backfill_index_meta_for_folder(target_scope_path))
        else:
            idx_meta_changed = int(db.backfill_index_meta_global(limit=1_000_000))

        kw_rows = connector.query(
            (
                """
                SELECT DISTINCT i.id AS image_id
                FROM images i
                WHERE EXISTS (SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id)
                  AND NOT EXISTS (
                    SELECT 1 FROM image_phase_status ips
                    JOIN pipeline_phases pp ON pp.id = ips.phase_id
                    WHERE ips.image_id = i.id
                      AND LOWER(TRIM(pp.code)) = 'keywords'
                      AND LOWER(TRIM(ips.status)) = 'done'
                  )
                """
                + image_scope_sql
            ),
            tuple(image_scope_params),
        )
        kw_backfilled = 0
        for row in kw_rows:
            db.set_image_phase_status(int(row["image_id"]), "keywords", "done")
            kw_backfilled += 1

        culling_rows = connector.query(
            (
                """
                SELECT ips.id AS ips_id
                FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                JOIN images i ON i.id = ips.image_id
                WHERE LOWER(TRIM(pp.code)) = 'culling'
                  AND LOWER(TRIM(ips.status)) = 'failed'
                  AND (
                """
                + has_culling_data_expr
                + """
                  )
                """
                + image_scope_sql
            ),
            tuple(image_scope_params),
        )
        culling_ids = [int(r["ips_id"]) for r in culling_rows]
        if culling_ids:
            now = datetime.now()

            def _repair_culling_tx(tx):
                for ips_id in culling_ids:
                    tx.execute(
                        """
                        UPDATE image_phase_status
                        SET status = 'done',
                            last_error = NULL,
                            finished_at = COALESCE(finished_at, ?),
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (now, now, ips_id),
                    )

            connector.run_transaction(_repair_culling_tx)

        folders_recomputed = 0
        keywords_flag_updates = 0
        for path in target_folder_paths:
            try:
                db.invalidate_folder_phase_aggregates(folder_path=path)
                db.get_folder_phase_summary(path, force_refresh=True)
                folders_recomputed += 1
                if db.check_and_update_folder_keywords_status(path):
                    keywords_flag_updates += 1
            except Exception as folder_err:
                warnings.append(f"Folder aggregate rebuild failed for {path}: {folder_err}")

        if selected_scope == "all" and not target_folder_paths:
            warnings.append("No folders found; aggregate rebuild skipped.")
        warnings.append(
            "total_rows_changed_estimate is heuristic: index/meta assumes up to 2 per-image phase rows per repaired image."
        )

        after["missing_indexing_or_metadata_with_scoring_done"] = int(
            (connector.query_one(before_idx_meta_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )
        after["missing_keywords_status_with_keywords_data"] = int(
            (connector.query_one(kw_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )
        after["culling_failed_with_data_present"] = int(
            (connector.query_one(culling_sql, tuple(image_scope_params)) or {}).get("cnt", 0)
        )

        target_images_row = connector.query_one(
            (
                "SELECT COUNT(*) AS cnt FROM images i WHERE 1=1"
                + image_scope_sql
            ),
            tuple(image_scope_params),
        )
        target_images = int((target_images_row or {}).get("cnt", 0))

        summary = {
            "scope": selected_scope,
            "scope_path": target_scope_path if selected_scope == "selected_folder" else None,
            "target_images": target_images,
            "per_image_changes": {
                "indexing_metadata_backfilled_images": idx_meta_changed,
                "keywords_phase_backfilled_rows": kw_backfilled,
                "culling_failed_to_done_rows": len(culling_ids),
                "total_rows_changed_estimate": (idx_meta_changed * 2) + kw_backfilled + len(culling_ids),
            },
            "folder_aggregate_changes": {
                "folders_recomputed": folders_recomputed,
                "folders_marked_keywords_processed": keywords_flag_updates,
            },
            "before": before,
            "after": after,
            "warnings": warnings,
        }

        # Durable audit row (sync endpoint): appears in Runs/history with full summary in jobs.log.
        audit_run_id = None
        try:
            audit_payload = attach_run_reason(
                augment_queue_payload_for_audit(
                    {
                        "action": "recalculate_status_from_data",
                        "scope": selected_scope,
                        "scope_path": target_scope_path,
                    },
                    trigger="api",
                    tool_id="recalculate_status_from_data",
                ),
                source=REASON_SOURCE_MAINTENANCE,
                summary=build_maintenance_summary(
                    action="recalculate_status_from_data",
                    input_path=target_scope_path,
                ),
                trigger="api",
                tool_id="recalculate_status_from_data",
                criteria={
                    "action": "recalculate_status_from_data",
                    "scope": selected_scope,
                },
            )
            audit_desc = (
                "Sync tool: recalculate derivable per-image phase statuses and folder aggregates. "
                + (
                    f"Folder scope: {target_scope_path}. "
                    if target_scope_path
                    else "Scope: entire database. "
                )
                + "Metrics: jobs.log JSON on this run."
            )
            audit_run_id = db.create_job(
                maintenance_job_input_path(
                    "recalculate_status_from_data",
                    {**audit_payload, "audit": True},
                    title_override="Recalculate status from data",
                ),
                job_type="maintenance",
                status="completed",
                queue_payload={**audit_payload, "summary": summary},
                description=audit_desc,
            )
            if audit_run_id:
                now = datetime.now()
                log_text = json.dumps({"summary": summary}, default=str)
                db.get_connector().execute(
                    "UPDATE jobs SET log = ?, started_at = ?, finished_at = ?, completed_at = ? WHERE id = ?",
                    (log_text, now, now, now, audit_run_id),
                )
                db.create_job_phases(audit_run_id, ["maintenance"], first_phase_state=None)
                db.set_job_phase_state(audit_run_id, "maintenance", "completed")
        except Exception as audit_err:
            logger.warning("recalculate_status_from_data: audit job row skipped: %s", audit_err)
            summary.setdefault("warnings", []).append(
                {
                    "type": "audit_row_skipped",
                    "message": "Audit job row creation failed; main recalculation completed successfully.",
                    "details": str(audit_err),
                }
            )

        summary_payload = summary if isinstance(summary, dict) else {}
        per_image_changes = summary_payload.get("per_image_changes") or {}
        folder_changes = summary_payload.get("folder_aggregate_changes") or {}
        total_rows_changed = int(per_image_changes.get("total_rows_changed_estimate") or 0)
        folders_rebuilt = int(folder_changes.get("folders_recomputed") or folders_recomputed or 0)

        return ApiResponse(
            success=True,
            message=(
                "Status recalculation finished: "
                f"{total_rows_changed} per-image row changes "
                f"(heuristic estimate), {folders_rebuilt} folder aggregate(s) rebuilt."
            ),
            data={"summary": summary_payload, "audit_run_id": audit_run_id},
        )

    @router.post(
        "/maintenance/backfill-exif-dates",
        response_model=ApiResponse,
        summary="Re-extract EXIF dates for rows with NULL date_time_original",
        description=(
            "Repairs image_exif rows where date_time_original is NULL due to a prior "
            "timestamp parsing bug. Re-runs exiftool extraction and updates date columns. "
            "Safe to repeat; skips images whose files lack EXIF dates."
        ),
        tags=["General API"],
    )
    async def maintenance_backfill_exif_dates(
        limit: int = Query(1000, ge=1, le=10000),
    ):
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("maintenance_backfill_exif_dates")
        queue_payload = {
            "action": "backfill_exif",
            "limit": limit,
        }
        queue_payload = attach_run_reason(
            augment_queue_payload_for_audit(queue_payload, trigger="api", tool_id="backfill_exif_dates"),
            source=REASON_SOURCE_MAINTENANCE,
            summary=build_maintenance_summary(action="backfill_exif"),
            trigger="api",
            tool_id="backfill_exif_dates",
            criteria={"action": "backfill_exif", "limit": limit},
        )
        job_id, _ = db.enqueue_job(
            maintenance_job_input_path("backfill_exif", queue_payload),
            None,
            job_type="maintenance",
            queue_payload=queue_payload,
            description=build_default_maintenance_description("backfill_exif", queue_payload),
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue maintenance job")
        return ApiResponse(
            success=True,
            message=f"EXIF backfill job queued (Run ID: {job_id})",
            data={"run_id": job_id},
        )

    @router.post(
        "/maintenance/regenerate-thumbnails",
        response_model=ApiResponse,
        summary="Regenerate missing thumbnails (global batch)",
        description=(
            "Regenerates up to 500 thumbnails globally where the DB path does not resolve to a file. "
            "May take several minutes on RAW-heavy libraries. Safe to repeat."
        ),
        tags=["General API"],
    )
    async def maintenance_regenerate_thumbnails():
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("maintenance_regenerate_thumbnails")
        queue_payload = {
            "action": "heal_thumbnails",
            "limit": 500,
        }
        queue_payload = attach_run_reason(
            augment_queue_payload_for_audit(queue_payload, trigger="api", tool_id="regenerate_thumbnails"),
            source=REASON_SOURCE_MAINTENANCE,
            summary=build_maintenance_summary(action="heal_thumbnails"),
            trigger="api",
            tool_id="regenerate_thumbnails",
            criteria={"action": "heal_thumbnails", "limit": 500},
        )
        job_id, _ = db.enqueue_job(
            maintenance_job_input_path("heal_thumbnails", queue_payload),
            None,
            job_type="maintenance",
            queue_payload=queue_payload,
            description=build_default_maintenance_description("heal_thumbnails", queue_payload),
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue maintenance job")
        return ApiResponse(
            success=True,
            message=f"Thumbnail healing job queued (Run ID: {job_id})",
            data={"run_id": job_id},
        )

    @router.post(
        "/maintenance/repair-thumbnail-paths",
        response_model=ApiResponse,
        summary="Repair malformed thumbnail path columns (global batch)",
        description=(
            "Normalizes up to 1000 thumbnail_path / thumbnail_path_win row updates per call. "
            "Default (repair_all=false): Postgres scans only likely-bad rows (Docker /app paths, "
            "repo-relative fragments, single-column pairs). "
            "repair_all=true: full-table scan; normalizes any row where values change (slower). "
            "Does not regenerate image pixels. Safe to repeat."
        ),
        tags=["General API"],
    )
    async def maintenance_repair_thumbnail_paths(
        repair_all: bool = Query(
            False,
            description="Full scan: normalize every row where normalize_stored_thumbnail_pair changes values",
        ),
    ):
        from modules import thumbnail_maintenance
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("maintenance_repair_thumbnail_paths")
        try:
            stats = thumbnail_maintenance.repair_thumbnail_paths_batch(
                limit=1000,
                repair_all_pairs=repair_all,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        parts = [
            f"{stats['repaired']} updated",
            f"{stats['unchanged']} unchanged",
            f"{stats['scanned']} rows scanned",
        ]
        if stats.get("used_candidate_filter"):
            parts.append("quick filter")
        msg = "Thumbnail path repair: " + ", ".join(parts)
        if not repair_all and stats["repaired"] == 0 and stats.get("used_candidate_filter") and stats["scanned"] == 0:
            msg += (
                ". No candidate rows (DB likely clean for common issues). "
                "Retry with repair_all=true for a deep normalize pass."
            )
        elif not repair_all and stats["repaired"] == 0 and stats["scanned"] > 0:
            msg += ". Candidate rows normalized with no changes; try repair_all=true if paths still look wrong."
        return ApiResponse(
            success=True,
            message=msg,
            data=dict(stats),
        )

    @router.post(
        "/maintenance/heal-thumbnails",
        response_model=ApiResponse,
        summary="Heal thumbnails (quick path repair + missing regeneration)",
        description=(
            "Runs quick thumbnail path normalization (up to 1000 row updates), then regenerates "
            "up to 500 missing thumbnail rasters. Order matters: normalize DB paths first, then decode pixels. "
            "Does not perform deep/full-table path repair; use POST /maintenance/repair-thumbnail-paths "
            "with repair_all=true when paths still look wrong after this."
        ),
        tags=["General API"],
    )
    async def maintenance_heal_thumbnails():
        from modules import thumbnail_maintenance
        from modules.ui.security import _check_rate_limit

        _check_rate_limit("maintenance_heal_thumbnails")
        try:
            result = thumbnail_maintenance.heal_thumbnails_batch()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        rep = result["repair"]
        reg = result["regenerate"]
        msg = (
            f"Heal thumbnails: path repair {rep['repaired']} updated / {rep['scanned']} scanned; "
            f"regenerate {reg['regenerated']} OK, {reg['skipped_thumb_ok']} skipped (thumb OK), "
            f"{reg['skipped_missing_original']} missing original, {reg['failed']} failed"
        )
        return ApiResponse(
            success=True,
            message=msg,
            data={"repair": dict(rep), "regenerate": dict(reg)},
        )

    @router.post(
        "/maintenance/start",
        response_model=ApiResponse,
        summary="Start a background maintenance run",
        description="Unified entry point for background data integrity tasks (heal_thumbnails, backfill_exif, prune_missing, reconcile, backfill_index_meta).",
        tags=["General API"]
    )
    async def maintenance_start(request: MaintenanceStartRequest):
        from modules import db
        from modules.ui.security import _check_rate_limit
        _check_rate_limit(f"maintenance_{request.action}")

        payload_dict = {
            "action": request.action,
            "limit": request.limit if request.limit is not None else 1000,
            "dry_run": request.dry_run,
        }
        if request.input_path and str(request.input_path).strip():
            payload_dict["input_path"] = str(request.input_path).strip()

        tid = (request.tool_id or "").strip() or (request.action or "").strip()
        payload_dict = augment_queue_payload_for_audit(
            payload_dict,
            trigger=(request.trigger or "api").strip() or "api",
            tool_id=tid or None,
            ui_selected_scope_path=request.ui_selected_scope_path,
        )
        payload_dict = attach_run_reason(
            payload_dict,
            source=REASON_SOURCE_MAINTENANCE,
            summary=build_maintenance_summary(
                action=str(request.action),
                input_path=request.input_path,
            ),
            trigger=(request.trigger or "api").strip() or "api",
            tool_id=tid or None,
            criteria={
                "action": request.action,
                "limit": payload_dict.get("limit"),
                "dry_run": payload_dict.get("dry_run"),
            },
        )
        maint_desc = (request.description or "").strip() or build_default_maintenance_description(
            request.action,
            payload_dict,
            job_name=request.job_name,
        )

        job_id, _ = db.enqueue_job(
            maintenance_job_input_path(
                request.action,
                payload_dict,
                job_name=request.job_name,
            ),
            None,
            job_type="maintenance",
            queue_payload=payload_dict,
            description=maint_desc,
        )
        if job_id is None:
            raise HTTPException(status_code=500, detail="Failed to enqueue maintenance job")
        return ApiResponse(
            success=True,
            message=f"Maintenance run '{request.action}' started in background.",
            data={"run_id": job_id}
        )
    
    @router.get(
        "/diagnostics",
        response_model=DiagnosticsResponse,
        summary="Get comprehensive system diagnostics",
        description="""
        Returns detailed diagnostic information about the system, database, models, and runners.
        
        **Note:** Some fields may be omitted if dependencies (like psutil) are not installed.
        """,
        tags=["General API"]
    )
    async def get_diagnostics_endpoint():
        from modules.diagnostics import get_diagnostics
        diag = get_diagnostics()
        
        # Add runner status to the diagnostics payload
        diag["runners"] = {
            "scoring": "available" if _api_module()._scoring_runner is not None else "unavailable",
            "tagging": "available" if _api_module()._tagging_runner is not None else "unavailable",
            "clustering": "available" if _api_module()._clustering_runner is not None else "unavailable",
            "selection": "available" if _api_module()._selection_runner is not None else "unavailable",
            "bird_species": "available" if _api_module()._bird_species_runner is not None else "unavailable",
            "indexing": "available" if _api_module()._indexing_runner is not None else "unavailable",
            "metadata": "available" if _api_module()._metadata_runner is not None else "unavailable",
            "maintenance": "available" if _api_module()._maintenance_runner is not None else "unavailable",
            "orchestrator": "active" if _api_module()._orchestrator and _api_module()._orchestrator.get_status().get("active") else "idle"
        }

        return diag

    @router.get(
        "/models",
        summary="List registered scoring models",
        description=(
            "Return the contents of the scoring-model registry: per-model "
            "name, version, framework, native score range, and whether the "
            "model is enabled (production) or running in shadow mode. "
            "Useful for UI / shadow-comparison tooling."
        ),
        tags=["General API"],
    )
    async def list_scoring_models():
        from modules.engines.registry import get_registry

        registry = get_registry()
        models = registry.all_registered()
        enabled_names = {m.name for m in registry.enabled()}
        shadow_names = {m.name for m in registry.shadow()}

        items = []
        for m in models:
            lo, hi = getattr(m, "score_range", (0.0, 1.0))
            items.append({
                "name": m.name,
                "version": getattr(m, "version", ""),
                "framework": getattr(m, "framework", ""),
                "score_range": [float(lo), float(hi)],
                "enabled": m.name in enabled_names,
                "shadow": m.name in shadow_names,
                "load_status": getattr(m, "load_status", "unknown"),
            })

        return {"models": items, "count": len(items)}

    _last_dump_time = 0.0
    _DUMP_COOLDOWN_S = 2.0

    @router.get(
        "/debug/thread-dump",
        summary="Capture Python thread dump",
        description="Returns a full Python thread dump for backend diagnostic and stall debugging.",
        tags=["General API"]
    )
    async def get_thread_dump():
        nonlocal _last_dump_time
        now = time.time()
        if now - _last_dump_time < _DUMP_COOLDOWN_S:
            raise HTTPException(status_code=429, detail="Too many thread dump requests. Please wait a few seconds.")
        _last_dump_time = now
        
        try:
            from modules.pipeline_diagnostics import get_thread_dump as _get_thread_dump
            return {"success": True, "thread_dump": _get_thread_dump()}
        except Exception as e:
            logger.exception("Failed to capture thread dump")
            raise HTTPException(status_code=500, detail=f"Failed to capture thread dump: {e}")


    return router
