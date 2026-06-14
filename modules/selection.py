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
from modules.culling_embeddings import collect_stacked_image_ids, ensure_embeddings_for_space
from modules.embedding_extractors import is_supported
from modules.embedding_spaces import OPENCLIP_L14_IMAGE_SPACE_CODE
from modules.two_level_culling import (
    LEVEL2_DEFAULT_DISTANCE_THRESHOLD,
    TWO_LEVEL_POLICY_VERSION,
    TwoLevelConfig,
    TwoLevelLevelConfig,
    process_stack_two_level,
)

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
    # Two-level culling (persisted sub-stacks, best-M with N cap). None = read config.
    two_level_enabled: Optional[bool] = None


def _load_two_level_config(cfg: SelectionConfig) -> TwoLevelConfig:
    """Resolve two-level culling settings from SelectionConfig + config.json."""
    tl = get_config_value("culling.two_level", default={}) or {}
    div = tl.get("diversity") or {}

    def _level(key: str, default_space: str, default_thr: float) -> TwoLevelLevelConfig:
        block = tl.get(key) or {}
        return TwoLevelLevelConfig(
            embedding_space=str(block.get("embedding_space") or default_space),
            distance_threshold=float(block.get("distance_threshold", default_thr)),
        )

    return TwoLevelConfig(
        picks_per_substack=int(tl.get("picks_per_substack", 3)),
        max_picks_per_stack=int(tl.get("max_picks_per_stack", 20)),
        reject_non_picks=bool(tl.get("reject_non_picks", True)),
        level1=_level("level1", "mobilenet_v2_imagenet_gap", 0.15),
        level2=_level("level2", OPENCLIP_L14_IMAGE_SPACE_CODE, LEVEL2_DEFAULT_DISTANCE_THRESHOLD),
        diversity_enabled=bool(div.get("enabled", True)),
        diversity_lambda=float(div.get("lambda", 0.70)),
        score_field=cfg.score_field,
    )


def _two_level_enabled(cfg: SelectionConfig) -> bool:
    if cfg.two_level_enabled is not None:
        return bool(cfg.two_level_enabled)
    return bool(get_config_value("culling.two_level.enabled", default=False))


def blended_rank_value(img: dict, score_field: str, clip_weight: float) -> float:
    """Within-stack ranking value: base quality blended with clip_quality_v0.

    ``(1 - w) * score_field + w * clip_quality_v0`` when a clip value is present and
    ``w > 0``; otherwise the plain ``score_field`` value. Pure + side-effect-free so
    the ranking math is unit-testable.
    """
    s = img.get(score_field) or 0
    base = float(s) if s else 0.0
    if clip_weight > 0.0:
        cq = img.get("clip_quality_v0")
        if cq is not None:
            base = (1.0 - clip_weight) * base + clip_weight * float(cq)
    return base


def apply_clip_reject_guard(
    folder_decisions: list[tuple[int, str, str]],
    clip_map: dict[int, float],
    stack_of: dict[int, object],
    threshold: float,
) -> list[tuple[int, str, str]]:
    """Downgrade frames with ``clip_quality_v0 < threshold`` to ``reject``.

    Conservative: never upgrades to pick, and never strips a stack's last surviving
    pick. Pure function over the decision list so the guard is unit-testable.
    """
    picks_per_stack: dict = defaultdict(int)
    for img_id, decision, _ in folder_decisions:
        if decision == "pick":
            picks_per_stack[stack_of.get(img_id)] += 1
    guarded: list[tuple[int, str, str]] = []
    for img_id, decision, path in folder_decisions:
        cq = clip_map.get(img_id)
        if cq is not None and cq < threshold and decision != "reject":
            st = stack_of.get(img_id)
            if decision == "pick" and picks_per_stack.get(st, 0) <= 1:
                pass  # keep the stack's only surviving pick
            else:
                if decision == "pick":
                    picks_per_stack[st] -= 1
                decision = "reject"
        guarded.append((img_id, decision, path))
    return guarded


def _clip_quality_cfg() -> dict:
    """Resolve the auxiliary CLIP prompt-quality culling settings from config.json.

    Default-off: when ``enabled`` is false the culling path is byte-identical to the
    pre-feature behaviour. ``weight`` blends ``clip_quality_v0`` into the within-stack
    ranking; ``reject_below`` (optional) downgrades obviously-bad frames to reject.
    See docs/technical/CULLING_ANALYTICS.md and reports/clip-culling/prompt-quality/.
    """
    cfg = get_config_value("culling.clip_quality", default={}) or {}
    weight = float(cfg.get("weight", 0.15))
    weight = min(1.0, max(0.0, weight))
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "weight": weight,
        "reject_below": cfg.get("reject_below", None),
    }


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
                    
                # Auxiliary CLIP prompt-quality signal (default-off). When enabled, the
                # clip_quality_v0 score (0–1) is generated just-in-time for stacked
                # images (clip_vit_b32_image embeddings are otherwise produced later in
                # the keywords phase) and blended into the within-stack ranking below.
                clip_cfg = _clip_quality_cfg()
                clip_map: dict[int, float] = {}
                if clip_cfg["enabled"]:
                    try:
                        from modules import clip_quality
                        stacked_ids = collect_stacked_image_ids(by_stack)
                        if stacked_ids:
                            self._progress(progress_cb, pct_base,
                                           "Computing CLIP prompt-quality...")
                            clip_map = clip_quality.compute_clip_quality(stacked_ids)
                            for im in images:
                                cq = clip_map.get(im["id"])
                                if cq is not None:
                                    im["clip_quality_v0"] = cq
                    except Exception as exc:  # noqa: BLE001 — degrade to score_general
                        logger.warning("[culling] clip_quality compute failed: %s", exc)
                        clip_map = {}

                score_col = cfg.score_field
                clip_w = clip_cfg["weight"] if clip_cfg["enabled"] else 0.0
                def sort_key(img):
                    c = img.get("created_at") or ""
                    i = img.get("id") or 0
                    return (
                        -blended_rank_value(img, score_col, clip_w),
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
                use_two_level = _two_level_enabled(cfg)
                tl_cfg = _load_two_level_config(cfg) if use_two_level else None
                policy_version = TWO_LEVEL_POLICY_VERSION if use_two_level else POLICY_VERSION

                if use_two_level:
                    db.clear_sub_stacks_for_folder(folder)
                    if tl_cfg is not None and is_supported(tl_cfg.level2.embedding_space):
                        stacked_ids = collect_stacked_image_ids(by_stack)
                        if stacked_ids:
                            ensure_embeddings_for_space(
                                tl_cfg.level2.embedding_space,
                                stacked_ids,
                                progress_cb=lambda msg: self._progress(
                                    progress_cb, pct_base, msg
                                ),
                            )

                self._progress(progress_cb, pct_base, "Assigning pick/reject bands...")
                folder_decisions: list[tuple[int, str, str]] = []
                folder_subcluster_count = 0
                for stack_id, group in by_stack.items():
                    if use_two_level and stack_id is not None and len(group) >= 2 and tl_cfg is not None:
                        ids_for_emb = [img["id"] for img in group]
                        emb_level2 = db.get_image_embeddings_batch_for_space(
                            tl_cfg.level2.embedding_space, ids_for_emb
                        )
                        persist_rows, stack_decisions, leaf_count = process_stack_two_level(
                            stack_id,
                            group,
                            emb_level2,
                            tl_cfg,
                            sort_key,
                        )
                        folder_subcluster_count += leaf_count
                        if persist_rows:
                            db.create_sub_stacks_batch(persist_rows)
                        folder_decisions.extend(stack_decisions)
                        continue

                    # Legacy path: in-memory sub-clusters + 33/33 bands (or unstacked bucket)
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

                if sub_clustering_enabled or use_two_level:
                    logger.debug(
                        "[culling] sub-clustering folder=%s stacks=%s sub_clusters=%s two_level=%s threshold=%s",
                        folder,
                        len(by_stack),
                        folder_subcluster_count,
                        use_two_level,
                        sub_thr_val,
                    )

                # 4b. Optional obvious-reject guard: downgrade frames whose CLIP
                # prompt-quality is below a configured floor to 'reject'. Conservative —
                # never upgrades to pick, and never strips a stack's last surviving pick.
                if clip_cfg["enabled"] and clip_cfg["reject_below"] is not None and clip_map:
                    try:
                        thr = float(clip_cfg["reject_below"])
                    except (TypeError, ValueError):
                        thr = None
                    if thr is not None:
                        stack_of = {img["id"]: img.get("stack_id") for img in images}
                        folder_decisions = apply_clip_reject_guard(
                            folder_decisions, clip_map, stack_of, thr
                        )

                # 5. Persist DB
                db.batch_update_cull_decisions(folder_decisions, policy_version=policy_version)
                
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
