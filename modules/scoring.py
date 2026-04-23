import os
import threading
import json
import logging
from modules import db, thumbnails
from modules.engine import BatchImageProcessor
from modules import pipeline
from modules.events import event_manager
from modules.run_log import runner_emit
from modules import score_normalization as snorm
from modules.phases import PhaseCode, normalize_phase_codes
from modules.indexing_policy import passes_nikon_nef_policy

logger = logging.getLogger(__name__)

_musiq_import_error = None
try:
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ
    try:
        from modules.engines.base import IScoringEngine

        IScoringEngine.register(MultiModelMUSIQ)
    except Exception:
        pass
except ImportError as exc:
    _musiq_import_error = exc
    MultiModelMUSIQ = None

class ScoringRunner:
    """
    Runs scoring in a local thread using modules.engine.

    scoring_engine: optional pre-built scorer (e.g. MockScoringEngine for tests).
    liqe_scorer: optional LIQE backend; None uses default LiqeScorer in the pipeline worker.
    """
    def __init__(self, scoring_engine=None, liqe_scorer=None):
        # We hold the shared scorer here to persist it across runs (None = lazy MultiModelMUSIQ)
        self.shared_scorer = scoring_engine
        self.liqe_scorer = liqe_scorer
        # We keep a ref to the current processor to stop it
        self.current_processor = None
        
        # State persistence
        self.is_running = False
        self._start_lock = threading.Lock()  # Prevents TOCTOU race on is_running
        self.job_type = None # 'scoring' or 'fix_db'
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0
        # Circuit breaker for model loading failures
        self._model_load_failures = 0
        self._MODEL_LOAD_MAX_FAILURES = 3
        
    def get_status(self):
        """
        Returns (is_running, log_text, status_message, current, total, pipeline_depth)
        """
        processor = self.current_processor
        depth = processor.get_pipeline_depth() if processor else 0
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count, depth

    def start_batch(self, input_path, job_id, skip_existing=False, resolved_image_ids=None, target_phases=None, report_collector=None):
        """
        Starts batch processing in a background thread. Non-blocking.
        """
        with self._start_lock:
            if self.is_running:
                return "Error: Already running."

            # Resolve cross-platform paths (WSL ↔ Windows) so the runner works regardless
            # of whether the caller passed a native or foreign path format.
            if input_path:
                from modules.utils import convert_path_to_local
                resolved = convert_path_to_local(input_path)
                if os.path.exists(resolved):
                    input_path = resolved

            if resolved_image_ids is None and (not input_path or not os.path.exists(input_path)):
                self.log_history.append(f"Error: Path not found: {input_path}")
                self.status_message = "Failed (Path not found)"
                return "Path not found"

            # All validation passed, now mark as running
            self.is_running = True

        self.job_type = 'scoring'
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0

        def target():
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                run_kwargs = {"resolved_image_ids": resolved_image_ids}
                if target_phases is not None:
                    run_kwargs["target_phases"] = target_phases
                try:
                    self._run_batch_internal(input_path, job_id, skip_existing, report_collector=report_collector, **run_kwargs)
                except Exception:
                    self.status_message = "Failed"
                    raise
                finally:
                    if "Error" in self.status_message:
                        self.status_message = "Failed"
                    elif not self.status_message.startswith("Done"):
                        self.status_message = "Done"

            safe_runner_thread(self, job_id, target_wrapper)

        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def _run_batch_internal(self, input_path, job_id, skip_existing, resolved_image_ids=None, target_phases=None, report_collector=None):
        """
        Internal synchronous runner.
        """
        db.update_job_status(job_id, "running")
        event_manager.broadcast_threadsafe("job_started", {"job_id": job_id, "job_type": "scoring", "input_path": input_path})

        def log(msg, level="INFO"):
            runner_emit(self.log_history, job_id, msg, level, phase="scoring")

        log("Starting batch processing...")
        log(f"Input: {input_path}")
        log("-" * 20)
        self.status_message = "Running..."
        if not target_phases:
             target_phases = [PhaseCode.SCORING]
        normalized_target_phases = normalize_phase_codes(target_phases)

        if _musiq_import_error is not None:
            msg = f"Failed to import MultiModelMUSIQ: {_musiq_import_error}"
            log(msg, "ERROR")
            self.status_message = "Error loading models"
            db.update_job_status(job_id, "failed", msg)
            event_manager.broadcast_threadsafe(
                "job_completed",
                {"job_id": job_id, "status": "failed", "error": msg},
            )
            return
        
        # Checking/Loading Models (skip when a scorer was injected via constructor)
        if self.shared_scorer is None:
            # Circuit breaker: stop retrying after repeated failures
            if self._model_load_failures >= self._MODEL_LOAD_MAX_FAILURES:
                msg = (f"Model loading circuit breaker open: {self._model_load_failures} consecutive failures. "
                       f"Restart the WebUI to reset.")
                log(msg, "ERROR")
                self.status_message = "Error loading models (circuit breaker open)"
                db.update_job_status(job_id, "failed", msg)
                event_manager.broadcast_threadsafe(
                    "job_completed",
                    {"job_id": job_id, "status": "failed", "error": msg},
                )
                return

            log("Initializing models first (this happens once)...")
            try:
                new_scorer = MultiModelMUSIQ()
                
                # Load models
                musiq_models = ['spaq', 'ava']
                all_loaded = True
                for model_name in musiq_models:
                    log(f"Loading model: {model_name.upper()}...")
                    success = new_scorer.load_model(model_name)
                    if not success:
                         log(f"Warning: Failed to load {model_name}", "WARNING")
                         all_loaded = False

                if not all_loaded:
                    self._model_load_failures += 1
                    msg = f"One or more models failed to load (attempt {self._model_load_failures}/{self._MODEL_LOAD_MAX_FAILURES})"
                    log(msg, "ERROR")
                    self.status_message = "Error loading models"
                    db.update_job_status(job_id, "failed", msg)
                    return

                self.shared_scorer = new_scorer
                self._model_load_failures = 0  # Reset on success
                log("Models initialized successfully.")

            except Exception as e:
                self._model_load_failures += 1
                msg = f"Error loading models (attempt {self._model_load_failures}/{self._MODEL_LOAD_MAX_FAILURES}): {str(e)}"
                log(msg, "ERROR")
                self.status_message = "Error loading models"
                db.update_job_status(job_id, "failed", msg)
                return
        else:
            log("Using injected scoring engine (no lazy model load).")

        def on_progress(cur, tot):
            self.current_count = cur
            self.total_count = tot
            event_manager.broadcast_threadsafe(
                "job_progress",
                {"job_id": job_id, "job_type": "scoring", "current": cur, "total": tot},
            )
            
        # Initialize processor
        processor = BatchImageProcessor(
            output_dir=input_path,
            skip_existing=skip_existing,
            scorer=self.shared_scorer,
            progress_callback=on_progress,
            target_phases=normalized_target_phases,
            liqe_scorer=self.liqe_scorer,
        )
        self.current_processor = processor
        
        # Inject job_id for DB upserts (Engine HACK)
        processor.current_job_id = job_id

        # Attach report collector for execution trail
        processor.report_collector = report_collector
        
        # Setup log capture
        # We hook directly to self.log_history via wrapper
        def log_capture(msg, level="INFO"):
            log(msg, level)

        processor.log_func = log_capture
        
        # Firebird .fdb file copy (no-op message when using PostgreSQL only; see db.backup_database)
        _backup_msg = db.backup_database()
        if _backup_msg:
            log(_backup_msg)
        
        try:
            # process_directory now blocks until all workers are done
            if resolved_image_ids is not None:
                if not resolved_image_ids:
                    log("No images matched selectors.")
                    self.status_message = "Done (no images)"
                    self._finalize_report(job_id, report_collector)
                    db.update_job_status(job_id, "completed", "\n".join(self.log_history))
                    event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "completed"})
                    return

                placeholders = ",".join("?" * len(resolved_image_ids))
                rows = db.get_connector().query(
                    f"SELECT id, file_path, file_type FROM images WHERE id IN ({placeholders})",
                    tuple(resolved_image_ids),
                )

                id_to_path = {}
                for r in rows:
                    fp = r.get("file_path")
                    if not fp or not os.path.exists(fp):
                        continue
                    if not passes_nikon_nef_policy(fp, r.get("file_type")):
                        continue
                    try:
                        id_to_path[int(r["id"])] = fp
                    except (TypeError, ValueError, KeyError):
                        continue
                jobs = [
                    pipeline.ImageJob(
                        image_path=id_to_path[i],
                        job_id=job_id,
                        skip_existing=skip_existing,
                        target_phases=list(normalized_target_phases),
                    )
                    for i in resolved_image_ids
                    if i in id_to_path
                ]
                log(f"Selector mode: resolved {len(jobs)} images for scoring.")
                processor.process_list(jobs, job_id_override=job_id)
            else:
                processor.process_directory(input_dir=input_path, output_dir_unused=input_path, job_id=job_id)

            # Cleanup
            proc = self.current_processor
            self.current_processor = None
            stopped_early = bool(proc and getattr(proc, "stop_event", None) and proc.stop_event.is_set())
            if stopped_early or db.job_should_stop_processing(job_id):
                log("Processing stopped before completion.", "WARNING")
                try:
                    db.reconcile_stale_running_phases_for_jobs(
                        [job_id],
                        error_message=db.GRACEFUL_PAUSE_MSG,
                        in_flight_to="not_started",
                    )
                except Exception:
                    logger.exception("scoring: reconcile after stop failed (job_id=%s)", job_id)
                j = db.get_job(job_id)
                st = (j.get("status") or "").strip().lower() if j else ""
                if st == "running":
                    try:
                        db.update_job_status(job_id, "paused", "\n".join(self.log_history))
                    except Exception:
                        pass
                    j = db.get_job(job_id)
                event_manager.broadcast_threadsafe(
                    "job_completed",
                    {"job_id": job_id, "status": (j or {}).get("status") or "paused"},
                )
            else:
                log("Processing finished.")
                self._finalize_report(job_id, report_collector)
                db.update_job_status(job_id, "completed", "\n".join(self.log_history))
                event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "completed"})

        except Exception as e:
            log(f"Error: {e}", "ERROR")
            self.status_message = "Error in processing"
            self._finalize_report(job_id, report_collector)
            db.update_job_status(job_id, "failed", "\n".join(self.log_history))
            event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "failed", "error": str(e)})

        # Firebird .fdb file copy after run (same semantics as pre-run backup)
        _backup_msg = db.backup_database()
        if _backup_msg:
            log(_backup_msg)


    @staticmethod
    def _finalize_report(job_id, report_collector):
        """Finalize and save the execution report if a collector was provided."""
        if report_collector is None:
            return
        try:
            from modules.report_collector import finalize_and_save_report

            # Compute aggregate before/after score stats.
            aggregate_before = ScoringRunner._compute_aggregate_before(report_collector)
            aggregate_after = ScoringRunner._compute_aggregate_after(report_collector)

            finalize_and_save_report(
                job_id,
                report_collector.run_mode,
                [report_collector],
                aggregate_before=aggregate_before,
                aggregate_after=aggregate_after,
            )
        except Exception:
            logger.debug("Failed to finalize report for job %s", job_id, exc_info=True)

    @staticmethod
    def _compute_aggregate_before(collector):
        """Compute mean/stddev/incomplete from collector's pending before_snapshots."""
        from modules.report_collector import SCORE_SNAPSHOT_COLUMNS
        import statistics as _stats

        scores = []
        incomplete = 0
        for rec in collector.get_pending_records():
            snap = rec.get("before_snapshot")
            if snap is None:
                continue
            s = snap.get("score")
            if s is not None and isinstance(s, (int, float)):
                scores.append(float(s))
            for col in SCORE_SNAPSHOT_COLUMNS:
                if col in ("rating", "label"):
                    continue
                v = snap.get(col)
                if v is None or (isinstance(v, (int, float)) and v <= 0):
                    incomplete += 1
                    break

        if not scores:
            return None
        return {
            "score_mean": round(_stats.mean(scores), 4),
            "score_stddev": round(_stats.stdev(scores) if len(scores) > 1 else 0.0, 4),
            "incomplete_count": incomplete,
        }

    @staticmethod
    def _compute_aggregate_after(collector):
        """Compute after-aggregate by querying current DB state for processed images."""
        import statistics as _stats

        processed_ids = [
            rec["image_id"] for rec in collector.get_pending_records() if rec.get("action") == "processed"
        ]
        if not processed_ids:
            return None

        try:
            placeholders = ",".join("?" * len(processed_ids))
            rows = db.get_connector().query(
                f"SELECT score, score_spaq, score_ava, score_koniq, score_paq2piq, score_liqe "
                f"FROM images WHERE id IN ({placeholders})",
                tuple(processed_ids),
            )
        except Exception:
            return None

        scores = []
        incomplete = 0
        for r in rows or []:
            s = r.get("score")
            if s is not None:
                scores.append(float(s))
            for col in ("score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe"):
                v = r.get(col)
                if v is None or (isinstance(v, (int, float)) and v <= 0):
                    incomplete += 1
                    break

        if not scores:
            return None
        return {
            "score_mean": round(_stats.mean(scores), 4),
            "score_stddev": round(_stats.stdev(scores) if len(scores) > 1 else 0.0, 4),
            "incomplete_count": incomplete,
        }

    def stop(self):
        if self.current_processor:
            self.current_processor.stop_event.set()
            self.log_history.append("Stop signal sent...")

    def start_fix_db(self, job_id):
        """
        Starts DB fix in background thread.
        """
        with self._start_lock:
            if self.is_running:
                return "Error: Already running."

            self.is_running = True

        self.job_type = 'fix_db'
        self.log_history = []
        self.status_message = "Starting Fix DB..."
        
        def target():
            try:
                self._fix_db_internal(job_id)
            except Exception:
                logger.exception("ScoringRunner fix_db thread crashed (job_id=%s)", job_id)
                self.status_message = "Failed"
            finally:
                self.is_running = False
            if "Error" in self.status_message:
                self.status_message = "Failed"
            elif not self.status_message.startswith("Done"):
                self.status_message = "Done"

        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def _fix_db_internal(self, job_id):
        """
        Internal synchronous fix db runner.
        """
        db.update_job_status(job_id, "running")
        event_manager.broadcast_threadsafe("job_started", {"job_id": job_id, "job_type": "fix_db"})
        
        def log(msg):
            self.log_history.append(msg)

        if _musiq_import_error is not None:
            msg = f"Failed to import MultiModelMUSIQ: {_musiq_import_error}"
            log(msg)
            self.status_message = "Error loading models"
            db.update_job_status(job_id, "failed", msg)
            event_manager.broadcast_threadsafe(
                "job_completed",
                {"job_id": job_id, "status": "failed", "error": msg},
            )
            return

        # Circuit breaker: stop retrying after repeated failures
        if self._model_load_failures >= self._MODEL_LOAD_MAX_FAILURES:
            msg = (f"Model loading circuit breaker open: {self._model_load_failures} consecutive failures. "
                   f"Restart the WebUI to reset.")
            log(msg)
            self.status_message = "Error loading models (circuit breaker open)"
            db.update_job_status(job_id, "failed", msg)
            event_manager.broadcast_threadsafe(
                "job_completed",
                {"job_id": job_id, "status": "failed", "error": msg},
            )
            return

        records = db.get_incomplete_records()
        if not records:
            log("No incomplete records found.")
            db.update_job_status(job_id, "completed", "No incomplete records.")
            return

        log(f"Found {len(records)} incomplete records requiring fix.")
        self.status_message = "Fixing..."

        # Checking/Loading Models (Same as run_batch)
        if self.shared_scorer is None:
            log("Initializing models...")
            try:
                new_scorer = MultiModelMUSIQ()
                musiq_models = ['spaq', 'ava']
                all_loaded = True
                for model_name in musiq_models:
                    success = new_scorer.load_model(model_name)
                    if not success:
                        log(f"Warning: Failed to load {model_name}")
                        all_loaded = False

                if not all_loaded:
                    self._model_load_failures += 1
                    msg = f"One or more models failed to load (attempt {self._model_load_failures}/{self._MODEL_LOAD_MAX_FAILURES})"
                    log(msg)
                    self.status_message = "Error loading models"
                    db.update_job_status(job_id, "failed", msg)
                    return

                self.shared_scorer = new_scorer
                self._model_load_failures = 0  # Reset on success
            except Exception as e:
                self._model_load_failures += 1
                msg = f"Error loading models (attempt {self._model_load_failures}/{self._MODEL_LOAD_MAX_FAILURES}): {str(e)}"
                log(msg)
                self.status_message = "Error loading models"
                db.update_job_status(job_id, "failed", msg)
                return

        # Create Jobs
        jobs = []
        deleted_count = 0
        for row in records:
             file_path = row['file_path']
             if not os.path.exists(file_path):
                 log(f"Deleting missing file from DB: {file_path}")
                 db.delete_image(file_path)
                 deleted_count += 1
                 continue
                 
             job = pipeline.ImageJob(
                 image_path=file_path,
                 job_id=job_id,
                 skip_existing=False 
             )
             
             # Pre-fill external scores
             models = ['spaq', 'ava', 'liqe']
             for m in models:
                 key = f'score_{m}'
                 try:
                     val = row[key]
                     if val is not None and val > 0:
                         job.external_scores[m] = {
                             "score": val,
                             "normalized_score": val, 
                             "status": "success"
                         }
                 except (KeyError, IndexError):
                     pass
             
             try:
                 if row.get('image_hash'):
                     job.external_scores['image_hash'] = row['image_hash']
                     hv = row.get('hash_version')
                     if hv is not None:
                         job.external_scores['hash_version'] = int(hv)
             except (KeyError, IndexError):
                 pass
                 
             jobs.append(job)
        
        if deleted_count > 0:
             log(f"Removed {deleted_count} orphaned records from database.")
             
        if not jobs:
            log("No valid files found to process.")
            db.update_job_status(job_id, "completed", "No valid files.")
            return
            
        log(f"Queueing {len(jobs)} jobs for processing...")
        
        def on_progress(cur, tot):
            self.current_count = cur
            self.total_count = tot
            event_manager.broadcast_threadsafe(
                "job_progress",
                {"job_id": job_id, "job_type": "fix_db", "current": cur, "total": tot},
            )

        # Initialize processor
        processor = BatchImageProcessor(
            output_dir=None, # In-place update
            scorer=self.shared_scorer,
            progress_callback=on_progress
        )
        self.current_processor = processor
        processor.current_job_id = job_id
        
        def log_capture(msg):
            log(msg)
        processor.log_func = log_capture
        
        _backup_msg = db.backup_database()
        if _backup_msg:
            log(_backup_msg)

        try:
            processor.process_list(jobs, job_id_override=job_id)
            self.current_processor = None
            log("DB Fix finished.")
            db.update_job_status(job_id, "completed", "\n".join(self.log_history))
            event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "completed"})
            
        except Exception as e:
            log(f"Error: {e}")
            self.status_message = "Error in processing"
            db.update_job_status(job_id, "failed", "\n".join(self.log_history))
            event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "failed", "error": str(e)})


    def fix_image_metadata(self, file_path):
        """
        Recalculates scores and updates metadata for a single image 
        without running neural networks, using existing data.
        Returns: Success (bool), Message (str)
        """
        try:
            # 1. File Check
            if not os.path.exists(file_path):
                # Check if it was moved/renamed? 
                # For now just error out
                return False, f"File not found: {file_path}"
                
            # 2. Get existing DB data
            details = db.get_image_details(file_path)
            if not details:
                return False, "Image not found in database"
            
            # Helper to retrieve score from various places
            scores = {}
            # Try DB columns first
            for m in ['spaq', 'ava', 'liqe']:
                key = f'score_{m}'
                val = details.get(key)
                if val is not None and val > 0:
                    scores[m] = float(val)
            
            # Fallback to JSON if missing in cols
            if len(scores) < 5:
                try:
                    scores_json = details.get('scores_json')
                    if isinstance(scores_json, str):
                        s_data = json.loads(scores_json)
                        if 'models' in s_data:
                            for m, res in s_data['models'].items():
                                if m not in scores and res.get('status') == 'success':
                                    scores[m] = float(res.get('normalized_score', 0))
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                    pass
            
            # 3. Recalculate if we have enough data
            if not scores:
                return False, "No existing model scores found to recalculate from."

            result = snorm.compute_all(scores)
            tech = result["technical"]
            aes = result["aesthetic"]
            gen = result["general"]
            rating = result["rating"]
            label = result["label"]
            
            # 4. Update Database
            # We need to construct a partial update or update the whole record
            # Let's verify what DB fields correspond to
            
            # Update specific columns
            with db.connection() as conn:
                c = conn.cursor()
                
                c.execute("""
                    UPDATE images 
                    SET score_general = ?, score_aesthetic = ?, score_technical = ?,
                        rating = ?, label = ?
                    WHERE file_path = ?
                """, (gen, aes, tech, rating, label, file_path))
                
                # Also update scores_json summary if possible (complex text manipulation)
                # Maybe skip for now as columns are the source of truth for UI
                
                conn.commit()
            
            # 5. Write Metadata (XMP)
            # Use xmp module
            from modules import xmp
            is_raw = os.path.splitext(file_path)[1].lower() in ['.nef', '.nrw']
            
            # Retrieve additional metadata from DB
            title = details.get('title', '')
            description = details.get('description', '')
            keywords_str = details.get('keywords', '')
            keywords = [k.strip() for k in keywords_str.split(',')] if keywords_str else []
            
            success = xmp.write_metadata_unified(
                image_path=file_path,
                rating=rating,
                label=label,
                title=title,
                description=description,
                keywords=keywords,
                use_sidecar=True,
                use_embedded=is_raw
            )
            
            # 6. Regenerate Thumbnail (User Request)
            new_thumb = None
            thumb_warn = ""
            try:
                thumb_path = thumbnails.get_thumb_path(file_path)
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)

                new_thumb = thumbnails.generate_thumbnail(file_path)
                if new_thumb and details.get("id"):
                    db.update_image_thumbnail_paths(int(details["id"]), new_thumb, None)
            except Exception as e:
                print(f"Error regenerating thumbnail: {e}")
                thumb_warn = " [Thumb Gen Failed]"

            msg = f"Fixed: Gen={gen:.2f} ({rating}*), Tech={tech:.2f}, Aes={aes:.2f} ({label})"
            msg += thumb_warn
            if new_thumb:
                msg += " [Thumb Updated]"
            
            if not success:
               msg += " [XMP Write Failed]"
               
            return True, msg
            
        except Exception as e:
            return False, f"Error fixing image: {e}"


    def run_single_image(self, file_path):
        """
        Runs full scoring pipeline for a single image, blocking.
        Returns: success (bool), message (str)
        """
        import uuid
        job_id = f"manual_{uuid.uuid4().hex[:8]}"

        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        # Circuit breaker: stop retrying after repeated failures
        if self._model_load_failures >= self._MODEL_LOAD_MAX_FAILURES:
            return False, (f"Model loading circuit breaker open: {self._model_load_failures} consecutive failures. "
                          f"Restart the WebUI to reset.")

        self.status_message = "Scoring (Manual)..."

        # Initialize models if needed
        if self.shared_scorer is None:
            try:
                # MultiModelMUSIQ is imported via canonical package path at module import time.
                new_scorer = MultiModelMUSIQ()
                all_loaded = True
                for m in ['spaq', 'ava']:
                    success = new_scorer.load_model(m)
                    if not success:
                        all_loaded = False

                if not all_loaded:
                    self._model_load_failures += 1
                    return False, (f"One or more models failed to load (attempt {self._model_load_failures}/"
                                  f"{self._MODEL_LOAD_MAX_FAILURES})")

                self.shared_scorer = new_scorer
                self._model_load_failures = 0  # Reset on success
            except Exception as e:
                self._model_load_failures += 1
                return False, (f"Error initializing models (attempt {self._model_load_failures}/"
                              f"{self._MODEL_LOAD_MAX_FAILURES}): {e}")

        # Create Job
        from modules import pipeline
        job = pipeline.ImageJob(
            image_path=file_path,
            job_id=job_id,
            skip_existing=False
        )

        # Capture logs
        log_msgs = []
        def capture_log(msg):
            log_msgs.append(msg)
            
        # Create temporary processor
        processor = BatchImageProcessor(
            scorer=self.shared_scorer,
            progress_callback=lambda c, t: None
        )
        processor.log_func = capture_log
        processor.current_job_id = job_id
        
        try:
            # Create a dedicated job row in DB for manual scoring
            db_job_id = db.create_job(file_path, job_type="manual_scoring", status="running", runner_state="running")
            if db_job_id:
                job.job_id = db_job_id
                processor.current_job_id = db_job_id

            processor.process_list([job], job_id_override=(db_job_id or job_id))
            
            # Check result
            # Retrieve latest data to confirm
            details = db.get_image_details(file_path)
            gen = details.get('score_general', 0)
            
            if db_job_id:
                db.update_job_status(db_job_id, "completed", runner_state="completed")
            self.status_message = "Idle"
            return True, f"Scoring Complete. General Score: {gen:.2f}"
            
        except Exception as e:
            if db_job_id:
                try:
                    db.update_job_status(db_job_id, "failed", error=str(e), runner_state="error")
                except Exception as update_err:
                    logger.error("Failed to mark job %s as failed: %s", db_job_id, update_err)
            self.status_message = "Error"
            return False, f"Error running scoring: {e}"
