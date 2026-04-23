
import os
import queue
import time
import threading
import logging
from datetime import datetime
from modules import pipeline, db, config
from modules.indexing_policy import (
    discovery_extensions,
    path_is_indexing_excluded,
    prune_indexing_excluded_walk_dirs,
)

class BatchImageProcessor:
    """
    Refactored Batch Processor using Threaded Pipeline.
    """
    def __init__(self, output_dir=None, skip_existing=False, write_json=False, 
                 json_stdout=False, skip_predicate=None, scorer=None, progress_callback=None,
                 target_phases=None, liqe_scorer=None):
        self.output_dir = output_dir
        self.skip_existing = skip_existing
        self.scorer = scorer
        self.liqe_scorer = liqe_scorer
        self.logger = logging.getLogger(__name__)
        self.stop_event = threading.Event()
        self.progress_callback = progress_callback
        self.processed_count = 0
        self.total_count = 0
        self.target_phases = target_phases or []
        self._folder_agg_dirty_ids = set()

    def _flush_folder_phase_aggregates(self):
        """Apply batched folder phase_agg_dirty updates after scoring batch."""
        if not self._folder_agg_dirty_ids:
            return
        for fid in list(self._folder_agg_dirty_ids):
            try:
                db.invalidate_folder_phase_aggregates(folder_id=fid)
            except Exception:
                pass
        self._folder_agg_dirty_ids.clear()
        
    def log(self, msg, level="INFO"):
        lvl = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(lvl, msg)
        if getattr(self, "log_func", None):
            try:
                self.log_func(msg, level)
            except TypeError:
                try:
                    self.log_func(msg)
                except Exception:
                    pass
            except Exception:
                pass

    def _on_item_finished(self):
        self.processed_count += 1
        if self.progress_callback:
            self.progress_callback(self.processed_count, self.total_count)

    def get_pipeline_depth(self):
        """Returns the number of images currently held in internal pipeline queues."""
        total = 0
        for q in (
            getattr(self, "_prep_queue", None),
            getattr(self, "_scoring_queue", None),
            getattr(self, "_result_queue", None),
        ):
            if q is not None:
                try:
                    total += q.qsize()
                except NotImplementedError:
                    pass
        return total

    def process_directory(self, input_dir, output_dir_unused, callback=None, job_id=None):
        """
        Main entry point for batch processing.
        """
        # 1. Setup
        if not self.scorer:
            self.log("Error: Scorer not provided!", "ERROR")
            return

        # 2. Find Images
        # 2. Find Images (using os.walk for folder-level control)
        # import glob # No longer used
        extensions = discovery_extensions()
        files = []
        visited_folders = set()
        
        # Normalize input_dir
        input_dir = os.path.normpath(input_dir)
        
        for root, dirs, filenames in os.walk(input_dir):
            prune_indexing_excluded_walk_dirs(root, dirs)
            # Check folder flag if we are skipping existing
            if self.skip_existing:
                try:
                    if db.is_folder_scored(root):
                        # One-time validation: does the flag still hold?
                        if not db.check_and_update_folder_status(root):
                            # Flag was stale; don't skip — fall through to scan.
                            pass
                        else:
                            self.log(f"Skipping fully scored folder: {root}")
                            # We do not process files in this folder.
                            # We DO continue into subdirectories (os.walk default), 
                            # because they might not be scored.
                            continue
                except Exception as e:
                    self.log(f"Error checking folder status for {root}: {e}", "WARNING")

            # Broadcast folder discovery
            try:
                from modules.events import event_manager
                event_manager.broadcast_threadsafe("folder_discovered", {"path": root})
            except Exception: pass

            visited_folders.add(root)
            
            for filename in filenames:
                file_path = os.path.join(root, filename)
                if path_is_indexing_excluded(file_path):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext in extensions:
                    files.append(file_path)
                    # Broadcast image discovery
                    try:
                        from modules.events import event_manager
                        event_manager.broadcast_threadsafe("image_discovered", {"path": file_path})
                    except Exception: pass

        files = sorted(list(set(files))) # Dedup just in case

        
        if not files:
            self.log("No images found.")
            # Update flags for visited (e.g. empty) folders as they might be "done" (empty)
            if visited_folders:
                self.log("Verifying empty folders...")
                for f in visited_folders:
                     try: db.check_and_update_folder_status(f)
                     except Exception: pass
            return

        self.log(f"Found {len(files)} images to process.")
        
        self.total_count = len(files)
        self.processed_count = 0
        self._folder_agg_dirty_ids.clear()
        if self.progress_callback:
            self.progress_callback(0, self.total_count)
        
        # 3. Setup Queues and Workers
        # Load queue sizes from config
        processing_config = config.get_config_section('processing')
        prep_queue_size = processing_config.get('prep_queue_size', 50)
        scoring_queue_size = processing_config.get('scoring_queue_size', 10)
        result_queue_size = processing_config.get('result_queue_size', 50)
        
        prep_queue = queue.Queue(maxsize=int(prep_queue_size))
        scoring_queue = queue.Queue(maxsize=int(scoring_queue_size)) # Keep small to avoid VRAM overload if buffering
        result_queue = queue.Queue(maxsize=int(result_queue_size)) # Just for sync
        self._prep_queue = prep_queue
        self._scoring_queue = scoring_queue
        self._result_queue = result_queue

        self.stop_event.clear()
        
        # Workers
        prep_worker = pipeline.PrepWorker(prep_queue, scoring_queue, self.stop_event, self.scorer)
        scoring_worker = pipeline.ScoringWorker(
            scoring_queue, result_queue, self.stop_event, self.scorer, liqe_scorer=self.liqe_scorer
        )
        
        # Result callback wrapper — self.log() forwards to log_func when set (ScoringRunner), so per-image progress appears in UI console
        def result_logger(msg, level="INFO"):
            self.log(msg, level)
            
        result_worker = pipeline.ResultWorker(
            result_queue,
            None,
            self.stop_event,
            scorer_instance=self.scorer,
            progress_callback=result_logger,
            item_finished_callback=self._on_item_finished,
            folder_agg_dirty_ids=self._folder_agg_dirty_ids,
        )
        # Attach report collector to result worker for after-snapshot recording.
        result_worker.report_collector = getattr(self, "report_collector", None)

        workers = [prep_worker, scoring_worker, result_worker]
        for w in workers:
            w.start()
            
        # 4. Feed the Beast
        # Creates a Job ID for this batch run (optional, or per file?)
        # db.py create_job was called by webui. 
        # But upsert_image needs a job_id. 
        # We need to pass the job_id down.
        # Wait, the current architecture passed `job_id` into `run_batch` in `scoring.py`.
        # But `process_directory` doesn't accept `job_id`. 
        # We need to hack/fix this.
        # I'll update `process_directory` signature or assume we can get it.
        # Actually `scoring.py` calls `process_directory`.
        
        # HACK: Retrieve job_id from somewhere or update signature?
        # Update signature is better but requires changing base class or calls.
        # Let's check `scoring.py` again. It calls `processor.process_directory`.
        # I can update `scoring.py` to inject job_id into the processor instance OR pass it.
        # I will inject it into the processor instance before calling process_directory.
        
        current_job_id = job_id or getattr(self, "current_job_id", 0) 
        
        for i, f in enumerate(files):
            if self.stop_event.is_set():
                break
            if current_job_id and db.job_should_stop_processing(current_job_id):
                self.stop_event.set()
                break

            job = pipeline.ImageJob(
                image_path=f,
                job_id=current_job_id,
                skip_existing=self.skip_existing,
                target_phases=self.target_phases
            )
            
            while not self.stop_event.is_set():
                try:
                    prep_queue.put(job, timeout=2.0)
                    break  # successfully enqueued
                except queue.Full:
                    continue  # retry same job
                except KeyboardInterrupt:
                    self.stop_event.set()
                    break
                
        # 5. Wait for completion
        # Send sentinels
        if not self.stop_event.is_set():
            prep_queue.put(None)
        
        # Wait for workers
        prep_worker.join()
        # After prep is done, it sends sentinel to scoring
        # Wait for scoring
        scoring_queue.put(None) # Safety incase prep didn't? No, Prep logic should.
        # Actually my PrepWorker implementation sends None when it gets None.
        
        scoring_worker.join()
        result_queue.put(None) # Sentinel for result
        result_worker.join()

        self._flush_folder_phase_aggregates()
        
        # 6. Update Folder Flags
        if visited_folders:
            self.log("Updating folder completion flags...")
            for f in visited_folders:
                 try:
                     db.check_and_update_folder_status(f)
                 except Exception as e:
                     self.log(f"Failed to update status for {f}: {e}", "WARNING")

        self.log("Batch processing finished.")

    def process_list(self, jobs_list, job_id_override=None):
        """
        Process a specific list of ImageJob objects.
        """
        if not self.scorer:
            self.log("Error: Scorer not provided!", "ERROR")
            return
            
        if not jobs_list:
            self.log("No jobs to process.")
            return
            
        self.log(f"Processing list of {len(jobs_list)} images...")
        self.total_count = len(jobs_list)
        self.processed_count = 0
        self._folder_agg_dirty_ids.clear()
        if self.progress_callback:
             self.progress_callback(0, self.total_count)
        
        # Setup Queues
        # Load queue sizes from config
        processing_config = config.get_config_section('processing')
        prep_queue_size = processing_config.get('prep_queue_size', 50)
        scoring_queue_size = processing_config.get('scoring_queue_size', 10)
        result_queue_size = processing_config.get('result_queue_size', 50)
        
        prep_queue = queue.Queue(maxsize=int(prep_queue_size))
        scoring_queue = queue.Queue(maxsize=int(scoring_queue_size))
        result_queue = queue.Queue(maxsize=int(result_queue_size))
        
        self.stop_event.clear()
        
        # Workers
        prep_worker = pipeline.PrepWorker(prep_queue, scoring_queue, self.stop_event, self.scorer)
        scoring_worker = pipeline.ScoringWorker(
            scoring_queue, result_queue, self.stop_event, self.scorer, liqe_scorer=self.liqe_scorer
        )
        
        def result_logger(msg, level="INFO"):
             if hasattr(self, "log_func") and self.log_func:
                 try:
                     self.log_func(msg, level)
                 except TypeError:
                     self.log_func(msg)
             else:
                 self.log(msg, level)

        result_worker = pipeline.ResultWorker(
            result_queue,
            None,
            self.stop_event,
            scorer_instance=self.scorer,
            progress_callback=result_logger,
            item_finished_callback=self._on_item_finished,
            folder_agg_dirty_ids=self._folder_agg_dirty_ids,
        )
        # Attach report collector to result worker for after-snapshot recording.
        result_worker.report_collector = getattr(self, "report_collector", None)

        workers = [prep_worker, scoring_worker, result_worker]
        for w in workers:
            w.start()

        # Feed jobs
        for job in jobs_list:
            if self.stop_event.is_set():
                break
            if job_id_override and db.job_should_stop_processing(job_id_override):
                self.stop_event.set()
                break

            # Ensure job has correct ID if overridden
            if job_id_override:
                job.job_id = job_id_override
            
            try:
                prep_queue.put(job, timeout=2.0)
                while prep_queue.full() and not self.stop_event.is_set():
                     time.sleep(0.1)
            except KeyboardInterrupt:
                self.stop_event.set()
                break
                
        # Wait for completion
        if not self.stop_event.is_set():
            prep_queue.put(None)
            
        prep_worker.join()
        scoring_queue.put(None)
        scoring_worker.join()
        result_queue.put(None)
        result_worker.join()

        self._flush_folder_phase_aggregates()
        
        self.log("List processing finished.")
