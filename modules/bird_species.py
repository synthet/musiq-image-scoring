"""
Bird species classification using BioCLIP 2.

Provides BioCLIPClassifier (zero-shot species identification via OpenCLIP) and
BirdSpeciesRunner (background thread runner following the same interface as TaggingRunner).

Only images that already have the "birds" keyword are processed — all others are skipped.
Top predicted species are stored as "species:Common Name" keywords.
"""

import os
import logging
import threading
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

BIRD_SPECIES_RUNNER_VERSION = "1.0.0"

# Default candidate species list (common North American names)
_DEFAULT_SPECIES_LIST_PATH = Path(__file__).resolve().parent.parent / "data" / "bird_species_list.txt"


def _load_default_species() -> List[str]:
    """Load species names from the bundled list file."""
    try:
        with open(_DEFAULT_SPECIES_LIST_PATH, "r", encoding="utf-8") as f:
            return [
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            ]
    except FileNotFoundError:
        logger.warning("Default species list not found at %s", _DEFAULT_SPECIES_LIST_PATH)
        return []


def _resolve_inference_path(row: dict, file_path: str) -> str:
    """Return the best image path for ML inference — uses thumbnail for RAW files."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".nef", ".nrw", ".arw", ".cr2", ".cr3", ".dng", ".orf", ".rw2"}:
        try:
            from modules.thumbnails import get_thumb_wsl
            thumb = get_thumb_wsl(row)
            if thumb and os.path.exists(thumb):
                return thumb
        except Exception:
            pass
    return file_path


def _get_image_ids_with_species_keyword(image_ids: List[int]) -> set:
    """Return the subset of image_ids that already have at least one 'species:' keyword."""
    if not image_ids:
        return set()
    from modules import db as _db
    conn = _db.get_db()
    c = conn.cursor()
    
    found_ids = set()
    try:
        # Firebird's parameter limit is ~1500 in v3, higher in v4. Chunk at 900 for safety.
        chunk_size = 900
        for i in range(0, len(image_ids), chunk_size):
            chunk = image_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            c.execute(
                f"SELECT DISTINCT ik.image_id FROM image_keywords ik "
                f"JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id "
                f"WHERE ik.image_id IN ({placeholders}) "
                f"AND LOWER(kd.keyword_norm) LIKE 'species:%'",
                tuple(int(x) for x in chunk),
            )
            found_ids.update(row[0] for row in c.fetchall())
        return found_ids
    except Exception as exc:
        logger.warning("_get_image_ids_with_species_keyword failed: %s", exc)
        return found_ids
    finally:
        conn.close()


class BioCLIPClassifier:
    """
    Zero-shot bird species classifier using BioCLIP 2 via OpenCLIP.

    Loads lazily on first call to classify(). Text embeddings for the candidate
    species list are pre-computed once per batch to avoid redundant encoding.

    Usage:
        classifier = BioCLIPClassifier()
        results = classifier.classify("/path/img.jpg", ["American Robin", "Mallard"])
        # → [("American Robin", 0.82), ("Mallard", 0.09)]
    """

    MODEL_ID = "hf-hub:imageomics/bioclip-2"

    def __init__(self, device: str = None):
        import torch
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        # Cache text embeddings when species list is stable across a batch
        self._cached_species_list: Optional[List[str]] = None
        self._cached_text_features = None
        # Most-recent BioCLIP image embedding (512-d, L2-normalized) populated
        # as a side effect of classify() so BirdSpeciesRunner can persist it
        # under the ``bioclip_2_image`` space without an extra forward pass.
        self.last_image_embedding = None

    def load_model(self):
        """Lazily load BioCLIP 2. Call once before running a batch."""
        if self.model is not None:
            return
        import open_clip
        logger.info("Loading BioCLIP 2 model (%s) on %s...", self.MODEL_ID, self.device)
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(self.MODEL_ID)
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer(self.MODEL_ID)
        logger.info("BioCLIP 2 loaded.")

    def _get_text_features(self, species_names: List[str]):
        """Return cached (or freshly computed) normalized text embeddings."""
        import torch
        if species_names == self._cached_species_list and self._cached_text_features is not None:
            return self._cached_text_features
        prompts = [f"a photo of {name}, a bird species" for name in species_names]
        tokens = self.tokenizer(prompts).to(self.device)
        with torch.no_grad():
            text_features = self.model.encode_text(tokens)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        self._cached_species_list = species_names
        self._cached_text_features = text_features
        return text_features

    def classify(
        self,
        image_path: str,
        candidate_species: List[str],
        threshold: float = 0.1,
        top_k: int = 3,
    ) -> List[Tuple[str, float]]:
        """
        Classify a single image against candidate_species.

        Returns:
            List of (species_name, confidence) tuples sorted by confidence descending,
            only including results at or above threshold, capped at top_k.
            Returns [] on error.
        """
        import torch

        from modules.thumbnails import open_image_for_ml

        self.load_model()
        self.last_image_embedding = None
        try:
            img = open_image_for_ml(image_path).convert("RGB")
            img_tensor = self.preprocess(img).unsqueeze(0).to(self.device)

            text_features = self._get_text_features(candidate_species)

            with torch.no_grad():
                img_features = self.model.encode_image(img_tensor)
                img_features = img_features / img_features.norm(dim=-1, keepdim=True)
                # Temperature-scaled cosine similarity → softmax probabilities
                logits = (img_features @ text_features.T) * 100
                probs = logits.softmax(dim=-1)[0].tolist()

            try:
                from modules.embeddings_extract import extract_bioclip_image_features

                self.last_image_embedding = extract_bioclip_image_features(img_features)
            except Exception as emb_err:  # noqa: BLE001 — best-effort side effect
                logger.debug("BioCLIP embedding extraction failed: %s", emb_err)

            results = sorted(
                zip(candidate_species, probs),
                key=lambda x: -x[1],
            )
            return [
                (name, round(prob, 4))
                for name, prob in results
                if prob >= threshold
            ][:top_k]
        except Exception as exc:
            logger.error("BioCLIP classify error for %s: %s", image_path, exc)
            return []


class BirdSpeciesRunner:
    """
    Runs bird species classification in a background thread.

    Follows the same interface as TaggingRunner (start_batch / get_status / stop).
    Only images that already have the 'birds' keyword are processed.
    """

    def __init__(self):
        self.stop_event = threading.Event()
        self.classifier: Optional[BioCLIPClassifier] = None

        self.is_running = False
        self.log_history: List[str] = []
        self.status_message = "Idle"
        self._thread: Optional[threading.Thread] = None
        self.current_count = 0
        self.total_count = 0

    def get_status(self):
        """Return (is_running, log_text, status_message, current_count, total_count)."""
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def stop(self):
        """Signal the running batch to stop after the current image."""
        self.stop_event.set()

    def _persist_bioclip_embedding(self, image_id: int) -> None:
        """Upsert the BioCLIP image embedding produced during the last classify.

        Best-effort: any DB or numpy error is logged at DEBUG and swallowed so
        embedding persistence never fails a bird-species job. No-op on
        non-Postgres engines (see ``db.update_image_embeddings_batch_for_space``).
        Gated by ``config.embeddings.persist_bioclip_image`` (default true).
        """
        if image_id is None or self.classifier is None:
            return
        vec = getattr(self.classifier, "last_image_embedding", None)
        if vec is None:
            return
        try:
            from modules import config as _cfg
            from modules import db as _db
            from modules.embedding_spaces import BIOCLIP_IMAGE_SPACE_CODE

            emb_section = _cfg.get_config_section('embeddings') or {}
            if not bool(emb_section.get('persist_bioclip_image', True)):
                return
            versions = emb_section.get('model_versions') or {}
            model_version = versions.get(BIOCLIP_IMAGE_SPACE_CODE) or getattr(
                self.classifier, "MODEL_ID", None
            )
            _db.update_image_embeddings_batch_for_space(
                BIOCLIP_IMAGE_SPACE_CODE,
                [(image_id, vec, model_version)],
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.debug(
                "bird_species: BioCLIP embedding upsert failed for image_id=%s: %s",
                image_id,
                exc,
            )

    def start_batch(
        self,
        input_path: str,
        job_id: int = None,
        candidate_species: List[str] = None,
        threshold: float = 0.1,
        top_k: int = 3,
        overwrite: bool = False,
        resolved_image_ids: List[int] = None,
    ) -> str:
        """Start classification in a background thread. Returns 'Started' or error string."""
        if self.is_running:
            return "Error: Already running."

        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0

        if job_id is None:
            from modules import db as _db
            job_id = _db.create_job(input_path or "BIRD_SPECIES")

        def target():
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                try:
                    from modules.pipeline_diagnostics import phase_timer
                    with phase_timer("BirdSpeciesRunner.batch", job_id):
                        self._run_batch_internal(
                            input_path, candidate_species, threshold, top_k,
                            overwrite, job_id=job_id, resolved_image_ids=resolved_image_ids,
                        )
                except Exception:
                    self.status_message = "Failed"
                    raise
                finally:
                    if "Error" in self.status_message:
                        self.status_message = "Failed"
                    elif not self.status_message.startswith("Done"):
                        self.status_message = "Done"

            safe_runner_thread(self, job_id, target_wrapper)

        self._thread = threading.Thread(target=target, name="bird-species-runner", daemon=True)
        self._thread.start()
        return "Started"

    def _run_batch_internal(
        self,
        input_path: str,
        candidate_species: Optional[List[str]],
        threshold: float,
        top_k: int,
        overwrite: bool,
        job_id: int = None,
        resolved_image_ids: Optional[List[int]] = None,
    ):
        from modules import db
        from modules.events import event_manager
        from modules.run_log import runner_emit

        def log(msg: str, level: str = "INFO") -> None:
            runner_emit(self.log_history, job_id, msg, level, phase="bird_species")

        self.stop_event.clear()
        log(f"Starting bird species classification on {input_path or 'Selected Images'}...")
        self.status_message = "Running..."

        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id,
                "job_type": "bird_species",
                "input_path": input_path,
            })

        # --- Load candidate species list ---
        species_list = candidate_species or _load_default_species()
        if not species_list:
            log(
                "Error: No candidate species list available. "
                "Add species to data/bird_species_list.txt or pass candidate_species.",
                "ERROR",
            )
            self.status_message = "Error: no species list"
            if job_id:
                db.update_job_status(job_id, "failed")
            return

        log(f"Using {len(species_list)} candidate species.")

        # --- Load model (lazy, cached on self.classifier) ---
        if not self.classifier:
            try:
                log("Loading BioCLIP 2 model (first run may take a while)...")
                self.classifier = BioCLIPClassifier()
                self.classifier.load_model()
                log("Model loaded.")
            except ImportError:
                log("Error: open_clip not installed. Run: pip install open_clip_torch", "ERROR")
                self.status_message = "Error: open_clip not installed"
                if job_id:
                    db.update_job_status(job_id, "failed")
                return
            except Exception as exc:
                log(f"Error loading BioCLIP 2: {exc}", "ERROR")
                self.status_message = "Error loading model"
                if job_id:
                    db.update_job_status(job_id, "failed")
                return

        # --- Fetch images that have "birds" keyword ---
        log("Querying images with 'birds' keyword...")
        all_images = db.get_images_with_keyword(
            folder_path=input_path,
            keyword="birds",
            resolved_image_ids=resolved_image_ids,
        )
        log(f"Found {len(all_images)} bird-tagged images.")

        if not all_images:
            # Check if reason for empty set is because Tagging hasn't run at all
            if resolved_image_ids:
                log("No images with 'birds' keyword found in selection. Ensure the Tagging phase has completed first.", "WARNING")
            else:
                log("No images with 'birds' keyword found in folder. Ensure images are tagged first.", "WARNING")
            
            self.status_message = "Done (no bird images)"
            if job_id:
                db.update_job_status(job_id, "completed")
                event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "completed"})
            return

        # --- Optionally skip images already classified ---
        if not overwrite:
            all_image_ids = [row["id"] for row in all_images]
            already_classified = _get_image_ids_with_species_keyword(all_image_ids)
            if already_classified:
                before = len(all_images)
                all_images = [row for row in all_images if row["id"] not in already_classified]
                log(f"Skipping {before - len(all_images)} already-classified images "
                    f"(use overwrite=true to re-classify).")

        self.total_count = len(all_images)
        self.current_count = 0

        if self.total_count == 0:
            log("All bird images already classified.")
            self.status_message = "Done (all already classified)"
            if job_id:
                db.update_job_status(job_id, "completed")
                event_manager.broadcast_threadsafe("job_completed", {"job_id": job_id, "status": "completed"})
            return

        log(f"Classifying {self.total_count} images...")
        processed = 0
        skipped = 0

        # Track phase status for each image
        phase_code = "bird_species"

        for row in all_images:
            if self.stop_event.is_set():
                log("Stopped by user.", "WARNING")
                break
            if job_id and db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("Paused (job status).", "WARNING")
                break

            file_path = row["file_path"]
            inference_path = _resolve_inference_path(row, file_path)

            if not inference_path or not os.path.exists(inference_path):
                # Terminal at this executor version: classification can't proceed
                # until the file reappears (or is pruned). 'skipped' lets the heal
                # status filter treat it as terminal; 'failed' caused heal to
                # re-queue the same folder forever.
                db.set_image_phase_status(
                    row["id"],
                    phase_code,
                    "skipped",
                    skip_reason="file_missing",
                    skipped_by="bird_species_runner",
                    executor_version=BIRD_SPECIES_RUNNER_VERSION,
                )
                log(f"Skipped (file not found): {os.path.basename(file_path)}", "WARNING")
                skipped += 1
                self.current_count += 1
                continue

            try:
                predictions = self.classifier.classify(
                    inference_path, species_list, threshold=threshold, top_k=top_k
                )

                # Best-effort: persist the BioCLIP image embedding computed during
                # classify() so similarity/diversity/tag-propagation can reuse it.
                try:
                    self._persist_bioclip_embedding(row["id"])
                except Exception:
                    logger.debug(
                        "bird_species: BioCLIP embedding persist failed for image_id=%s",
                        row.get("id"),
                        exc_info=True,
                    )

                if predictions:
                    # Build merged keywords: keep existing non-species keywords + new species: ones
                    existing_kw_str = (row.get("keywords") or "").strip()
                    existing_kws = [k.strip() for k in existing_kw_str.split(",") if k.strip()]
                    base_kws = [k for k in existing_kws if not k.lower().startswith("species:")]
                    new_species_kws = [f"species:{name}" for name, _ in predictions]
                    merged = base_kws + new_species_kws
                    merged_str = ",".join(merged)

                    db.update_image_fields_batch([(row["id"], {"keywords": merged_str})])
                    db.set_image_phase_status(
                        row["id"],
                        phase_code,
                        "done",
                        executor_version=BIRD_SPECIES_RUNNER_VERSION,
                    )
                    log(f"{os.path.basename(file_path)}: {', '.join(new_species_kws)}")
                    processed += 1
                else:
                    db.set_image_phase_status(
                        row["id"],
                        phase_code,
                        "done",
                        executor_version=BIRD_SPECIES_RUNNER_VERSION,
                    )
                    log(f"{os.path.basename(file_path)}: no species above threshold")
                    skipped += 1

            except Exception as exc:
                db.set_image_phase_status(
                    row["id"],
                    phase_code,
                    "failed",
                    error=str(exc),
                    executor_version=BIRD_SPECIES_RUNNER_VERSION,
                )
                log(f"Error classifying {os.path.basename(file_path)}: {exc}", "ERROR")
                logger.exception("BirdSpeciesRunner error on %s", file_path)
                skipped += 1

            self.current_count += 1
            if self.current_count % 5 == 0:
                event_manager.broadcast_threadsafe("job_progress", {
                    "job_id": job_id,
                    "job_type": "bird_species",
                    "current": self.current_count,
                    "total": self.total_count,
                })

        log(f"Done. Classified: {processed}, Skipped: {skipped}")
        self.status_message = f"Done ({processed} classified, {skipped} skipped)"

        if job_id:
            if self.stop_event.is_set() or db.job_should_stop_processing(job_id):
                try:
                    db.reconcile_stale_running_phases_for_jobs(
                        [job_id],
                        error_message=db.GRACEFUL_PAUSE_MSG,
                        in_flight_to="not_started",
                    )
                except Exception:
                    logger.exception("bird_species: reconcile after stop failed (job_id=%s)", job_id)
                j = db.get_job(job_id)
                st = (j.get("status") or "").strip().lower() if j else ""
                if st == "running":
                    try:
                        db.update_job_status(job_id, "paused", "\n".join(self.log_history))
                    except Exception:
                        pass
                event_manager.broadcast_threadsafe(
                    "job_completed",
                    {"job_id": job_id, "status": (j or {}).get("status") or "paused"},
                )
            else:
                db.update_job_status(job_id, "completed")
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id,
                    "status": "completed",
                })
