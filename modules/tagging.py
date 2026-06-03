import os
import torch
import logging
import threading
from typing import List, Dict, Optional
from modules import db, xmp
from modules.events import event_manager
from modules.phases import PhaseCode, PhaseStatus
from modules.phases_policy import explain_phase_run_decision
from modules.version import APP_VERSION
from modules.indexing_policy import filter_image_rows_for_nef_policy

TAGGER_VERSION = "1.0.0"  # bump when CLIP model or tagging logic changes

# Setup logging
logger = logging.getLogger(__name__)


def propagate_tags(
    folder_path: str = None,
    dry_run: bool = True,
    k: int = None,
    min_similarity: float = None,
    min_keyword_confidence: float = None,
    min_support_neighbors: int = None,
    write_mode: str = None,
    max_keywords: int = None,
    focus_image_id: Optional[int] = None,
) -> Dict:
    """
    Propagate keywords from tagged images to untagged neighbors using embedding similarity.

    For each untagged image with a stored embedding:
      1. Find k nearest *tagged* neighbors by cosine similarity.
      2. Aggregate neighbor keywords with similarity-weighted voting.
      3. Apply keywords that pass confidence, support, and anchor thresholds.

    Args:
        folder_path: Optional folder scope (None = all images).
        dry_run: If True, compute candidates but do not write to DB.
        k: Number of nearest neighbors to consider.
        min_similarity: Minimum cosine similarity for the top neighbor (anchor).
        min_keyword_confidence: Minimum weighted keyword score to accept.
        min_support_neighbors: Minimum number of neighbors that must contain the keyword.
        write_mode: 'replace_missing_only' (default) or 'append'.
        max_keywords: Maximum keywords to propagate per image.
        focus_image_id: With dry_run=True, preview suggestions for this image even if tagged;
            excludes keywords already on the image. Omits duplicate processing if also untagged.

    Returns:
        Dict with 'propagated', 'skipped', 'total_untagged', and 'candidates' (dry_run only).
    """
    import numpy as np
    from modules import config
    from modules.similar_search import _normalize

    # Load defaults from config
    cfg = config.get_config_section("tagging")
    k = k if k is not None else cfg.get("propagation_k", 5)
    min_similarity = min_similarity if min_similarity is not None else cfg.get("propagation_min_similarity", 0.85)
    min_keyword_confidence = min_keyword_confidence if min_keyword_confidence is not None else cfg.get("propagation_min_keyword_confidence", 0.60)
    min_support_neighbors = min_support_neighbors if min_support_neighbors is not None else cfg.get("propagation_min_support_neighbors", 2)
    write_mode = write_mode or cfg.get("propagation_write_mode", "replace_missing_only")
    max_keywords = max_keywords if max_keywords is not None else cfg.get("propagation_max_keywords", 10)

    # Fetch data
    untagged, tagged = db.get_images_for_tag_propagation(folder_path=folder_path)
    orig_untagged_count = len(untagged)

    result = {
        "propagated": 0,
        "skipped": 0,
        "total_untagged": orig_untagged_count,
        "total_tagged": len(tagged),
    }

    if not tagged:
        logger.info("Tag propagation: no tagged images with embeddings found.")
        if untagged:
            result["skipped"] = len(untagged)
        return result

    if not untagged and not (dry_run and focus_image_id):
        logger.info("Tag propagation: no untagged images with embeddings found.")
        return result

    # Build tagged matrix once
    tagged_ids = [t[0] for t in tagged]
    tagged_keywords = [t[3].split(",") for t in tagged]  # list of keyword lists
    tagged_vecs = np.stack([np.frombuffer(t[2], dtype=np.float32) for t in tagged])
    tagged_norm = _normalize(tagged_vecs)

    # Collect all unique keywords across tagged images for indexing
    all_kw = sorted({kw.strip() for kwl in tagged_keywords for kw in kwl if kw.strip()})
    kw_to_idx = {kw: i for i, kw in enumerate(all_kw)}

    # Build keyword presence matrix: (num_tagged, num_keywords) bool
    kw_matrix = np.zeros((len(tagged_ids), len(all_kw)), dtype=np.float32)
    for row_i, kwl in enumerate(tagged_keywords):
        for kw in kwl:
            kw = kw.strip()
            if kw and kw in kw_to_idx:
                kw_matrix[row_i, kw_to_idx[kw]] = 1.0

    candidates_list = []  # for dry-run reporting

    def score_embedding(emb_bytes: bytes):
        """Return (accepted list of (keyword, score), anchor_similarity) or None if skipped."""
        query_vec = np.frombuffer(emb_bytes, dtype=np.float32)
        query_norm = _normalize(query_vec)
        sims = tagged_norm @ query_norm
        top_k_idx = np.argsort(-sims)[:k]
        top_sims = sims[top_k_idx]
        if len(top_sims) == 0 or top_sims[0] < min_similarity:
            return None
        valid_mask = top_sims >= min_similarity
        top_k_idx = top_k_idx[valid_mask]
        top_sims = top_sims[valid_mask]
        if len(top_k_idx) == 0:
            return None
        sim_total = top_sims.sum()
        neighbor_kw = kw_matrix[top_k_idx]
        weighted_scores = (top_sims[:, None] * neighbor_kw).sum(axis=0) / sim_total
        support_counts = neighbor_kw.sum(axis=0)
        accepted_local = []
        for kw_idx, kw in enumerate(all_kw):
            score = float(weighted_scores[kw_idx])
            support = int(support_counts[kw_idx])
            if score >= min_keyword_confidence and support >= min_support_neighbors:
                accepted_local.append((kw, score))
        if not accepted_local:
            return None
        accepted_local.sort(key=lambda x: -x[1])
        accepted_local = accepted_local[:max_keywords]
        return accepted_local, float(top_sims[0])

    def append_candidate(img_id, file_path, accepted_pairs, anchor_sim):
        new_keywords = [kw for kw, _ in accepted_pairs]
        candidates_list.append({
            "image_id": img_id,
            "file_path": file_path,
            "keywords": new_keywords,
            "keyword_scores": [
                {"keyword": kw, "confidence": round(float(sc), 4)} for kw, sc in accepted_pairs
            ],
            "top_neighbor_similarity": round(anchor_sim, 4),
        })

    work_untagged = list(untagged)
    if focus_image_id is not None:
        work_untagged = [t for t in work_untagged if t[0] != focus_image_id]

    try:
        for img_id, file_path, emb_bytes in work_untagged:
            scored = score_embedding(emb_bytes)
            if scored is None:
                result["skipped"] += 1
                continue
            accepted, anchor_sim = scored
            if dry_run:
                append_candidate(img_id, file_path, accepted, anchor_sim)
                result["propagated"] += 1
            else:
                new_keywords = [kw for kw, _ in accepted]
                tags_str = ",".join(new_keywords)
                if db.update_image_field(img_id, "keywords", tags_str):
                    result["propagated"] += 1
                    logger.info("Propagated %d keywords to image %d: %s", len(new_keywords), img_id, tags_str)
                else:
                    result["skipped"] += 1
                    logger.warning("Tag propagation update failed for image %d", img_id)

        if dry_run and focus_image_id is not None:
            focus_row = db.get_image_tag_propagation_focus(focus_image_id)
            if focus_row:
                emb, fp, img_folder, kw_csv = focus_row
                ok_folder = True
                if folder_path:
                    norm_req = os.path.normpath(folder_path)
                    ok_folder = bool(img_folder) and os.path.normpath(img_folder) == norm_req
                if not ok_folder:
                    logger.info(
                        "Tag propagation focus_image_id=%s not in folder %s (image folder=%s)",
                        focus_image_id, folder_path, img_folder,
                    )
                else:
                    scored = score_embedding(emb)
                    if scored:
                        accepted, anchor_sim = scored
                        existing = {x.strip().lower() for x in kw_csv.split(",") if x.strip()}
                        accepted = [(kw, sc) for kw, sc in accepted if kw.strip().lower() not in existing]
                        if accepted:
                            append_candidate(focus_image_id, fp, accepted, anchor_sim)
                            result["propagated"] += 1

    except Exception as e:
        logger.error("Tag propagation error: %s", e)
        raise

    if dry_run:
        result["candidates"] = candidates_list

    logger.info(
        "Tag propagation complete: %d propagated, %d skipped, %d untagged, %d tagged (dry_run=%s)",
        result["propagated"], result["skipped"], result["total_untagged"], result["total_tagged"], dry_run,
    )
    return result

class KeywordScorer:
    """
    Uses CLIP (Contrastive Language-Image Pre-Training) to tag images with keywords.
    """
    
    DEFAULT_KEYWORDS = [
        "landscape", "portrait", "urban", "cityscape", "nature", "wildlife", 
        "architecture", "macro", "street", "night", "black and white", 
        "sunset", "sunrise", "beach", "forest", "mountain", "water", 
        "flowers", "animals", "birds", "insect", "people", "abstract", "minimal",
        "aerial", "transportation"
    ]

    def __init__(self, model_name: str = None, device: str = None):
        # Load model name from config if not provided
        if model_name is None:
            from modules import config
            tagging_config = config.get_config_section('tagging')
            model_name = tagging_config.get('clip_model', "openai/clip-vit-base-patch32")
        self.model_name = model_name
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        # Most-recent CLIP image embedding (512-d, L2-normalized) populated as a
        # side effect of predict() so TaggingRunner can persist it under the
        # ``clip_vit_b32_image`` space without an extra forward pass.
        self.last_image_embedding = None
        logger.info(f"KeywordScorer initialized. Device: {self.device}")

    def load_model(self):
        """Lazy load the model."""
        if self.model is None:
            try:
                from transformers import CLIPModel, CLIPProcessor

                logger.info(f"Loading CLIP model: {self.model_name}...")
                self.model = CLIPModel.from_pretrained(self.model_name).to(self.device)
                self.processor = CLIPProcessor.from_pretrained(self.model_name)
                logger.info("CLIP model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                raise

    def predict(self, image_path: str, keywords: List[str] = None, threshold: float = 0.2, top_k: int = 5) -> List[str]:
        """
        Predict keywords for an image using zero-shot classification.
        """
        self.load_model()

        self.last_image_embedding = None
        target_keywords = keywords if keywords else self.DEFAULT_KEYWORDS
        prompts = [f"a photo of {k}" for k in target_keywords]
        
        try:
            from modules.thumbnails import open_image_for_ml

            image = open_image_for_ml(image_path)

            inputs = self.processor(text=prompts, images=image, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)

            try:
                from modules.embeddings_extract import extract_clip_image_features_from_outputs

                self.last_image_embedding = extract_clip_image_features_from_outputs(outputs)
            except Exception as emb_err:  # noqa: BLE001 — best-effort side effect
                logger.debug("CLIP image embedding extraction failed: %s", emb_err)

            logits_per_image = outputs.logits_per_image 
            probs = logits_per_image.softmax(dim=1) 
            
            probs_list = probs[0].tolist()
            
            valid_results = []
            for i, score in enumerate(probs_list):
                if score >= threshold:
                    valid_results.append((target_keywords[i], score))
            
            valid_results.sort(key=lambda x: x[1], reverse=True)
            final_keywords = [k for k, s in valid_results[:top_k]]
            
            return final_keywords
            
        except Exception as e:
            logger.error(f"Error processing {image_path}: {e}")
            return []


class CaptionGenerator:
    """
    Uses BLIP for image captioning.
    """
    def __init__(self, model_name: str = "Salesforce/blip-image-captioning-base", device: str = None):
        self.model_name = model_name
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        # Most-recent BLIP vision-encoder pooler_output (768-d, L2-normalized);
        # populated by generate() when the extract_blip flag is enabled so
        # TaggingRunner can persist it under the ``blip_vit_b16_image`` space.
        self.last_image_embedding = None
        logger.info(f"CaptionGenerator initialized. Device: {self.device}")

    def load_model(self):
        if self.model is None:
            try:
                from transformers import BlipForConditionalGeneration, BlipProcessor

                logger.info(f"Loading BLIP model: {self.model_name}...")
                self.processor = BlipProcessor.from_pretrained(self.model_name)
                self.model = BlipForConditionalGeneration.from_pretrained(self.model_name).to(self.device)
                logger.info("BLIP model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load BLIP model: {e}")
                raise

    def generate(self, image_path: str, extract_embedding: bool = False) -> str:
        """Generate a caption for the image.

        If ``extract_embedding`` is True, also populate ``self.last_image_embedding``
        with a 768-d L2-normalized vector from the BLIP vision tower for
        persistence by the caller. This costs one extra vision-tower forward
        pass per image.
        """
        self.load_model()
        self.last_image_embedding = None
        try:
            from modules.thumbnails import open_image_for_ml

            image = open_image_for_ml(image_path).convert("RGB")
            inputs = self.processor(image, return_tensors="pt").to(self.device)
            # Load max_new_tokens from config
            from modules import config
            tagging_config = config.get_config_section('tagging')
            max_tokens = tagging_config.get('max_new_tokens', 50)
            context_tokens = self.model.generate(**inputs, max_new_tokens=max_tokens)
            caption = self.processor.decode(context_tokens[0], skip_special_tokens=True)

            if extract_embedding:
                try:
                    from modules.embeddings_extract import extract_blip_image_features

                    pixel_values = inputs.get("pixel_values") if isinstance(inputs, dict) else getattr(inputs, "pixel_values", None)
                    if pixel_values is not None:
                        self.last_image_embedding = extract_blip_image_features(self.model, pixel_values)
                except Exception as emb_err:  # noqa: BLE001 — best-effort side effect
                    logger.debug("BLIP image embedding extraction failed: %s", emb_err)

            return caption.capitalize()
        except Exception as e:
            logger.error(f"Caption generation failed for {image_path}: {e}")
            return ""

class TaggingRunner:
    """
    Runs tagging in a local thread, yielding logs.

    tagging_engine: optional ITaggingEngine (e.g. MockTaggingEngine); when set, CLIP/BLIP are not loaded.
    """
    def __init__(self, tagging_engine=None):
        self.stop_event = threading.Event()
        self.tagging_engine = tagging_engine
        self.scorer = None
        self.captioner = None
        
        # State persistence
        self.is_running = False
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0
        
    def get_status(self):
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count
        
    def start_batch(self, input_path: str, job_id: int = None, custom_keywords: List[str] = None, overwrite: bool = False, generate_captions: Optional[bool] = None, generate_accessibility: Optional[bool] = None, resolved_image_ids: List[int] = None, report_collector=None):
        # Resolve generate_captions from config if not provided
        if generate_captions is None:
            from modules import config
            generate_captions = config.get_config_section('tagging').get('captions_default', True)
        if generate_accessibility is None:
            from modules import config
            generate_accessibility = config.get_config_section('tagging').get('accessibility_default', False)
        if self.is_running:
            return "Error: Already running."

        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0

        if job_id is None:
            from modules import db
            job_id = db.create_job(input_path or "ALL_IMAGES_TAGGING")

        def target():
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                try:
                    from modules.pipeline_diagnostics import phase_timer
                    with phase_timer("TaggingRunner.batch", job_id):
                        self._run_batch_internal(
                            input_path,
                            custom_keywords,
                            overwrite,
                            generate_captions,
                            generate_accessibility,
                            job_id=job_id,
                            resolved_image_ids=resolved_image_ids,
                            report_collector=report_collector,
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

        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def _run_batch_internal(self, input_path: str, custom_keywords: List[str] = None, overwrite: bool = False, generate_captions: bool = False, generate_accessibility: bool = False, job_id: int = None, resolved_image_ids: List[int] = None, report_collector=None):
        """
        Internal sync runner for tagging process.
        """
        from modules.run_log import runner_emit

        def log(msg: str, level: str = "INFO", image_id: Optional[int] = None) -> None:
            runner_emit(self.log_history, job_id, msg, level, phase="keywords", image_id=image_id)

        # Convert Windows path to WSL path if running in WSL
        if input_path and ":" in input_path and len(input_path) > 1 and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            # Check if we are actually in WSL context (mnt exists)
            if os.path.exists("/mnt/"): 
                 if os.path.exists(wsl_path):
                     input_path = wsl_path
                     
        self.stop_event.clear()
        log(f"Starting Tagging process on {input_path or 'Selected Images'}...")
        self.status_message = "Running..."
        
        # Notify job started
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "tagging", 
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
        
        # Initialize Scorer (skipped when a tagging engine was injected)
        if self.tagging_engine is None:
            if not self.scorer:
                try:
                    log("Loading CLIP model (this may take a while)...")
                    self.scorer = KeywordScorer()
                    self.scorer.load_model()
                    log("Model loaded.")
                except Exception as e:
                    log(f"Error loading model: {e}", "ERROR")
                    fail_terminal("Error loading model")
                    return

            if generate_captions and not self.captioner:
                try:
                    log("Loading Captioning model (BLIP)...")
                    self.captioner = CaptionGenerator()
                    self.captioner.load_model()
                    log("Captioning model loaded.")
                except Exception as e:
                    log(f"Error loading captioning model: {e}", "ERROR")
                    fail_terminal("Error loading captioning model")
                    return
        else:
            log("Using injected tagging engine (no CLIP/BLIP load).")

        log("Scanning for images...")
        all_images = []

        if resolved_image_ids is not None:
             try:
                 rows = db.get_all_images(limit=-1)
             except Exception as e:
                 log(f"Error fetching from DB: {e}", "ERROR")
                 fail_terminal("Error DB")
                 return
             if not resolved_image_ids:
                 log("No images matched selectors.")
                 self.status_message = "Done (no images)"
                 self.total_count = 0
                 self.current_count = 0
                 if job_id:
                     db.update_job_status(job_id, "completed", "\n".join(self.log_history))
                     event_manager.broadcast_threadsafe("job_completed", {
                         "job_id": job_id,
                         "status": "completed"
                     })
                 return

             selected_ids = {int(i) for i in resolved_image_ids}
             all_images = [row for row in rows if row.get('id') in selected_ids]
             log(f"Selector mode enabled. Matched {len(all_images)} images by ID.")
        elif not input_path or not input_path.strip():
             log("Input path empty. Processing all images in DB...")
             try:
                 rows = db.get_all_images(limit=-1)
             except Exception as e:
                 log(f"Error fetching from DB: {e}", "ERROR")
                 fail_terminal("Error DB")
                 return
             all_images = [row for row in rows]
        elif os.path.isdir(input_path):
             # Use folder_id-based lookup (same as SelectionRunner) to avoid
             # path format mismatch (Windows vs WSL) when filtering by file_path.
             db.invalidate_folder_images_cache()
             all_images = db.get_images_by_folder(input_path)
             if not all_images:
                 # Fallback: recursive lookup across subfolders.
                 from modules import utils
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
            log(f"Input path not found or not a directory: {input_path}", "ERROR")
            fail_terminal("Error Path")
            return

        all_images = filter_image_rows_for_nef_policy(all_images)

        # Filtering logic for phase policy
        in_scope_total = len(all_images)
        final_images = []
        for row in all_images:
            decision = explain_phase_run_decision(
                row['id'],
                PhaseCode.KEYWORDS,
                current_executor_version=TAGGER_VERSION,
                force_run=overwrite
            )
            if decision['should_run']:
                final_images.append(row)
            else:
                logger.info("Skipping keywords image_id=%s: %s", row['id'], decision['reason'])
                # Issue #160: record filtered-out images as skipped so job_phases.images_skipped
                # reflects the phase-policy filter, not just per-image failures inside the loop.
                if report_collector is not None:
                    try:
                        report_collector.record_skip(int(row['id']), decision.get('reason') or 'phase_policy_skip')
                    except Exception:
                        logger.debug("tagging: record_skip failed for image_id=%s", row.get('id'), exc_info=True)

        all_images = final_images
        log(f"Found {len(all_images)} images to process.")
        self.total_count = len(all_images)
        self.current_count = 0

        # Issue #160: push the post-filter scope so job_phases denominator reflects what
        # the runner will actually attempt. The dispatcher seeded with the pre-filter
        # count (#159); this overwrites with the accurate targeted value.
        if report_collector is not None:
            try:
                report_collector.set_scope_counts(in_scope=in_scope_total, targeted=len(all_images))
            except Exception:
                logger.debug("tagging: set_scope_counts failed for job_id=%s", job_id, exc_info=True)
        
        processed_count = 0
        skipped_count = 0
        processed_folders = set()
        
        for row in all_images:
            if self.stop_event.is_set():
                log("Tagging stopped by user.", "WARNING")
                break
            if job_id and db.job_should_stop_processing(job_id):
                self.stop_event.set()
                log("Tagging paused (job status).", "WARNING")
                break

            path = row['file_path']
            folder = os.path.dirname(path)


            # Convert DB path to WSL path for processing if needed
            original_windows_path = path
            if ":" in path and path[1] == ":" and os.path.exists("/mnt/"):
                drive = path[0].lower()
                p = path[2:].replace("\\", "/")
                wsl_p = f"/mnt/{drive}{p}"
                path = wsl_p

            db.set_image_phase_status(
                row['id'],
                PhaseCode.KEYWORDS,
                PhaseStatus.RUNNING,
                app_version=APP_VERSION,
                executor_version=TAGGER_VERSION,
                job_id=job_id,
            )

            try:
                log(f"Tagging image_id={row['id']}: {path}", "DEBUG", image_id=row["id"])
                # Determine inference path (NEF vs Thumbnail)
                inference_path = path
                ext = os.path.splitext(path)[1].lower()
                if ext in ['.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng']:
                    from modules.thumbnails import get_thumb_wsl
                    thumb_path = get_thumb_wsl(row)
                    if thumb_path and os.path.exists(thumb_path):
                        inference_path = thumb_path

                # Resolve embedding-persistence flags once per image (cheap dict lookups).
                from modules import config as _emb_cfg
                _emb_section = _emb_cfg.get_config_section('embeddings') or {}
                _persist_clip = bool(_emb_section.get('persist_clip_image', True))
                _persist_blip = bool(_emb_section.get('persist_blip_image', True))

                # Run inference
                if self.tagging_engine is not None:
                    tags = self.tagging_engine.predict_keywords(inference_path, custom_keywords)
                    caption = ""
                    title = ""
                    if generate_captions:
                        caption = self.tagging_engine.generate_caption(inference_path)
                        import textwrap
                        title = textwrap.shorten(caption, width=50, placeholder="...")
                else:
                    tags = self.scorer.predict(inference_path, keywords=custom_keywords)
                    caption = ""
                    title = ""
                    if generate_captions:
                        caption = self.captioner.generate(
                            inference_path, extract_embedding=_persist_blip
                        )
                        import textwrap
                        title = textwrap.shorten(caption, width=50, placeholder="...")

                # Best-effort: persist the freshly-computed image embeddings for
                # this image (CLIP 512-d, BLIP 768-d) so downstream features
                # (similarity, diversity, tag propagation) can reuse them.
                if self.tagging_engine is None:
                    try:
                        self._persist_tagging_embeddings(row['id'], _persist_clip, _persist_blip)
                    except Exception:
                        logger.warning(
                            "tagging: embedding persist failed for image_id=%s",
                            row.get('id'),
                            exc_info=True,
                        )
                elif (_persist_clip or _persist_blip) and not getattr(self, "_warned_engine_persist_gap", False):
                    logger.warning(
                        "tagging: shared tagging_engine path does not yet extract "
                        "CLIP/BLIP image embeddings; image_embeddings_512 / "
                        "image_embeddings_768 will not populate via this runner. "
                        "Set embeddings.persist_clip_image / persist_blip_image to "
                        "false to silence this warning, or use TaggingRunner() with "
                        "no engine arg."
                    )
                    self._warned_engine_persist_gap = True

                tags = [t.strip() for t in (tags or []) if t and t.strip()]
                caption = (caption or "").strip()

                alt_text = None
                extended_description = None
                if generate_accessibility:
                    from modules import clip_accessibility

                    acc = clip_accessibility.describe_from_clip(
                        image_id=row['id'],
                        image_path=original_windows_path,
                        keywords=tags,
                        scorer=self.scorer if self.tagging_engine is None else None,
                        overwrite=overwrite,
                    )
                    if not acc.get('error'):
                        alt_text = (acc.get('alt_text') or '').strip() or None
                        extended_description = (
                            (acc.get('extended_description') or '').strip() or None
                        )
                        if acc.get('skipped'):
                            log(
                                f"Accessibility skipped image_id={row['id']}: {acc.get('reason')}",
                                "DEBUG",
                                image_id=row["id"],
                            )

                keywords_produced = bool(tags)
                metadata_produced = bool(caption or alt_text or extended_description)

                if keywords_produced or metadata_produced:
                    tags_str = ",".join(tags)
                    db.update_image_fields_batch([(row['id'], {
                        "keywords": tags_str,
                        "title": title if title else row.get('title'),
                        "description": caption if caption else row.get('description')
                    })])
                    if alt_text or extended_description:
                        db.upsert_image_xmp(row['id'], {
                            'alt_text': alt_text,
                            'extended_description': extended_description,
                        })
                    self.write_metadata(
                        original_windows_path,
                        tags,
                        title,
                        caption,
                        alt_text=alt_text or "",
                        extended_description=extended_description or "",
                    )
                    if keywords_produced:
                        processed_count += 1
                        processed_folders.add(folder)
                        db.set_image_phase_status(
                            row['id'],
                            PhaseCode.KEYWORDS,
                            PhaseStatus.DONE,
                            app_version=APP_VERSION,
                            executor_version=TAGGER_VERSION,
                            job_id=job_id,
                        )
                        if report_collector is not None:
                            try:
                                report_collector.record_after(
                                    int(row['id']),
                                    {
                                        "keywords": tags_str,
                                        "title": title or None,
                                        "description": caption or None,
                                    },
                                    action="processed",
                                )
                            except Exception:
                                logger.debug(
                                    "tagging: record_after failed for image_id=%s",
                                    row.get('id'),
                                    exc_info=True,
                                )
                    else:
                        skipped_count += 1
                        db.set_image_phase_status(
                            row['id'],
                            PhaseCode.KEYWORDS,
                            PhaseStatus.SKIPPED,
                            app_version=APP_VERSION,
                            executor_version=TAGGER_VERSION,
                            job_id=job_id,
                            skip_reason="caption_only_no_keywords",
                            skipped_by="tagging",
                        )
                        if report_collector is not None:
                            try:
                                report_collector.record_skip(
                                    int(row['id']),
                                    "caption_only_no_keywords",
                                )
                            except Exception:
                                logger.debug(
                                    "tagging: record_skip failed for image_id=%s",
                                    row.get('id'),
                                    exc_info=True,
                                )
                else:
                    skipped_count += 1
                    db.set_image_phase_status(
                        row['id'],
                        PhaseCode.KEYWORDS,
                        PhaseStatus.SKIPPED,
                        app_version=APP_VERSION,
                        executor_version=TAGGER_VERSION,
                        job_id=job_id,
                        skip_reason="no tags produced",
                        skipped_by="tagging",
                    )
                    # Issue #160: increment job_phases.images_skipped.
                    if report_collector is not None:
                        try:
                            report_collector.record_skip(int(row['id']), "no tags produced")
                        except Exception:
                            logger.debug("tagging: record_skip failed for image_id=%s", row.get('id'), exc_info=True)
            except Exception as e:
                log(f"Error processing {path}: {e}", "ERROR", image_id=row["id"])
                skipped_count += 1
                try:
                    db.set_image_phase_status(
                        row['id'],
                        PhaseCode.KEYWORDS,
                        PhaseStatus.FAILED,
                        app_version=APP_VERSION,
                        executor_version=TAGGER_VERSION,
                        job_id=job_id,
                        error=str(e)[:1024],
                    )
                except Exception:
                    logger.exception(
                        "tagging: failed to record FAILED phase status for image_id=%s",
                        row.get('id'),
                    )
                # Issue #160: increment job_phases.images_failed.
                if report_collector is not None:
                    try:
                        report_collector.record_failure(int(row['id']), str(e)[:1024])
                    except Exception:
                        logger.debug("tagging: record_failure failed for image_id=%s", row.get('id'), exc_info=True)

            self.current_count += 1
            if self.current_count % 5 == 0:
                event_manager.broadcast_threadsafe(
                    "job_progress",
                    {
                        "job_id": job_id,
                        "job_type": "tagging",
                        "phase_code": "keywords",
                        "current": self.current_count,
                        "total": self.total_count,
                    },
                )
                
        log(f"Done. Processed: {processed_count}, Skipped: {skipped_count}")

        # Issue #160: flush collector — writes final job_phases counters and any
        # pending job_image_actions rows. Best-effort; never blocks job completion.
        if report_collector is not None:
            try:
                report_collector.finalize()
            except Exception:
                logger.exception("tagging: report_collector.finalize() failed for job_id=%s", job_id)

        # Update Job Status
        if job_id:
            if self.stop_event.is_set() or db.job_should_stop_processing(job_id):
                try:
                    db.reconcile_stale_running_phases_for_jobs(
                        [job_id],
                        error_message=db.GRACEFUL_PAUSE_MSG,
                        in_flight_to="not_started",
                    )
                except Exception:
                    logger.exception("tagging: reconcile after stop failed (job_id=%s)", job_id)
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
                db.update_job_status(job_id, "completed")
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id,
                    "status": "completed",
                })

        # Update Folder Status
        if processed_folders:
            log("Updating folder completion flags...")
            for f in processed_folders:
                 try:
                     if db.check_and_update_folder_keywords_status(f):
                         log(f"Folder marked as fully processed: {f}")
                 except Exception as e:
                     log(f"Failed to update status for {f}: {e}")

    def _persist_tagging_embeddings(self, image_id: int, persist_clip: bool, persist_blip: bool) -> None:
        """Upsert CLIP / BLIP image embeddings produced during the last inference.

        Best-effort: any DB or numpy error is logged at DEBUG and swallowed so
        embedding persistence never fails a tagging job. No-op on non-Postgres
        engines (see ``db.update_image_embeddings_batch_for_space``).
        """
        if image_id is None:
            return
        from modules.embedding_spaces import (
            BLIP_IMAGE_SPACE_CODE,
            CLIP_IMAGE_SPACE_CODE,
        )

        emb_section = {}
        try:
            from modules import config as _cfg

            emb_section = _cfg.get_config_section('embeddings') or {}
        except Exception:
            emb_section = {}
        versions = emb_section.get('model_versions') or {}

        if persist_clip and self.scorer is not None:
            vec = getattr(self.scorer, "last_image_embedding", None)
            if vec is not None:
                try:
                    db.update_image_embeddings_batch_for_space(
                        CLIP_IMAGE_SPACE_CODE,
                        [(image_id, vec, versions.get(CLIP_IMAGE_SPACE_CODE) or getattr(self.scorer, "model_name", None))],
                    )
                except Exception as exc:  # noqa: BLE001 — best-effort
                    logger.warning(
                        "tagging: CLIP embedding upsert failed for image_id=%s: %s",
                        image_id,
                        exc,
                    )

        if persist_blip and self.captioner is not None:
            vec = getattr(self.captioner, "last_image_embedding", None)
            if vec is not None:
                try:
                    db.update_image_embeddings_batch_for_space(
                        BLIP_IMAGE_SPACE_CODE,
                        [(image_id, vec, versions.get(BLIP_IMAGE_SPACE_CODE) or getattr(self.captioner, "model_name", None))],
                    )
                except Exception as exc:  # noqa: BLE001 — best-effort
                    logger.warning(
                        "tagging: BLIP embedding upsert failed for image_id=%s: %s",
                        image_id,
                        exc,
                    )

    def write_metadata(
        self,
        image_path: str,
        keywords: List[str],
        title: str = "",
        description: str = "",
        rating: int = 0,
        label: str = "",
        alt_text: str = "",
        extended_description: str = "",
    ) -> bool:
        """
        Write keywords and metadata to image using unified XMP module.
        """
        try:
            success = xmp.write_metadata_unified(
                image_path=image_path,
                rating=rating if rating and rating > 0 else None,
                label=label if label else None,
                keywords=keywords if keywords else None,
                title=title if title else None,
                description=description if description else None,
                alt_text=alt_text if alt_text else None,
                extended_description=extended_description if extended_description else None,
                use_sidecar=True,
                use_embedded=True
            )
            if success:
                logger.info(f"Metadata written for {os.path.basename(image_path)}")
            return success
        except Exception as e:
            logger.error(f"Metadata write failed: {e}")
            return False
        
    def stop(self):
        self.stop_event.set()

    def run_single_image(
        self,
        file_path,
        custom_keywords=None,
        generate_captions=True,
        generate_accessibility=None,
    ):
        """
        Runs tagging/captioning for a single image, blocking.
        Returns: success (bool), message (str)
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        if generate_accessibility is None:
            from modules import config
            generate_accessibility = config.get_config_section('tagging').get(
                'accessibility_default', False
            )
        
        self.status_message = "Tagging (Manual)..."
        
        # Initialize Scorer
        if not self.scorer:
            try:
                self.scorer = KeywordScorer()
                self.scorer.load_model()
            except Exception as e:
                self.status_message = "Error"
                return False, f"Error loading CLIP model: {e}"

        if generate_captions and not self.captioner:
            try:
                self.captioner = CaptionGenerator()
                self.captioner.load_model()
            except Exception as e:
                self.status_message = "Error"
                return False, f"Error loading BLIP model: {e}"

        # Determine inference path (use thumbnail for NEF/RAW)
        inference_path = file_path
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng']:
             row = db.get_image_details(file_path)
             if row:
                from modules.thumbnails import get_thumb_wsl
                thumb_path = get_thumb_wsl(row)
                if thumb_path and os.path.exists(thumb_path):
                    inference_path = thumb_path
        
        try:
            tags = self.scorer.predict(inference_path, keywords=custom_keywords)
            caption = ""
            title = ""
            
            if generate_captions:
                 caption = self.captioner.generate(inference_path)
                 import textwrap
                 title = textwrap.shorten(caption, width=50, placeholder="...")
                 
            alt_text = None
            extended_description = None
            if generate_accessibility:
                from modules import clip_accessibility

                row_for_acc = db.get_image_details(file_path)
                image_id_acc = row_for_acc['id'] if row_for_acc else None
                acc = clip_accessibility.describe_from_clip(
                    image_id=image_id_acc,
                    image_path=file_path,
                    keywords=tags,
                    scorer=self.scorer,
                    overwrite=False,
                )
                if not acc.get('error'):
                    alt_text = (acc.get('alt_text') or '').strip() or None
                    extended_description = (
                        (acc.get('extended_description') or '').strip() or None
                    )

            if tags or caption or alt_text or extended_description:
                tags_str = ",".join(tags)
                # Update DB
                try:
                    row = db.get_image_details(file_path)
                    image_id = row['id'] if row else None

                    if not image_id:
                        return False, "Image not found in DB"

                    with db.connection() as conn:
                        c = conn.cursor()
                        if caption:
                            c.execute("UPDATE images SET keywords = ?, title = ?, description = ? WHERE id = ?",
                                      (tags_str, title, caption, image_id))
                        else:
                            c.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, image_id))
                        conn.commit()

                    # Sync keywords to normalized schema (dual-write)
                    db._sync_image_keywords(image_id, tags_str)
                    if alt_text or extended_description:
                        db.upsert_image_xmp(image_id, {
                            'alt_text': alt_text,
                            'extended_description': extended_description,
                        })
                    success_msg = f"Tags: {len(tags)} found"
                    if caption:
                        success_msg += ", Caption generated"
                    if alt_text or extended_description:
                        success_msg += ", Accessibility metadata generated"
                except Exception as e:
                    logger.error(f"Error updating image tags: {e}", exc_info=True)
                    return False, f"Database error: {e}"
                
                # Write Metadata
                self.write_metadata(
                    file_path,
                    tags,
                    title,
                    caption,
                    alt_text=alt_text or "",
                    extended_description=extended_description or "",
                )
                
                self.status_message = "Idle"
                return True, success_msg
                
            else:
                self.status_message = "Idle"
                return True, "No tags found."

        except Exception as e:
            self.status_message = "Error"
            return False, f"Error tagging: {e}"
