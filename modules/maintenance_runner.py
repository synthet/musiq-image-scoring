"""
Background runner for maintenance and data integrity tasks.
Supports heal_thumbnails, backfill_exif, prune_missing, reconcile_phases, etc.
"""
from __future__ import annotations

import logging
import json
from typing import Any, Dict, List

from modules import db
from modules.maintenance_job_display import maintenance_job_input_path
from modules.run_log import runner_emit

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
        self.log_history: List[str] = []

    def start_batch(self, input_path: str, job_id: int = None, **kwargs) -> str:
        """Entry point from JobDispatcher."""
        import threading
        if self.is_running:
            return "Error: Already running."
        
        self.is_running = True
        self._cancel_requested = False
        
        if job_id is None:
            # Should not happen when called from dispatcher, but for safety:
            job_id = db.create_job(
                input_path
                or maintenance_job_input_path("", {}, title_override="Maintenance (unqueued fallback)"),
                job_type="maintenance",
            )

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
        self.log_history = []
        try:
            if not db.get_job_phases(job_id):
                db.create_job_phases(job_id, ["maintenance"], first_phase_state="queued")
            # Update job to running
            db.update_job_status(job_id, "running")
            db.set_job_phase_state(job_id, "maintenance", "running")
            
            payload = {}
            if job.get("queue_payload"):
                try:
                    payload = json.loads(job["queue_payload"])
                except Exception:
                    pass
            
            action = payload.get("action", "reconcile")
            input_path = job.get("input_path") or ""
            logger.info(
                "Maintenance job %s starting: input_path=%r action=%r payload=%s",
                job_id,
                input_path,
                action,
                payload,
            )
            runner_emit(
                self.log_history, job_id,
                f"Job {job_id} starting — label={input_path!r}, action={action}, "
                f"params={json.dumps(payload, default=str)}",
                phase="maintenance",
            )
            runner_emit(self.log_history, job_id, f"Starting maintenance action: {action}", phase="maintenance")
            
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
            elif action == "deduplicate_images":
                self._action_deduplicate_images(job_id, payload)
            elif action == "heal_folder_ids":
                self._action_heal_folder_ids(job_id, payload)
            elif action == "backfill_exif_camera_lens":
                self._action_backfill_exif_camera_lens(job_id, payload)
            elif action == "backfill_exif_gps":
                self._action_backfill_exif_gps(job_id, payload)
            elif action == "backfill_embeddings":
                self._action_backfill_embeddings(job_id, payload)
            elif action == "backfill_clip_vectors":
                self._action_backfill_clip_vectors(job_id, payload)
            else:
                runner_emit(self.log_history, job_id, f"Unknown maintenance action: {action}", "ERROR", phase="maintenance")
                db.update_job_status(job_id, "failed", log=f"Unknown action: {action}")
                return

            db.update_job_status(job_id, "completed")
            db.set_job_phase_state(job_id, "maintenance", "completed")
            runner_emit(self.log_history, job_id, f"Maintenance action {action} completed.", phase="maintenance")
            logger.info(
                "Maintenance job %s completed successfully (action=%r, label=%r)",
                job_id,
                action,
                input_path,
            )

        except Exception as e:
            logger.exception("MaintenanceRunner failed (job_id=%s, label=%r)", job_id, job.get("input_path"))
            db.update_job_status(job_id, "failed", log=str(e))
            db.set_job_phase_state(job_id, "maintenance", "failed")
        finally:
            self.is_running = False

    def _action_reconcile(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 5000)
        logger.info("Maintenance reconcile: job_id=%s limit=%s", job_id, limit)
        n = db.reconcile_stale_running_phases_for_terminal_jobs(limit=limit)
        runner_emit(self.log_history, job_id, f"Reconciled {n} stuck phase row(s).", phase="maintenance")
        
        try:
            db.delete_orphan_stacks()
            runner_emit(self.log_history, job_id, "Cleaned up orphan stacks.", phase="maintenance")
        except Exception as e:
            logger.warning("Failed to delete orphan stacks during reconcile: %s", e)
            
        logger.info("Maintenance reconcile: job_id=%s done, rows_updated=%s", job_id, n)
        db.update_job_progress(job_id, 100)

    def _action_heal_thumbnails(self, job_id: int, payload: Dict[str, Any]):
        from modules import thumbnail_maintenance
        repair_limit = payload.get("repair_limit", 1000)
        regen_limit = payload.get("regen_limit", 500)
        repair_all = payload.get("repair_all", False)
        logger.info(
            "Maintenance heal_thumbnails: job_id=%s repair_limit=%s regen_limit=%s repair_all=%s",
            job_id,
            repair_limit,
            regen_limit,
            repair_all,
        )

        runner_emit(self.log_history, job_id, f"Repairing thumbnail paths (limit={repair_limit}, all={repair_all})...", phase="maintenance")
        repair_stats = thumbnail_maintenance.repair_thumbnail_paths_batch(limit=repair_limit, repair_all_pairs=repair_all)
        runner_emit(self.log_history, job_id, f"Repair results: {repair_stats['repaired']} updated, {repair_stats['scanned']} scanned.", phase="maintenance")
        db.update_job_progress(job_id, 50)
        
        if self._cancel_requested:
            return

        runner_emit(self.log_history, job_id, f"Regenerating missing rasters (limit={regen_limit})...", phase="maintenance")
        regen_stats = thumbnail_maintenance.regenerate_missing_thumbnails_batch(limit=regen_limit)
        runner_emit(self.log_history, job_id, f"Regenerate results: {regen_stats['regenerated']} OK, {regen_stats['failed']} failed.", phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_backfill_exif(self, job_id: int, payload: Dict[str, Any]):
        from modules import exif_extractor
        limit = payload.get("limit", 1000)
        logger.info("Maintenance backfill_exif: job_id=%s limit=%s", job_id, limit)
        runner_emit(self.log_history, job_id, f"Backfilling EXIF capture dates (limit={limit})...", phase="maintenance")
        
        # We process in smaller chunks to report progress if possible, 
        # but backfill_exif_dates is already batched.
        stats = exif_extractor.backfill_exif_dates(limit=limit)
        
        msg = f"EXIF backfill: {stats['updated']} updated, {stats['checked']} checked, {stats['errors']} errors."
        runner_emit(self.log_history, job_id, msg, phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_prune_missing(self, job_id: int, payload: Dict[str, Any]):
        from modules import utils
        limit = payload.get("limit", 5000)
        dry_run = payload.get("dry_run", False)
        logger.info(
            "Maintenance prune_missing: job_id=%s limit=%s dry_run=%s",
            job_id,
            limit,
            dry_run,
        )

        runner_emit(self.log_history, job_id, f"Pruning records for missing files (limit={limit}, dry_run={dry_run})...", phase="maintenance")
        
        pruned = 0
        scanned = 0
        
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, file_path FROM images FETCH FIRST ? ROWS ONLY", (limit,))
            rows = cur.fetchall()
            
            total = len(rows)
            for i, row in enumerate(rows):
                if self._cancel_requested:
                    break
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
                        runner_emit(self.log_history, job_id, f"Pruned {pruned} images so far...", phase="maintenance")
                
                if i % 100 == 0:
                    db.update_job_progress(job_id, int((i/total)*100))

        runner_emit(self.log_history, job_id, f"Pruning done: {pruned} records removed, {scanned} scanned.", phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_backfill_index_meta(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 1000)
        logger.info("Maintenance backfill_index_meta: job_id=%s limit=%s", job_id, limit)
        runner_emit(self.log_history, job_id, f"Global Index/Meta backfill (limit={limit})...", phase="maintenance")
        updated = db.backfill_index_meta_global(limit=limit)
        runner_emit(self.log_history, job_id, f"Updated {updated} image(s).", phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_deduplicate_images(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 1000)
        dry_run = payload.get("dry_run", False)
        logger.info("Maintenance deduplicate_images: job_id=%s limit=%s dry_run=%s", job_id, limit, dry_run)
        runner_emit(self.log_history, job_id, f"Deduplicating images (limit={limit}, dry_run={dry_run})...", phase="maintenance")
        
        merged_count = 0
        
        # Phase 1: Duplicate paths (same file_path, different IDs)
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT file_path FROM images 
                WHERE file_path IS NOT NULL AND file_path != ''
                GROUP BY file_path HAVING COUNT(*) > 1
                FETCH FIRST ? ROWS ONLY
            """, (limit,))
            dupe_paths = [r[0] for r in cur.fetchall()]
        
        for path in dupe_paths:
            if self._cancel_requested: break
            rows = db.get_connector().query("SELECT id, image_hash, hash_version FROM images WHERE file_path = ? ORDER BY id", (path,))
            if len(rows) < 2: continue
            
            # Find the best hash to backfill
            best_hash_row = next((r for r in rows if (r.get("image_hash") or "").strip()), None)
            if not best_hash_row:
                continue
                
            h, v = best_hash_row["image_hash"], best_hash_row["hash_version"]
            others = [r for r in rows if r["id"] != best_hash_row["id"] and not (r.get("image_hash") or "").strip()]
            
            for other in others:
                if not dry_run:
                    db.get_connector().execute("UPDATE images SET image_hash = ?, hash_version = ? WHERE id = ?", (h, v, other["id"]))
                merged_count += 1
                if merged_count % 50 == 0:
                    runner_emit(self.log_history, job_id, f"Synced {merged_count} path duplicates...", phase="maintenance")

        # Phase 2: Duplicate content in same folder (same hash + folder_id)
        # This is the "split-brain" case caused by rebasing or re-indexing.
        # Since we can't delete, we just log these for now or ensure they all have hashes.
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT folder_id, image_hash, hash_version FROM images 
                WHERE image_hash IS NOT NULL AND folder_id IS NOT NULL
                GROUP BY folder_id, image_hash, hash_version HAVING COUNT(*) > 1
                FETCH FIRST ? ROWS ONLY
            """, (limit,))
            dupe_groups = cur.fetchall()
            
        for fid, h, v in dupe_groups:
            if self._cancel_requested: break
            rows = db.get_connector().query(
                "SELECT id, file_path FROM images WHERE folder_id = ? AND image_hash = ? AND hash_version = ? ORDER BY id", 
                (fid, h, v)
            )
            if len(rows) < 2: continue
            
            # Since we can't delete, we just log that these are confirmed duplicates.
            # In a future pass, we could 'deactivate' them by setting a flag.
            runner_emit(self.log_history, job_id, f"Found {len(rows)} duplicates for hash {h[:8]}... in folder {fid}", phase="maintenance")
            merged_count += (len(rows) - 1)

        runner_emit(self.log_history, job_id, f"Deduplication (sync mode) completed. {merged_count} records identified/synced.", phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_heal_folder_ids(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 10000)
        dry_run = payload.get("dry_run", False)
        logger.info("Maintenance heal_folder_ids: job_id=%s limit=%s dry_run=%s", job_id, limit, dry_run)
        runner_emit(self.log_history, job_id, f"Healing folder IDs based on file paths (limit={limit}, dry_run={dry_run})...", phase="maintenance")
        
        import os
        folder_cache = {}
        updated_count = 0
        scanned = 0
        
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, file_path, folder_id FROM images FETCH FIRST ? ROWS ONLY", (limit,))
            rows = cur.fetchall()
            
            total = len(rows)
            for i, row in enumerate(rows):
                if self._cancel_requested: break
                scanned += 1
                
                img_id = row["id"] if hasattr(row, "keys") or isinstance(row, dict) else row[0]
                file_path = row["file_path"] if hasattr(row, "keys") or isinstance(row, dict) else row[1]
                old_fid = row["folder_id"] if hasattr(row, "keys") or isinstance(row, dict) else row[2]
                
                if not file_path: continue
                
                parent = os.path.normpath(os.path.dirname(file_path))
                if parent not in folder_cache:
                    folder_cache[parent] = db.get_or_create_folder(parent)
                new_fid = folder_cache[parent]
                
                if new_fid != old_fid:
                    if not dry_run:
                        db.get_connector().execute("UPDATE images SET folder_id = ? WHERE id = ?", (new_fid, img_id))
                        if old_fid:
                            db.invalidate_folder_phase_aggregates(folder_id=old_fid)
                        if new_fid:
                            db.invalidate_folder_phase_aggregates(folder_id=new_fid)
                    
                    updated_count += 1
                    if updated_count % 100 == 0:
                        runner_emit(self.log_history, job_id, f"Healed {updated_count} folder IDs...", phase="maintenance")
                
                if i % 500 == 0:
                    db.update_job_progress(job_id, int((i/total)*100))

        runner_emit(self.log_history, job_id, f"Heal folder IDs completed. {updated_count} IDs updated, {scanned} scanned.", phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_backfill_exif_camera_lens(self, job_id: int, payload: Dict[str, Any]):
        from modules import exif_extractor
        limit = payload.get("limit", 1000)
        logger.info("Maintenance backfill_exif_camera_lens: job_id=%s limit=%s", job_id, limit)
        runner_emit(self.log_history, job_id, f"Backfilling EXIF Camera/Lens (limit={limit})...", phase="maintenance")
        
        stats = exif_extractor.backfill_exif_camera_lens(limit=limit)
        
        msg = f"Camera/Lens backfill: {stats['updated']} updated, {stats['checked']} checked, {stats['errors']} errors."
        runner_emit(self.log_history, job_id, msg, phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_backfill_exif_gps(self, job_id: int, payload: Dict[str, Any]):
        from modules import exif_extractor
        limit = payload.get("limit", 1000)
        logger.info("Maintenance backfill_exif_gps: job_id=%s limit=%s", job_id, limit)
        runner_emit(self.log_history, job_id, f"Backfilling EXIF GPS (limit={limit})...", phase="maintenance")
        
        stats = exif_extractor.backfill_exif_gps(limit=limit)
        
        msg = f"GPS backfill: {stats['updated']} updated, {stats['checked']} checked, {stats['errors']} errors."
        runner_emit(self.log_history, job_id, msg, phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_backfill_embeddings(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 10000)
        logger.info("Maintenance backfill_embeddings: job_id=%s limit=%s", job_id, limit)
        runner_emit(self.log_history, job_id, f"Backfilling MobileNet Embeddings (limit={limit})...", phase="maintenance")
        
        rows = db.get_images_missing_embeddings(limit=limit)
        total = len(rows)
        if total == 0:
            runner_emit(self.log_history, job_id, "No images missing MobileNet embeddings.", phase="maintenance")
            db.update_job_progress(job_id, 100)
            return
            
        runner_emit(self.log_history, job_id, f"Found {total} images missing embeddings. Initializing engine...", phase="maintenance")
        
        from modules.clustering import ClusteringEngine
        engine = ClusteringEngine()
        
        batch_size = 32
        updated = 0
        errors = 0
        
        import os
        from modules import utils
        
        for i in range(0, total, batch_size):
            if self._cancel_requested: break
            batch_rows = rows[i:i+batch_size]
            batch_ids = []
            batch_paths = []
            
            for row in batch_rows:
                img_id = row["id"] if isinstance(row, dict) and "id" in row else row[0]
                fp = row["file_path"] if isinstance(row, dict) and "file_path" in row else row[1]
                path = utils.resolve_file_path(fp, img_id)
                if not path:
                    path = utils.convert_path_to_local(fp)
                if path and os.path.exists(path):
                    batch_ids.append(img_id)
                    batch_paths.append(path)
            
            if not batch_paths:
                continue
                
            try:
                features, valid_indices = engine.extract_features(batch_paths)
                if features.size:
                    embedding_pairs = []
                    for j, orig_idx in enumerate(valid_indices):
                        vec = features[j].astype("float32")
                        embedding_pairs.append((batch_ids[orig_idx], vec.tobytes()))
                    
                    if embedding_pairs:
                        db.update_image_embeddings_batch(embedding_pairs)
                        updated += len(embedding_pairs)
            except Exception as e:
                logger.error("Error in backfill embeddings batch: %s", e)
                errors += len(batch_paths)
                
            progress = int((i + len(batch_rows)) / total * 100)
            db.update_job_progress(job_id, progress)
            if (i // batch_size) % 5 == 0:
                runner_emit(self.log_history, job_id, f"Backfilled {updated} embeddings so far...", phase="maintenance")
                
        runner_emit(self.log_history, job_id, f"MobileNet backfill complete: {updated} updated, {errors} errors.", phase="maintenance")
        db.update_job_progress(job_id, 100)

    def _action_backfill_clip_vectors(self, job_id: int, payload: Dict[str, Any]):
        limit = payload.get("limit", 10000)
        logger.info("Maintenance backfill_clip_vectors: job_id=%s limit=%s", job_id, limit)
        runner_emit(self.log_history, job_id, f"Backfilling CLIP Vectors (limit={limit})...", phase="maintenance")
        
        if not hasattr(db, "get_images_missing_embedding_for_space"):
            runner_emit(self.log_history, job_id, "CLIP backfill requires Postgres.", phase="maintenance", level="ERROR")
            db.update_job_progress(job_id, 100)
            return

        rows = db.get_images_missing_embedding_for_space('clip_vit_b32_image', limit=limit)
        total = len(rows)
        if total == 0:
            runner_emit(self.log_history, job_id, "No images missing CLIP vectors.", phase="maintenance")
            db.update_job_progress(job_id, 100)
            return
            
        runner_emit(self.log_history, job_id, f"Found {total} images missing CLIP embeddings. Initializing engine...", phase="maintenance")
        
        try:
            from modules.tagging import KeywordScorer
            scorer = KeywordScorer()
            scorer.load_model()
        except Exception as e:
            logger.error("Failed to load CLIP engine: %s", e)
            runner_emit(self.log_history, job_id, f"Failed to load CLIP engine: {e}", phase="maintenance", level="ERROR")
            db.update_job_progress(job_id, 100)
            return
            
        batch_size = 16
        updated = 0
        errors = 0
        
        import os
        import torch
        from modules import utils
        from modules.thumbnails import open_image_for_ml
        from modules.embeddings_extract import extract_clip_image_features_from_outputs
        
        for i in range(0, total, batch_size):
            if self._cancel_requested: break
            batch_rows = rows[i:i+batch_size]
            
            for row in batch_rows:
                if self._cancel_requested: break
                img_id = row["id"] if isinstance(row, dict) and "id" in row else row[0]
                fp = row["file_path"] if isinstance(row, dict) and "file_path" in row else row[1]
                path = utils.resolve_file_path(fp, img_id)
                if not path:
                    path = utils.convert_path_to_local(fp)
                if path and os.path.exists(path):
                    try:
                        image = open_image_for_ml(path)
                        inputs = scorer.processor(text=["dummy"], images=image, return_tensors="pt", padding=True)
                        inputs = {k: v.to(scorer.device) for k, v in inputs.items()}
                        
                        with torch.no_grad():
                            outputs = scorer.model(**inputs)
                            
                        vec = extract_clip_image_features_from_outputs(outputs)
                        if vec is not None:
                            db.update_image_embeddings_batch_for_space(
                                'clip_vit_b32_image',
                                [
                                    (
                                        img_id,
                                        vec,
                                        getattr(scorer, "model_name", "ViT-B/32"),
                                    )
                                ],
                            )
                            updated += 1
                    except Exception as e:
                        logger.error("Error extracting CLIP for image %d: %s", img_id, e)
                        errors += 1
            
            progress = int((i + len(batch_rows)) / total * 100)
            db.update_job_progress(job_id, progress)
            if (i // batch_size) % 5 == 0:
                runner_emit(self.log_history, job_id, f"Backfilled {updated} CLIP embeddings so far...", phase="maintenance")
                
        runner_emit(self.log_history, job_id, f"CLIP backfill complete: {updated} updated, {errors} errors.", phase="maintenance")
        db.update_job_progress(job_id, 100)
