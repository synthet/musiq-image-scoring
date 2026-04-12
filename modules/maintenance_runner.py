"""
Background runner for maintenance and data integrity tasks.
Supports heal_thumbnails, backfill_exif, prune_missing, reconcile_phases, etc.
"""
from __future__ import annotations

import logging
import json
import time
import os
from typing import Dict, Any, List

from modules import db

logger = logging.getLogger(__name__)


class MaintenanceRunner:
    """
    Runner for 'maintenance' job type.
    Handles various data-integrity 'actions' as a single-phase background job.
    Contract: start_batch (returns "Started" | error string), is_running.
    """

    def __init__(self):
        self.job_type = "maintenance"
        self.is_running = False
        self._thread = None
        self._cancel_requested = False

    def start_batch(self, input_path: str, job_id: int = None, **kwargs) -> str:
        """Entry point from JobDispatcher."""
        import threading
        if self.is_running:
            return "Error: Already running."
        
        self.is_running = True
        self._cancel_requested = False
        
        if job_id is None:
            # Should not happen when called from dispatcher, but for safety:
            job_id = db.create_job(input_path or "GLOBAL_MAINTENANCE", job_type="maintenance")

        def target():
            try:
                # We need to fetch the job to get the queue_payload
                job = db.get_job(job_id)
                self._run_job_internal(job)
            except Exception:
                logger.exception("MaintenanceRunner thread crashed (job_id=%s)", job_id)
            finally:
                self.is_running = False

        self._thread = threading.Thread(
            target=target,
            name=f"Maintenance-{job_id}"
        )
        self._thread.start()
        return "Started"

    def _run_job_internal(self, job: Dict[str, Any]):
        job_id = job["id"]
        try:
            # Update job to running
            db.update_job_status(job_id, "running")
            db.update_job_phase_state(job_id, "maintenance", "running")
            
            payload = {}
            if job.get("queue_payload"):
                try:
                    payload = json.loads(job["queue_payload"])
                except Exception:
                    pass
            
            action = payload.get("action", "reconcile")
            limit = payload.get("limit", 1000)
            
            db.log_job_event(job_id, "maintenance", f"Starting maintenance action: {action}")
            
            if action == "heal_thumbnails":
                self._action_heal_thumbnails(job_id, payload)
            elif action == "backfill_exif":
                self._action_backfill_exif(job_id, payload)
            elif action == "prune_missing":
                self._action_prune_missing(job_id, payload)
            elif action == "reconcile":
                self._action_reconcile(job_id, payload)
            elif action == "backfill_index_meta":
                self._action_backfill_index_meta(job_id, payload)
            else:
                db.log_job_event(job_id, "maintenance", f"Unknown maintenance action: {action}", level="ERROR")
                db.update_job_status(job_id, "failed", log=f"Unknown action: {action}")
                return

            db.update_job_status(job_id, "completed")
            db.update_job_phase_state(job_id, "maintenance", "completed")
            db.log_job_event(job_id, "maintenance", f"Maintenance action {action} completed.")

        except Exception as e:
            logger.exception("MaintenanceRunner failed")
            db.update_job_status(job_id, "failed", log=str(e))
            db.update_job_phase_state(job_id, "maintenance", "failed")
        finally:
            self.is_running = False

    def _action_reconcile(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 5000)
        n = db.reconcile_stale_running_phases_for_terminal_jobs(limit=limit)
        db.log_job_event(job_id, "maintenance", f"Reconciled {n} stuck phase row(s).")
        db.update_job_progress(job_id, 100)

    def _action_heal_thumbnails(self, job_id: int, payload: Dict[str, Any]):
        from modules import thumbnail_maintenance
        repair_limit = payload.get("repair_limit", 1000)
        regen_limit = payload.get("regen_limit", 500)
        repair_all = payload.get("repair_all", False)
        
        db.log_job_event(job_id, "maintenance", f"Repairing thumbnail paths (limit={repair_limit}, all={repair_all})...")
        repair_stats = thumbnail_maintenance.repair_thumbnail_paths_batch(limit=repair_limit, repair_all_pairs=repair_all)
        db.log_job_event(job_id, "maintenance", f"Repair results: {repair_stats['repaired']} updated, {repair_stats['scanned']} scanned.")
        db.update_job_progress(job_id, 50)
        
        if self._cancel_requested: return
        
        db.log_job_event(job_id, "maintenance", f"Regenerating missing rasters (limit={regen_limit})...")
        regen_stats = thumbnail_maintenance.regenerate_missing_thumbnails_batch(limit=regen_limit)
        db.log_job_event(job_id, "maintenance", f"Regenerate results: {regen_stats['regenerated']} OK, {regen_stats['failed']} failed.")
        db.update_job_progress(job_id, 100)

    def _action_backfill_exif(self, job_id: int, payload: Dict[str, Any]):
        from modules import exif_extractor
        limit = payload.get("limit", 1000)
        db.log_job_event(job_id, "maintenance", f"Backfilling EXIF capture dates (limit={limit})...")
        
        # We process in smaller chunks to report progress if possible, 
        # but backfill_exif_dates is already batched.
        stats = exif_extractor.backfill_exif_dates(limit=limit)
        
        msg = f"EXIF backfill: {stats['updated']} updated, {stats['checked']} checked, {stats['errors']} errors."
        db.log_job_event(job_id, "maintenance", msg)
        db.update_job_progress(job_id, 100)

    def _action_prune_missing(self, job_id: int, payload: Dict[str, Any]):
        from modules import utils
        limit = payload.get("limit", 5000)
        dry_run = payload.get("dry_run", False)
        
        db.log_job_event(job_id, "maintenance", f"Pruning records for missing files (limit={limit}, dry_run={dry_run})...")
        
        pruned = 0
        scanned = 0
        
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, file_path FROM images FETCH FIRST ? ROWS ONLY", (limit,))
            rows = cur.fetchall()
            
            total = len(rows)
            for i, row in enumerate(rows):
                if self._cancel_requested: break
                scanned += 1
                
                # Support both RowWrapper (Firebird) and dict/tuple (Postgres)
                img_id = row["id"] if hasattr(row, "keys") or isinstance(row, dict) else row[0]
                file_path = row["file_path"] if hasattr(row, "keys") or isinstance(row, dict) else row[1]
                
                resolved = utils.resolve_file_path(file_path, image_id=img_id)
                if not resolved:
                    if not dry_run:
                        # We use db.delete_image which handles its own connection/transaction
                        db.delete_image(img_id)
                    pruned += 1
                    if pruned % 10 == 0:
                        db.log_job_event(job_id, "maintenance", f"Pruned {pruned} images so far...")
                
                if i % 100 == 0:
                    db.update_job_progress(job_id, int((i/total)*100))

        db.log_job_event(job_id, "maintenance", f"Pruning done: {pruned} records removed, {scanned} scanned.")
        db.update_job_progress(job_id, 100)

    def _action_backfill_index_meta(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 1000)
        db.log_job_event(job_id, "maintenance", f"Global Index/Meta backfill (limit={limit})...")
        updated = db.backfill_index_meta_global(limit=limit)
        db.log_job_event(job_id, "maintenance", f"Updated {updated} image(s).")
        db.update_job_progress(job_id, 100)
