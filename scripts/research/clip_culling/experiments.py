#!/usr/bin/env python3
"""Experiments 1-7 over the seeded E2E corpus. Emits per-experiment JSON.

    python -m scripts.research.clip_culling.experiments --all

Signals are derived from persisted L/14 image embeddings (read from E2E) plus a
text tower for prompt-margin / keyword scoring. Ground-truth columns: human
``rating`` (1-5), ``label`` (Red/Yellow/Green/Blue/Purple), ``cull_decision``
(pick/neutral/reject). All reads target ``image_scoring_test``.
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
from scipy.stats import pearsonr, spearmanr

from scripts.research.clip_culling import common, checkpoints, data
from scripts.research.clip_culling.wrappers import (
    AestheticHead,
    HFImageTower,
    PromptMargin,
    Tower,
    l2_normalize,
)

logger = logging.getLogger("clip_culling.exp")

# ---- Prompt banks (English; CLIP-IQA / antonym style) --------------------
SHARP_POS = ["a sharp, in-focus photo"]
SHARP_NEG = ["a blurry, out-of-focus photo"]
EXPO_POS = ["a well-exposed photo with good lighting"]
EXPO_NEG = ["an overexposed photo", "an underexposed, too dark photo"]
QUAL_POS = ["a good photo"]
QUAL_NEG = ["a bad photo"]

# Exp 6 color-label rubric (closed set over images.label values).
LABEL_RUBRIC = {
    "Red": ["a blurry out-of-focus photo", "a badly exposed photo"],
    "Yellow": ["an average snapshot", "a mediocre photo"],
    "Green": ["a sharp, well-composed, high quality photo"],
    "Blue": ["a bird in its natural habitat", "a wildlife photo"],
    "Purple": ["a striking, artistic, award-winning wildlife photo"],
}
LABEL_KEEPER_ORDINAL = {"Red": 0, "Yellow": 1, "Blue": 2, "Green": 3}


def _stats(x: np.ndarray) -> dict:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    return {
        "n": int(x.size),
        "min": float(x.min()), "max": float(x.max()),
        "mean": float(x.mean()), "std": float(x.std()),
        "p02": float(np.percentile(x, 2)),
        "p50": float(np.percentile(x, 50)),
        "p98": float(np.percentile(x, 98)),
    }


def _corr(a: np.ndarray, b: np.ndarray) -> dict:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 5:
        return {"n": int(m.sum()), "spearman": None, "pearson": None}
    sp = spearmanr(a[m], b[m]).correlation
    pe = pearsonr(a[m], b[m])[0]
    return {"n": int(m.sum()), "spearman": round(float(sp), 4), "pearson": round(float(pe), 4)}


class Corpus:
    """Loads embeddings/meta once and derives L/14 signals."""

    def __init__(self):
        common.assert_e2e()
        common.register_l14_spaces()
        self.meta = data.load_meta()
        self.model_scores = data.load_model_scores()
        self.emb_openai = data.load_embeddings(common.SPACE_OPENAI_L14)
        self.emb_openclip = data.load_embeddings(common.SPACE_OPENCLIP_L14)
        self.emb_mobilenet = data.load_embeddings("mobilenet_v2_imagenet_gap")
        self.emb_bioclip = data.load_embeddings("bioclip_2_image")
        self.emb_dinov2 = data.load_embeddings(common.SPACE_DINOV2)
        self.emb_siglip2 = data.load_embeddings(common.SPACE_SIGLIP2)
        self.emb_by_space = {
            "mobilenet_v2_imagenet_gap": self.emb_mobilenet,
            "clip_vit_b32_image": data.load_embeddings("clip_vit_b32_image"),
            common.SPACE_OPENAI_L14: self.emb_openai,
            common.SPACE_OPENCLIP_L14: self.emb_openclip,
            common.SPACE_DINOV2: self.emb_dinov2,
            common.SPACE_SIGLIP2: self.emb_siglip2,
        }
        logger.info(
            "Corpus: meta=%d openai=%d openclip=%d mobilenet=%d bioclip=%d dinov2=%d siglip2=%d",
            len(self.meta), len(self.emb_openai), len(self.emb_openclip),
            len(self.emb_mobilenet), len(self.emb_bioclip),
            len(self.emb_dinov2), len(self.emb_siglip2),
        )
        self.signals: dict[str, dict[int, float]] = {}

    def derive_signals(self):
        """Score aesthetic head + prompt margins over persisted embeddings."""
        manifest = checkpoints.write_manifest()
        head = AestheticHead(manifest["aesthetic_head"]["path"])
        text_tower = Tower("ViT-L-14-quickgelu", "openai")
        pm = PromptMargin(text_tower)

        def score_space(emb_map, tag, use_head, use_margins):
            ids = sorted(emb_map)
            if not ids:
                return
            mat = l2_normalize(np.stack([emb_map[i] for i in ids]))
            if use_head:
                aes = head.score(mat)
                self.signals[f"aes_{tag}"] = dict(zip(ids, [float(x) for x in aes]))
            if use_margins:
                self.signals[f"sharp_{tag}"] = dict(zip(ids, [float(x) for x in pm.score(mat, SHARP_POS, SHARP_NEG)]))
                self.signals[f"expo_{tag}"] = dict(zip(ids, [float(x) for x in pm.score(mat, EXPO_POS, EXPO_NEG)]))
                self.signals[f"clipiqa_{tag}"] = dict(zip(ids, [float(x) for x in pm.softmax_pair(mat, QUAL_POS, QUAL_NEG)]))

        score_space(self.emb_openai, "openai", use_head=True, use_margins=True)
        # OpenCLIP head numbers are diagnostic only (tower mismatch).
        score_space(self.emb_openclip, "openclip", use_head=True, use_margins=True)
        text_tower.unload()
        logger.info("Derived signals: %s", list(self.signals))

    # --- accessors -------------------------------------------------------
    def aligned(self, signal: str, target: str):
        """Return (sig_values, target_values) aligned over common image_ids."""
        sig = self.signals.get(signal, {})
        a, b = [], []
        for iid, sv in sig.items():
            tv = self._target_value(iid, target)
            if tv is None:
                continue
            a.append(sv)
            b.append(tv)
        return np.array(a, float), np.array(b, float)

    def _target_value(self, iid: int, target: str):
        m = self.meta.get(iid, {})
        if target in ("score_general", "score_technical", "score_aesthetic", "rating"):
            v = m.get(target)
            return float(v) if v is not None else None
        if target == "label_keeper":
            return LABEL_KEEPER_ORDINAL.get(m.get("label"))
        if target.startswith("model:"):
            return self.model_scores.get(iid, {}).get(target.split(":", 1)[1])
        return None


# ---------------------------------------------------------------------------
# Experiment 1 — score signal quality / novelty
# ---------------------------------------------------------------------------
def exp1_signal(c: Corpus) -> dict:
    signals = ["aes_openai", "sharp_openai", "expo_openai", "clipiqa_openai", "aes_openclip"]
    existing = ["score_general", "score_technical", "score_aesthetic",
                "model:liqe", "model:ava", "model:spaq", "model:arniqa", "model:topiq"]
    human = ["rating", "label_keeper"]
    out = {"distributions": {}, "correlations": {}, "novelty": {}}
    for s in signals:
        vals = np.array(list(c.signals.get(s, {}).values()), float)
        out["distributions"][s] = _stats(vals)
        out["correlations"][s] = {}
        for t in existing + human:
            a, b = c.aligned(s, t)
            out["correlations"][s][t] = _corr(a, b)
    # novelty: low |spearman| vs existing scores, non-trivial vs human picks
    for s in signals:
        corrs = out["correlations"][s]
        max_existing = max(
            (abs(corrs[t]["spearman"]) for t in existing if corrs[t]["spearman"] is not None),
            default=None,
        )
        human_rating = corrs.get("rating", {}).get("spearman")
        out["novelty"][s] = {
            "max_abs_spearman_vs_existing": round(max_existing, 4) if max_existing is not None else None,
            "abs_spearman_vs_rating": round(abs(human_rating), 4) if human_rating is not None else None,
            "is_new_signal": bool(
                max_existing is not None and max_existing < 0.5
                and human_rating is not None and abs(human_rating) > 0.1
            ),
        }
    # OpenAI vs OpenCLIP aesthetic-head agreement (diagnostic)
    ids = sorted(set(c.signals.get("aes_openai", {})) & set(c.signals.get("aes_openclip", {})))
    if len(ids) > 5:
        ao = np.array([c.signals["aes_openai"][i] for i in ids])
        ac = np.array([c.signals["aes_openclip"][i] for i in ids])
        out["openai_vs_openclip_aesthetic_agreement"] = _corr(ao, ac)
    common.write_json("exp1_signal.json", out)
    return out


# ---------------------------------------------------------------------------
# Experiment 2 — mishot rejection
# ---------------------------------------------------------------------------
def exp2_mishot(c: Corpus) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    # Ground-truth reject: explicit cull reject, OR Red label, OR rating<=2
    y, ids = [], []
    for iid, m in c.meta.items():
        cull = m.get("cull_decision")
        rating = m.get("rating")
        label = m.get("label")
        reject = (cull == "reject") or (label == "Red") or (rating is not None and rating <= 2)
        y.append(1 if reject else 0)
        ids.append(iid)
    y = np.array(y)
    idx = {iid: k for k, iid in enumerate(ids)}

    # Candidate reject scores (higher = more likely reject)
    def signal_vec(name, invert=False, model=False):
        vec = np.full(len(ids), np.nan)
        for iid in ids:
            if model:
                v = c.model_scores.get(iid, {}).get(name)
            else:
                v = c.signals.get(name, {}).get(iid)
            if v is not None:
                vec[idx[iid]] = -v if invert else v
        return vec

    candidates = {
        "clipiqa_bad_openai": signal_vec("clipiqa_openai", invert=True),
        "neg_sharp_openai": signal_vec("sharp_openai", invert=True),
        "neg_expo_openai": signal_vec("expo_openai", invert=True),
        "neg_aesthetic_openai": signal_vec("aes_openai", invert=True),
        "baseline_neg_score_technical": np.array(
            [-(c.meta[iid].get("score_technical") or np.nan) for iid in ids]),
        "baseline_neg_arniqa": signal_vec("arniqa", invert=True, model=True),
    }
    out = {"n_total": int(len(y)), "n_reject": int(y.sum()), "metrics": {}}
    for name, vec in candidates.items():
        m = np.isfinite(vec)
        if m.sum() < 10 or len(np.unique(y[m])) < 2:
            out["metrics"][name] = {"n": int(m.sum()), "roc_auc": None, "pr_auc": None}
            continue
        out["metrics"][name] = {
            "n": int(m.sum()),
            "roc_auc": round(float(roc_auc_score(y[m], vec[m])), 4),
            "pr_auc": round(float(average_precision_score(y[m], vec[m])), 4),
        }
    common.write_json("exp2_mishot.json", out)
    return out


# ---------------------------------------------------------------------------
# Experiment 3 — diverse high-scored stack picks (MMR vs single-best)
# ---------------------------------------------------------------------------
def _mmr(cand_ids, emb_map, quality, k, lam=0.5):
    sel = []
    remaining = list(cand_ids)
    while remaining and len(sel) < k:
        best, best_score = None, -1e9
        for cid in remaining:
            rel = quality[cid]
            if not sel:
                div = 1.0
            else:
                sims = [float(emb_map[cid] @ emb_map[s]) for s in sel]
                div = 1.0 - max(sims)
            score = lam * rel + (1 - lam) * div
            if score > best_score:
                best, best_score = cid, score
        sel.append(best)
        remaining.remove(best)
    return sel


def _mean_pairwise_dist(ids, emb_map):
    if len(ids) < 2:
        return 0.0
    d = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            d.append(1.0 - float(emb_map[ids[i]] @ emb_map[ids[j]]))
    return float(np.mean(d))


def exp3_diversity(c: Corpus, k=3, min_size=4) -> dict:
    emb = {i: l2_normalize(v) for i, v in c.emb_openai.items()}
    stacks = data.stacks(min_size=min_size)
    quality_signal = c.signals.get("aes_openai", {})
    rows, mmr_div, topk_div, qkept_mmr, qkept_top = [], [], [], [], []
    for sid, members in stacks.items():
        members = [m for m in members if m in emb and m in quality_signal]
        if len(members) < min_size:
            continue
        q = {m: quality_signal[m] for m in members}
        top = sorted(members, key=lambda m: q[m], reverse=True)[:k]
        mmr = _mmr(members, emb, q, k)
        d_mmr = _mean_pairwise_dist(mmr, emb)
        d_top = _mean_pairwise_dist(top, emb)
        qkept_mmr.append(np.mean([q[m] for m in mmr]))
        qkept_top.append(np.mean([q[m] for m in top]))
        mmr_div.append(d_mmr)
        topk_div.append(d_top)
        rows.append({"stack": sid, "size": len(members), "top_div": round(d_top, 4),
                     "mmr_div": round(d_mmr, 4)})
    out = {
        "n_stacks": len(rows), "k": k,
        "mean_diversity_topk": round(float(np.mean(topk_div)), 4) if topk_div else None,
        "mean_diversity_mmr": round(float(np.mean(mmr_div)), 4) if mmr_div else None,
        "diversity_gain_pct": round(100 * (np.mean(mmr_div) / np.mean(topk_div) - 1), 1) if topk_div and np.mean(topk_div) else None,
        "mean_quality_topk": round(float(np.mean(qkept_top)), 4) if qkept_top else None,
        "mean_quality_mmr": round(float(np.mean(qkept_mmr)), 4) if qkept_mmr else None,
        "examples": rows[:15],
    }
    common.write_json("exp3_diversity.json", out)
    return out


# ---------------------------------------------------------------------------
# Experiment 4 — distinctive bird poses (BioCLIP vs CLIP L/14)
# ---------------------------------------------------------------------------
def _farthest_point(ids, emb_map, k):
    if len(ids) <= k:
        return list(ids)
    start = ids[0]
    sel = [start]
    while len(sel) < k:
        best, bestd = None, -1
        for cid in ids:
            if cid in sel:
                continue
            d = min(1.0 - float(emb_map[cid] @ emb_map[s]) for s in sel)
            if d > bestd:
                best, bestd = cid, d
        sel.append(best)
    return sel


def exp4_birds(c: Corpus, k=3, min_size=4) -> dict:
    species = data.species_images()
    stacks = data.stacks(min_size=min_size)
    emb_l14 = {i: l2_normalize(v) for i, v in c.emb_openai.items()}
    emb_bio = {i: l2_normalize(v) for i, v in c.emb_bioclip.items()}
    rows = []
    overlaps = []
    for sid, members in stacks.items():
        sp = [m for m in members if m in species and m in emb_l14 and m in emb_bio]
        if len(sp) < min_size:
            continue
        sel_l14 = set(_farthest_point(sp, emb_l14, k))
        sel_bio = set(_farthest_point(sp, emb_bio, k))
        overlap = len(sel_l14 & sel_bio) / k
        overlaps.append(overlap)
        rows.append({
            "stack": sid, "n_species_imgs": len(sp),
            "div_l14": round(_mean_pairwise_dist(list(sel_l14), emb_l14), 4),
            "div_bioclip": round(_mean_pairwise_dist(list(sel_bio), emb_bio), 4),
            "selection_overlap": round(overlap, 3),
            "picks_l14": sorted(sel_l14), "picks_bioclip": sorted(sel_bio),
        })
    out = {
        "n_species_stacks": len(rows), "k": k,
        "mean_selection_overlap_l14_vs_bioclip": round(float(np.mean(overlaps)), 3) if overlaps else None,
        "examples": rows[:15],
    }
    common.write_json("exp4_birds.json", out)
    return out


# ---------------------------------------------------------------------------
# Experiment 5 — scene-based sub-stacking (semantic vs visual)
# ---------------------------------------------------------------------------
def exp5_substack(c: Corpus, min_size=8, thresholds=(0.08, 0.12, 0.18, 0.25, 0.3)) -> dict:
    """Sweep cosine thresholds; report the one that yields the most real sub-splits.

    Near-duplicate stacks have small within-stack cosine distances, so a single
    fixed threshold often collapses to one cluster (silhouette undefined). The
    sweep finds a threshold where both spaces actually split, enabling a fair
    semantic (CLIP L/14) vs visual (MobileNet) silhouette comparison.
    """
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import silhouette_score

    stacks = data.stacks(min_size=min_size)
    emb_sem = {i: l2_normalize(v) for i, v in c.emb_openai.items()}
    emb_vis = {i: l2_normalize(v) for i, v in c.emb_mobilenet.items()}
    members_by_stack = {}
    for sid, members in stacks.items():
        ms = [m for m in members if m in emb_sem and m in emb_vis]
        if len(ms) >= min_size:
            members_by_stack[sid] = ms

    def cluster(emb_map, ms, dist_thr):
        X = np.stack([emb_map[m] for m in ms])
        labels = AgglomerativeClustering(
            n_clusters=None, distance_threshold=dist_thr,
            metric="cosine", linkage="average").fit_predict(X)
        n = len(set(labels))
        sil = float(silhouette_score(X, labels, metric="cosine")) if 1 < n < len(ms) else None
        return n, labels, sil

    sweep = {}
    best_thr, best_rows, best_sem, best_vis = None, [], [], []
    for thr in thresholds:
        rows, sil_sem, sil_vis = [], [], []
        for sid, ms in members_by_stack.items():
            n_sem, _, s_sem = cluster(emb_sem, ms, thr)
            n_vis, _, s_vis = cluster(emb_vis, ms, thr)
            if s_sem is not None:
                sil_sem.append(s_sem)
            if s_vis is not None:
                sil_vis.append(s_vis)
            rows.append({"stack": sid, "size": len(ms), "n_sub_semantic": n_sem,
                         "n_sub_visual": n_vis,
                         "silhouette_semantic": round(s_sem, 4) if s_sem is not None else None,
                         "silhouette_visual": round(s_vis, 4) if s_vis is not None else None})
        sweep[thr] = {"n_stacks_split_semantic": len(sil_sem), "n_stacks_split_visual": len(sil_vis),
                      "mean_silhouette_semantic": round(float(np.mean(sil_sem)), 4) if sil_sem else None,
                      "mean_silhouette_visual": round(float(np.mean(sil_vis)), 4) if sil_vis else None}
        if len(sil_sem) > len(best_sem):
            best_thr, best_rows, best_sem, best_vis = thr, rows, sil_sem, sil_vis
    out = {
        "n_stacks": len(members_by_stack), "selected_threshold": best_thr,
        "threshold_sweep": {str(k): v for k, v in sweep.items()},
        "mean_silhouette_semantic": round(float(np.mean(best_sem)), 4) if best_sem else None,
        "mean_silhouette_visual": round(float(np.mean(best_vis)), 4) if best_vis else None,
        "examples": best_rows[:15],
    }
    common.write_json("exp5_substack.json", out)
    return out


# ---------------------------------------------------------------------------
# Experiment 6 — CLIP-query color labels
# ---------------------------------------------------------------------------
def exp6_colorlabel(c: Corpus, conf_threshold=0.0) -> dict:
    from sklearn.metrics import confusion_matrix

    text_tower = Tower("ViT-L-14-quickgelu", "openai")
    labels = list(LABEL_RUBRIC)
    bank_emb = {lab: text_tower.encode_text(LABEL_RUBRIC[lab]) for lab in labels}
    scale = text_tower.logit_scale

    ids = [i for i in c.emb_openai if c.meta.get(i, {}).get("label") in labels]
    pred, truth = [], []
    for iid in ids:
        e = l2_normalize(c.emb_openai[iid])
        per_label = np.array([float((e @ bank_emb[lab].T).mean()) for lab in labels])
        logits = per_label * scale
        logits -= logits.max()
        p = np.exp(logits)
        p /= p.sum()
        am = int(p.argmax())
        if p[am] < conf_threshold:
            continue
        pred.append(labels[am])
        truth.append(c.meta[iid]["label"])
    text_tower.unload()

    present = [lab for lab in labels if lab in truth or lab in pred]
    cm = confusion_matrix(truth, pred, labels=present).tolist() if truth else []
    agreement = float(np.mean([p == t for p, t in zip(pred, truth)])) if truth else None
    per_label = {}
    for lab in present:
        tp = sum(1 for p, t in zip(pred, truth) if p == lab and t == lab)
        fp = sum(1 for p, t in zip(pred, truth) if p == lab and t != lab)
        fn = sum(1 for p, t in zip(pred, truth) if p != lab and t == lab)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        per_label[lab] = {"precision": round(prec, 3) if prec is not None else None,
                          "recall": round(rec, 3) if rec is not None else None,
                          "support": sum(1 for t in truth if t == lab)}
    out = {
        "n_evaluated": len(truth), "overall_agreement": round(agreement, 4) if agreement is not None else None,
        "labels": present, "confusion_matrix": cm, "per_label": per_label,
        "rubric": LABEL_RUBRIC,
        "note": "Heuristic rubric; bird folders are label-skewed. Agreement is directional.",
    }
    common.write_json("exp6_colorlabel.json", out)
    return out


# ---------------------------------------------------------------------------
# Experiment 7 — keyword accuracy vs current DB (B/32 baseline)
# ---------------------------------------------------------------------------
def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not (a | b):
        return 0.0
    return len(a & b) / len(a | b)


def exp7_keywords(c: Corpus) -> dict:
    from scripts.research.clip_culling.wrappers import Tower as T

    taxonomy = [
        "landscape", "portrait", "urban", "cityscape", "nature", "wildlife",
        "architecture", "macro", "street", "night", "black and white",
        "sunset", "sunrise", "beach", "forest", "mountain", "water",
        "flowers", "animals", "birds", "insect", "people", "abstract", "minimal",
        "aerial", "transportation",
    ]
    db_auto = data.load_keywords(source="auto")
    db_user = data.load_keywords(source="user")
    # restrict baseline to taxonomy tags for a fair comparison
    tax_set = set(taxonomy)
    db_auto_tax = {i: (kw & tax_set) for i, kw in db_auto.items()}

    results = {}
    preds_by_model = {}
    for tag, (mn, pt) in {"openai": ("ViT-L-14-quickgelu", "openai"),
                          "openclip": ("ViT-L-14", "laion2b_s32b_b82k")}.items():
        emb_map = c.emb_openai if tag == "openai" else c.emb_openclip
        ids = sorted(emb_map)
        if not ids:
            continue
        tower = T(mn, pt)
        mat = l2_normalize(np.stack([emb_map[i] for i in ids]))
        preds = tower.predict_keywords(mat, taxonomy, threshold=0.2, top_k=5)
        tower.unload()
        preds_by_model[tag] = {iid: set(p) for iid, p in zip(ids, preds)}

    # inter-model agreement (Jaccard) + vs B/32 baseline
    def agree(mp_a, mp_b):
        common_ids = set(mp_a) & set(mp_b)
        if not common_ids:
            return None
        return round(float(np.mean([_jaccard(mp_a[i], mp_b[i]) for i in common_ids])), 4)

    base = {i: db_auto_tax.get(i, set()) for i in (preds_by_model.get("openai") or {})}
    results["jaccard_vs_b32_baseline"] = {
        m: agree(preds_by_model[m], base) for m in preds_by_model
    }
    if "openai" in preds_by_model and "openclip" in preds_by_model:
        results["jaccard_openai_vs_openclip"] = agree(preds_by_model["openai"], preds_by_model["openclip"])

    # tag frequency per model + baseline
    def freq(mp):
        from collections import Counter
        cnt = Counter()
        for s in mp.values():
            cnt.update(s)
        return dict(cnt.most_common(12))
    results["top_tags"] = {m: freq(mp) for m, mp in preds_by_model.items()}
    results["top_tags"]["b32_baseline"] = freq(base)

    # accuracy vs human (if any user keywords exist)
    if db_user:
        from collections import defaultdict
        f1s = defaultdict(list)
        for m, mp in preds_by_model.items():
            for iid, truth in db_user.items():
                if iid not in mp:
                    continue
                pred = mp[iid] & tax_set
                t = truth & tax_set
                tp = len(pred & t)
                prec = tp / len(pred) if pred else 0
                rec = tp / len(t) if t else 0
                f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
                f1s[m].append(f1)
        results["f1_vs_human"] = {m: round(float(np.mean(v)), 4) for m, v in f1s.items()}
        results["n_human_truth"] = len(db_user)
    else:
        results["f1_vs_human"] = None
        results["n_human_truth"] = 0
        results["note"] = "No source='user' keywords in seed; reporting inter-model agreement vs B/32 baseline only."

    # qualitative spot-check
    spot = []
    sample_ids = sorted(preds_by_model.get("openai", {}))[:8]
    for iid in sample_ids:
        spot.append({
            "image_id": iid,
            "file": (c.meta.get(iid, {}).get("file_path") or "").split("/")[-1],
            "b32_baseline": sorted(base.get(iid, set())),
            "openai_l14": sorted(preds_by_model.get("openai", {}).get(iid, set())),
            "openclip_l14": sorted(preds_by_model.get("openclip", {}).get(iid, set())),
        })
    results["spot_check"] = spot
    # SigLIP2 per-tag sigmoid (roadmap-preferred keyword method)
    emb_sig = c.emb_siglip2
    ids_sig = sorted(emb_sig)
    if ids_sig:
        try:
            sig_tower = HFImageTower(
                "google/siglip2-base-patch16-224", kind="siglip2",
            )
            mat_sig = l2_normalize(np.stack([emb_sig[i] for i in ids_sig]))
            preds_sig = sig_tower.predict_keywords_sigmoid(
                mat_sig, taxonomy, threshold=0.2, top_k=5,
            )
            sig_tower.unload()
            preds_by_model["siglip2"] = {iid: set(p) for iid, p in zip(ids_sig, preds_sig)}
            results["jaccard_vs_b32_baseline"]["siglip2"] = agree(
                preds_by_model["siglip2"], base,
            )
            if "openai" in preds_by_model:
                results["jaccard_siglip2_vs_openai_l14"] = agree(
                    preds_by_model["siglip2"], preds_by_model["openai"],
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("SigLIP2 keyword scoring skipped: %s", e)
            results["siglip2_keywords_error"] = str(e)

    common.write_json("exp7_keywords.json", results)
    return results


# ---------------------------------------------------------------------------
# Experiment 8 — grouping quality (EXIF-burst GT vs embedding clustering)
# ---------------------------------------------------------------------------
def _exif_burst_groups(
    image_ids: list[int],
    capture: dict[int, object],
    gap_seconds: float = 2.0,
) -> dict[int, int]:
    """Assign burst group labels from sorted EXIF capture times."""
    dated = [(iid, capture[iid]) for iid in image_ids if iid in capture]
    if not dated:
        return {}
    dated.sort(key=lambda x: x[1])
    labels: dict[int, int] = {}
    gid = 0
    labels[dated[0][0]] = gid
    for i in range(1, len(dated)):
        iid, ts = dated[i]
        prev_ts = dated[i - 1][1]
        delta = (ts - prev_ts).total_seconds()
        if delta > gap_seconds:
            gid += 1
        labels[iid] = gid
    return labels


def _pair_rates(pred: dict[int, int], gt: dict[int, int], ids: list[int]) -> dict:
    """False-merge / false-split rates over image pairs in ``ids``."""
    n = len(ids)
    if n < 2:
        return {"false_merge_rate": None, "false_split_rate": None, "pairs": 0}
    fm = fs = total = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = ids[i], ids[j]
            if a not in pred or b not in pred or a not in gt or b not in gt:
                continue
            total += 1
            same_p = pred[a] == pred[b]
            same_g = gt[a] == gt[b]
            if same_p and not same_g:
                fm += 1
            if same_g and not same_p:
                fs += 1
    if total == 0:
        return {"false_merge_rate": None, "false_split_rate": None, "pairs": 0}
    return {
        "false_merge_rate": round(fm / total, 4),
        "false_split_rate": round(fs / total, 4),
        "pairs": total,
    }


def exp8_grouping(
    c: Corpus,
    gap_seconds: float = 2.0,
    thresholds=(0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.25, 0.30),
    min_folder_images: int = 8,
) -> dict:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import (
        adjusted_mutual_info_score,
        adjusted_rand_score,
        completeness_score,
        homogeneity_score,
        silhouette_score,
    )

    capture = data.capture_times()
    by_folder = data.images_by_folder()
    out_spaces: dict[str, dict] = {}

    for space_code in common.GROUPING_SPACES:
        emb_map = c.emb_by_space.get(space_code) or {}
        if not emb_map:
            out_spaces[space_code] = {"error": "no embeddings", "n_images": 0}
            continue

        sweep_rows = []
        best = None
        for thr in thresholds:
            aris, amis, homs, comps, sils = [], [], [], [], []
            fm_rates, fs_rates = [], []
            n_clusters_list = []
            for _fid, img_ids in by_folder.items():
                ids = [i for i in img_ids if i in emb_map and i in capture]
                if len(ids) < min_folder_images:
                    continue
                gt = _exif_burst_groups(ids, capture, gap_seconds=gap_seconds)
                if len(set(gt.values())) < 2:
                    continue
                X = np.stack([l2_normalize(emb_map[i]) for i in ids])
                labels = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=thr,
                    metric="cosine",
                    linkage="average",
                ).fit_predict(X)
                n_cl = len(set(labels))
                n_clusters_list.append(n_cl)
                pred = {ids[k]: int(labels[k]) for k in range(len(ids))}
                gt_vec = [gt[i] for i in ids]
                pred_vec = [pred[i] for i in ids]
                aris.append(adjusted_rand_score(gt_vec, pred_vec))
                amis.append(adjusted_mutual_info_score(gt_vec, pred_vec))
                homs.append(homogeneity_score(gt_vec, pred_vec))
                comps.append(completeness_score(gt_vec, pred_vec))
                pr = _pair_rates(pred, gt, ids)
                if pr["false_merge_rate"] is not None:
                    fm_rates.append(pr["false_merge_rate"])
                    fs_rates.append(pr["false_split_rate"])
                if 1 < n_cl < len(ids):
                    sils.append(float(silhouette_score(X, labels, metric="cosine")))

            row = {
                "threshold": thr,
                "n_folders_evaluated": len(aris),
                "mean_ari": round(float(np.mean(aris)), 4) if aris else None,
                "mean_ami": round(float(np.mean(amis)), 4) if amis else None,
                "mean_homogeneity": round(float(np.mean(homs)), 4) if homs else None,
                "mean_completeness": round(float(np.mean(comps)), 4) if comps else None,
                "mean_false_merge_rate": round(float(np.mean(fm_rates)), 4) if fm_rates else None,
                "mean_false_split_rate": round(float(np.mean(fs_rates)), 4) if fs_rates else None,
                "mean_silhouette": round(float(np.mean(sils)), 4) if sils else None,
                "mean_n_clusters": round(float(np.mean(n_clusters_list)), 2) if n_clusters_list else None,
            }
            sweep_rows.append(row)
            score = row["mean_ari"]
            if score is not None and (best is None or score > best["mean_ari"]):
                best = row

        # Secondary: agreement with existing MobileNet-derived stacks (bias-flagged)
        stack_ari = []
        for _fid, img_ids in by_folder.items():
            ids = [i for i in img_ids if i in emb_map]
            if len(ids) < min_folder_images:
                continue
            stack_gt = {}
            for iid in ids:
                sid = c.meta.get(iid, {}).get("stack_id")
                if sid is not None:
                    stack_gt[iid] = sid
            if len(set(stack_gt.values())) < 2 or len(stack_gt) < min_folder_images:
                continue
            if best is None:
                continue
            X = np.stack([l2_normalize(emb_map[i]) for i in stack_gt])
            labels = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=best["threshold"],
                metric="cosine",
                linkage="average",
            ).fit_predict(X)
            sids = sorted(stack_gt)
            stack_ari.append(adjusted_rand_score(
                [stack_gt[i] for i in sids],
                [int(labels[k]) for k in range(len(sids))],
            ))

        out_spaces[space_code] = {
            "n_images_with_emb": len(emb_map),
            "gap_seconds": gap_seconds,
            "threshold_sweep": sweep_rows,
            "best_threshold": best,
            "mean_ari_vs_existing_stacks_bias_flagged": (
                round(float(np.mean(stack_ari)), 4) if stack_ari else None
            ),
            "note": "Primary GT is EXIF-burst (unbiased). stack_id ARI is MobileNet-biased secondary.",
        }

    # Rank spaces by best mean ARI on burst GT
    ranking = []
    for code, info in out_spaces.items():
        bt = info.get("best_threshold") or {}
        ranking.append((code, bt.get("mean_ari"), bt.get("threshold")))
    ranking.sort(key=lambda x: (x[1] is None, -(x[1] or -1)))

    result = {
        "gap_seconds": gap_seconds,
        "thresholds": list(thresholds),
        "spaces": out_spaces,
        "ranking_by_burst_ari": [
            {"space": c, "mean_ari": a, "best_threshold": t} for c, a, t in ranking
        ],
    }
    common.write_json("exp8_grouping.json", result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="", help="comma list: 1,2,3,4,5,6,7,8")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or {
        "1", "2", "3", "4", "5", "6", "7", "8",
    }

    c = Corpus()
    c.derive_signals()
    if "1" in only:
        logger.info("Exp1: %s", exp1_signal(c).get("novelty"))
    if "2" in only:
        logger.info("Exp2: %s", exp2_mishot(c).get("metrics"))
    if "3" in only:
        logger.info("Exp3: %s", {k: v for k, v in exp3_diversity(c).items() if k != "examples"})
    if "4" in only:
        logger.info("Exp4: %s", {k: v for k, v in exp4_birds(c).items() if k != "examples"})
    if "5" in only:
        logger.info("Exp5: %s", {k: v for k, v in exp5_substack(c).items() if k != "examples"})
    if "6" in only:
        logger.info("Exp6: %s", {k: v for k, v in exp6_colorlabel(c).items() if k not in ("rubric", "confusion_matrix")})
    if "7" in only:
        logger.info("Exp7: %s", {k: v for k, v in exp7_keywords(c).items() if k not in ("spot_check", "top_tags")})
    if "8" in only:
        e8 = exp8_grouping(c)
        logger.info("Exp8 ranking: %s", e8.get("ranking_by_burst_ari"))


if __name__ == "__main__":
    main()
