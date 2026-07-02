#!/usr/bin/env python
"""Sweep level-2 sub-stack distance thresholds against live OpenCLIP embeddings.

Samples root stacks with >= ``--min-stack-size`` images, re-runs
``compute_sub_clusters`` at each candidate threshold, and reports leaf-size
distribution metrics used to pick ``culling.two_level.level2.distance_threshold``.

Usage::

    python -m scripts.study.substack_threshold_sweep --limit 200
    python -m scripts.study.substack_threshold_sweep --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from statistics import median
from typing import Any

from modules import db
from modules.culling_analytics._common import require_postgres
from modules.embedding_spaces import OPENCLIP_L14_IMAGE_SPACE_CODE
from modules.sub_clustering import compute_sub_clusters
from modules import config as app_config


@dataclass
class ThresholdMetrics:
    threshold: float
    stacks_sampled: int
    stacks_with_embeddings: int
    single_leaf_stacks: int
    multi_leaf_stacks: int
    giant_leaves: int
    leaves_over_batch: int
    median_max_leaf: float
    pct_leaves_lte_batch: float


def _candidate_thresholds() -> list[float]:
    return [round(x * 0.01, 2) for x in range(2, 13)]  # 0.02 .. 0.12


def _load_sample_stacks(limit: int, min_stack_size: int) -> list[tuple[int, list[dict]]]:
    rows = db.get_connector().query(
        """
        SELECT i.id, i.stack_id, i.score_general, i.created_at
        FROM images i
        WHERE i.stack_id IS NOT NULL
        ORDER BY i.stack_id, i.id
        """
    ) or []
    by_stack: dict[int, list[dict]] = {}
    for row in rows:
        sid = int(row["stack_id"])
        by_stack.setdefault(sid, []).append(dict(row))

    candidates = [
        (sid, imgs)
        for sid, imgs in sorted(by_stack.items())
        if len(imgs) >= min_stack_size
    ]
    # Prefer larger stacks first (where splitting matters most).
    candidates.sort(key=lambda t: (-len(t[1]), t[0]))
    return candidates[:limit]


def _metrics_for_threshold(
    stacks: list[tuple[int, list[dict]]],
    embeddings_by_stack: dict[int, dict[int, object]],
    threshold: float,
    *,
    batch_size: int,
) -> ThresholdMetrics:
    single_leaf = 0
    multi_leaf = 0
    giant = 0
    leaves_over_batch = 0
    total_leaves = 0
    leaves_lte_batch = 0
    max_leaf_sizes: list[int] = []
    with_emb = 0

    for stack_id, images in stacks:
        emb_map = embeddings_by_stack.get(stack_id) or {}
        if len(emb_map) < 2:
            continue
        with_emb += 1
        leaves = compute_sub_clusters(images, emb_map, threshold)
        if not leaves:
            leaves = [images]
        if len(leaves) == 1:
            single_leaf += 1
        else:
            multi_leaf += 1
        sizes = [len(leaf) for leaf in leaves]
        max_leaf_sizes.append(max(sizes))
        for sz in sizes:
            total_leaves += 1
            if sz > 50:
                giant += 1
            if sz > batch_size:
                leaves_over_batch += 1
            else:
                leaves_lte_batch += 1

    pct_lte = round(100.0 * leaves_lte_batch / total_leaves, 2) if total_leaves else 0.0
    med_max = float(median(max_leaf_sizes)) if max_leaf_sizes else 0.0
    return ThresholdMetrics(
        threshold=threshold,
        stacks_sampled=len(stacks),
        stacks_with_embeddings=with_emb,
        single_leaf_stacks=single_leaf,
        multi_leaf_stacks=multi_leaf,
        giant_leaves=giant,
        leaves_over_batch=leaves_over_batch,
        median_max_leaf=med_max,
        pct_leaves_lte_batch=pct_lte,
    )


def _pick_best(metrics: list[ThresholdMetrics]) -> float:
    """Lower single-leaf + giant counts; tie-break higher pct_leaves_lte_batch."""
    if not metrics:
        return 0.06

    def _score(m: ThresholdMetrics) -> tuple:
        return (
            m.single_leaf_stacks,
            m.giant_leaves,
            m.leaves_over_batch,
            -m.pct_leaves_lte_batch,
            m.median_max_leaf,
        )

    return min(metrics, key=_score).threshold


def run_sweep(
    *,
    limit: int = 200,
    min_stack_size: int = 10,
    batch_size: int = 10,
    embedding_space: str | None = None,
) -> dict[str, Any]:
    require_postgres()
    tl = app_config.get_config_value("culling.two_level", default={}) or {}
    level2 = tl.get("level2") or {}
    space = embedding_space or str(
        level2.get("embedding_space") or OPENCLIP_L14_IMAGE_SPACE_CODE
    )
    current = float(level2.get("distance_threshold", 0.06))

    stacks = _load_sample_stacks(limit, min_stack_size)
    embeddings_by_stack: dict[int, dict[int, object]] = {}
    for stack_id, images in stacks:
        ids = [int(img["id"]) for img in images]
        embeddings_by_stack[stack_id] = db.get_image_embeddings_batch_for_space(space, ids)

    metrics = [
        _metrics_for_threshold(stacks, embeddings_by_stack, thr, batch_size=batch_size)
        for thr in _candidate_thresholds()
    ]
    recommended = _pick_best(metrics)
    return {
        "embedding_space": space,
        "current_threshold": current,
        "recommended_threshold": recommended,
        "batch_size": batch_size,
        "stacks_sampled": len(stacks),
        "min_stack_size": min_stack_size,
        "metrics": [m.__dict__ for m in metrics],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep sub-stack level-2 thresholds")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-stack-size", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_sweep(
        limit=args.limit,
        min_stack_size=args.min_stack_size,
        batch_size=args.batch_size,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"current={report['current_threshold']} recommended={report['recommended_threshold']}")
        for row in report["metrics"]:
            print(
                f"  thr={row['threshold']:.2f} single_leaf={row['single_leaf_stacks']} "
                f"giant={row['giant_leaves']} over_batch={row['leaves_over_batch']} "
                f"pct_leaves_lte_batch={row['pct_leaves_lte_batch']}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
