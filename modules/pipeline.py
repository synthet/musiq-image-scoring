
import threading
import queue
import time
import os
import sys
import tempfile
import logging
from datetime import datetime
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Local imports
from modules import db, thumbnails, xmp
from modules import score_normalization as snorm
from modules import config as app_config
from modules.phases import PhaseCode, PhaseStatus
from modules.version import APP_VERSION
from modules.run_log import attach_image_log_suffix, emit_run_log
# Lazy imports — TensorFlow/PyTorch live behind ScoringWorker._get_liqe_scorer()
# so tests that only exercise phase gating or prep paths need not import LIQE.

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class ImageJob:
    image_path: str
    job_id: int
    skip_existing: bool = False
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    temp_files: List[str] = field(default_factory=list)
    retry_count: int = 0
    error: Optional[str] = None
    
    # Pre-calculated data
    is_raw: bool = False
    process_path: str = "" # Path to actual image to score (original or temp jpeg)
    external_scores: Dict[str, Any] = field(default_factory=dict)
    thumbnail_path: Optional[str] = None
    image_id: Optional[int] = None  # DB id, set when image is found/created
    target_phases: List[PhaseCode] = field(default_factory=list) # List of phases to execute in this job
    skip_reason: Optional[str] = None  # Reason from policy/runner when status is "skipped"


def safe_runner_thread(runner_obj, job_id, run_func, *args, **kwargs):
    """
    Executes a runner's core logic inside a try/finally block that guarantees
    the runner clears its is_running flag.

    Acts as a safety net for terminal job state:
    - On exception, marks the job ``failed`` (using supported ``log=`` kwarg)
      and re-raises.
    - On clean return, marks the job ``completed`` only when the runner left
      the job in a non-terminal status and did not signal a graceful stop. A
      runner can opt out of this fallback by leaving its ``_status_message``
      set to ``"stopped"`` (graceful pause/interrupt) — caller is expected to
      record the resumable terminal state (e.g. ``interrupted``) explicitly.
    """
    try:
        run_func(*args, **kwargs)
        if job_id:
            try:
                runner_msg = (getattr(runner_obj, "_status_message", "") or "").strip().lower()
                if runner_msg == "stopped":
                    return
                row = db.get_job(job_id)
                current = (row or {}).get("status", "").strip().lower()
                if current not in db.JOB_TERMINAL_STATES:
                    db.update_job_status(job_id, "completed")
            except Exception:
                logger.exception("safe_runner_thread: terminal write failed for job %s", job_id)
    except Exception as e:
        logger.exception("Runner %s failed", runner_obj.__class__.__name__)
        if job_id:
            try:
                db.update_job_status(job_id, "failed", log=str(e)[:500])
            except Exception:
                pass
        raise
    finally:
        runner_obj.is_running = False

def _is_phase_targeted(target_phases: List[Any], phase_code: PhaseCode) -> bool:
    """
    Return True when a phase should run for this job.

    Accepts mixed target phase representations (PhaseCode enums or strings).
    Empty/None target list means full pipeline behavior (all phases).
    """
    if not target_phases:
        return True

    normalized = set()
    for p in target_phases:
        if p is None:
            continue
        if isinstance(p, PhaseCode):
            normalized.add(p.value)
        else:
            normalized.add(str(p).strip().lower())
    return phase_code.value in normalized

    
class PipelineWorker(threading.Thread):
    def __init__(self, name, input_queue, output_queue, stop_event):
        super().__init__(name=name)
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.daemon = True

    def run(self):
        logger.info(f"{self.name} started.")
        while not self.stop_event.is_set():
            try:
                # Timeout allows checking stop_event periodically
                item = self.input_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None: # Sentinel
                if self.output_queue:
                    self.output_queue.put(None)
                break
            
            try:
                self.process(item)
            except Exception as e:
                logger.error(f"Error in {self.name}: {e}")
                traceback.print_exc()
                if isinstance(item, ImageJob):
                    item.status = "failed"
                    item.error = str(e)
                    # Pass it along to handle failure in DB/Cleanup
                    if self.output_queue:
                         self.output_queue.put(item)
            finally:
                self.input_queue.task_done()
        logger.info(f"{self.name} stopped.")

    def process(self, item):
        raise NotImplementedError

class PrepWorker(PipelineWorker):
    """
    Scans for existence, generates thumbnails, converts RAWs.
    """
    def __init__(self, input_queue, output_queue, stop_event, scorer_ref):
        super().__init__("PrepWorker", input_queue, output_queue, stop_event)
        self.scorer = scorer_ref # Reference to scorer class for static methods (is_raw, etc)
        self._raw_converter = None  # Lazy-init; reused for RAW conversion to avoid per-image instantiation
        
    def process(self, job: ImageJob):
        try:
            # 1. Image Record Check
            # We need an image_id for phase tracking. If it's not set in the job,
            # we should look it up by path. This replaces the old Indexing/Metadata logic.
            if not job.image_id:
                path_record = db.get_image_details(job.image_path)
                if path_record:
                    job.image_id = path_record.get('id')
                    if not job.external_scores.get("image_hash"):
                        job.external_scores["image_hash"] = path_record.get('image_hash')
                    if path_record.get("hash_version") is not None and not job.external_scores.get("hash_version"):
                        job.external_scores["hash_version"] = int(path_record["hash_version"])
                    
                    # Audit safeguard: log if overwriting non-default rating/label
                    if not job.skip_existing and _is_phase_targeted(job.target_phases, PhaseCode.SCORING):
                        rating = path_record.get("rating")
                        label = path_record.get("label")
                        try:
                            has_rating = rating is not None and int(rating) > 0
                        except (TypeError, ValueError):
                            has_rating = False
                        has_label = bool(label and str(label).strip().lower() not in ("none", "null", ""))
                        if has_rating or has_label:
                            emit_run_log(
                                job.job_id,
                                f"Audit: Overwriting existing metadata for {Path(job.image_path).name} (Rating={rating}, Label={label})",
                                "WARNING",
                                phase="scoring",
                                step="prep"
                            )

            # --- PHASE C: SCORING (Preparation) ---
            if _is_phase_targeted(job.target_phases, PhaseCode.SCORING):
                # Ensure we have a thumbnail for scoring if needed
                if not job.thumbnail_path:
                    # MetadataRunner should have created this, but we'll check just in case
                    thumb = thumbnails.get_thumb_path(job.image_path)
                    if not os.path.exists(thumb):
                        generated = thumbnails.generate_thumbnail(job.image_path)
                        if generated:
                            thumb = generated
                    job.thumbnail_path = thumb

                # Per-image rerun gate (symmetric with tagging/culling runners)
                if job.image_id:
                    from modules.phases_policy import explain_phase_run_decision
                    decision = explain_phase_run_decision(
                        job.image_id,
                        PhaseCode.SCORING,
                        current_executor_version=self.scorer.VERSION if self.scorer else None,
                        force_run=not job.skip_existing,
                    )
                    if not decision['should_run']:
                        skip_reason = decision.get("reason", "scoring_policy_skip")
                        job.status = "skipped"
                        job.skip_reason = skip_reason
                        db.set_image_phase_status(
                            job.image_id,
                            PhaseCode.SCORING,
                            PhaseStatus.SKIPPED,
                            app_version=APP_VERSION,
                            executor_version=self.scorer.VERSION if self.scorer else None,
                            job_id=job.job_id,
                            skip_reason=skip_reason,
                            skipped_by="scoring_pipeline",
                        )
                        if job.job_id:
                            emit_run_log(
                                job.job_id,
                                f"Scoring skipped (policy): {Path(job.image_path).name}",
                                "INFO",
                                phase="scoring",
                                step="prep",
                            )
                        self.output_queue.put(job)
                        return

                # Identify Type
                job.is_raw = self.scorer.is_raw_file(job.image_path) if self.scorer else False
                if job.job_id:
                    emit_run_log(
                        job.job_id,
                        f"Prep {Path(job.image_path).name} raw={job.is_raw}",
                        "DEBUG",
                        phase="scoring",
                        step="prep",
                    )

                # RAW Conversion for Scoring
                if job.is_raw:
                    # Custom conversion logic here to avoid sharing state
                    t_dir = tempfile.mkdtemp(prefix="musiq_prep_")
                    job.temp_files.append(t_dir)
                    
                    if self._raw_converter is None:
                        from scripts.python.run_all_musiq_models import MultiModelMUSIQ
                        self._raw_converter = MultiModelMUSIQ(skip_gpu=True)
                    self._raw_converter.temp_dir = t_dir
                    
                    jpg = self._raw_converter.convert_raw_to_jpeg(job.image_path)
                    if jpg:
                        job.process_path = jpg
                        job.temp_files.append(jpg)
                        if job.job_id:
                            emit_run_log(
                                job.job_id,
                                f"RAW converted: {Path(job.image_path).name}",
                                "DEBUG",
                                phase="scoring",
                                step="prep",
                            )
                    else:
                        job.status = "failed"
                        job.error = "RAW Conversion Failed"
                        if job.job_id:
                            emit_run_log(
                                job.job_id,
                                f"RAW conversion failed: {job.image_path}",
                                "ERROR",
                                phase="scoring",
                                step="prep",
                            )
                        self.output_queue.put(job)
                        return
                else:
                    job.process_path = job.image_path

                if job.image_id:
                    db.set_image_phase_status(
                        job.image_id,
                        PhaseCode.SCORING,
                        PhaseStatus.RUNNING,
                        app_version=APP_VERSION,
                        executor_version=self.scorer.VERSION if self.scorer else None,
                        job_id=job.job_id,
                    )

            self.output_queue.put(job)
            
        except Exception as e:
            job.status = "failed"
            job.error = f"Prep failed: {str(e)}"
            self.output_queue.put(job)

class ScoringWorker(PipelineWorker):
    """
    Runs GPU Inference.
    """
    def __init__(self, input_queue, output_queue, stop_event, scorer_instance, liqe_scorer=None):
        super().__init__("ScoringWorker", input_queue, output_queue, stop_event)
        self.scorer = scorer_instance # The actual loaded heavy model
        # None => lazily construct LiqeScorer on first LIQE use (keeps ml imports out of __init__).
        self._liqe_scorer_explicit = liqe_scorer
        self._liqe_scorer_lazy = None

    def _get_liqe_scorer(self):
        if self._liqe_scorer_explicit is not None:
            return self._liqe_scorer_explicit
        if self._liqe_scorer_lazy is None:
            from modules.liqe import LiqeScorer

            self._liqe_scorer_lazy = LiqeScorer()
        return self._liqe_scorer_lazy

    def process(self, job: ImageJob):
        if job.status in ["skipped", "failed"]:
            self.output_queue.put(job)
            return

        # Operation-scoped pipeline runs can intentionally omit scoring.
        if not _is_phase_targeted(job.target_phases, PhaseCode.SCORING):
            job.status = "skipped"
            if job.job_id:
                emit_run_log(
                    job.job_id,
                    f"Scoring not targeted for phase list: {Path(job.image_path).name}",
                    "INFO",
                    phase="scoring",
                    step="inference",
                )
            self.output_queue.put(job)
            return

        # Prepare external scores container
        external = job.external_scores if job.external_scores else {}
        
        # Preprocess using config (raw_conversion or scoring.model_preprocessing)
        try:
            temp_dir = tempfile.mkdtemp(prefix="score_512_")
            job.temp_files.append(temp_dir)
            cfg = app_config.load_config()
            model_prep = (cfg.get("scoring") or {}).get("model_preprocessing") or {}
            def get_res(key):
                v = model_prep.get(key)
                if isinstance(v, dict):
                    return v.get("resolution")
                return v
            liqe_res = get_res("liqe")
            musiq_res = get_res("spaq") or get_res("ava")
            # Single path: no per-model preprocessing or same resolution
            if not liqe_res and not musiq_res:
                path_512 = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir)
                if path_512:
                    job.process_path = path_512
            else:
                # Per-model: preprocess at LIQE resolution and at MUSIQ resolution
                res_liqe = int(liqe_res) if liqe_res is not None else None
                res_musiq = int(musiq_res) if musiq_res is not None else None
                if res_liqe is not None and res_musiq is not None and res_liqe != res_musiq:
                    path_liqe = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_liqe)
                    path_musiq = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_musiq)
                    if path_liqe and path_musiq:
                        job.process_path = path_musiq
                        job.external_scores["_liqe_preprocess_path"] = path_liqe
                elif res_liqe is not None:
                    path_liqe = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_liqe)
                    if path_liqe:
                        job.process_path = path_liqe
                        job.external_scores["_liqe_preprocess_path"] = path_liqe
                else:
                    path_512 = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_musiq)
                    if path_512:
                        job.process_path = path_512
        except Exception as e:
            logger.warning("Preprocess failed, using original path: %s", e)
        
        # Check/Run LIQE if missing
        if "liqe" not in external:
            try:
                path = external.get("_liqe_preprocess_path") or job.process_path
                liqe_result = self._get_liqe_scorer().predict(path)
                external["liqe"] = liqe_result
            except Exception as e:
                logger.error(f"LIQE failed for {job.image_path}: {e}")
                external["liqe"] = {"status": "failed", "error": str(e)}

        try:
            # Run All Models
            # We assume scorer.run_all_models is thread safe if called serially by this single worker
            # (TF sessions can be tricky but single thread consumption is fine)
            
            # Clear Cache
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except (ImportError, RuntimeError) as e:
                logger.warning("CUDA cache clear failed: %s", e)

            def _inference_log(msg):
                if job.job_id:
                    emit_run_log(
                        job.job_id,
                        str(msg),
                        "DEBUG",
                        phase="scoring",
                        step="inference",
                    )

            results = self.scorer.run_all_models(
                job.process_path,
                external_scores=external,
                logger=_inference_log,
                write_metadata=False,  # Handled in ResultWorker to avoid I/O blocking GPU
            )
            
            job.result = results
            
            # Post-check
            if results["summary"]["failed_predictions"] == results["summary"]["total_models"]:
                 job.status = "failed"
                 job.error = "All models failed"
            else:
                 job.status = "success"
                 
            self.output_queue.put(job)
            
        except Exception as e:
            job.status = "failed"
            job.error = f"Scoring failed: {str(e)}"
            self.output_queue.put(job)

class ResultWorker(PipelineWorker):
    """
    Upserts to DB, cleans up, logs.
    Also handles writing metadata to NEF files (I/O bound).
    """
    def __init__(self, input_queue, output_queue, stop_event, scorer_instance, progress_callback=None, item_finished_callback=None, folder_agg_dirty_ids=None):
        super().__init__("ResultWorker", input_queue, output_queue, stop_event) # Output queue unused
        self.progress_callback = progress_callback # func(str, level="INFO") -> log
        self.item_finished_callback = item_finished_callback # func() -> void
        self.scorer = scorer_instance
        self._folder_agg_dirty_ids = folder_agg_dirty_ids

    def _progress(self, msg: str, level: str = "INFO", *, image_id: Optional[int] = None) -> None:
        if not self.progress_callback:
            return
        out = attach_image_log_suffix(msg, image_id)
        try:
            self.progress_callback(out, level)
        except TypeError:
            self.progress_callback(out)

    def process(self, job: ImageJob):
        collector = getattr(self, "report_collector", None)

        # 1. Handle Status
        if job.status == "skipped":
            self._progress(f"Skipped: {job.image_path}", "INFO", image_id=job.image_id)
            if job.image_id and _is_phase_targeted(job.target_phases, PhaseCode.SCORING):
                thumb = job.thumbnail_path
                if not thumb or not os.path.isfile(thumb):
                    thumb = thumbnails.get_thumb_path(job.image_path)
                if thumb and os.path.isfile(thumb):
                    db.update_image_thumbnail_paths(job.image_id, thumb, None)
                if collector and job.image_id:
                    collector.record_skip(job.image_id, job.skip_reason or "scoring_policy_skip")

        elif job.status == "failed":
            self._progress(f"FAILED: {job.image_path} - {job.error}", "ERROR", image_id=job.image_id)
            if job.image_id:
                db.set_image_phase_status(
                    job.image_id,
                    PhaseCode.SCORING,
                    PhaseStatus.FAILED,
                    app_version=APP_VERSION,
                    executor_version=self.scorer.VERSION if self.scorer else None,
                    job_id=job.job_id,
                    error=job.error,
                )
                if collector:
                    collector.record_failure(job.image_id, job.error or "unknown")
                
        elif job.status == "success":
            # Write Metadata using unified XMP module
            # Doing this here takes I/O off the GPU thread
            metadata_written = False
            if self.scorer and "weighted_scores" in job.result["summary"]:
                try:
                    normalized_scores_dict = {}
                    for m_name, m_res in job.result["models"].items():
                         # Shadow models run alongside production but must NOT contribute
                         # to fused scores (Phase 1 shadow-mode). The host stamps
                         # is_shadow=True on those rows; legacy results omit the key
                         # entirely, which `not m_res.get("is_shadow")` treats as production.
                         if m_res.get("status") == "success" and not m_res.get("is_shadow"):
                             normalized_scores_dict[m_name] = m_res.get("normalized_score", 0)

                    result_all = snorm.compute_all(normalized_scores_dict)
                    avg_score = result_all["general"]
                    rating = result_all["rating"]
                    label = result_all["label"]

                    job.result["summary"]["weighted_scores"] = {
                        "technical": result_all["technical"],
                        "aesthetic": result_all["aesthetic"],
                        "general": result_all["general"],
                    }
                    
                    # Use unified XMP module for consistent metadata handling
                    # Write XMP sidecar (non-destructive) for all images
                    metadata_written = xmp.write_metadata_unified(
                        image_path=job.image_path,
                        rating=rating,
                        label=label,
                        use_sidecar=True,  # Always create XMP sidecar
                        use_embedded=job.is_raw  # Only write embedded for RAW files
                    )
                    
                    if metadata_written:
                        # Inject metadata into result for DB upsert
                        job.result["nef_metadata"] = {
                            "rating": rating,
                            "label": label
                        }
                        
                except Exception as e:
                    self._progress(f"Metadata Write Failed: {e}", "WARNING", image_id=job.image_id)

            # Upsert
            try:
                # Add original path to result so DB knows
                job.result["image_path"] = job.image_path
                job.result["image_name"] = Path(job.image_path).name
                if "image_hash" in job.external_scores:
                    job.result["image_hash"] = job.external_scores["image_hash"]
                if "hash_version" in job.external_scores:
                    job.result["hash_version"] = job.external_scores["hash_version"]
                
                if job.thumbnail_path:
                    job.result["thumbnail_path"] = job.thumbnail_path
                
                if self._folder_agg_dirty_ids is not None:
                    db.upsert_image(
                        job.job_id,
                        job.result,
                        invalidate_agg=False,
                        dirty_folder_ids=self._folder_agg_dirty_ids,
                    )
                else:
                    db.upsert_image(job.job_id, job.result)
                
                # Resolve image_id for phase tracking (may have been created by upsert)
                had_no_image_id = not job.image_id
                if not job.image_id:
                    try:
                        img_rec = db.get_image_details(job.image_path)
                        if img_rec:
                            job.image_id = img_rec['id']
                    except Exception:
                        pass

                # Phase status updates
                if job.image_id:
                    db.set_image_phase_status(job.image_id, PhaseCode.SCORING, PhaseStatus.DONE,
                                              app_version=APP_VERSION,
                                              executor_version=self.scorer.VERSION if self.scorer else None,
                                              job_id=job.job_id)

                score = job.result.get("summary", {}).get("weighted_scores", {}).get("general", 0)
                self._progress(
                    f"Scored: {Path(job.image_path).name} - {score:.2f}",
                    "INFO",
                    image_id=job.image_id,
                )

                # Record after-snapshot for execution trail.
                if collector and job.image_id:
                    try:
                        ws = job.result.get("summary", {}).get("weighted_scores", {})
                        models = job.result.get("models", {})
                        nef_meta = job.result.get("nef_metadata", {})
                        after = {
                            "score": ws.get("general"),
                            "score_general": ws.get("general"),
                            "score_technical": ws.get("technical"),
                            "score_aesthetic": ws.get("aesthetic"),
                            "rating": nef_meta.get("rating"),
                            "label": nef_meta.get("label"),
                        }
                        for m_name in ("spaq", "ava", "koniq", "paq2piq", "liqe"):
                            m_data = models.get(m_name, {})
                            after[f"score_{m_name}"] = m_data.get("normalized_score")
                        collector.record_after(job.image_id, after)
                    except Exception:
                        logger.debug("ResultWorker: after-snapshot recording failed for image %s", job.image_id, exc_info=True)
            except Exception as e:
                # Phase C (Scoring) — failed
                if job.image_id:
                    db.set_image_phase_status(job.image_id, PhaseCode.SCORING, PhaseStatus.FAILED,
                                              job_id=job.job_id, error=str(e))
                    if collector:
                        collector.record_failure(job.image_id, str(e))
                self._progress(f"DB Error: {e}", "ERROR", image_id=job.image_id)
        
        # 2. Cleanup
        for p in job.temp_files:
            try:
                if os.path.isdir(p):
                    import shutil
                    shutil.rmtree(p)
                else:
                    if os.path.exists(p):
                        os.remove(p)
            except OSError as e:
                logger.warning("Cleanup failed for %s: %s", p, e)
        
        if self.item_finished_callback:
            self.item_finished_callback()
