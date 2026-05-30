#!/usr/bin/env python3
"""Sweep the level2 sub-stacking distance threshold (single model) for two-level culling.

Reuses persisted embeddings from the clip_culling E2E corpus. Emits JSON with
mean leaf sub-stack counts per threshold grid point.

Usage (WSL + ~/.venvs/tf)::

    python -m scripts.research.clip_culling.two_level_thresholds \\
        --visual-space mobilenet_v2_imagenet_gap \\
        --semantic-space clip_vit_b32_image \\
        --output reports/clip-culling/two_level_thresholds.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np

from modules.two_level_culling import compute_leaf_substacks
from scripts.research.clip_culling import data

logger = logging.getLogger("clip_culling.two_level_thresholds")


def _emb_bytes_map(emb_np: dict[int, np.ndarray]) -> dict[int, bytes]:
    return {iid: vec.astype(np.float32).tobytes() for iid, vec in emb_np.items()}


def sweep_thresholds(
    stack_map: dict[int, list[int]],
    meta: dict[int, dict],
    emb: dict[int, bytes],
    space: str,
    thresholds: list[float],
) -> dict:
    """Single-pass within-stack sub-stacking sweep for one embedding space."""
    results = []
    for t in thresholds:
        leaf_counts = []
        for _sid, img_ids in stack_map.items():
            if len(img_ids) < 2:
                continue
            group = [{"id": iid, **meta.get(iid, {})} for iid in img_ids]
            leaves = compute_leaf_substacks(group, emb, t)
            leaf_counts.append(len(leaves))
        results.append(
            {
                "threshold": t,
                "stacks_evaluated": len(leaf_counts),
                "mean_leaf_substacks": float(np.mean(leaf_counts)) if leaf_counts else 0.0,
                "max_leaf_substacks": max(leaf_counts) if leaf_counts else 0,
                "min_leaf_substacks": min(leaf_counts) if leaf_counts else 0,
            }
        )
    return {"space": space, "grid": results}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Two-level culling threshold sweep")
    parser.add_argument("--space", default="openclip_l14_laion2b_image")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/clip-culling/two_level_thresholds.json"),
    )
    parser.add_argument(
        "--thresholds",
        default="0.03,0.05,0.06,0.08,0.10,0.12",
    )
    args = parser.parse_args()

    stack_map = data.stacks(min_size=2)
    meta = data.load_meta()
    emb = _emb_bytes_map(data.load_embeddings(args.space))

    thr = [float(x.strip()) for x in args.thresholds.split(",") if x.strip()]

    payload = sweep_thresholds(stack_map, meta, emb, args.space, thr)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote %s (%d grid points)", args.output, len(payload["grid"]))


if __name__ == "__main__":
    main()
