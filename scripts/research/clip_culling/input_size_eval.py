#!/usr/bin/env python3
"""Evaluate input-size NPZ caches: grouping ARI, pick/reject gap, pair margin, IQA mishot.

    python -m scripts.research.clip_culling.input_size_eval --all
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import (
    adjusted_rand_score,
    average_precision_score,
    roc_auc_score,
    silhouette_score,
)

from scripts.research.clip_culling import common, data
from scripts.research.clip_culling.experiments import _exif_burst_groups
from scripts.research.clip_culling.wrappers import l2_normalize

logger = logging.getLogger("clip_culling.input_size_eval")

EXP8_THRESHOLDS = (0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.25, 0.30)
BASELINE_LONG_EDGE = 512
BASELINE_SOURCE = "thumb"


def load_npz_embeddings(path: Path) -> dict[int, np.ndarray]:
    if not path.exists():
        return {}
    z = np.load(path, allow_pickle=True)
    ids = z["image_ids"]
    emb = z["embeddings"]
    out = {}
    for i, eid in enumerate(ids):
        out[int(eid)] = l2_normalize(emb[i])
    return out


def load_npz_scores(path: Path) -> dict[int, float]:
    if not path.exists():
        return {}
    z = np.load(path, allow_pickle=True)
    ids = z["image_ids"]
    sc = z["embeddings"].reshape(-1)
    return {int(ids[i]): float(sc[i]) for i in range(len(ids))}


def pair_margin(emb_map: dict[int, np.ndarray], burst_gt: dict[int, int], max_pairs: int = 5000) -> dict:
    """median(cosine dist | same burst) - median(dist | different burst)."""
    ids = [i for i in emb_map if i in burst_gt]
    if len(ids) < 2:
        return {"pair_margin": None, "same_burst_median_dist": None, "diff_burst_median_dist": None}
    same_d, diff_d = [], []

    def _record(a: int, b: int) -> None:
        dist = 1.0 - float(emb_map[a] @ emb_map[b])
        if burst_gt[a] == burst_gt[b]:
            same_d.append(dist)
        else:
            diff_d.append(dist)

    if len(ids) <= 32:
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                _record(ids[i], ids[j])
    else:
        rng = np.random.default_rng(42)
        for _ in range(min(max_pairs, len(ids) * 10)):
            a, b = rng.choice(ids, size=2, replace=False)
            _record(int(a), int(b))
    if not same_d or not diff_d:
        return {"pair_margin": None, "same_burst_median_dist": None, "diff_burst_median_dist": None}
    sm, dm = float(np.median(same_d)), float(np.median(diff_d))
    return {
        "pair_margin": round(dm - sm, 4),
        "same_burst_median_dist": round(sm, 4),
        "diff_burst_median_dist": round(dm, 4),
    }


def eval_grouping(
    emb_map: dict[int, np.ndarray],
    gap_seconds: float = 2.0,
    min_folder_images: int = 8,
) -> dict:
    capture = data.capture_times()
    by_folder = data.images_by_folder()
    sweep_rows = []
    best = None
    for thr in EXP8_THRESHOLDS:
        aris = []
        for _fid, img_ids in by_folder.items():
            ids = [i for i in img_ids if i in emb_map and i in capture]
            if len(ids) < min_folder_images:
                continue
            gt = _exif_burst_groups(ids, capture, gap_seconds=gap_seconds)
            if len(set(gt.values())) < 2:
                continue
            X = np.stack([emb_map[i] for i in ids])
            labels = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=thr,
                metric="cosine",
                linkage="average",
            ).fit_predict(X)
            pred = {ids[k]: int(labels[k]) for k in range(len(ids))}
            gt_vec = [gt[i] for i in ids]
            pred_vec = [pred[i] for i in ids]
            aris.append(adjusted_rand_score(gt_vec, pred_vec))
        row = {
            "threshold": thr,
            "n_folders_evaluated": len(aris),
            "mean_ari": round(float(np.mean(aris)), 4) if aris else None,
        }
        sweep_rows.append(row)
        if row["mean_ari"] is not None and (best is None or row["mean_ari"] > best["mean_ari"]):
            best = row
    return {"threshold_sweep": sweep_rows, "best_threshold": best}


def eval_pick_review(emb_map: dict[int, np.ndarray], meta: dict[int, dict]) -> dict:
    """Aggregate keep-reject gap over eligible stacks (mirrors culling_pick_review)."""
    from modules import db_postgres

    rows = db_postgres.execute_select(
        "SELECT i.stack_id, count(*) n FROM images i "
        "WHERE i.stack_id IS NOT NULL AND i.thumbnail_path<>'' "
        "AND i.rating IS NOT NULL AND i.label IS NOT NULL "
        "GROUP BY i.stack_id HAVING count(*) BETWEEN 8 AND 19 "
        "ORDER BY n DESC, i.stack_id LIMIT 12"
    )
    sils, kept_r, rej_r, misdrop, badpick = [], [], [], 0, 0
    for r in rows:
        stack_id = r["stack_id"]
        stack_rows = [
            meta[iid] for iid in meta
            if meta[iid].get("stack_id") == stack_id and meta[iid].get("rating") is not None
        ]
        if len(stack_rows) < 8:
            continue
        valid = [dict(id=m["id"], score_general=float(m.get("score_general") or 0),
                      rating=int(m["rating"]), label=m.get("label") or "")
                 for m in stack_rows if m["id"] in emb_map]
        k = max(2, round(len(valid) / 4))
        if len(valid) < k:
            continue
        X = np.vstack([emb_map[r["id"]] for r in valid])
        labels = AgglomerativeClustering(
            n_clusters=k, metric="cosine", linkage="average"
        ).fit_predict(X)
        try:
            sils.append(float(silhouette_score(X, labels, metric="cosine")))
        except Exception:  # noqa: BLE001
            sils.append(float("nan"))
        clusters: dict[int, list] = {}
        for lab, row in zip(labels, valid):
            clusters.setdefault(int(lab), []).append(row)
        picks, rejects = [], []
        for grp in clusters.values():
            srt = sorted(grp, key=lambda x: -x["score_general"])
            picks += srt[:3]
            rejects += srt[3:]
        kept_r += [p["rating"] for p in picks]
        rej_r += [p["rating"] for p in rejects]
        for p in rejects:
            if p["rating"] >= 4:
                misdrop += 1
        for p in picks:
            if p["rating"] <= 2 or (p["label"] or "").lower() == "red":
                badpick += 1
    mk = float(np.mean(kept_r)) if kept_r else float("nan")
    mr = float(np.mean(rej_r)) if rej_r else float("nan")
    return {
        "mean_silhouette": round(float(np.nanmean(sils)), 4) if sils else None,
        "mean_keep_rating": round(mk, 4),
        "mean_reject_rating": round(mr, 4),
        "keep_reject_gap": round(mk - mr, 4) if np.isfinite(mk) and np.isfinite(mr) else None,
        "misdrop": misdrop,
        "badpick": badpick,
    }


def eval_iqa_mishot(scores: dict[int, float], meta: dict[int, dict]) -> dict:
    ids, y, vec = [], [], []
    for iid, m in meta.items():
        if iid not in scores:
            continue
        rating = m.get("rating")
        label = m.get("label")
        cull = m.get("cull_decision")
        reject = (cull == "reject") or (label == "Red") or (rating is not None and rating <= 2)
        ids.append(iid)
        y.append(1 if reject else 0)
        vec.append(-scores[iid])
    y = np.array(y)
    vec = np.array(vec)
    m = np.isfinite(vec)
    if m.sum() < 10 or len(np.unique(y[m])) < 2:
        return {"roc_auc": None, "pr_auc": None, "n": int(m.sum())}
    return {
        "roc_auc": round(float(roc_auc_score(y[m], vec[m])), 4),
        "pr_auc": round(float(average_precision_score(y[m], vec[m])), 4),
        "n": int(m.sum()),
    }


def eval_iqa_rating_corr(scores: dict[int, float], meta: dict[int, dict]) -> dict:
    a, b = [], []
    for iid, sc in scores.items():
        r = meta.get(iid, {}).get("rating")
        if r is not None and np.isfinite(sc):
            a.append(sc)
            b.append(float(r))
    if len(a) < 5:
        return {"spearman": None, "pearson": None, "n": len(a)}
    sp = spearmanr(a, b).correlation
    pe = pearsonr(a, b)[0]
    return {"spearman": round(float(sp), 4), "pearson": round(float(pe), 4), "n": len(a)}


def discover_npz_runs(track: str = "embedding") -> list[tuple[str, str, int, Path]]:
    """List (model_key, source, long_edge, path) from NPZ dir."""
    d = common.INPUT_SIZE_NPZ_DIR
    if not d.exists():
        return []
    out = []
    prefix = f"{track}_"
    for p in sorted(d.glob(f"{prefix}*.npz")):
        stem = p.stem[len(prefix):]
        parts = stem.rsplit("_", 2)
        if len(parts) != 3:
            continue
        model_key, source, le_str = parts
        if le_str.startswith("preprocess"):
            continue
        try:
            le = int(le_str)
        except ValueError:
            continue
        out.append((model_key, source, le, p))
    return out


def run_embedding_eval() -> dict:
    meta = data.load_meta()
    capture = data.capture_times()
    by_folder = data.images_by_folder()
    all_burst_gt: dict[int, int] = {}
    for _fid, img_ids in by_folder.items():
        ids = [i for i in img_ids if i in capture]
        if len(ids) >= 2:
            bg = _exif_burst_groups(ids, capture)
            all_burst_gt.update(bg)

    runs = discover_npz_runs("embedding")
    results = []
    baselines: dict[str, dict] = {}

    for model_key, source, long_edge, path in runs:
        emb_map = load_npz_embeddings(path)
        if not emb_map:
            continue
        grouping = eval_grouping(emb_map)
        pick = eval_pick_review(emb_map, meta)
        margin = pair_margin(emb_map, all_burst_gt)
        row = {
            "model": model_key,
            "source": source,
            "long_edge": long_edge,
            "n_embeddings": len(emb_map),
            "grouping": grouping,
            "pick_review": pick,
            "pair_margin": margin,
        }
        key = f"{model_key}:{source}"
        if source == BASELINE_SOURCE and long_edge == BASELINE_LONG_EDGE:
            baselines[key] = row
        results.append(row)

    for row in results:
        key = f"{row['model']}:{row['source']}"
        base = baselines.get(key)
        if base:
            bt = base["grouping"].get("best_threshold") or {}
            rt = row["grouping"].get("best_threshold") or {}
            row["delta_vs_baseline_512_thumb"] = {
                "mean_ari": (
                    None if not bt.get("mean_ari") or not rt.get("mean_ari")
                    else round(rt["mean_ari"] - bt["mean_ari"], 4)
                ),
                "keep_reject_gap": (
                    None
                    if base["pick_review"].get("keep_reject_gap") is None
                    or row["pick_review"].get("keep_reject_gap") is None
                    else round(
                        row["pick_review"]["keep_reject_gap"]
                        - base["pick_review"]["keep_reject_gap"],
                        4,
                    )
                ),
                "pair_margin": (
                    None
                    if base["pair_margin"].get("pair_margin") is None
                    or row["pair_margin"].get("pair_margin") is None
                    else round(
                        row["pair_margin"]["pair_margin"] - base["pair_margin"]["pair_margin"],
                        4,
                    )
                ),
            }

    ranking = sorted(
        results,
        key=lambda r: (
            (r.get("grouping", {}).get("best_threshold") or {}).get("mean_ari") is None,
            -((r.get("grouping", {}).get("best_threshold") or {}).get("mean_ari") or -1),
        ),
    )
    return {
        "baseline": {"long_edge": BASELINE_LONG_EDGE, "source": BASELINE_SOURCE},
        "runs": results,
        "ranking_by_mean_ari": [
            {
                "model": r["model"],
                "source": r["source"],
                "long_edge": r["long_edge"],
                "mean_ari": (r.get("grouping", {}).get("best_threshold") or {}).get("mean_ari"),
            }
            for r in ranking[:20]
        ],
    }


def run_iqa_eval() -> dict:
    meta = data.load_meta()
    results = []
    for model_key, source, long_edge, path in discover_npz_runs("iqa"):
        scores = load_npz_scores(path)
        if not scores:
            continue
        results.append({
            "model": model_key,
            "source": source,
            "long_edge": long_edge,
            "n_scores": len(scores),
            "mishot": eval_iqa_mishot(scores, meta),
            "rating_corr": eval_iqa_rating_corr(scores, meta),
        })
    return {"runs": results}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="embedding + iqa eval")
    ap.add_argument("--embedding", action="store_true")
    ap.add_argument("--iqa", action="store_true")
    args = ap.parse_args()
    if not (args.all or args.embedding or args.iqa):
        args.all = True

    common.assert_e2e()
    payload: dict = {}
    if args.all or args.embedding:
        payload["embedding"] = run_embedding_eval()
    if args.all or args.iqa:
        payload["iqa"] = run_iqa_eval()
    common.write_input_size_json("eval_summary.json", payload)
    logger.info("Wrote eval_summary.json (%d embedding runs)", len(payload.get("embedding", {}).get("runs", [])))


if __name__ == "__main__":
    main()
