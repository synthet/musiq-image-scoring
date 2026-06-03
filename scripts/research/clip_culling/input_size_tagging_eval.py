#!/usr/bin/env python3
"""Keyword prediction sweep + eval from embedding NPZ caches.

    python -m scripts.research.clip_culling.input_size_tagging_eval --sweep
    python -m scripts.research.clip_culling.input_size_tagging_eval --eval-only
"""

from __future__ import annotations

import argparse
import logging
import math
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.research.clip_culling import common, data
from scripts.research.clip_culling.input_size_eval import discover_npz_runs, load_npz_embeddings
from scripts.research.clip_culling.wrappers import HFImageTower, Tower, l2_normalize

logger = logging.getLogger("clip_culling.input_size_tagging_eval")

TAXONOMY = list(common.KEYWORD_TAXONOMY)
TAX_SET = set(TAXONOMY)

# Embedding model_key (NPZ filename) -> keyword inference backend.
KEYWORD_BACKENDS: dict[str, str] = {
    "clip_b32": "clip_b32",
    "openai": "openai",
    "openclip": "openclip",
    "siglip2": "siglip2",
}

OPENCLIP_SPECS = {
    "openai": ("ViT-L-14-quickgelu", "openai"),
    "openclip": ("ViT-L-14", "laion2b_s32b_b82k"),
}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not (a | b):
        return 0.0
    return len(a & b) / len(a | b)


def _predict_keywords(
    model_key: str,
    emb_map: dict[int, np.ndarray],
    preprocess_size: int | None = None,
) -> dict[int, set[str]]:
    ids = sorted(emb_map)
    if not ids:
        return {}
    mat = l2_normalize(np.stack([emb_map[i] for i in ids]))

    backend = KEYWORD_BACKENDS.get(model_key)
    if backend == "clip_b32":
        tower = Tower("ViT-B-32", "openai", preprocess_size=preprocess_size)
        preds = tower.predict_keywords(mat, TAXONOMY, threshold=0.2, top_k=5)
        tower.unload()
    elif backend in OPENCLIP_SPECS:
        mn, pt = OPENCLIP_SPECS[backend]
        tower = Tower(mn, pt, preprocess_size=preprocess_size)
        preds = tower.predict_keywords(mat, TAXONOMY, threshold=0.2, top_k=5)
        tower.unload()
    elif backend == "siglip2":
        tower = HFImageTower("google/siglip2-base-patch16-224", kind="siglip2")
        preds = tower.predict_keywords_sigmoid(mat, TAXONOMY, threshold=0.2, top_k=5)
        tower.unload()
    else:
        return {}
    return {iid: set(p) for iid, p in zip(ids, preds)}


def _save_tagging_npz(
    path: Path,
    preds: dict[int, set[str]],
    meta: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = sorted(preds)
    tags = np.asarray([sorted(preds[i]) for i in ids], dtype=object)
    np.savez_compressed(
        path,
        image_ids=np.asarray(ids, dtype=np.int32),
        tags=tags,
        meta=np.array([meta], dtype=object),
    )
    logger.info("Wrote %s (%d tag rows)", path, len(ids))


def load_tagging_npz(path: Path) -> dict[int, set[str]]:
    if not path.exists():
        return {}
    z = np.load(path, allow_pickle=True)
    out: dict[int, set[str]] = {}
    for i, iid in enumerate(z["image_ids"]):
        raw = z["tags"][i]
        if isinstance(raw, (list, tuple, np.ndarray)):
            out[int(iid)] = set(str(x) for x in raw)
        else:
            out[int(iid)] = set()
    return out


def tag_entropy(preds: dict[int, set[str]]) -> float:
    cnt: Counter = Counter()
    for tags in preds.values():
        cnt.update(tags)
    total = sum(cnt.values())
    if total <= 0:
        return 0.0
    ent = 0.0
    for c in cnt.values():
        p = c / total
        ent -= p * math.log2(p)
    return round(ent, 4)


def eval_tagging_run(
    preds: dict[int, set[str]],
    db_auto_tax: dict[int, set[str]],
    burst_gt: dict[int, int],
) -> dict:
    common_ids = set(preds) & set(db_auto_tax)
    jaccard_b32 = (
        round(float(np.mean([_jaccard(preds[i], db_auto_tax[i]) for i in common_ids])), 4)
        if common_ids else None
    )
    mean_tags = round(float(np.mean([len(preds[i]) for i in preds])), 4) if preds else None
    ent = tag_entropy(preds)

    # Within-burst tag duplication: mean Jaccard between pairs in same burst.
    burst_pairs: list[float] = []
    by_burst: dict[int, list[int]] = {}
    for iid in preds:
        if iid in burst_gt:
            by_burst.setdefault(burst_gt[iid], []).append(iid)
    for members in by_burst.values():
        if len(members) < 2:
            continue
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                burst_pairs.append(_jaccard(preds[members[a]], preds[members[b]]))
    burst_dup = round(float(np.mean(burst_pairs)), 4) if burst_pairs else None

    return {
        "jaccard_vs_b32_baseline": jaccard_b32,
        "mean_tags_per_image": mean_tags,
        "tag_entropy": ent,
        "within_burst_tag_jaccard": burst_dup,
        "n_images": len(preds),
    }


def run_tagging_sweep(
    models: list[str] | None = None,
    force: bool = False,
) -> list[dict]:
    """Generate tagging NPZ from existing embedding NPZ files."""
    stats = []
    runs = discover_npz_runs("embedding")
    if models:
        model_set = set(models)
        runs = [r for r in runs if r[0] in model_set]
    for model_key, source, long_edge, emb_path in runs:
        if model_key not in KEYWORD_BACKENDS:
            continue
        out_path = common.npz_cache_path(model_key, source, long_edge, track="tagging")
        if out_path.exists() and not force:
            stats.append({"model": model_key, "source": source, "long_edge": long_edge, "skipped": True})
            continue
        emb_map = load_npz_embeddings(emb_path)
        if not emb_map:
            continue
        logger.info("tagging sweep %s %s le=%d (%d embeddings)", model_key, source, long_edge, len(emb_map))
        preds = _predict_keywords(model_key, emb_map)
        if not preds:
            continue
        _save_tagging_npz(
            out_path,
            preds,
            {"model": model_key, "source": source, "long_edge": long_edge, "track": "tagging"},
        )
        stats.append({"model": model_key, "source": source, "long_edge": long_edge, "n": len(preds), "path": str(out_path)})
    return stats


def run_tagging_eval() -> dict:
    from scripts.research.clip_culling.experiments import _exif_burst_groups

    db_auto = data.load_keywords(source="auto")
    db_auto_tax = {i: (kw & TAX_SET) for i, kw in db_auto.items()}
    capture = data.capture_times()
    by_folder = data.images_by_folder()
    all_burst_gt: dict[int, int] = {}
    for _fid, img_ids in by_folder.items():
        ids = [i for i in img_ids if i in capture]
        if len(ids) >= 2:
            all_burst_gt.update(_exif_burst_groups(ids, capture))

    results = []
    d = common.INPUT_SIZE_NPZ_DIR
    if not d.exists():
        return {"runs": results}

    for p in sorted(d.glob("tagging_*.npz")):
        stem = p.stem[len("tagging_"):]
        parts = stem.rsplit("_", 2)
        if len(parts) != 3:
            continue
        model_key, source, le_str = parts
        try:
            long_edge = int(le_str)
        except ValueError:
            continue
        preds = load_tagging_npz(p)
        row = {
            "model": model_key,
            "source": source,
            "long_edge": long_edge,
            "metrics": eval_tagging_run(preds, db_auto_tax, all_burst_gt),
        }
        results.append(row)

    baseline = next(
        (r for r in results if r["source"] == "thumb" and r["long_edge"] == 512),
        None,
    )
    if baseline:
        bj = (baseline.get("metrics") or {}).get("jaccard_vs_b32_baseline")
        for row in results:
            j = (row.get("metrics") or {}).get("jaccard_vs_b32_baseline")
            row["delta_jaccard_vs_512_thumb"] = (
                None if bj is None or j is None else round(j - bj, 4)
            )

    return {"baseline": {"long_edge": 512, "source": "thumb"}, "runs": results}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweep", action="store_true", help="Generate tagging NPZ from embedding caches")
    ap.add_argument("--eval-only", action="store_true", help="Evaluate existing tagging NPZ only")
    ap.add_argument("--models", default="", help="Comma list of embedding model keys (default: all supported)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not (args.sweep or args.eval_only):
        args.sweep = True
        args.eval_only = True

    common.assert_e2e()
    payload: dict = {}
    models = [m.strip() for m in args.models.split(",") if m.strip()] or None
    if args.sweep:
        payload["sweep_stats"] = run_tagging_sweep(models=models, force=args.force)
    if args.eval_only:
        payload["tagging"] = run_tagging_eval()
        common.write_input_size_json("tagging_eval.json", payload.get("tagging", {}))
    common.write_input_size_json("tagging_sweep_stats.json", payload)
    logger.info("Tagging eval complete (%d runs)", len(payload.get("tagging", {}).get("runs", [])))


if __name__ == "__main__":
    main()
