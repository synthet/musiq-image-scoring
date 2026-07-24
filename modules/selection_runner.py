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
from modules.job_description import augment_queue_payload_for_audit
from modules.run_manifest import REASON_SOURCE_PHASE_FOLLOWUP, attach_run_reason

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

    def start_batch(
        self,
        input_path: str,
        job_id: int = None,
        force_rescan: bool = False,
        resolved_image_ids: list[int] | None = None,
    ) -> str:
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
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                from modules.pipeline_diagnostics import phase_timer
                with phase_timer("SelectionRunner.batch", job_id):
                    self._run_internal(input_path, force_rescan, job_id, resolved_image_ids)
            safe_runner_thread(self, job_id, target_wrapper)

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return "Started"

    def _resolve_culling_scope(
        self,
        input_path: str,
        force_rescan: bool,
        resolved_image_ids: list[int] | None,
        log,
    ):
        """Load images in scope and filter to culling-eligible rows."""
        from modules.phases import PhaseCode
        from modules.phases_policy import explain_phase_run_decision

        images = []
        images_for_phase = []
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
        if resolved_image_ids is not None:
            target_ids = {int(i) for i in resolved_image_ids}
            images = [img for img in images if int(img.get("id") or 0) in target_ids]
            if not target_ids:
                return "empty_queue", images, images_for_phase
        if images:
            # score_general == 0 is a legitimate composite (issue #162); only NULL
            # means finalize/scoring never wrote the aggregate.
            valid_images = [
                img for img in images
                if img.get("score_general") is not None
            ]
            missing_scores = len(images) - len(valid_images)
            if missing_scores > 0:
                log(
                    f"Warning: {missing_scores} images are missing score_general "
                    "(NULL composite). They will be skipped. Run scoring finalize "
                    "or re-score before culling.",
                    "WARNING",
                )
            images = valid_images
            if not images:
                return "missing_prerequisites", images, images_for_phase
            if force_rescan:
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
        return "ok", images, images_for_phase

    def _run_internal(
        self,
        input_path: str,
        force_rescan: bool,
        job_id: int = None,
        resolved_image_ids: list[int] | None = None,
    ):
        
        def log(msg: str, level: str = "INFO") -> None:
            with self._lock:
                runner_emit(self._log_history, job_id, msg, level, phase="culling")

        def debug_culling(msg: str) -> None:
            suffix = f" job_id={job_id}" if job_id else ""
            logger.debug("[culling]%s %s", suffix, msg)
            if job_id is not None:
                with self._lock:
                    runner_emit(self._log_history, job_id, msg, "DEBUG", phase="culling")

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
        debug_culling(
            f"run start input_path={input_path!r} force_rescan={force_rescan}"
        )
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
            scope_status, images, images_for_phase = self._resolve_culling_scope(
                input_path, force_rescan, resolved_image_ids, log
            )
            if scope_status == "empty_queue":
                log("No images in planner queue for culling.")
                if job_id:
                    db.update_job_status(job_id, "completed", "Culling: empty planner queue")
                with self._lock:
                    self._status_message = "Done (no images)"
                return
            if scope_status == "missing_prerequisites":
                log(
                    "Error: No images in the current scope have required scoring data. "
                    "Aborting Selection/Culling phase. Run 'Scoring' first.",
                    "ERROR",
                )
                with self._lock:
                    self._status_message = "Failed: missing prerequisites"
                if job_id:
                    # Do not mark completed — that re-triggers auto-drive post-audit
                    # follow-ups while culling phase rows stay not_started.
                    db.update_job_status(
                        job_id,
                        "failed",
                        "Culling aborted: missing score_general (run scoring / finalize phantoms first)",
                    )
                    event_manager.broadcast_threadsafe("job_completed", {
                        "job_id": job_id,
                        "status": "failed",
                    })
                return
        except Exception as pe:
            log(f"Phase status eligibility check error: {pe}")

        skipped_by_policy = max(0, len(images) - len(images_for_phase))
        debug_culling(
            f"scope images={len(images)} eligible_for_phase={len(images_for_phase)} "
            f"skipped_by_policy={skipped_by_policy}"
        )
        if skipped_by_policy:
            log(
                f"Culling: skipping re-run for {skipped_by_policy} image(s) (already current); "
                f"{len(images_for_phase)} image(s) will be driven through clustering for this run."
            )

        if job_id and db.job_should_stop_processing(job_id):
            debug_culling("abort before SelectionService.run: job paused or canceled")
            log("Selection/culling skipped: job already paused or canceled.")
            return

        cfg = SelectionConfig(force_rescan=force_rescan)
        log(
            f"Starting clustering for {len(images_for_phase)} of {len(images)} image(s) in scope "
            f"(force_rescan={force_rescan})..."
        )
        debug_culling("calling SelectionService.run")
        try:
            # SelectionService operates at folder scope; phase status updates are limited
            # to policy-eligible images tracked in images_for_phase.
            summary = self._service.run(input_path, cfg=cfg, progress_cb=progress_cb)
            debug_culling(
                f"SelectionService.run finished status={summary.status!r} "
                f"images={summary.total_images} stacks={summary.total_stacks} "
                f"pick={summary.picked} reject={summary.rejected} neutral={summary.neutral}"
            )
            
            if summary.status == "stopped":
                log("Selection stopped gracefully. Skipping finalization.", "WARNING")
                with self._lock:
                    self._status_message = "stopped"
                return

            # FIX: Do not mark images DONE here. ClusteringEngine already marks processed 
            # images as DONE per-folder. Redundant marking here can clobber more granular 
            # failures or skip policy decisions made inside the engine.
        except Exception as e:
            debug_culling(f"SelectionService.run failed: {e!r}")
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

        logger.debug(
            "[culling] job_id=%s complete_phase_and_advance remaining_phases=%s input_path=%r",
            job_id,
            [p.get("phase_code") for p in remaining],
            input_path,
        )

        if remaining:
            # Enqueue a follow-up job for the next phase (e.g. bird_species)
            next_phase = remaining[0]
            next_code = next_phase.get("phase_code")
            log(f"Advancing to next phase: {next_code}")
            try:
                # Forward tagging-relevant flags from the parent payload so the
                # keywords phase sees the same generate_captions/custom_keywords
                # the user requested at /runs/submit time (otherwise the
                # dispatcher defaults generate_captions to False and BLIP
                # title/description never get written).
                parent_payload: dict = {}
                try:
                    import json as _json
                    row = db.get_connector().query_one(
                        "SELECT queue_payload FROM jobs WHERE id = ?", (job_id,)
                    )
                    raw = (row or {}).get("queue_payload")
                    if isinstance(raw, str) and raw:
                        parsed = _json.loads(raw)
                        if isinstance(parsed, dict):
                            parent_payload = parsed
                    elif isinstance(raw, dict):
                        parent_payload = raw
                except Exception as _pe:
                    logger.debug("follow-up payload propagation: parent read failed: %s", _pe)

                followup_body: dict = {
                    "input_path": input_path,
                    "parent_job_id": job_id,
                }
                for _k in ("generate_captions", "custom_keywords", "overwrite"):
                    if _k in parent_payload:
                        followup_body[_k] = parent_payload[_k]

                fq_payload = attach_run_reason(
                    augment_queue_payload_for_audit(
                        followup_body,
                        trigger="runner",
                        tool_id="phase_followup",
                    ),
                    source=REASON_SOURCE_PHASE_FOLLOWUP,
                    summary=f"Follow-up stage {next_code!r} after parent job #{job_id}.",
                    trigger="runner",
                    tool_id="phase_followup",
                    criteria={
                        "parent_job_id": job_id,
                        "enqueued_phases": [next_code],
                        "input_path": input_path,
                    },
                )
                follow_job_id, _ = db.enqueue_job(
                    input_path,
                    phase_code=next_code,
                    job_type=next_code,
                    queue_payload=fq_payload,
                    description=f"Follow-up stage {next_code!r} after parent job #{job_id} (orchestrator advance).",
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
        # Best-effort: wait briefly for the background thread to drain so UI/tests
        # observe ``is_running`` flipping promptly (safe_runner_thread also clears it).
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=5.0)
