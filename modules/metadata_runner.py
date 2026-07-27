import logging
import os
import threading

from modules import db, exif_extractor, thumbnails, utils, xmp
from modules.events import event_manager
from modules.indexing_policy import filter_image_rows_for_nef_policy
from modules.phases import PhaseCode, PhaseStatus
from modules.run_log import runner_emit
from modules.version import APP_VERSION

logger = logging.getLogger(__name__)

METADATA_VERSION = "1.0.0"
PROGRESS_INTERVAL = 50

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

    def start_batch(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: list[int] = None, report_collector=None):
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
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                try:
                    from modules.pipeline_diagnostics import phase_timer
                    with phase_timer("MetadataRunner.batch", job_id):
                        self._run_batch_internal(input_path, job_id, skip_existing, resolved_image_ids, report_collector=report_collector)
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


    def _process_metadata_image_row(
        self,
        row,
        *,
        skip_existing,
        job_id,
        report_collector,
        log,
        processed_count,
        skipped_count,
    ):
        """Process one item in a batch run."""
        self.current_count += 1

        image_id = row['id']

        original_path = row['file_path']

        local_path = utils.convert_path_to_local(original_path)



        if skip_existing:

            # Check if 'metadata' phase is already DONE

            phase_status = db.get_image_phase_status(image_id, PhaseCode.METADATA)

            if phase_status and phase_status.get('status') == PhaseStatus.DONE:

                asset_gap = db.get_image_metadata_asset_gap_reason(image_id)

                if not asset_gap:

                    skipped_count += 1

                    if report_collector:

                        report_collector.record_skip(image_id, "metadata_already_done")

                    log(f"Skip (metadata done): {original_path}", "DEBUG", image_id=image_id)

                    if self.current_count % PROGRESS_INTERVAL == 0:

                        log(

                            f"Progress {self.current_count}/{self.total_count} "

                            f"(processed={processed_count}, skipped={skipped_count})",

                            "INFO",

                        )

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

                    return processed_count, skipped_count

                log(

                    f"Re-run metadata (asset gap={asset_gap}): {original_path}",

                    "DEBUG",

                    image_id=image_id,

                )



        db.set_image_phase_status(

            image_id,

            PhaseCode.METADATA,

            PhaseStatus.RUNNING,

            app_version=APP_VERSION,

            executor_version=METADATA_VERSION,

            job_id=job_id

        )



        if not local_path or not os.path.isfile(local_path):

            path_error = (

                f"Local path unavailable for metadata processing. "

                f"original_path='{original_path}', local_path='{local_path}'"

            )

            log(path_error, "ERROR", image_id=image_id)

            skipped_count += 1

            if report_collector:

                report_collector.record_failure(image_id, path_error)

            try:

                db.set_image_phase_status(

                    image_id,

                    PhaseCode.METADATA,

                    PhaseStatus.FAILED,

                    app_version=APP_VERSION,

                    executor_version=METADATA_VERSION,

                    job_id=job_id,

                    error=path_error,

                )

            except Exception:

                logger.exception(

                    "metadata_runner: failed to mark image %s FAILED for missing local path",

                    image_id,

                )

            return processed_count, skipped_count



        try:

            log(

                f"Metadata: EXIF/XMP/thumbnail for image_id={image_id}, "

                f"original_path={original_path}, local_path={local_path}",

                "DEBUG",

                image_id=image_id,

            )

            # 1. Image Identity (UUID)

            image_uuid = row.get("uuid")

            if not image_uuid:

                temp_exif = exif_extractor.extract_exif(local_path)

                image_uuid = db.generate_image_uuid(temp_exif)



            # 2. Physical Metadata Sync (EXIF + XMP)

            exif_extractor.ensure_image_unique_id(local_path, image_uuid)

            xmp.write_image_unique_id(local_path, image_uuid)



            # 3. Database Sync (IMAGE_XMP first so sidecar shot dates exist alongside EXIF cache)

            xmp.extract_and_upsert_xmp(local_path, image_id)

            exif_extractor.extract_and_upsert_exif(local_path, image_id)

            db.update_image_uuid(image_id, image_uuid)



            # 4. Thumbnails creation

            thumb = thumbnails.get_thumb_path(local_path)

            if not os.path.exists(thumb):

                generated = thumbnails.generate_thumbnail(local_path)

                if generated:

                    thumb = generated

            thumb_written = False

            if thumb and os.path.isfile(thumb):

                thumb_written = bool(db.update_image_thumbnail_paths(image_id, thumb, None))



            if not thumb_written:

                thumb_error = "thumbnail_generation_failed"

                log(thumb_error, "ERROR", image_id=image_id)

                skipped_count += 1

                if report_collector:

                    report_collector.record_failure(image_id, thumb_error)

                db.set_image_phase_status(

                    image_id,

                    PhaseCode.METADATA,

                    PhaseStatus.FAILED,

                    app_version=APP_VERSION,

                    executor_version=METADATA_VERSION,

                    job_id=job_id,

                    error=thumb_error,

                )

                return processed_count, skipped_count



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

            if report_collector:

                report_collector.record_after(image_id, {}, action="processed")

            log(f"Metadata done: {original_path}", "DEBUG", image_id=image_id)



        except Exception as e:

            log(

                f"Error processing original_path={original_path}, "

                f"local_path={local_path}: {e}",

                "ERROR",

                image_id=image_id,

            )

            skipped_count += 1

            if report_collector:

                report_collector.record_failure(image_id, str(e))

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



        if self.current_count % PROGRESS_INTERVAL == 0:

            log(

                f"Progress {self.current_count}/{self.total_count} "

                f"(processed={processed_count}, skipped={skipped_count})",

                "INFO",

            )

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

        return processed_count, skipped_count

    def _run_batch_internal(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: list[int] = None, report_collector=None):
        def log(msg: str, level: str = "INFO", image_id: int | None = None) -> None:
            runner_emit(self.log_history, job_id, msg, level, phase="metadata", image_id=image_id)

        # Handle WSL path conversion if needed (e.g. running on Windows but path is /mnt/d/...)
        converted = utils.convert_path_to_local(input_path)
        if converted != input_path:
            log(f"Normalized path: {input_path} -> {converted}", "DEBUG")
            input_path = converted

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
                 log(f"Error fetching from DB: {e}", "ERROR")
                 fail_terminal("Error DB")
                 return
        elif not input_path or not input_path.strip():
             log("Input path empty. Processing all missing metadata in DB...")
             try:
                 # TODO: A better query would fetch images without metadata IPS done.
                 rows = db.get_all_images(limit=-1)
                 all_images = rows
             except Exception as e:
                 log(f"Error fetching from DB: {e}", "ERROR")
                 fail_terminal("Error DB")
                 return
        elif os.path.isdir(input_path):
             # Clear stale folder images cache — indexing may have invalidated
             # under different cache keys (WSL vs Windows path normalization).
             db.invalidate_folder_images_cache()
             all_images = db.get_images_by_folder(input_path)
             if not all_images:
                 # Fallback: recursive lookup across subfolders, matching how
                 # get_folder_phase_summary counts images for status reporting.
                 scope_path = input_path
                 local = utils.convert_path_to_local(scope_path)
                 if local and os.path.isdir(local):
                     scope_path = local
                 seen_ids = set()
                 for folder_path in db.list_folder_paths_under_scope(scope_path):
                     for row in db.get_images_by_folder(folder_path) or []:
                         iid = row.get("id")
                         if iid is not None and iid not in seen_ids:
                             seen_ids.add(iid)
                             all_images.append(row)
                 if all_images:
                     log(f"Recursive fallback found {len(all_images)} images "
                         f"across subfolders of {input_path}", "INFO")
        else:
             # Just one file?
             row = db.get_image_details(input_path)
             if row:
                 all_images = [row]
             else:
                 log(f"Input path not found in DB: {input_path}", "ERROR")
                 fail_terminal("Error Path")
                 return

        all_images = filter_image_rows_for_nef_policy(all_images)

        # Defensive guard: if scope resolution returned an empty list but the
        # target folder demonstrably has indexed images, the runner would
        # silently mark this phase complete with zero work and the orchestrator
        # would advance — leaving an entire folder un-touched until a Heal job
        # caught up days later (job 2140 vs heal job 2158 on folder
        # /mnt/d/Photos/Z8/180-600mm/2026/2026-05-03). Treat the mismatch as a
        # hard failure so the operator can investigate path/folder_id drift.
        if (
            resolved_image_ids is None
            and not all_images
            and input_path
            and os.path.isdir(input_path)
        ):
            try:
                folder_image_count = db.get_image_count(folder_path=input_path)
            except Exception:
                folder_image_count = 0
                logger.exception(
                    "metadata_runner: get_image_count probe failed for %s",
                    input_path,
                )
            if folder_image_count > 0:
                msg = (
                    f"Metadata scope resolved to 0 images, but folder {input_path!r} "
                    f"contains {folder_image_count} indexed images. Refusing to "
                    "silently complete this phase — investigate path normalization "
                    "or folder_id mismatch before re-running."
                )
                log(msg, "ERROR")
                fail_terminal("Error Empty Scope")
                return

        log(f"Found {len(all_images)} images to potentially process.")
        self.total_count = len(all_images)
        self.current_count = 0

        if report_collector is not None:
            targeted = len(resolved_image_ids) if resolved_image_ids is not None else len(all_images)
            report_collector.set_scope_counts(in_scope=len(all_images), targeted=targeted)

        processed_count = 0
        skipped_count = 0
        
        for row in all_images:
            if self.stop_event.is_set():
                log("Metadata runner stopped by user.", "WARNING")
                break
            if job_id and db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("Metadata runner paused (job status).", "WARNING")
                break


            processed_count, skipped_count = self._process_metadata_image_row(
                row,
                skip_existing=skip_existing,
                job_id=job_id,
                report_collector=report_collector,
                log=log,
                processed_count=processed_count,
                skipped_count=skipped_count,
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
            if self.stop_event.is_set() or db.job_should_stop_processing(job_id):
                try:
                    db.reconcile_stale_running_phases_for_jobs(
                        [job_id],
                        error_message=db.GRACEFUL_PAUSE_MSG,
                        in_flight_to="not_started",
                    )
                except Exception:
                    logger.exception("metadata: reconcile after stop failed (job_id=%s)", job_id)
                j = db.get_job(job_id)
                st = (j.get("status") or "").strip().lower() if j else ""
                if st == "running":
                    try:
                        db.update_job_status(job_id, "paused", "\n".join(self.log_history))
                    except Exception:
                        pass
            else:
                self._finalize_report(job_id, report_collector)
                job = db.get_job(job_id)
                st = (job.get("status") or "").strip().lower() if job else ""
                if st not in db.JOB_TERMINAL_STATES:
                    db.update_job_status(job_id, "completed")

    @staticmethod
    def _finalize_report(job_id, report_collector):
        if report_collector is None:
            return
        try:
            from modules.report_collector import finalize_and_save_report
            finalize_and_save_report(job_id, report_collector.run_mode, [report_collector])
        except Exception:
            logger.debug("Failed to finalize report for job %s", job_id, exc_info=True)

    def stop(self):
        self.stop_event.set()
