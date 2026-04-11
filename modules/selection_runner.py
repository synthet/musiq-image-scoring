"""
SelectionRunner - Run/stop/status interface for the Selection tab.

Matches Scoring/Keywords runner contract for polling-based UI integration.
"""

import logging
import os
import threading
from modules.selection import SelectionService, SelectionConfig
from modules import db
from modules import utils
from modules.events import event_manager
from modules.run_log import runner_emit
from modules.phases import PhaseCode, PhaseStatus
from modules.phases_policy import explain_phase_run_decision
from modules.version import APP_VERSION

logger = logging.getLogger(__name__)


class SelectionRunner:
    """
    Runs Selection workflow in a background thread.
    Contract: start_batch, stop, get_status (running, log, status_msg, cur, tot)
    """

    def __init__(self):
        self._service = SelectionService()
        self._lock = threading.Lock()
        self.is_running = False
        self._log_history: list[str] = []
        self._status_message = "Idle"
        self._current_count = 0
        self._total_count = 0
        self._thread: threading.Thread | None = None

    def get_status(self) -> tuple[bool, str, str, int, int]:
        """Returns (is_running, log_text, status_message, current, total)."""
        with self._lock:
            log_text = "\n".join(self._log_history)
            return (
                self.is_running,
                log_text,
                self._status_message,
                self._current_count,
                self._total_count,
            )

    def start_batch(self, input_path: str, job_id: int = None, force_rescan: bool = False) -> str:
        """Starts Selection in a background thread. Non-blocking."""
        with self._lock:
            if self.is_running:
                return "Error: Already running."

            self.is_running = True
            self._log_history = []
            self._status_message = "Starting..."
            self._current_count = 0
            self._total_count = 0

        if job_id is None:
            job_id = db.create_job(input_path or "ALL_IMAGES_SELECTION")

        def target():
            try:
                self._run_internal(input_path, force_rescan, job_id=job_id)
            except Exception:
                logger.exception("SelectionRunner thread crashed (job_id=%s)", job_id)
                with self._lock:
                    self._status_message = "Failed"
            finally:
                with self._lock:
                    self.is_running = False

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return "Started"

    def _run_internal(self, input_path: str, force_rescan: bool, job_id: int = None):
        
        def log(msg: str, level: str = "INFO") -> None:
            with self._lock:
                runner_emit(self._log_history, job_id, msg, level, phase="culling")

        def progress_cb(pct: float, msg: str, cur: int | None = None, tot: int | None = None):
            with self._lock:
                self._status_message = msg
                if cur is not None and tot is not None and tot > 0:
                    self._current_count = cur
                    self._total_count = tot
                else:
                    self._total_count = 100
                    self._current_count = int(pct * 100)
                runner_emit(self._log_history, job_id, msg, "INFO", phase="culling")
                if len(self._log_history) > 200:
                    self._log_history.pop(0)

            if job_id:
                event_manager.broadcast_threadsafe("job_progress", {
                    "job_id": job_id,
                    "job_type": "selection",
                    "phase_code": "culling",
                    "current": self._current_count,
                    "total": self._total_count,
                    "message": msg
                })

        log("Starting Selection workflow...")
        log(f"Input: {input_path}")
        log("-" * 20)
        
        # Notify job started
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "selection", 
                "input_path": input_path
            })

        images = []
        images_for_phase = []
        try:
            local_scope = utils.convert_path_to_local((input_path or "").strip())
            seen_ids: set[int] = set()
            if local_scope and os.path.isdir(local_scope):
                for folder_path in db.list_folder_paths_under_scope(local_scope):
                    for row in db.get_images_by_folder(folder_path) or []:
                        iid = row.get("id")
                        if iid is None or iid in seen_ids:
                            continue
                        seen_ids.add(iid)
                        images.append(row)
            if not images:
                images = db.get_images_by_folder(input_path) or []
            if images:
                if force_rescan:
                    # Skip per-image phase updates: clustering will set RUNNING when it processes.
                    # Avoids ~10k DB calls for large folders (3256 images × 3 calls each).
                    images_for_phase = images
                else:
                    for img in images:
                        decision = explain_phase_run_decision(
                            img['id'],
                            PhaseCode.CULLING,
                            current_executor_version="1.0.0",
                            force_run=False,
                        )
                        if decision['should_run']:
                            images_for_phase.append(img)
                            db.set_image_phase_status(
                                img['id'],
                                PhaseCode.CULLING,
                                PhaseStatus.RUNNING,
                                app_version=APP_VERSION,
                                executor_version="1.0.0",
                                job_id=job_id,
                            )
        except Exception as pe:
            log(f"Phase status pre-run update error: {pe}")

        skipped_by_policy = max(0, len(images) - len(images_for_phase))
        if skipped_by_policy:
            log(
                f"Culling: skipping re-run for {skipped_by_policy} image(s) (already current); "
                f"{len(images_for_phase)} image(s) will be driven through clustering for this run."
            )

        if job_id and db.job_should_stop_processing(job_id):
            log("Selection/culling skipped: job already paused or canceled.")
            return

        cfg = SelectionConfig(force_rescan=force_rescan)
        log(
            f"Starting clustering for {len(images_for_phase)} of {len(images)} image(s) in scope "
            f"(force_rescan={force_rescan})..."
        )
        try:
            # SelectionService operates at folder scope; phase status updates are limited
            # to policy-eligible images tracked in images_for_phase.
            summary = self._service.run(input_path, cfg=cfg, progress_cb=progress_cb)
            
            if summary.status == "stopped":
                log("Selection stopped gracefully. Skipping finalization.", "WARNING")
                with self._lock:
                    self._status_message = "stopped"
                return

            # Phase D (Culling) — mark attempted images in the processed folder as done
            try:
                for img in images_for_phase:
                    db.set_image_phase_status(
                        img['id'],
                        PhaseCode.CULLING,
                        PhaseStatus.DONE,
                        app_version=APP_VERSION,
                        executor_version="1.0.0",
                        job_id=job_id,
                    )
            except Exception as pe:
                log(f"Phase status update error: {pe}")
        except Exception as e:
            for img in images_for_phase:
                db.set_image_phase_status(
                    img['id'],
                    PhaseCode.CULLING,
                    PhaseStatus.FAILED,
                    app_version=APP_VERSION,
                    executor_version="1.0.0",
                    job_id=job_id,
                    error=str(e),
                )
            raise

        with self._lock:
            self._status_message = summary.status
            self._current_count = 100
            self._total_count = 100
            
        if job_id:
            # Only advance if we didn't stop (handled by the return check above, 
            # but being explicit here for safety if the structure changes)
            if summary.status != "stopped":
                self._complete_phase_and_advance(job_id, input_path, log)

        log(f"Total images: {summary.total_images}")
        log(f"Total stacks: {summary.total_stacks}")
        if summary.total_images:
            pct_pick = summary.picked / summary.total_images * 100
            pct_rej = summary.rejected / summary.total_images * 100
            log(f"Picked: {summary.picked} ({pct_pick:.1f}%)")
            log(f"Rejected: {summary.rejected} ({pct_rej:.1f}%)")
        else:
            log("Picked: 0, Rejected: 0")
        log(f"Neutral: {summary.neutral}")
        log(f"Sidecar written: {summary.sidecar_written}, errors: {summary.sidecar_errors}")
        log(f"Status: {summary.status}")

    def _complete_phase_and_advance(self, job_id: int, input_path: str, log):
        """Mark culling phase done and advance to next phase or complete the job."""
        try:
            # Mark our own phase as completed
            db.set_job_phase_state(job_id, PhaseCode.CULLING.value, "completed")
        except Exception as e:
            logger.warning("Failed to set culling phase completed for job %s: %s", job_id, e)

        # Check for remaining pending/queued phases
        remaining = []
        try:
            phases = db.get_job_phases(job_id) or []
            remaining = [
                p for p in phases
                if (p.get("state") or "").strip().lower() in ("pending", "queued", "running")
                and p.get("phase_code") != PhaseCode.CULLING.value
            ]
        except Exception as e:
            logger.warning("Failed to check remaining phases for job %s: %s", job_id, e)

        if remaining:
            # Enqueue a follow-up job for the next phase (e.g. bird_species)
            next_phase = remaining[0]
            next_code = next_phase.get("phase_code")
            log(f"Advancing to next phase: {next_code}")
            try:
                follow_job_id, _ = db.enqueue_job(
                    input_path,
                    phase_code=next_code,
                    job_type=next_code,
                    queue_payload={
                        "input_path": input_path,
                        "parent_job_id": job_id,
                    },
                )
                if follow_job_id:
                    db.create_job_phases(follow_job_id, [next_code], first_phase_state="queued")
                    logger.info("Enqueued follow-up %s job %s for parent job %s", next_code, follow_job_id, job_id)
                # Mark the remaining phase as completed in the parent job
                # so the parent shows as fully done in the UI
                db.set_job_phase_state(job_id, next_code, "completed")
            except Exception as e:
                logger.error("Failed to enqueue follow-up %s job for job %s: %s", next_code, job_id, e)

        # Now complete the parent job
        db.update_job_status(job_id, "completed")
        event_manager.broadcast_threadsafe("job_completed", {
            "job_id": job_id,
            "status": "completed"
        })

    def stop(self) -> None:
        """Request stop. Checked between stages."""
        self._service.stop()
