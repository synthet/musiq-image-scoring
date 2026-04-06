import os
import threading
import logging
from typing import List, Dict, Optional
from modules import db, thumbnails, xmp, exif_extractor
from modules.version import APP_VERSION
from modules.phases import PhaseCode, PhaseStatus
from modules.events import event_manager, broadcast_run_log_line
from modules.indexing_policy import filter_image_rows_for_nef_policy

logger = logging.getLogger(__name__)

METADATA_VERSION = "1.0.0"

class MetadataRunner:
    """
    Independent runner for the Metadata (Inspection) phase.
    Extracts EXIF/XMP, generates thumbnails, and updates `images` and junction tables.
    """
    def __init__(self):
        self.stop_event = threading.Event()
        self.is_running = False
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0

    def get_status(self):
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def start_batch(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None):
        if self.is_running:
            return "Error: Already running."
            
        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0
        
        if job_id is None:
            job_id = db.create_job(input_path or "ALL_IMAGES_METADATA", job_type="metadata")
            
        def target():
            try:
                self._run_batch_internal(input_path, job_id, skip_existing, resolved_image_ids)
            except Exception:
                logger.exception("MetadataRunner thread crashed (job_id=%s)", job_id)
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

    def _run_batch_internal(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None):
        def log(msg):
            self.log_history.append(msg)
            if job_id:
                broadcast_run_log_line(job_id, msg)

        # Handle WSL path conversion if needed
        if input_path and ":" in input_path and len(input_path) > 1 and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            if os.path.exists("/mnt/") and os.path.exists(wsl_path):
                input_path = wsl_path

        self.stop_event.clear()
        log(f"Starting Metadata process on {input_path or 'Selected Images'}...")
        self.status_message = "Running..."
        
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "metadata", 
                "input_path": input_path
            })

        def fail_terminal(error_summary: str):
            self.status_message = error_summary
            if job_id:
                db.update_job_status(job_id, "failed", "\n".join(self.log_history))
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id,
                    "status": "failed",
                    "error": error_summary,
                })

        all_images = []
        
        if resolved_image_ids is not None:
             try:
                 rows = db.get_all_images(limit=-1)
                 selected_ids = {int(i) for i in resolved_image_ids}
                 all_images = [row for row in rows if row.get('id') in selected_ids]
                 log(f"Selector mode enabled. Matched {len(all_images)} images by ID.")
             except Exception as e:
                 log(f"Error fetching from DB: {e}")
                 fail_terminal("Error DB")
                 return
        elif not input_path or not input_path.strip():
             log("Input path empty. Processing all missing metadata in DB...")
             try:
                 # TODO: A better query would fetch images without metadata IPS done.
                 rows = db.get_all_images(limit=-1)
                 all_images = rows
             except Exception as e:
                 log(f"Error fetching from DB: {e}")
                 fail_terminal("Error DB")
                 return
        elif os.path.isdir(input_path):
             all_images = db.get_images_by_folder(input_path)
        else:
             # Just one file?
             row = db.get_image_details(input_path)
             if row:
                 all_images = [row]
             else:
                 log(f"Input path not found in DB: {input_path}")
                 fail_terminal("Error Path")
                 return

        all_images = filter_image_rows_for_nef_policy(all_images)
        log(f"Found {len(all_images)} images to potentially process.")
        self.total_count = len(all_images)
        self.current_count = 0
        
        processed_count = 0
        skipped_count = 0
        
        for row in all_images:
            if self.stop_event.is_set():
                log("Metadata runner stopped by user.")
                break
                
            self.current_count += 1
            image_id = row['id']
            file_path = row['file_path']
            
            if skip_existing:
                # Check if 'metadata' phase is already DONE
                phase_status = db.get_image_phase_status(image_id, PhaseCode.METADATA)
                if phase_status and phase_status.get('status') == PhaseStatus.DONE:
                    skipped_count += 1
                    continue

            db.set_image_phase_status(
                image_id,
                PhaseCode.METADATA,
                PhaseStatus.RUNNING,
                app_version=APP_VERSION,
                executor_version=METADATA_VERSION,
                job_id=job_id
            )

            try:
                # 1. Image Identity (UUID)
                image_uuid = row.get("uuid")
                if not image_uuid:
                    temp_exif = exif_extractor.extract_exif(file_path)
                    image_uuid = db.generate_image_uuid(temp_exif)
                    
                # 2. Physical Metadata Sync (EXIF + XMP)
                exif_extractor.ensure_image_unique_id(file_path, image_uuid)
                xmp.write_image_unique_id(file_path, image_uuid)
                
                # 3. Database Sync (IMAGE_EXIF + IMAGE_XMP)
                exif_extractor.extract_and_upsert_exif(file_path, image_id)
                xmp.extract_and_upsert_xmp(file_path, image_id)
                db.update_image_uuid(image_id, image_uuid)

                # 4. Thumbnails creation
                thumb = thumbnails.get_thumb_path(file_path)
                if not os.path.exists(thumb):
                    generated = thumbnails.generate_thumbnail(file_path)
                    if generated:
                        thumb = generated
                if thumb and os.path.isfile(thumb):
                    db.update_image_thumbnail_paths(image_id, thumb, None)

                # 5. Update Status
                db.set_image_phase_status(
                    image_id,
                    PhaseCode.METADATA,
                    PhaseStatus.DONE,
                    app_version=APP_VERSION,
                    executor_version=METADATA_VERSION,
                    job_id=job_id
                )
                processed_count += 1

            except Exception as e:
                log(f"Error processing {file_path}: {e}")
                skipped_count += 1
                try:
                    db.set_image_phase_status(
                        image_id,
                        PhaseCode.METADATA,
                        PhaseStatus.FAILED,
                        app_version=APP_VERSION,
                        executor_version=METADATA_VERSION,
                        job_id=job_id,
                        error=str(e),
                    )
                except Exception:
                    pass

            if self.current_count % 50 == 0:
                event_manager.broadcast_threadsafe(
                    "job_progress",
                    {
                        "job_id": job_id,
                        "job_type": "metadata",
                        "phase_code": "metadata",
                        "current": self.current_count,
                        "total": self.total_count,
                    },
                )
                
        log(f"Done. Processed: {processed_count}, Skipped: {skipped_count}")

        try:
            seen_parents = set()
            for row in all_images:
                fp = row.get("file_path")
                if not fp:
                    continue
                parent = os.path.normpath(os.path.dirname(fp))
                if parent and parent not in seen_parents:
                    seen_parents.add(parent)
                    db.invalidate_folder_phase_aggregates(folder_path=parent)
            if not all_images and input_path and os.path.isdir(input_path):
                db.invalidate_folder_phase_aggregates(folder_path=input_path)
        except Exception:
            logger.exception("MetadataRunner: invalidate_folder_phase_aggregates after batch failed")

        if job_id:
            job = db.get_job(job_id)
            st = (job.get("status") or "").strip().lower() if job else ""
            if st not in db.JOB_TERMINAL_STATES:
                db.update_job_status(job_id, "completed")

    def stop(self):
        self.stop_event.set()
