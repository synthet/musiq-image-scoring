"""
Selection Service Module

Unified orchestrator for stack creation + pick/reject assignment.
Replaces separate Stacks and Culling workflows with a single run/stop/status flow.
"""

import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Optional

from modules import db, clustering, utils
from modules.selection_policy import classify_sorted_ids, POLICY_VERSION
from modules.quality_ranking import quality_tiebreak_sort_key_best_first
from modules.selection_metadata import write_selection_metadata
from modules.indexing_policy import filter_image_rows_for_nef_policy
from modules.sub_clustering import compute_sub_clusters
from modules.config import get_config_value

logger = logging.getLogger(__name__)

ProgressCb = Callable[[float, str, Optional[int], Optional[int]], None]

# Threshold and time_gap are now read from config.json at runtime
# via cluster_images() defaults (clustering.default_threshold / clustering.default_time_gap).


@dataclass
class SelectionConfig:
    score_field: str = "score_general"
    pick_fraction: float = 0.33
    reject_fraction: float = 0.33
    force_rescan: bool = False
    write_stack_ids: bool = True
    write_pick_reject: bool = True
    verify_sidecar_write: bool = False
    # Diversity selection settings
    diversity_enabled: bool = False
    diversity_lambda: float = 0.70
    diversity_min_similarity_penalty: float = 0.85
    diversity_fallback_on_missing_embedding: str = "score_only"
    # Two-level (sub-)clustering: tighter cosine threshold applied within each
    # stack so the pick/reject policy is run per visually-distinct sub-group
    # rather than the whole stack. Set to None to disable.
    sub_cluster_distance_threshold: Optional[float] = None


@dataclass
class SelectionSummary:
    total_images: int
    total_stacks: int
    picked: int
    rejected: int
    neutral: int
    sidecar_written: int
    sidecar_errors: int
    status: str


class SelectionService:
    """
    Orchestrates the full Selection pipeline: cluster -> assign pick/reject -> persist.
    """

    def __init__(self):
        self._stop_requested = threading.Event()
        self._cluster_engine = clustering.ClusteringEngine()

    def _progress(
        self,
        progress_cb: Optional[ProgressCb],
        pct: float,
        msg: str,
        cur: Optional[int] = None,
        tot: Optional[int] = None,
    ):
        if progress_cb:
            try:
                progress_cb(pct, msg, cur, tot)
            except Exception:
                pass

    def _check_stop(self) -> bool:
        return self._stop_requested.is_set()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(
        self,
        input_path: str,
        cfg: Optional[SelectionConfig] = None,
        progress_cb: Optional[ProgressCb] = None,
    ) -> SelectionSummary:
        cfg = cfg or SelectionConfig()
        self._stop_requested.clear()

        # Normalize path
        input_path = (input_path or "").strip()
        if not input_path:
            return SelectionSummary(
                0, 0, 0, 0, 0, 0, 0,
                status="error",
            )

        # Convert to local path (WSL support)
        local_path = utils.convert_path_to_local(input_path)
        if not os.path.exists(local_path):
            return SelectionSummary(
                0, 0, 0, 0, 0, 0, 0,
                status=f"error: Path not found: {input_path}",
            )

        try:
            # Stage 1: Resolve folders (same tree as get_folder_phase_summary / scope preview)
            self._progress(progress_cb, 0.01, "Scanning folders...")

            target_folders = db.list_folder_paths_under_scope(local_path)

            if not target_folders:
                return SelectionSummary(
                    0, 0, 0, 0, 0, 0, 0,
                    status="No folders found in database matching path.",
                )
                
            n_folders = len(target_folders)
            self._progress(progress_cb, 0.02, f"Found {n_folders} folders. Starting processing...")
            logger.debug(
                "[culling] selection scope folders=%s root=%r",
                n_folders,
                local_path,
            )

            # Aggregate stats
            total_images_processed = 0
            total_stacks_created = 0
            total_picked = 0
            total_rejected = 0
            total_neutral = 0
            total_written = 0
            total_errors = 0
            
            for i, folder in enumerate(target_folders):
                if self._check_stop():
                    break
                    
                pct_base = 0.05 + (0.9 * (i / n_folders))
                self._progress(progress_cb, pct_base, f"Processing folder {i+1}/{n_folders}: {os.path.basename(folder)}")
                
                # --- Per-folder processing ---
                
                # 1. Get images
                images = filter_image_rows_for_nef_policy(db.get_images_by_folder(folder))
                if not images:
                    logger.debug("[culling] folder skip (no images): %r", folder)
                    continue
                    
                n_images_folder = len(images)
                logger.debug(
                    "[culling] folder begin %s images=%s force_rescan=%s",
                    folder,
                    n_images_folder,
                    cfg.force_rescan,
                )
                
                # 2. Cluster (threshold + time_gap read from config.json by cluster_images)
                for status_msg in self._cluster_engine.cluster_images(
                    distance_threshold=None,
                    time_gap_seconds=None,
                    force_rescan=cfg.force_rescan,
                    target_folder=folder,
                    stop_event=self._stop_requested,
                ):
                    if self._check_stop():
                        break
                    # Forward clustering progress to UI (msg, cur, tot) or plain str
                    if isinstance(status_msg, tuple) and len(status_msg) >= 1:
                        msg = status_msg[0]
                        cur = status_msg[1] if len(status_msg) > 1 else 0
                        tot = status_msg[2] if len(status_msg) > 2 else n_images_folder
                        pct = cur / tot if tot else 0
                        folder_pct = pct_base + (0.85 / n_folders) * pct
                        self._progress(progress_cb, folder_pct, msg, cur=cur, tot=tot)
                
                if self._check_stop():
                    break
                    
                # 3. Reload images with stack_ids
                images = filter_image_rows_for_nef_policy(db.get_images_by_folder(folder))
                if not images:
                    continue

                exif_map = db.get_exif_fields_for_quality_tiebreak([img["id"] for img in images])
                for im in images:
                    ex = exif_map.get(im["id"])
                    if ex:
                        im["iso"] = ex.get("iso")
                        im["exposure_time"] = ex.get("exposure_time")
                        im["date_time_original"] = ex.get("date_time_original")

                # 4. Group & Sort
                by_stack = defaultdict(list)
                for img in images:
                    sid = img.get("stack_id")
                    by_stack[sid].append(img)

                # by_stack includes stack_id=None for all unstacked images — that is ONE dict key, not one stack.
                real_stack_ids = [k for k in by_stack if k is not None]
                unstacked_n = len(by_stack.get(None, ()))
                logger.debug(
                    "[culling] after cluster folder=%s db_stack_groups=%s unstacked_images=%s",
                    folder,
                    len(real_stack_ids),
                    unstacked_n,
                )
                    
                score_col = cfg.score_field
                def sort_key(img):
                    s = img.get(score_col) or 0
                    c = img.get("created_at") or ""
                    i = img.get("id") or 0
                    return (
                        -float(s) if s else 0,
                        quality_tiebreak_sort_key_best_first(img),
                        str(c),
                        int(i),
                    )

                # Resolve sub-cluster threshold once per folder. A None or
                # non-positive value disables the second pass and preserves
                # legacy whole-stack behaviour.
                sub_thr = cfg.sub_cluster_distance_threshold
                if sub_thr is None:
                    sub_thr = get_config_value(
                        "culling.sub_cluster_distance_threshold", default=None
                    )
                try:
                    sub_thr_val = float(sub_thr) if sub_thr is not None else None
                except (TypeError, ValueError):
                    sub_thr_val = None
                sub_clustering_enabled = sub_thr_val is not None and sub_thr_val > 0.0

                self._progress(progress_cb, pct_base, "Assigning pick/reject bands...")
                folder_decisions: list[tuple[int, str, str]] = []
                folder_subcluster_count = 0
                for stack_id, group in by_stack.items():
                    # Group images of this stack into tight sub-clusters
                    # (visually near-identical micro-groups) so we can apply
                    # the 33/33 (or configured) policy *per sub-group*. The
                    # None bucket — unstacked images — is treated as one
                    # implicit sub-cluster to preserve legacy behaviour.
                    if sub_clustering_enabled and stack_id is not None and len(group) >= 2:
                        ids_for_emb = [img["id"] for img in group]
                        emb_map = db.get_image_embeddings_batch(ids_for_emb)
                        sub_groups = compute_sub_clusters(
                            group, emb_map, distance_threshold=sub_thr_val
                        )
                        if not sub_groups:
                            sub_groups = [list(group)]
                    else:
                        sub_groups = [list(group)]

                    folder_subcluster_count += len(sub_groups)

                    for sub_group in sub_groups:
                        sorted_sub = sorted(sub_group, key=sort_key)

                        if cfg.diversity_enabled and len(sorted_sub) > 2:
                            from modules.selection_policy import band_sizes
                            from modules.diversity import reorder_with_mmr
                            k_picks, _ = band_sizes(len(sorted_sub), cfg.pick_fraction)
                            if k_picks > 0:
                                sub_ids = [img["id"] for img in sorted_sub]
                                embeddings_dict = db.get_image_embeddings_batch(sub_ids)
                                sorted_sub = reorder_with_mmr(
                                    sorted_images=sorted_sub,
                                    k=k_picks,
                                    embeddings_dict=embeddings_dict,
                                    lambda_val=cfg.diversity_lambda,
                                    score_key=cfg.score_field,
                                )

                        sorted_ids = [img["id"] for img in sorted_sub]
                        path_by_id = {img["id"]: img.get("file_path") or "" for img in sorted_sub}
                        classifications = classify_sorted_ids(sorted_ids, frac=cfg.pick_fraction)
                        for img_id, decision in classifications.items():
                            path = path_by_id.get(img_id, "")
                            folder_decisions.append((img_id, decision, path))

                if sub_clustering_enabled:
                    logger.debug(
                        "[culling] sub-clustering folder=%s stacks=%s sub_clusters=%s threshold=%.4f",
                        folder,
                        len(by_stack),
                        folder_subcluster_count,
                        sub_thr_val,
                    )
                        
                # 5. Persist DB
                db.batch_update_cull_decisions(folder_decisions, policy_version=POLICY_VERSION)
                
                # 6. Write Sidecars
                stack_id_by_img = {img["id"]: img.get("stack_id") for img in images}
                
                for img_id, decision, file_path in folder_decisions:
                    if self._check_stop():
                        break
                    if not file_path:
                        continue
                    try:
                        sid = stack_id_by_img.get(img_id)
                        stack_ok, pr_ok = write_selection_metadata(file_path, sid, decision)
                        if stack_ok and pr_ok:
                            total_written += 1
                        else:
                            total_errors += 1
                    except Exception as e:
                        logger.warning("Sidecar write failed for %s: %s", file_path, e)
                        total_errors += 1
                        
                # Update stats — only count real stacks (stack_id IS NOT NULL), not the None bucket
                total_images_processed += n_images_folder
                total_stacks_created += len(real_stack_ids)
                total_picked += sum(1 for _, d, _ in folder_decisions if d == "pick")
                total_rejected += sum(1 for _, d, _ in folder_decisions if d == "reject")
                total_neutral += sum(1 for _, d, _ in folder_decisions if d == "neutral")
                
            # --- End Loop ---
            
            status = "completed"
            if self._check_stop():
                status = "stopped"
                
            return SelectionSummary(
                total_images=total_images_processed,
                total_stacks=total_stacks_created,
                picked=total_picked,
                rejected=total_rejected,
                neutral=total_neutral,
                sidecar_written=total_written,
                sidecar_errors=total_errors,
                status=status,
            )

        except Exception as e:
            logger.exception("Selection run failed: %s", e)
            return SelectionSummary(
                0, 0, 0, 0, 0, 0, 0,
                status=f"error: {e}",
            )
