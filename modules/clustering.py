import os
import logging
import uuid
import numpy as np
import threading
import time
import json
from datetime import datetime
from PIL import Image
from sklearn.cluster import AgglomerativeClustering
from modules import db, utils, config
from modules.events import event_manager
from modules.run_log import runner_emit
from modules.phases import PhaseCode, PhaseStatus
from modules.phases_policy import explain_phase_run_decision
from modules.version import APP_VERSION
from modules.engines.base import IClusteringEngine
from modules.indexing_policy import filter_image_rows_for_nef_policy
from modules.quality_ranking import quality_tiebreak_sort_key_best_first

logger = logging.getLogger(__name__)

CLUSTER_VERSION = "1.0.0"  # bump when clustering algorithm or model changes

# Suppress TF logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Default cache directory for persisted feature vectors
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'thumbnails', 'feature_cache')


class ClusteringEngine(IClusteringEngine):
    def __init__(self, cache_dir=None):
        self.model = None
        self.feature_cache = {}  # In-memory cache (hash -> feature vector)
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        # Status tracking for UI button state management
        self.is_running = False
        self.status_message = "Idle"
        self.current = 0
        self.total = 0
        self._ensure_cache_dir()
        self._load_cache()

    def get_status(self):
        """Returns current status tuple: (is_running, status_message, current, total)"""
        return self.is_running, self.status_message, self.current, self.total

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            logging.info(f"Created feature cache directory: {self.cache_dir}")

    def _get_cache_file(self):
        """Returns path to the cache file."""
        return os.path.join(self.cache_dir, 'feature_cache.npz')

    def _load_cache(self):
        """Load persisted feature cache from disk."""
        cache_file = self._get_cache_file()
        if os.path.exists(cache_file):
            try:
                data = np.load(cache_file, allow_pickle=True)
                # Load the cache dict from the npz file
                if 'cache' in data:
                    self.feature_cache = data['cache'].item()
                    logging.info(f"Loaded {len(self.feature_cache)} cached feature vectors from disk.")
                data.close()
            except Exception as e:
                logging.warning(f"Failed to load feature cache: {e}")
                self.feature_cache = {}

    def _save_cache(self):
        """Persist feature cache to disk."""
        cache_file = self._get_cache_file()
        try:
            np.savez_compressed(cache_file, cache=self.feature_cache)
            logging.debug(f"Saved {len(self.feature_cache)} feature vectors to cache.")
        except Exception as e:
            logging.error(f"Failed to save feature cache: {e}")

    def _get_image_hash(self, file_path):
        """Get cache key from DB (image_hash + hash_version when present)."""
        details = db.get_image_details(file_path)
        if not details or not details.get("image_hash"):
            return None
        h = details["image_hash"]
        hv = details.get("hash_version")
        if hv is None:
            return h
        try:
            return f"{h}\tv{int(hv)}"
        except (TypeError, ValueError):
            return h

    def _select_best_image(self, img_ids, id_to_score, id_to_feature=None, id_to_exif=None):
        """
        Select the best representative image from a stack.

        Strategy is read from config key ``clustering.stack_representative_strategy``
        (or legacy ``clustering.best_image_strategy``)
        as ``score`` | ``centroid`` | ``balanced``. Falls back to ``score``
        when embeddings are unavailable.

        Args:
            img_ids: List of image IDs in the stack.
            id_to_score: Dict mapping image_id -> score_general (float or None).
            id_to_feature: Optional dict mapping image_id -> 1-D numpy embedding.
            id_to_exif: Optional ``image_id`` -> EXIF row (``iso``, ``exposure_time``,
                ``date_time_original``) for deterministic tie-break in ``score`` strategy.

        Returns:
            The image_id selected as best representative.
        """
        if not img_ids:
            return None
        if len(img_ids) == 1:
            return img_ids[0]

        clustering_config = config.get_config_section('clustering')
        strategy = clustering_config.get(
            'stack_representative_strategy',
            clustering_config.get('best_image_strategy', 'score')
        )
        alpha = float(clustering_config.get('best_image_alpha', 0.65))

        # Normalise scores to [0, 1] across the stack
        scores = np.array([float(id_to_score.get(i) or 0.0) for i in img_ids], dtype=np.float64)
        score_range = scores.max() - scores.min()
        if score_range > 0:
            norm_scores = (scores - scores.min()) / score_range
        else:
            norm_scores = np.zeros_like(scores)

        # Build embedding matrix; may be incomplete/missing
        features_available = id_to_feature is not None
        feat_matrix = None
        valid_mask = None
        if features_available:
            feats = [id_to_feature.get(i) for i in img_ids]
            valid_mask = [f is not None for f in feats]
            if any(valid_mask):
                feat_matrix = np.array(
                    [f if f is not None else np.zeros_like(next(x for x in feats if x is not None))
                     for f in feats],
                    dtype=np.float64
                )

        # Fall back to score strategy if no useful embeddings
        if strategy != 'score' and feat_matrix is None:
            strategy = 'score'

        if strategy == 'score':
            max_ns = float(np.max(norm_scores))
            tol = 1e-9
            best_indices = [j for j in range(len(img_ids)) if abs(norm_scores[j] - max_ns) <= tol]
            if len(best_indices) == 1:
                return img_ids[best_indices[0]]
            candidates = [img_ids[j] for j in best_indices]
            exif_by_id = id_to_exif
            if exif_by_id is None:
                exif_by_id = db.get_exif_fields_for_quality_tiebreak(list(img_ids))

            def _exif_row(iid: int) -> dict:
                ex = exif_by_id.get(iid) or {}
                return {
                    "id": iid,
                    "iso": ex.get("iso"),
                    "exposure_time": ex.get("exposure_time"),
                    "date_time_original": ex.get("date_time_original"),
                }

            return min(candidates, key=lambda iid: quality_tiebreak_sort_key_best_first(_exif_row(iid)))

        # Compute centroid from valid-embedding images only
        valid_feats = feat_matrix[[i for i, v in enumerate(valid_mask) if v]]
        centroid = valid_feats.mean(axis=0)

        # Cosine distance to centroid per image
        norms = np.linalg.norm(feat_matrix, axis=1, keepdims=True)
        centroid_norm = np.linalg.norm(centroid)
        # Avoid division by zero
        safe_norms = np.where(norms > 0, norms, 1.0)
        safe_centroid_norm = centroid_norm if centroid_norm > 0 else 1.0
        cosine_sim = feat_matrix.dot(centroid) / (safe_norms.squeeze() * safe_centroid_norm)
        # Images without valid embeddings should not be preferred
        cosine_sim[[i for i, v in enumerate(valid_mask) if not v]] = -1.0

        # Normalise cosine similarity to [0, 1]
        sim_range = cosine_sim.max() - cosine_sim.min()
        if sim_range > 0:
            norm_represent = (cosine_sim - cosine_sim.min()) / sim_range
        else:
            norm_represent = np.zeros_like(cosine_sim)

        if strategy == 'centroid':
            best_idx = int(np.argmax(norm_represent))
            return img_ids[best_idx]

        # balanced: alpha * quality + (1 - alpha) * representativeness
        combined = alpha * norm_scores + (1.0 - alpha) * norm_represent
        best_idx = int(np.argmax(combined))
        return img_ids[best_idx]

    def load_model(self):
        if self.model is None:
            # Deferred import
            import tensorflow as tf
            from tensorflow.keras.applications import MobileNetV2
            
            # Load MobileNetV2, exclude top layer, use global average pooling
            self.model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg', input_shape=(224, 224, 3))
            logging.info("Clustering Model (MobileNetV2) loaded.")

    def extract_features(self, image_paths, original_paths=None, progress_log=None, stop_event=None):
        """
        Extract features for a list of image paths.
        Uses persisted cache when available.
        Returns numpy array of features.

        Args:
            image_paths: Paths to load images from (may be thumbnails).
            original_paths: Original file paths for DB hash lookup. If None, image_paths are used.
            progress_log: Optional ``callable(message, level="INFO")`` for run-scoped UI logs.
            stop_event: Optional threading.Event to check for interruption.
        """
        if original_paths is None:
            original_paths = image_paths

        features_list = []
        valid_indices = []  # Track which images were successfully processed

        # Separate cached vs uncached images
        uncached_paths = []
        uncached_indices = []
        path_to_hash = {}
        cached_count = 0

        for i, (path, orig_path) in enumerate(zip(image_paths, original_paths)):
            if not os.path.exists(path):
                logger.debug(f"[Clustering] File not found for feature extraction: {path}")
                continue

            # Get hash for cache lookup using original path (DB stores original paths)
            img_hash = self._get_image_hash(orig_path)
            path_to_hash[path] = img_hash
            
            if img_hash and img_hash in self.feature_cache:
                # Use cached feature
                features_list.append(self.feature_cache[img_hash])
                valid_indices.append(i)
                cached_count += 1
            else:
                # Need to extract
                uncached_paths.append(path)
                uncached_indices.append(i)
        
        if cached_count > 0:
            logger.debug(f"[Clustering] Found {cached_count} image(s) in feature cache.")
        
        # Process uncached images in batches (model loaded only when needed)
        if uncached_paths:
            if progress_log:
                n_cached = cached_count
                progress_log(
                    f"Computing embeddings for {len(uncached_paths)} image(s) "
                    f"({n_cached} from cache); loading MobileNetV2 if needed — "
                    f"first load or large batches can take several minutes.",
                    "INFO",
                )
            logger.info(f"[Clustering] Computing embeddings for {len(uncached_paths)} image(s) ({cached_count} hit cache)")
            self.load_model()
            batch_images = []
            batch_paths = []
            batch_indices = []
            # Load batch size from config
            from modules import config
            processing_config = config.get_config_section('processing')
            batch_size = processing_config.get('clustering_batch_size', 32)
            new_features = []
            
            for idx, path in zip(uncached_indices, uncached_paths):
                try:
                    # Load image, resize to 224x224
                    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
                    from modules.thumbnails import open_image_for_ml

                    img = open_image_for_ml(path)
                    img = img.convert("RGB").resize((224, 224), Image.LANCZOS)
                    x = np.array(img, dtype=np.float32)
                    x = preprocess_input(x)
                    batch_images.append(x)
                    batch_paths.append(path)
                    batch_indices.append(idx)
                    
                    if len(batch_images) >= batch_size:
                        logger.debug(f"[Clustering] Predicting batch of {len(batch_images)} images...")
                        batch_arr = np.array(batch_images)
                        preds = self.model.predict(batch_arr, verbose=0)
                        
                        # Cache and collect results
                        for j, (p, feat) in enumerate(zip(batch_paths, preds)):
                            h = path_to_hash.get(p)
                            if h:
                                self.feature_cache[h] = feat
                            new_features.append((batch_indices[j], feat))
                        
                        logger.debug(f"[Clustering] Batch prediction complete. Processed {len(new_features)} uncached images so far.")
                        batch_images = []
                        batch_paths = []
                        batch_indices = []
                    
                    if stop_event and stop_event.is_set():
                        logger.info("[Clustering] Feature extraction interrupted by stop event.")
                        break
                        
                except Exception as e:
                    logging.error(f"Error extracting features for {path}: {e}")
            
            # Process remaining batch
            if batch_images:
                logger.debug(f"[Clustering] Predicting final batch of {len(batch_images)} images...")
                batch_arr = np.array(batch_images)
                preds = self.model.predict(batch_arr, verbose=0)
                
                for j, (p, feat) in enumerate(zip(batch_paths, preds)):
                    h = path_to_hash.get(p)
                    if h:
                        self.feature_cache[h] = feat
                    new_features.append((batch_indices[j], feat))
                logger.debug(f"[Clustering] Final batch prediction complete.")
            
            # Add new features to results in original index order
            for orig_idx, feat in new_features:
                features_list.append(feat)
                valid_indices.append(orig_idx)

            n_failed = len(uncached_paths) - len(new_features)
            if n_failed > 0:
                logging.warning(
                    "[Clustering] Feature extraction: %d/%d succeeded, %d failed",
                    len(new_features), len(uncached_paths), n_failed,
                )

            # Persist cache to disk after extraction
            if new_features:
                self._save_cache()
                logging.info(f"Cached {len(new_features)} new feature vectors. Total cache size: {len(self.feature_cache)}")
        
        # Sort by original index to maintain order consistency
        if features_list:
            sorted_pairs = sorted(zip(valid_indices, features_list), key=lambda x: x[0])
            valid_indices = [p[0] for p in sorted_pairs]
            features_list = [p[1] for p in sorted_pairs]
        
        return np.array(features_list), valid_indices

    def _get_image_time(self, row):
        """
        Returns timestamp for image. Tries metadata, falls back to file mtime.
        """
        # Try metadata
        if row['metadata']:
            try:
                meta = json.loads(row['metadata'])
                # Look for common EXIF date keys
                # "DateTimeOriginal", "CreateDate"
                # formats: "YYYY:MM:DD HH:MM:SS"
                date_str = meta.get('DateTimeOriginal') or meta.get('CreateDate')
                if date_str:
                    # Parse
                    return datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S").timestamp()
            except (ValueError, KeyError, TypeError):
                pass

        # Fallback: Filesystem mtime
        try:
            p = row['file_path']
            if os.path.exists(p):
                return os.path.getmtime(p)
        except (OSError, KeyError):
            pass
            
        return 0.0

    def _get_burst_uuid(self, row):
        """
        Get BurstUUID from image metadata if present.
        Returns None if not an Apple burst photo.
        """
        from modules import utils
        
        # Try from database burst_uuid column first (cached)
        if row.get('burst_uuid'):
            return row['burst_uuid']
        
        # Try from metadata JSON
        if row.get('metadata'):
            burst_uuid = utils.read_burst_uuid(row['file_path'], row['metadata'])
            if burst_uuid:
                return burst_uuid
        
        # Try from file directly (slower)
        burst_uuid = utils.read_burst_uuid(row['file_path'])
        return burst_uuid

    def cluster_images(
        self,
        distance_threshold=None,
        time_gap_seconds=None,
        force_rescan=None,
        target_folder=None,
        job_id=None,
        target_image_ids=None,
        progress_log=None,
        stop_event=None,
    ):
        """
        Main function to load images from DB, cluster them, and update DB.
        Enforces: 1. Folder Isolation 2. Time Gap Splitting 3. Persistence
        """
        import datetime
        import json
        from itertools import groupby
        from modules import config
        
        # Mark as running at start
        self.is_running = True
        self.status_message = "Starting..."
        self.current = 0
        self.total = 0
        
        try:
            from modules.pipeline_diagnostics import phase_timer
            with phase_timer("ClusteringEngine.batch", job_id):
                yield from self._cluster_images_impl(
                    distance_threshold,
                    time_gap_seconds,
                    force_rescan,
                    target_folder,
                    job_id,
                    target_image_ids=target_image_ids,
                    progress_log=progress_log,
                    stop_event=stop_event,
                )
        finally:
            # Always mark as not running when done
            self.is_running = False
            self.status_message = "Idle"
            
    def _cluster_images_impl(
        self,
        distance_threshold,
        time_gap_seconds,
        force_rescan,
        target_folder,
        job_id=None,
        target_image_ids=None,
        progress_log=None,
        stop_event=None,
    ):
        """Internal implementation of cluster_images."""
        import datetime
        import json
        from itertools import groupby
        from modules import config
        
        def update_status(msg, cur, tot):
            """Helper to update status and yield progress."""
            self.status_message = msg
            self.current = cur
            self.total = tot
            return msg, cur, tot

        if progress_log:
            progress_log("Preparing clustering scope (database query)...")
        
        # Load defaults from config if not provided
        #
        # default_threshold  — AgglomerativeClustering cosine-distance cutoff (visual similarity).
        #                      This is NOT a shot count; it only applies *within* each time batch.
        # default_time_gap   — Seconds (capture-time based). Shots are sorted by time; whenever
        #                      (current_time - previous_time) exceeds this value, a NEW batch starts.
        #                      Only images in the same batch are compared for visual clustering.
        #                      Example: 3 → burst-style grouping (neighbors must be within ~3s).
        if distance_threshold is None:
            clustering_config = config.get_config_section('clustering')
            distance_threshold = clustering_config.get('default_threshold', 0.15)
        if time_gap_seconds is None:
            clustering_config = config.get_config_section('clustering')
            time_gap_seconds = clustering_config.get('default_time_gap', 120)
        if force_rescan is None:
            clustering_config = config.get_config_section('clustering')
            force_rescan = clustering_config.get('force_rescan_default', False)
        
        startup_msg = (
            f"Clustering started. Parameters: distance_threshold={distance_threshold}, "
            f"time_gap={time_gap_seconds}s, force_rescan={force_rescan}"
        )
        logger.info(f"[Clustering] {startup_msg}")
        if progress_log:
            progress_log(startup_msg)
        
        logging.info("Fetching images for clustering...")
        
        # Get processed folders early (needed for both paths)
        processed_folders = db.get_clustered_folders()
        
        if target_image_ids is not None:
            # --- Selector mode (target ID list) ---
            if not target_image_ids:
                yield update_status("No images matched target IDs.", 0, 0)
                return
            rows = db.get_all_images(limit=-1)
            selected_ids = {int(i) for i in target_image_ids}
            images_rows = [row for row in rows if row.get('id') in selected_ids]
            images_rows = filter_image_rows_for_nef_policy(images_rows)

            if not images_rows:
                yield update_status("No images matched target IDs.", 0, 0)
                return
                
            by_folder = {}
            for row in images_rows:
                p = row['file_path']
                if not p:
                    continue
                folder = os.path.normpath(os.path.dirname(p))
                by_folder.setdefault(folder, []).append(row)
            folders_to_process = list(by_folder.keys())
            yield update_status(f"Selector mode: {len(images_rows)} images across {len(folders_to_process)} folders.", 0, len(images_rows))

        elif target_folder:
            # --- Single folder mode ---
            images_rows = filter_image_rows_for_nef_policy(db.get_images_by_folder(target_folder))
            if not images_rows:
                yield update_status(f"No images found in folder: {target_folder}", 0, 0)
                return
            
            yield update_status(f"Found {len(images_rows)} images. Checking progress...", 0, len(images_rows))
            
            # Group by folder (usually just one for single-folder mode)
            by_folder = {}
            for row in images_rows:
                p = row['file_path']
                if not p: continue
                folder = os.path.normpath(os.path.dirname(p))
                if folder not in by_folder:
                    by_folder[folder] = []
                by_folder[folder].append(row)
            
            if force_rescan:
                success, msg = db.clear_stacks_in_folder(target_folder)
                if success:
                    processed_folders.discard(os.path.normpath(target_folder))
                    yield update_status(f"Force Rescan: {msg}", 0, len(images_rows))
                else:
                    yield update_status(f"Warning: {msg}", 0, len(images_rows))
            
            target_norm = os.path.normpath(target_folder)
            if target_norm in by_folder:
                folders_to_process = [target_norm]
            else:
                folders_to_process = list(by_folder.keys())
        else:
            # --- All unprocessed folders mode ---
            # Get all folders from DB and subtract already-clustered ones
            all_folders = db.get_all_folders()
            
            if force_rescan:
                db.clear_cluster_progress()
                processed_folders = set()
                yield update_status("Force Rescan: Cleared previous progress.", 0, 0)
                folders_to_process = list(all_folders)
            else:
                folders_to_process = [f for f in all_folders if f not in processed_folders]
            
            if not folders_to_process:
                yield update_status("All folders already processed.", 0, 0)
                return
            
            yield update_status(f"Found {len(folders_to_process)} unprocessed folders. Loading images...", 0, len(folders_to_process))
            
            # Load images per-folder into by_folder dict
            by_folder = {}
            images_rows = []  # Aggregate for total count tracking
            for i, folder_path in enumerate(folders_to_process):
                folder_images = filter_image_rows_for_nef_policy(db.get_images_by_folder(folder_path))
                if folder_images:
                    by_folder[folder_path] = folder_images
                    images_rows.extend(folder_images)
            
            # Re-filter folders_to_process to only those with actual images
            folders_to_process = list(by_folder.keys())
            
            if not folders_to_process:
                yield update_status("No images found in unprocessed folders.", 0, 0)
                return
            
            yield update_status(f"Found {len(images_rows)} images across {len(folders_to_process)} folders.", 0, len(images_rows))
        
        if not folders_to_process:
            yield update_status("All folders already processed or no images in target folder.", 0, 0)
            return
        
        initial_stack_count = db.get_stack_count()
        total_clusters = initial_stack_count
        processed_count = 0

        yield update_status(f"Processing {len(folders_to_process)} folders...", processed_count, len(images_rows))
        
        for folder in folders_to_process:
            if stop_event and stop_event.is_set():
                break
            rows = by_folder[folder]
            runnable_rows = []
            for r in rows:
                decision = explain_phase_run_decision(
                    r['id'],
                    PhaseCode.CULLING,
                    current_executor_version=CLUSTER_VERSION,
                    force_run=force_rescan,
                )
                if decision['should_run']:
                    # Pre-requisite validation: ensure image has a hash and a score
                    # (Score is used for representative selection; Hash for embedding cache)
                    if not r.get("image_hash") and not force_rescan:
                        logger.warning("[Clustering] Skipping image_id=%s: missing image_hash. Run Indexing phase first.", r["id"])
                        continue
                    if r.get("score_general") is None:
                        logger.warning("[Clustering] image_id=%s: missing score_general. Run Scoring phase first for better representative selection.", r["id"])
                        # We don't abort here because clustering can still happen (spatial/temporal),
                        # but representative selection will fall back to default order.
                    
                    runnable_rows.append(r)
                else:
                    logger.debug(
                        "[culling] skip image_id=%s reason=%s",
                        r["id"],
                        decision.get("reason"),
                    )

            if not runnable_rows:
                logger.warning(
                    "[Clustering] Skipping folder %s: runnable_rows=0 (all images current)",
                    folder,
                )
                logger.debug(
                    "[culling] folder skip all current folder=%r rows=%s",
                    folder,
                    len(rows),
                )
                # Recover stuck RUNNING rows (e.g. crashed job) so folder previews / phase summaries stay accurate.
                for r in rows:
                    st = (db.get_image_phase_statuses(r["id"]) or {}).get("culling") or {}
                    if (st.get("status") or "").strip() != PhaseStatus.RUNNING:
                        continue
                    decision = explain_phase_run_decision(
                        r["id"],
                        PhaseCode.CULLING,
                        current_executor_version=CLUSTER_VERSION,
                        force_run=force_rescan,
                    )
                    if decision.get("should_run") or decision.get("reason") != "already_running":
                        continue
                    try:
                        db.set_image_phase_status(
                            r["id"],
                            PhaseCode.CULLING,
                            PhaseStatus.DONE,
                            app_version=APP_VERSION,
                            executor_version=CLUSTER_VERSION,
                            job_id=job_id,
                        )
                    except Exception:
                        pass
                yield update_status(f"Skipping folder: {folder} (all images current)", processed_count, len(images_rows))
                logger.debug(f"[Clustering] Skipping folder {folder}: all images are already up to date according to version {CLUSTER_VERSION}.")
                continue

            logger.info(
                "[Clustering] Processing folder %s: %s runnable images",
                folder,
                len(runnable_rows),
            )
            logger.debug(
                "[culling] process folder=%r runnable=%s of %s rows job_id=%s",
                folder,
                len(runnable_rows),
                len(rows),
                job_id,
            )
            for r in runnable_rows:
                # If force_rescan and image is in RUNNING state, reset to DONE first to allow rerun
                if force_rescan:
                    statuses = db.get_image_phase_statuses(r['id']) or {}
                    culling_status = statuses.get("culling")
                    if culling_status and culling_status.get("status") == "running":
                        logger.debug(
                            "[culling] force_rescan reset image_id=%s from running to done",
                            r["id"],
                        )
                        db.set_image_phase_status(
                            r['id'],
                            PhaseCode.CULLING,
                            PhaseStatus.DONE,
                            app_version=APP_VERSION,
                            executor_version=CLUSTER_VERSION,
                        )

                db.set_image_phase_status(
                    r['id'],
                    PhaseCode.CULLING,
                    PhaseStatus.RUNNING,
                    app_version=APP_VERSION,
                    executor_version=CLUSTER_VERSION,
                    job_id=job_id,
                )

            rows = runnable_rows
            yield update_status(f"Processing folder: {folder} ({len(rows)} images)...", processed_count, len(images_rows))
            
            folder_stacks = 0
            
            # ===== PRE-GROUP BY BURSTUUID =====
            # Images with same BurstUUID go directly into stacks, skip visual clustering
            from modules import xmp
            
            burst_groups = {}  # BurstUUID -> list of rows
            non_burst_rows = []  # Rows without BurstUUID (need visual clustering)
            
            for r in rows:
                burst_uuid = self._get_burst_uuid(r)
                if burst_uuid:
                    if burst_uuid not in burst_groups:
                        burst_groups[burst_uuid] = []
                    burst_groups[burst_uuid].append(r)
                else:
                    non_burst_rows.append(r)
            
            # Create stacks from BurstUUID groups
            burst_stacks_data = []
            for burst_uuid, group_rows in burst_groups.items():
                if len(group_rows) < 2:
                    # Single image with BurstUUID - add to visual clustering
                    non_burst_rows.extend(group_rows)
                    continue
                
                # Find best image (no embeddings available for burst path; falls back to score)
                img_ids = [r['id'] for r in group_rows]
                id_to_score_burst = {r['id']: r.get('score_general') or 0 for r in group_rows}
                best_id = self._select_best_image(img_ids, id_to_score_burst)
                
                s_name = f"Burst {os.path.basename(folder)} ({len(group_rows)} shots)"
                burst_stacks_data.append({
                    'name': s_name,
                    'best_image_id': best_id,
                    'image_ids': img_ids,
                    'burst_uuid': burst_uuid
                })
                logger.debug(f"[Clustering] Grouped {len(img_ids)} images into burst stack: {s_name} (UUID: {burst_uuid})")
                folder_stacks += 1
                total_clusters += 1
            
            # Create burst stacks
            if burst_stacks_data:
                msg = f"Created {len(burst_stacks_data)} burst stacks from BurstUUID in {folder}"
                logging.info(f"[Clustering] {msg}")
                if progress_log:
                    progress_log(msg)
                db.create_stacks_batch(burst_stacks_data)
                # Update burst_uuid in database for these images
                for stack_data in burst_stacks_data:
                    for img_id in stack_data['image_ids']:
                        db.update_image_field(img_id, 'burst_uuid', stack_data['burst_uuid'])
                yield update_status(f"Created {len(burst_stacks_data)} burst stacks from BurstUUID", processed_count, len(images_rows))
            
            # ===== CONTINUE WITH VISUAL CLUSTERING FOR REMAINING IMAGES =====
            logging.info(f"[Clustering] non_burst_rows={len(non_burst_rows)}, time_batches will be built")
            if not non_burst_rows:
                # All images were burst photos - skip to next folder
                db.mark_folder_clustered(folder)
                processed_count += len(rows)
                yield update_status(f"Finished {folder}. Created {folder_stacks} stacks.", processed_count, len(images_rows))
                continue
            
            # Sort by Time
            rows_with_time = []
            for r in non_burst_rows:
                t = self._get_image_time(r)
                rows_with_time.append((r, t))
            
            rows_with_time.sort(key=lambda x: x[1])
            
            # Split by Time Gap
            time_batches = []
            if not rows_with_time: continue
            
            current_batch = [rows_with_time[0]]
            
            for i in range(1, len(rows_with_time)):
                prev_row, prev_time = rows_with_time[i-1]
                curr_row, curr_time = rows_with_time[i]
                
                if (curr_time - prev_time) > time_gap_seconds:
                    time_batches.append(current_batch)
                    current_batch = []
                
                current_batch.append((curr_row, curr_time))
            
            if current_batch:
                time_batches.append(current_batch)
            
            non_burst_msg = (
                f"Temporal analysis in {folder}: split {len(non_burst_rows)} images into {len(time_batches)} time batch(es) "
                f"(new batch when consecutive capture times differ by > {time_gap_seconds}s). "
                f"Batches with >=2 images: {sum(1 for b in time_batches if len(b) >= 2)}"
            )
            logger.info(f"[Clustering] {non_burst_msg}")
            if progress_log:
                progress_log(non_burst_msg)
            for b_idx, batch in enumerate(time_batches):
                if stop_event and stop_event.is_set():
                    break
                # Calculate overall progress for this folder
                folder_progress = processed_count + (len(rows) * (b_idx / len(time_batches)))
                yield update_status(f"Processing folder: {folder} - Batch {b_idx+1}/{len(time_batches)}", folder_progress, len(images_rows))

                # Extract features for this batch (including single-image batches — embeddings
                # are always persisted; clustering is skipped below when len(features) < 2)
                batch_paths = []
                batch_original_paths = []
                batch_ids = []
                for r, t in batch:
                    from modules.thumbnails import _resolve_thumbnail_filesystem_path
                    thumb = _resolve_thumbnail_filesystem_path(
                        r.get('thumbnail_path'), r.get('thumbnail_path_win'),
                    )
                    p = thumb if thumb else r['file_path']

                    if p and os.path.exists(p):
                        batch_paths.append(p)
                        batch_original_paths.append(r['file_path'])
                        batch_ids.append(r['id'])

                if not batch_paths:
                    logging.warning(
                        "[Clustering] Batch %d/%d skipped: no valid image paths resolved (%d images in batch)",
                        b_idx + 1,
                        len(time_batches),
                        len(batch),
                    )
                    continue

                features, valid_indices = self.extract_features(
                    batch_paths,
                    original_paths=batch_original_paths,
                    progress_log=progress_log,
                    stop_event=stop_event,
                )

                # Persist embeddings to DB for similarity search
                embedding_pairs = []
                for i, feat in enumerate(features):
                    orig_idx = valid_indices[i]
                    img_id = batch_ids[orig_idx]
                    embedding_pairs.append((img_id, feat.astype(np.float32).tobytes()))
                if embedding_pairs:
                    db.update_image_embeddings_batch(embedding_pairs, model_version=CLUSTER_VERSION)

                if len(features) == 0 and len(batch_paths) > 0:
                    logging.warning(
                        "[Clustering] Batch %d/%d: 0 features from %d paths — "
                        "thumbnail or image loading failed for all images",
                        b_idx + 1, len(time_batches), len(batch_paths),
                    )

                if len(features) < 2:
                    logging.info(
                        "[Clustering] Batch %d/%d: single-image batch, skipping cluster step (embeddings persisted)",
                        b_idx + 1,
                        len(time_batches),
                    )
                    continue

                # Cluster
                logger.debug(f"[Clustering] Batch {b_idx+1}: Running AgglomerativeClustering on {len(features)} images (threshold={distance_threshold})...")
                clustering = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=distance_threshold,
                    metric='cosine',
                    linkage='average'
                )
                labels = clustering.fit_predict(features)
                logger.debug(f"[Clustering] Batch {b_idx+1}: Clustering algorithm finished.")
                
                # Build id -> feature map for centroid/balanced strategies
                id_to_feature = {}
                for i, feat in enumerate(features):
                    orig_idx = valid_indices[i]
                    img_id = batch_ids[orig_idx]
                    id_to_feature[img_id] = feat

                local_clusters = {}
                for i, lbl in enumerate(labels):
                    orig_idx = valid_indices[i]
                    img_id = batch_ids[orig_idx]

                    if lbl not in local_clusters:
                        local_clusters[lbl] = []
                    local_clusters[lbl].append(img_id)

                # Collect stacks for this batch
                batch_stacks_data = [] # List of dicts

                # Build score lookup once per batch
                id_to_score_batch = {}
                for r, t in batch:
                    id_to_score_batch[r['id']] = r.get('score_general') or 0

                id_to_exif_batch = db.get_exif_fields_for_quality_tiebreak([r["id"] for r, t in batch])

                for lbl, img_ids in local_clusters.items():
                    if len(img_ids) < 2:
                        continue

                    best_id = self._select_best_image(
                        img_ids, id_to_score_batch, id_to_feature, id_to_exif_batch
                    )
                    logger.debug(f"[Clustering] Batch {b_idx+1}: Found similarity group with {len(img_ids)} images. Best representative selected: {best_id}")
                            
                    # Name based on Time? or Folder?
                    # Stack (Time)
                    timestamp = datetime.datetime.fromtimestamp(batch[0][1]).strftime("%H:%M")
                    s_name = f"Stack {os.path.basename(folder)} {timestamp} #{lbl}"
                    
                    batch_stacks_data.append({
                        'name': s_name,
                        'best_image_id': best_id,
                        'image_ids': img_ids
                    })
                    
                    folder_stacks += 1
                    total_clusters += 1
                
                # Execute batch for this time-group
                if batch_stacks_data:
                    batch_msg = f"Creating {len(batch_stacks_data)} visual stacks for batch {b_idx+1} in {folder}"
                    logging.info(f"[Clustering] {batch_msg}")
                    if progress_log:
                        progress_log(batch_msg)
                    db.create_stacks_batch(batch_stacks_data)
                    
                    # Generate and write BurstUUID for newly created stacks
                    for stack_data in batch_stacks_data:
                        # Generate a new UUID for this visual stack
                        new_burst_uuid = str(uuid.uuid4())
                        
                        # Update database and write to XMP for each image
                        for img_id in stack_data['image_ids']:
                            db.update_image_field(img_id, 'burst_uuid', new_burst_uuid)
                            
                            # Write to XMP sidecar
                            # Find the file path for this image from the batch
                            for r, t in batch:
                                if r['id'] == img_id:
                                    xmp.write_burst_uuid(r['file_path'], new_burst_uuid)
                                    break
                    
                    # Broadcast event
                    try:
                        from modules.events import event_manager
                        event_manager.broadcast_threadsafe("stack_created", {
                            "folder": folder, 
                            "count": len(batch_stacks_data),
                            "total_stacks": folder_stacks
                        })
                    except Exception as e:
                        logging.debug(f"Failed to broadcast batch event: {e}")

            # Mark as processed
            db.mark_folder_clustered(folder)
            processed_count += len(rows)

            # Phase D (Culling) — mark all images in this folder as done
            for r in rows:
                try:
                    db.set_image_phase_status(r['id'], PhaseCode.CULLING, PhaseStatus.DONE,
                                              app_version=APP_VERSION, executor_version=CLUSTER_VERSION,
                                              job_id=job_id)
                except Exception:
                    pass

            finish_folder_msg = f"Finished {folder}: created {folder_stacks} stacks total"
            logging.info(f"[Clustering] {finish_folder_msg}")
            yield update_status(f"Finished {folder}. Created {folder_stacks} stacks.", processed_count, len(images_rows))
            
            # Broadcast final event for folder
            try:
                from modules.events import event_manager
                # Hack: Just use a global trigger that the webui poller checks?
                # Or better: event_manager should have a thread_safe_broadcast method.
                event_manager.broadcast_threadsafe("stack_created", {"folder": folder, "count": folder_stacks})
            except Exception as e:
                logging.debug(f"Failed to broadcast event: {e}")

        new_stacks = total_clusters - initial_stack_count
        if new_stacks == 0 and processed_count > 0:
            msg = (
                f"Done. Processed {processed_count} images — 0 new stacks created. "
                f"Images may be too dissimilar or spread across time gaps > {time_gap_seconds}s. "
                f"Total stacks in DB: {db.get_stack_count()}"
            )
            logging.warning("[Clustering] %s", msg)
        else:
            msg = (
                f"Done! Processed {processed_count} images, created {new_stacks} new stacks. "
                f"Total: {db.get_stack_count()}"
            )
        yield update_status(msg, len(images_rows), len(images_rows))
        logger.info(f"[Clustering] {msg}")
        if progress_log:
            progress_log(msg)


class ClusteringRunner:
    """
    Runs clustering in a local thread, providing status updates.
    Matches the runner contract: start_batch, stop, get_status.

    clustering_engine: optional IClusteringEngine (default ClusteringEngine).
    """
    def __init__(self, clustering_engine=None):
        self.engine = clustering_engine if clustering_engine is not None else ClusteringEngine()
        self.stop_event = threading.Event()
        self._thread = None
        
        # State
        self.is_running = False
        self.status_message = "Idle"
        self.current_count = 0
        self.total_count = 0
        self.log_history = []
        
    def get_status(self):
        """Returns (is_running, log_text, status_message, current, total)"""
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count
        
    def start_batch(self, input_path, threshold=None, time_gap=None, force_rescan=False, job_id=None, resolved_image_ids=None):
        """Starts clustering in background."""
        if self.is_running:
            return "Error: Already running."
            
        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0
        self.stop_event.clear()
        
        def target():
            from modules.pipeline import safe_runner_thread
            def target_wrapper():
                try:
                    self._run_internal(input_path, threshold, time_gap, force_rescan, job_id, resolved_image_ids=resolved_image_ids)
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
        
    def _run_internal(self, input_path, threshold, time_gap, force_rescan, job_id=None, resolved_image_ids=None):
        def log(msg, level="INFO"):
            runner_emit(self.log_history, job_id, msg, level, phase="culling")
            logger.info(f"[Job {job_id}] {msg}")
            
        log(f"Starting Clustering on {input_path or 'all unprocessed folders'}...")
        
        # Notify job started
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "clustering", 
                "input_path": input_path
            })
            
        try:
            # We use the generator from engine
            for msg_tuple in self.engine.cluster_images(
                distance_threshold=threshold,
                time_gap_seconds=time_gap,
                force_rescan=force_rescan,
                target_folder=input_path,
                job_id=job_id,
                target_image_ids=resolved_image_ids,
                progress_log=log,
                stop_event=self.stop_event,
            ):
                if self.stop_event.is_set():
                    log("Stopped by user.", "WARNING")
                    break
                    
                # unpack tuple (msg, cur, tot) or just msg string if engine changed?
                # engine.cluster_images yields (msg, cur, tot) via update_status helper
                if isinstance(msg_tuple, tuple):
                    msg, cur, tot = msg_tuple
                    self.status_message = msg
                    self.current_count = cur
                    self.total_count = tot
                    log(msg)
                    
                    if job_id:
                         event_manager.broadcast_threadsafe("job_progress", {
                             "job_id": job_id,
                             "job_type": "clustering",
                             "phase_code": "culling",
                             "current": cur,
                             "total": tot,
                             "message": msg
                         })
                else:
                    self.status_message = str(msg_tuple)
                    log(str(msg_tuple))
            
            if job_id:
                db.update_job_status(job_id, "completed", log="\n".join(self.log_history))
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id, 
                    "status": "completed"
                })
                
        except Exception as e:
            log(f"Error: {e}", "ERROR")
            self.status_message = f"Error: {e}"
            if job_id:
                db.update_job_status(job_id, "failed", log="\n".join(self.log_history))
                event_manager.broadcast_threadsafe("job_completed", {
                    "job_id": job_id, 
                    "status": "failed", 
                    "error": str(e)
                })
            
    def stop(self):
        self.stop_event.set()
        # The engine checks is_running but doesn't have a stop_event passed to it 
        # structure in cluster_images. We might need to check how to interrupt it.
        # The engine loop yields frequently, so we check stop_event in _run_internal loop.
        # But _run_internal iterates over the generator. So we break the loop.
        # That handles it.
