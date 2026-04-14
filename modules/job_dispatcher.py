import json
import logging
import threading
from typing import Any, Dict, Optional

from modules import db
from modules.run_modes import infer_run_mode, resolve_run_mode_flags

logger = logging.getLogger(__name__)


class JobDispatcher:
    """Dispatches queued jobs and ensures only one active job starts at a time."""

    def __init__(
        self,
        scoring_runner=None,
        tagging_runner=None,
        clustering_runner=None,
        selection_runner=None,
        bird_species_runner=None,
        indexing_runner=None,
        metadata_runner=None,
        maintenance_runner=None,
        poll_interval: float = 1.0,
    ):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.bird_species_runner = bird_species_runner
        self.indexing_runner = indexing_runner
        self.metadata_runner = metadata_runner
        self.maintenance_runner = maintenance_runner
        self.poll_interval = max(0.2, float(poll_interval or 1.0))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dispatch_lock = threading.Lock()

    def set_runners(self, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None, bird_species_runner=None, indexing_runner=None, metadata_runner=None, maintenance_runner=None):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.bird_species_runner = bird_species_runner
        self.indexing_runner = indexing_runner
        self.metadata_runner = metadata_runner
        self.maintenance_runner = maintenance_runner

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="job-dispatcher", daemon=True)
        self._thread.start()
        logger.info("JobDispatcher started")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("JobDispatcher stopped")

    def get_state(self) -> Dict[str, Any]:
        queue = db.get_queued_jobs(limit=200)
        active = self._get_active_runner()
        return {
            "queue": queue,
            "queue_size": len(queue),
            "active_runner": active,
            "is_dispatcher_running": bool(self._thread and self._thread.is_alive()),
        }

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.exception("JobDispatcher tick failed: %s", exc)
            self._stop_event.wait(self.poll_interval)

    def tick_for_tests(self) -> None:
        """Single dispatch iteration for unit tests (does not require start())."""
        self._tick()

    def _tick(self):
        if self._any_runner_busy():
            return

        with self._dispatch_lock:
            if self._any_runner_busy():
                return
            job = db.dequeue_next_job()
            if job:
                payload = self._parse_queue_payload(job)
                started, err = self._start_job(job, payload)
                if not started:
                    reason = err or "Dispatcher failed to start job (unknown reason)"
                    logger.warning("Dispatcher: job %s failed to start: %s", job.get("id"), reason)
                    db.update_job_status(job["id"], "failed", reason)
                return

            cont = db.get_running_job_for_phase_continuation()
            if not cont:
                return

            phase_code = (cont.pop("_active_phase_code", None) or "").strip().lower()
            if not phase_code:
                logger.warning("Dispatcher: continuation job %s missing active phase code", cont.get("id"))
                return

            payload = self._parse_queue_payload(cont)
            started, err = self._start_job(cont, payload, phase_override=phase_code)
            if not started:
                reason = err or "Dispatcher failed to continue multi-phase job (unknown reason)"
                logger.warning("Dispatcher: continuation job %s failed to start: %s", cont.get("id"), reason)
                db.update_job_status(cont["id"], "failed", reason)

    @staticmethod
    def _parse_queue_payload(job: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        raw_payload = job.get("queue_payload")
        if raw_payload:
            try:
                parsed = json.loads(raw_payload)
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                payload = parsed if isinstance(parsed, dict) else {}
            except Exception:
                logger.warning("Invalid queue payload for job %s", job.get("id"))
        return payload

    @staticmethod
    def _run_mode_flags(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            run_mode = infer_run_mode(
                payload.get("run_mode"),
                run_mode_explicit=bool(payload.get("run_mode")),
                skip_done=payload.get("skip_done"),
                force_rerun=payload.get("force_rerun"),
                fix_incomplete_stages=payload.get("fix_incomplete_stages"),
            )
        except ValueError:
            run_mode = infer_run_mode(
                None,
                run_mode_explicit=False,
                skip_done=payload.get("skip_done"),
                force_rerun=payload.get("force_rerun"),
                fix_incomplete_stages=payload.get("fix_incomplete_stages"),
            )
        return resolve_run_mode_flags(run_mode)

    def _start_job(self, job: Dict[str, Any], payload: Dict[str, Any], phase_override: Optional[str] = None) -> tuple:
        """Try to start the job. Returns (success: bool, error_msg: str|None)."""
        phase = (phase_override or job.get("job_type") or "").lower()
        job_id = int(job["id"])
        input_path = job.get("input_path")

        if phase_override:
            try:
                from modules.run_log import emit_run_log

                emit_run_log(
                    job_id,
                    f"Continuing multi-phase run with phase: {phase}",
                    "INFO",
                    phase=phase,
                    step="dispatcher",
                )
            except Exception:
                pass

        runner_map = {
            "indexing": ("indexing_runner", self.indexing_runner),
            "metadata": ("metadata_runner", self.metadata_runner),
            "score": ("scoring_runner", self.scoring_runner),
            "scoring": ("scoring_runner", self.scoring_runner),
            "tag": ("tagging_runner", self.tagging_runner),
            "tagging": ("tagging_runner", self.tagging_runner),
            "keywords": ("tagging_runner", self.tagging_runner),
            "cluster": ("clustering_runner", self.clustering_runner),
            "clustering": ("clustering_runner", self.clustering_runner),
            "selection": ("selection_runner", self.selection_runner),
            "culling": ("selection_runner", self.selection_runner),
            "bird_species": ("bird_species_runner", self.bird_species_runner),
            "bird-species": ("bird_species_runner", self.bird_species_runner),
            "maintenance": ("maintenance_runner", self.maintenance_runner),
        }

        entry = runner_map.get(phase)
        if entry is None:
            logger.warning("Unknown queued job_type=%s for job_id=%s", phase, job_id)
            return False, f"Unknown job type: {phase}"

        runner_name, runner = entry
        if not runner:
            return False, f"No runner available for '{phase}' (runner '{runner_name}' is not initialized)"

        try:
            result = self._dispatch_to_runner(phase, runner, job_id, input_path, payload)
        except Exception as exc:
            logger.exception("Runner %s raised during start for job %s", runner_name, job_id)
            return False, f"Runner '{runner_name}' raised: {exc}"

        if result == "Started":
            return True, None
        return False, f"Runner '{runner_name}' returned: {result}"

    def _dispatch_to_runner(self, phase: str, runner, job_id: int, input_path: str, payload: Dict[str, Any]) -> str:
        """Call the appropriate start_batch method on the runner. Returns the result string."""
        phase_key = str(phase).strip().lower()
        phase_alias = {
            "score": "scoring",
            "tagging": "keywords",
            "tag": "keywords",
            "selection": "culling",
            "cluster": "clustering",
        }
        queue_key = phase_alias.get(phase_key, phase_key)
        stage_queues = payload.get("resolved_image_ids_by_stage")
        scoped_resolved = payload.get("resolved_image_ids")
        if isinstance(stage_queues, dict):
            per_stage = stage_queues.get(queue_key)
            if isinstance(per_stage, list):
                scoped_resolved = per_stage

        if phase_key == "indexing":
            mode_flags = self._run_mode_flags(payload)
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                skip_existing=bool(mode_flags["skip_existing"]),
                resolved_image_ids=scoped_resolved,
            )

        if phase_key == "metadata":
            mode_flags = self._run_mode_flags(payload)
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                skip_existing=bool(mode_flags["skip_existing"]),
                resolved_image_ids=scoped_resolved,
            )

        if phase_key in ("score", "scoring"):
            mode_flags = self._run_mode_flags(payload)
            skip_existing_val = bool(mode_flags["skip_existing"])
            resolved = scoped_resolved
            # Short-term behavior: fix_incomplete_stages resolves scoped IDs only for scoring.
            # Metadata/tagging/culling continue to use their normal skip/re-run semantics.
            if bool(mode_flags["fix_incomplete_stages"]) and not resolved:
                paths = payload.get("scope_paths")
                if not isinstance(paths, list) or not paths:
                    paths = [payload.get("input_path", input_path)]
                id_set: set[int] = set()
                for p in paths:
                    if not p:
                        continue
                    for i in db.get_incomplete_image_ids_under_folder(str(p)):
                        id_set.add(int(i))
                resolved = sorted(id_set) if id_set else []
                if resolved:
                    skip_existing_val = False
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id,
                skip_existing_val,
                resolved_image_ids=resolved,
                target_phases=payload.get("target_phases"),
            )

        if phase_key in ("tag", "tagging", "keywords"):
            mode_flags = self._run_mode_flags(payload)
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                custom_keywords=payload.get("custom_keywords"),
                overwrite=bool(mode_flags["overwrite"]),
                generate_captions=bool(payload.get("generate_captions", False)),
                resolved_image_ids=scoped_resolved,
            )

        if phase_key in ("cluster", "clustering"):
            mode_flags = self._run_mode_flags(payload)
            # POST /api/clustering/start sets force_rescan on queue_payload; it is not part of run_mode.
            force_rescan = bool(mode_flags["force_rescan"]) or bool(payload.get("force_rescan"))
            return runner.start_batch(
                payload.get("input_path", input_path),
                threshold=payload.get("threshold"),
                time_gap=payload.get("time_gap"),
                force_rescan=force_rescan,
                job_id=job_id,
                resolved_image_ids=scoped_resolved,
            )

        if phase_key in ("selection", "culling"):
            mode_flags = self._run_mode_flags(payload)
            force_rescan = bool(mode_flags["force_rescan"]) or bool(payload.get("force_rescan"))
            logger.debug(
                "[culling] dispatch job_id=%s phase=%s input_path=%r force_rescan=%s",
                job_id,
                phase_key,
                payload.get("input_path", input_path),
                force_rescan,
            )
            if scoped_resolved:
                logger.info(
                    "Selection runner does not accept resolved_image_ids yet; "
                    "culling queue constraints are advisory only (job_id=%s)",
                    job_id,
                )
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                force_rescan=force_rescan,
            )

        if phase_key in ("bird_species", "bird-species"):
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                candidate_species=payload.get("candidate_species"),
                threshold=float(payload.get("threshold", 0.1)),
                top_k=int(payload.get("top_k", 3)),
                overwrite=bool(payload.get("overwrite", False)),
                resolved_image_ids=scoped_resolved,
            )

        if phase == "maintenance":
            act = (payload or {}).get("action", "")
            logger.info(
                "Dispatching maintenance job id=%s action=%r input_path=%r",
                job_id,
                act,
                input_path,
            )
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
            )

        return f"No dispatch handler for phase '{phase}'"

    def _runner_busy(self, runner) -> bool:
        return bool(runner and getattr(runner, "is_running", False))

    def _any_runner_busy(self) -> bool:
        return any([
            self._runner_busy(self.indexing_runner),
            self._runner_busy(self.metadata_runner),
            self._runner_busy(self.scoring_runner),
            self._runner_busy(self.tagging_runner),
            self._runner_busy(self.clustering_runner),
            self._runner_busy(self.selection_runner),
            self._runner_busy(self.bird_species_runner),
            self._runner_busy(self.maintenance_runner),
        ])

    def _get_active_runner(self) -> Optional[str]:
        if self._runner_busy(self.indexing_runner):
            return "indexing"
        if self._runner_busy(self.metadata_runner):
            return "metadata"
        if self._runner_busy(self.scoring_runner):
            return "scoring"
        if self._runner_busy(self.tagging_runner):
            return "tagging"
        if self._runner_busy(self.clustering_runner):
            return "clustering"
        if self._runner_busy(self.selection_runner):
            return "selection"
        if self._runner_busy(self.bird_species_runner):
            return "bird_species"
        if self._runner_busy(self.maintenance_runner):
            return "maintenance"
        return None
