"""Two-level culling: sequential visual→semantic sub-stacks and best-M/N-cap picks.

Pure compute helpers plus orchestration helpers used by ``SelectionService``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Callable, List, Mapping, Sequence

from modules.selection_policy import classify_best_m
from modules.sub_clustering import compute_sub_clusters

TWO_LEVEL_POLICY_VERSION = "2.0"


@dataclass(frozen=True)
class TwoLevelLevelConfig:
    embedding_space: str
    distance_threshold: float


@dataclass
class TwoLevelConfig:
    picks_per_substack: int = 3
    max_picks_per_stack: int = 20
    reject_non_picks: bool = True
    level1: TwoLevelLevelConfig = None  # type: ignore[assignment]
    level2: TwoLevelLevelConfig = None  # type: ignore[assignment]
    diversity_enabled: bool = True
    diversity_lambda: float = 0.70
    score_field: str = "score_general"

    def __post_init__(self):
        if self.level1 is None:
            self.level1 = TwoLevelLevelConfig("mobilenet_v2_imagenet_gap", 0.15)
        if self.level2 is None:
            # Single sub-stacking pass with one model. Code default is the
            # always-populated MobileNet space; config.example.json documents the
            # recommended opt-in OpenCLIP L/14 (requires backfill).
            self.level2 = TwoLevelLevelConfig("mobilenet_v2_imagenet_gap", 0.05)


@dataclass
class SubStackSlotInfo:
    """Metadata for uniform pick allocation."""

    size: int
    top_score: float = 0.0


def compute_leaf_substacks(
    images: Sequence[Mapping],
    embeddings: Mapping[int, object],
    threshold: float,
    *,
    id_key: str = "id",
) -> List[List[dict]]:
    """Single-pass sub-clustering within one root stack.

    Splits ``images`` into leaf sub-stacks via one agglomerative pass on
    ``embeddings`` at ``threshold`` (one model, one threshold). Images with
    missing/malformed embeddings fall back to a single bucket (see
    ``compute_sub_clusters``).
    """
    if not images:
        return []
    if len(images) == 1:
        return [list(images)]

    leaves = compute_sub_clusters(
        images,
        embeddings,
        float(threshold),
        id_key=id_key,
    )
    return leaves or [list(images)]


def allocate_picks_uniform(
    substacks: Sequence[SubStackSlotInfo],
    m: int,
    n: int,
) -> List[int]:
    """Return per-sub-stack pick slot counts; uniform M_eff with leftover to largest.

    ``M_eff = min(M, max(1, floor(N / c)))``. Leftover slots go to largest sub-stacks
    (tie-break: higher ``top_score``), capped at ``M`` and sub-stack size.
    """
    c = len(substacks)
    if c == 0:
        return []
    m = max(1, int(m))
    n = max(1, int(n))

    m_eff = min(m, max(1, floor(n / c)))
    slots = [min(m_eff, info.size) for info in substacks]
    leftover = n - sum(slots)

    if leftover <= 0:
        return slots

    order = sorted(
        range(c),
        key=lambda i: (-substacks[i].size, -substacks[i].top_score, i),
    )
    for idx in order:
        if leftover <= 0:
            break
        cap = min(m, substacks[idx].size) - slots[idx]
        if cap <= 0:
            continue
        add = min(cap, leftover)
        slots[idx] += add
        leftover -= add

    return slots


def build_substack_persist_rows(
    stack_id: int,
    leaf_groups: Sequence[Sequence[Mapping]],
    *,
    level1_space: str,
    level2_space: str,
    sort_key: Callable[[Mapping], tuple],
    id_key: str = "id",
) -> List[dict]:
    """Build dicts for ``db.create_sub_stacks_batch``.

    Single sub-stacking pass: ``level2_space`` is recorded in the
    ``level2_visual_space`` audit column; ``level2_semantic_space`` stays NULL.
    """
    rows: List[dict] = []
    for idx, group in enumerate(leaf_groups):
        if not group:
            continue
        sorted_group = sorted(group, key=sort_key)
        best_id = None
        image_ids: List[int] = []
        for img in sorted_group:
            try:
                iid = int(img[id_key])
            except (KeyError, TypeError, ValueError):
                continue
            image_ids.append(iid)
            if best_id is None:
                best_id = iid
        if not image_ids:
            continue
        rows.append(
            {
                "stack_id": stack_id,
                "name": f"substack_{stack_id}_{idx + 1}",
                "best_image_id": best_id,
                "level1_space": level1_space,
                "level2_visual_space": level2_space,
                "level2_semantic_space": None,
                "policy_version": TWO_LEVEL_POLICY_VERSION,
                "image_ids": image_ids,
            }
        )
    return rows


def assign_decisions_for_stack(
    leaf_groups: Sequence[Sequence[Mapping]],
    slot_counts: Sequence[int],
    *,
    sort_key: Callable[[Mapping], tuple],
    reject_non_picks: bool,
    diversity_enabled: bool,
    diversity_lambda: float,
    score_field: str,
    embeddings_for_mmr: Mapping[int, object],
    id_key: str = "id",
) -> List[tuple]:
    """Return ``(image_id, decision, file_path)`` tuples for one root stack."""
    from modules.diversity import reorder_with_mmr

    decisions: List[tuple] = []
    for group, pick_slots in zip(leaf_groups, slot_counts):
        if not group:
            continue
        sorted_sub = sorted(group, key=sort_key)
        k = int(pick_slots)

        if diversity_enabled and k > 1 and len(sorted_sub) > k:
            sub_ids = []
            for img in sorted_sub:
                try:
                    sub_ids.append(int(img[id_key]))
                except (KeyError, TypeError, ValueError):
                    pass
            if sub_ids:
                sorted_sub = reorder_with_mmr(
                    sorted_images=sorted_sub,
                    k=k,
                    embeddings_dict=embeddings_for_mmr,
                    lambda_val=diversity_lambda,
                    score_key=score_field,
                )

        sorted_ids = []
        path_by_id = {}
        for img in sorted_sub:
            try:
                iid = int(img[id_key])
            except (KeyError, TypeError, ValueError):
                continue
            sorted_ids.append(iid)
            path_by_id[iid] = img.get("file_path") or ""

        if len(sorted_ids) == 1:
            classifications = {sorted_ids[0]: "neutral"}
        else:
            classifications = classify_best_m(
                sorted_ids,
                m=k,
                reject_rest=reject_non_picks,
            )

        for img_id, decision in classifications.items():
            decisions.append((img_id, decision, path_by_id.get(img_id, "")))

    return decisions
