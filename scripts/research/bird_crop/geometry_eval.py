"""Step 1 — what the bounding box tells us with no extra inference at all.

Two questions, deliberately kept apart because they have different epistemic
standing:

**Bias probe** (no ground truth needed). Does the *existing* fused score depend on
subject geometry? ``images.score_general`` is produced by full-frame IQA models,
so if it drifts systematically with subject size or position, the current stack is
partly measuring "how much of the frame is bird" rather than "how good is this
photo". That is a finding about the incumbent, reportable on its own, and it needs
no labels because it makes no accuracy claim.

**Predictive value** (needs ``reports/bird-crop/labels/label_set.csv``). Do the
geometry features predict the verdict within a burst, and do they add anything
on top of the existing score? The label provenance determines whether this is a
human accuracy check or agreement with agent judges.

Everything here is pure SQL plus arithmetic: no GPU, no model loads, no writes to
production.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.bird_crop.geometry_eval
    python -m scripts.research.bird_crop.geometry_eval --folders 62,44,45,676
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional, Sequence

import numpy as np
from numpy.typing import ArrayLike

from scripts.research.bird_crop import bursts, labels, prod
from scripts.research.bird_crop.bbox import (
    geometry_features,
    parse_bbox,
    subject_px_at_long_edge,
)

logger = logging.getLogger("bird_crop.geometry_eval")

#: Features under test. Small on purpose: 54 labelled bursts cannot support a
#: wide model without overfitting.
FEATURES = (
    "area_frac",
    "offset_center",
    "offset_thirds",
    "aspect",
    "edges_touched",
    "conf",
)

#: Model input sizes the subject-resolution table is reported at.
REPORT_LONG_EDGES = (224, 384, 512)

#: Terciles/deciles are reported on this column, which the scoring phase writes.
SCORE_COL = "score_general"


# ---------------------------------------------------------------------------
# Metrics (kept dependency-light and unit-testable)
# ---------------------------------------------------------------------------
def spearman(a: ArrayLike, b: ArrayLike) -> Optional[float]:
    """Spearman rank correlation, or ``None`` when there is too little data."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 5:
        return None
    from scipy.stats import spearmanr

    rho = spearmanr(x[mask], y[mask]).correlation
    return None if rho is None or not np.isfinite(rho) else round(float(rho), 4)


def roc_auc(scores: ArrayLike, positives: ArrayLike) -> Optional[float]:
    """ROC-AUC of *scores* against a boolean label, or ``None`` if degenerate."""
    s, y = np.asarray(scores, dtype=float), np.asarray(positives, dtype=bool)
    mask = np.isfinite(s)
    if mask.sum() < 10 or len(np.unique(y[mask])) < 2:
        return None
    from sklearn.metrics import roc_auc_score

    return round(float(roc_auc_score(y[mask], s[mask])), 4)


def zscore_within_group(values: ArrayLike, groups: ArrayLike) -> np.ndarray:
    """Standardise *values* inside each group.

    Within-burst standardisation is what makes the comparison fair: it removes
    the between-burst variation (species, light, distance) that neither the model
    nor the labeller was asked to judge, leaving only "which frame in *this*
    burst is better".
    """
    v = np.asarray(values, dtype=float)
    g = np.asarray(groups)
    out = np.full(v.shape, np.nan, dtype=float)
    for gid in np.unique(g):
        m = g == gid
        chunk = v[m]
        finite = np.isfinite(chunk)
        if finite.sum() < 2:
            continue
        mu = chunk[finite].mean()
        sd = chunk[finite].std()
        out[m] = (chunk - mu) / sd if sd > 0 else 0.0
    return out


def top1_accuracy(
    scores: ArrayLike,
    image_ids: ArrayLike,
    burst_ids: ArrayLike,
    best_by_burst: dict[int, set[int]],
    *,
    higher_is_better: bool = True,
) -> Optional[dict]:
    """Fraction of bursts where the highest-scoring frame is a human ``best``.

    Reported alongside the chance rate, because bursts here hold 3-8 frames and a
    raw accuracy number is meaningless without it.
    """
    s = np.asarray(scores, dtype=float)
    ids = np.asarray(image_ids)
    g = np.asarray(burst_ids)
    hits = 0
    total = 0
    chance = []
    for gid in np.unique(g):
        m = g == gid
        best_ids = best_by_burst.get(int(gid))
        if not best_ids:
            continue
        chunk, chunk_ids = s[m], ids[m]
        finite = np.isfinite(chunk)
        if finite.sum() < 2:
            continue
        chunk, chunk_ids = chunk[finite], chunk_ids[finite]
        pick = chunk_ids[int(np.argmax(chunk) if higher_is_better else np.argmin(chunk))]
        hits += int(int(pick) in best_ids)
        total += 1
        chance.append(len(best_ids & set(int(i) for i in chunk_ids)) / len(chunk_ids))
    if total == 0:
        return None
    return {
        "top1_accuracy": round(hits / total, 4),
        "chance_rate": round(float(np.mean(chance)), 4) if chance else None,
        "n_bursts": total,
    }


# ---------------------------------------------------------------------------
# Feature table
# ---------------------------------------------------------------------------
def build_feature_table(rows: Sequence[dict]) -> list[dict]:
    """Attach geometry features (and subject-resolution figures) to each row."""
    table: list[dict] = []
    for r in rows:
        box = parse_bbox(r.get("bird_bbox"))
        if box is None:
            continue
        rec = dict(geometry_features(box))
        rec["image_id"] = r["id"]
        rec["folder_id"] = r["folder_id"]
        rec["stack_id"] = r.get("stack_id")
        rec["score_general"] = _as_float(r.get("score_general"))
        rec["score_technical"] = _as_float(r.get("score_technical"))
        rec["score_aesthetic"] = _as_float(r.get("score_aesthetic"))
        rec["rating"] = _as_float(r.get("rating"))
        rec["pick_status"] = _as_float(r.get("pick_status"))
        for le in REPORT_LONG_EDGES:
            rec[f"subject_px_full{le}"] = subject_px_at_long_edge(box, le)
        table.append(rec)
    return table


def _as_float(v) -> float:
    try:
        return float(v) if v is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _percentiles(values: Sequence[float], ps=(10, 50, 90), *, digits: int = 4) -> dict:
    arr = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return {f"p{p}": None for p in ps}
    return {f"p{p}": round(float(np.percentile(arr, p)), digits) for p in ps}


# ---------------------------------------------------------------------------
# Part 1 — bias probe (no ground truth)
# ---------------------------------------------------------------------------
def bias_probe(table: Sequence[dict], not_detected_scores: Sequence[float]) -> dict:
    """Measure how the existing fused score responds to subject geometry."""
    scores = [r[SCORE_COL] for r in table]

    correlations = {
        f: {
            "spearman_vs_score_general": spearman([r[f] for r in table], scores),
            "spearman_vs_rating": spearman([r[f] for r in table], [r["rating"] for r in table]),
        }
        for f in FEATURES
    }

    # Score by subject-size decile: the clearest way to see a size bias.
    area = np.asarray([r["area_frac"] for r in table], dtype=float)
    sc = np.asarray(scores, dtype=float)
    finite = np.isfinite(area) & np.isfinite(sc)
    by_decile = []
    if finite.sum() >= 100:
        edges = np.percentile(area[finite], np.arange(0, 101, 10))
        for i in range(10):
            lo, hi = edges[i], edges[i + 1]
            m = finite & (area >= lo) & (area <= hi if i == 9 else area < hi)
            if m.sum() == 0:
                continue
            by_decile.append(
                {
                    "decile": i + 1,
                    "area_frac_range": [round(float(lo), 4), round(float(hi), 4)],
                    "n": int(m.sum()),
                    "mean_score_general": round(float(sc[m].mean()), 4),
                    "mean_subject_px_at_224": round(
                        float(np.mean([r["subject_px_full224"] for r, keep in zip(table, m) if keep])), 1
                    ),
                }
            )

    edge = np.asarray([r["edges_touched"] > 0 for r in table], dtype=bool)
    edge_effect = {
        "n_touching_frame_edge": int(edge.sum()),
        "pct_touching_frame_edge": round(100.0 * float(edge.mean()), 2) if edge.size else None,
        "mean_score_touching": _safe_mean(sc[np.isfinite(sc) & edge]),
        "mean_score_not_touching": _safe_mean(sc[np.isfinite(sc) & ~edge]),
    }

    nd = np.asarray([v for v in not_detected_scores if np.isfinite(v)], dtype=float)
    detected_vs_not = {
        "n_detected": int(finite.sum()),
        "n_not_detected": int(nd.size),
        "mean_score_detected": _safe_mean(sc[np.isfinite(sc)]),
        "mean_score_not_detected": _safe_mean(nd),
        "note": (
            "Compares images where the detector found a bird against the "
            "{'detected': false} sentinel population. Both score columns are "
            "pipeline-derived, so this is a property of the incumbent stack, not "
            "evidence about human preference."
        ),
    }

    return {
        "n": len(table),
        "feature_correlations": correlations,
        "score_by_subject_size_decile": by_decile,
        "frame_edge_effect": edge_effect,
        "detected_vs_not_detected": detected_vs_not,
        "subject_resolution": {
            # Pixel counts, so one decimal is plenty.
            f"full_frame_resize_to_{le}": _percentiles(
                [r[f"subject_px_full{le}"] for r in table], digits=1
            )
            for le in REPORT_LONG_EDGES
        },
        "area_frac": _percentiles([r["area_frac"] for r in table]),
        "ground_truth": "none — derived columns only; no accuracy claim",
    }


def _safe_mean(arr) -> Optional[float]:
    a = np.asarray(arr, dtype=float)
    a = a[np.isfinite(a)]
    return round(float(a.mean()), 4) if a.size else None


# ---------------------------------------------------------------------------
# Part 2 — predictive value against human labels
# ---------------------------------------------------------------------------
def label_eval(table: Sequence[dict], label_rows: list[labels.LabelRow]) -> dict:
    """Do geometry features predict the human verdict within a burst?"""
    by_id = {r["image_id"]: r for r in table}
    burst_of = {lr.image_id: lr.burst_id for lr in label_rows}
    verdict_of = {lr.image_id: lr.verdict for lr in label_rows}
    best_by_burst = labels.best_ids(label_rows)

    matched = [lr for lr in label_rows if lr.image_id in by_id]
    missing = len(label_rows) - len(matched)
    if missing:
        logger.warning(
            "%d labelled image(s) have no usable box in the current data; excluded.", missing
        )
    if len(matched) < 20:
        return {
            "status": "insufficient",
            "n_matched": len(matched),
            "note": "Fewer than 20 labelled images matched a boxed row.",
        }

    ids = [lr.image_id for lr in matched]
    groups = [burst_of[i] for i in ids]
    is_best = [verdict_of[i] == "best" for i in ids]
    is_reject = [verdict_of[i] == "reject" for i in ids]
    ranks = [labels.VERDICT_RANK[verdict_of[i]] for i in ids]

    per_feature = {}
    for f in list(FEATURES) + [SCORE_COL, "score_technical"]:
        raw = [by_id[i].get(f, float("nan")) for i in ids]
        within = zscore_within_group(raw, groups)
        per_feature[f] = {
            # Within-burst standardised, so between-burst variation cannot leak in.
            "spearman_vs_verdict_rank_within_burst": spearman(within, ranks),
            "roc_auc_best_vs_rest": roc_auc(within, is_best),
            "roc_auc_reject_vs_rest": roc_auc([-v for v in within], is_reject),
            "top1_pick_best": top1_accuracy(within, ids, groups, best_by_burst),
        }

    combined = _combined_model(by_id, ids, groups, is_best)
    provenance = labels.ground_truth_provenance()

    return {
        "status": "ok",
        "n_matched": len(matched),
        "n_bursts": len(set(groups)),
        "verdict_counts": {
            v: sum(1 for i in ids if verdict_of[i] == v) for v in labels.VERDICTS
        },
        "per_feature": per_feature,
        "combined_model": combined,
        "ground_truth": provenance["description"],
        "ground_truth_kind": provenance["kind"],
        "ground_truth_sidecar": provenance["sidecar"],
    }


def _combined_model(
    by_id: dict[int, dict],
    ids: Sequence[int],
    groups: Sequence[int],
    is_best: Sequence[bool],
) -> dict:
    """Leave-one-burst-out logistic model: geometry alone, score alone, and both.

    Leave-one-*burst*-out rather than plain k-fold: frames from one burst are
    near-duplicates, so splitting inside a burst would leak the answer across the
    fold boundary and inflate every number.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    g = np.asarray(groups)
    y = np.asarray(is_best, dtype=int)

    variants = {
        "geometry_only": list(FEATURES),
        "score_only": [SCORE_COL],
        "geometry_plus_score": list(FEATURES) + [SCORE_COL],
    }

    # Z-score each feature once, then assemble design matrices from the columns.
    all_feats = sorted({f for feats in variants.values() for f in feats})
    columns = {
        f: zscore_within_group([by_id[i].get(f, np.nan) for i in ids], groups)
        for f in all_feats
    }

    out: dict = {}
    for name, feats in variants.items():
        X = np.column_stack([columns[f] for f in feats])
        ok = np.all(np.isfinite(X), axis=1)
        if ok.sum() < 20 or len(np.unique(y[ok])) < 2:
            out[name] = {"roc_auc_loo_burst": None, "n": int(ok.sum())}
            continue

        Xo, yo, go = X[ok], y[ok], g[ok]
        preds = np.full(yo.shape, np.nan, dtype=float)
        for gid in np.unique(go):
            test = go == gid
            train = ~test
            if len(np.unique(yo[train])) < 2:
                continue
            scaler = StandardScaler().fit(Xo[train])
            clf = LogisticRegression(max_iter=1000, C=0.5).fit(scaler.transform(Xo[train]), yo[train])
            preds[test] = clf.predict_proba(scaler.transform(Xo[test]))[:, 1]

        out[name] = {
            "roc_auc_loo_burst": roc_auc(preds, yo.astype(bool)),
            "n": int(ok.sum()),
            "n_features": len(feats),
        }

    base = (out.get("score_only") or {}).get("roc_auc_loo_burst")
    both = (out.get("geometry_plus_score") or {}).get("roc_auc_loo_burst")
    out["delta_auc_from_adding_geometry"] = (
        round(both - base, 4) if base is not None and both is not None else None
    )
    out["decision_gate"] = (
        "Plan gate: geometry earns first-class exposure if it adds >= 0.03 ROC-AUC "
        "over score-alone."
    )
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_markdown(payload: dict) -> str:
    bias = payload["bias_probe"]
    folders = payload["folders"]
    scope = "" if folders == "all" else f" (folders {folders})"
    lines = [
        "# Bird bbox geometry — zero-inference study",
        "",
        f"Corpus: **{bias['n']}** production images with a real bird box{scope}.",
        "",
        "## Subject resolution — the premise of the whole study",
        "",
        "Bird long side, in pixels, after the **whole frame** is resized to a model input:",
        "",
        "| Full-frame resize | p10 | p50 | p90 |",
        "|---|---|---|---|",
    ]
    for le in REPORT_LONG_EDGES:
        s = bias["subject_resolution"][f"full_frame_resize_to_{le}"]
        lines.append(f"| {le} px | {s['p10']} | {s['p50']} | {s['p90']} |")

    af = bias["area_frac"]
    lines += [
        "",
        f"`area_frac` p10/p50/p90: **{af['p10']} / {af['p50']} / {af['p90']}**.",
        "",
        "## Bias probe — does the existing score track subject geometry?",
        "",
        "> Ground truth: **none**. `score_general` and `rating` are produced by the "
        "scoring pipeline itself, so this section describes the incumbent stack's "
        "behaviour and makes no accuracy claim.",
        "",
        "| Feature | Spearman vs score_general | Spearman vs rating |",
        "|---|---|---|",
    ]
    for f, v in bias["feature_correlations"].items():
        lines.append(
            f"| `{f}` | {v['spearman_vs_score_general']} | {v['spearman_vs_rating']} |"
        )

    if bias["score_by_subject_size_decile"]:
        lines += [
            "",
            "### Mean score by subject-size decile",
            "",
            "| Decile | area_frac range | n | mean score_general | mean bird px @224 |",
            "|---|---|---|---|---|",
        ]
        for d in bias["score_by_subject_size_decile"]:
            lines.append(
                f"| {d['decile']} | {d['area_frac_range'][0]}–{d['area_frac_range'][1]} | "
                f"{d['n']} | {d['mean_score_general']} | {d['mean_subject_px_at_224']} |"
            )

    e = bias["frame_edge_effect"]
    d = bias["detected_vs_not_detected"]
    lines += [
        "",
        "### Frame-edge contact and detection",
        "",
        f"- Boxes touching a frame edge (bird clipped): **{e['n_touching_frame_edge']}** "
        f"({e['pct_touching_frame_edge']}%). Mean score touching "
        f"**{e['mean_score_touching']}** vs not touching **{e['mean_score_not_touching']}**.",
        f"- Detected **{d['n_detected']}** (mean score {d['mean_score_detected']}) vs "
        f"not-detected **{d['n_not_detected']}** (mean score {d['mean_score_not_detected']}).",
        "",
        "## Predictive value against within-burst labels",
        "",
    ]

    le_ = payload.get("label_eval") or {}
    if le_.get("status") != "ok":
        lines += [
            "> **Not yet available.** "
            f"({le_.get('note', 'no label set')})",
            "",
            "Build and fill the label set, then re-run:",
            "",
            "```bash",
            "python -m scripts.research.bird_crop.build_label_set",
            "# fill in the verdict column, then",
            "python -m scripts.research.bird_crop.geometry_eval",
            "```",
        ]
    else:
        lines += [
            f"Ground truth: **{le_['ground_truth']}** — {le_['n_matched']} images "
            f"across {le_['n_bursts']} bursts. Verdicts: {le_['verdict_counts']}.",
            "",
            "All features are standardised **within burst**, so only "
            "\"which frame in this burst is better\" is being measured.",
            "",
            "| Feature | Spearman vs verdict | AUC best-vs-rest | AUC reject-vs-rest | top-1 picks best |",
            "|---|---|---|---|---|",
        ]
        for f, v in le_["per_feature"].items():
            t = v["top1_pick_best"] or {}
            top1 = (
                f"{t.get('top1_accuracy')} (chance {t.get('chance_rate')})"
                if t else "—"
            )
            lines.append(
                f"| `{f}` | {v['spearman_vs_verdict_rank_within_burst']} | "
                f"{v['roc_auc_best_vs_rest']} | {v['roc_auc_reject_vs_rest']} | {top1} |"
            )
        cm = le_["combined_model"]
        lines += [
            "",
            "### Combined model (leave-one-burst-out)",
            "",
            "| Model | ROC-AUC | n |",
            "|---|---|---|",
        ]
        for name in ("geometry_only", "score_only", "geometry_plus_score"):
            v = cm.get(name) or {}
            lines.append(f"| {name} | {v.get('roc_auc_loo_burst')} | {v.get('n')} |")
        lines += [
            "",
            f"**Delta from adding geometry: {cm.get('delta_auc_from_adding_geometry')}** — "
            f"{cm.get('decision_gate')}",
        ]

    lines += [
        "",
        "---",
        "",
        "Generated by `scripts.research.bird_crop.geometry_eval`. "
        "Production was read read-only; nothing was written to it.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folders", default="", help="Comma-separated folder_id list (default: whole library)")
    parser.add_argument("--limit", type=int, default=0, help="Cap rows for a quick pass (0 = all)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    prod.configure_logging(args.verbose)
    prod.assert_prod()

    folders = [int(x) for x in args.folders.split(",") if x.strip()] or None
    rows = bursts.load_boxed_rows(folders=folders, limit=args.limit)
    table = build_feature_table(rows)
    if not table:
        logger.error("No usable boxes; nothing to report.")
        return 1

    nd_scores = _load_not_detected_scores(folders)
    payload = {
        "folders": folders or "all",
        "bias_probe": bias_probe(table, nd_scores),
    }

    label_rows = labels.try_load()
    payload["label_eval"] = (
        label_eval(table, label_rows)
        if label_rows
        else {"status": "absent", "note": "no complete label set yet"}
    )

    prod.write_json("geometry.json", payload)
    prod.write_text("geometry.md", render_markdown(payload))
    return 0


def _load_not_detected_scores(folders: Optional[Sequence[int]]) -> list[float]:
    """Scores for images where the detector ran cleanly and found no bird.

    Excludes the ``{"detected": false, "error": ...}`` scan-failure sentinel: an
    unreadable file is evidence about the pipeline, not about bird presence, so
    including it would corrupt the comparison.
    """
    sql = (
        "SELECT i.score_general FROM images i "
        "WHERE i.bird_bbox IS NOT NULL "
        "  AND NOT jsonb_exists(i.bird_bbox, 'x1') "
        "  AND NOT jsonb_exists(i.bird_bbox, 'error')"
    )
    params: list = []
    if folders:
        sql += " AND i.folder_id = ANY(%s)"
        params.append(list(folders))
    return [_as_float(r["score_general"]) for r in prod.select(sql, params or None)]


if __name__ == "__main__":
    raise SystemExit(main())
