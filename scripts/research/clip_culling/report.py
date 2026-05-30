#!/usr/bin/env python3
"""Consolidate per-experiment JSON into one Markdown + HTML summary report.

    python -m scripts.research.clip_culling.report

Reads ``reports/clip-culling/*.json`` and writes ``SUMMARY.md`` / ``SUMMARY.html``
with distribution tables, correlation/AUC tables, and per-use-case recommendations.
"""

from __future__ import annotations

import datetime as _dt
import html
import logging

from scripts.research.clip_culling import common

logger = logging.getLogger("clip_culling.report")


def _g(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p, default)
    return d


def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(out)


def build() -> str:
    seed = common.read_json("phase0_seed_stats.json") or {}
    manifest = common.read_json("checkpoints_manifest.json") or {}
    embed = common.read_json("embed_persist_stats.json") or []
    e1 = common.read_json("exp1_signal.json") or {}
    e2 = common.read_json("exp2_mishot.json") or {}
    e3 = common.read_json("exp3_diversity.json") or {}
    e4 = common.read_json("exp4_birds.json") or {}
    e5 = common.read_json("exp5_substack.json") or {}
    e6 = common.read_json("exp6_colorlabel.json") or {}
    e7 = common.read_json("exp7_keywords.json") or {}
    e8 = common.read_json("exp8_grouping.json") or {}

    L = []
    L.append("# Culling embedding spike — summary report (CLIP L/14 + DINOv2 + SigLIP2)")
    L.append("")
    L.append(f"_Generated {_dt.datetime.now().isoformat(timespec='seconds')} — "
             f"E2E DB `image_scoring_test` (read/write), prod `image_scoring` (read-only seed)._")
    L.append("")
    L.append("Offline research harness: seeds a representative bird/stack/label subset into the "
             "E2E Postgres DB, registers OpenAI + OpenCLIP ViT-L/14 (768-d) embedding spaces, and "
             "evaluates score signal novelty, mishot rejection, diverse stack picks, bird-pose "
             "selection, scene sub-stacking, CLIP color labels, keyword accuracy, and "
             "grouping quality (EXIF-burst GT). See `REFERENCES.md` for model/paper sources.")
    L.append("")

    # --- corpus / setup ---
    L.append("## Corpus & setup")
    st = seed.get("stats", {})
    L.append(_md_table(
        ["metric", "value"],
        [["seed folders", seed.get("folders")],
         ["images", st.get("images")],
         ["stacks", st.get("stacks")],
         ["image_keywords", st.get("image_keywords")],
         ["image_model_scores", st.get("image_model_scores")],
         ["baseline embeddings copied", st.get("embeddings")]],
    ))
    L.append("")
    if embed:
        L.append("**L/14 embedding persist (E2E):**")
        L.append(_md_table(
            ["space", "embedded", "ms/img", "peak VRAM MB"],
            [[e.get("space"), e.get("embedded"),
              _g(e, "telemetry", "ms_per_image"), _g(e, "telemetry", "peak_vram_mb")] for e in embed],
        ))
        L.append("")
    if manifest:
        ah = manifest.get("aesthetic_head", {})
        L.append(f"Aesthetic head: `{ah.get('sha256', '')[:16]}` ({ah.get('size')} bytes). "
                 f"Towers: OpenAI `ViT-L-14-quickgelu/openai`, OpenCLIP `ViT-L-14/laion2b_s32b_b82k`.")
        L.append("")

    # --- Exp 1 ---
    L.append("## Exp 1 — Score signal quality / novelty")
    if e1:
        def _r(v):
            return round(v, 4) if isinstance(v, (int, float)) else v
        rows = []
        for s, dist in (e1.get("distributions") or {}).items():
            nov = _g(e1, "novelty", s) or {}
            note = "✅" if nov.get("is_new_signal") else ""
            if s.endswith("_openclip"):
                note = "(diag.)"
            rows.append([s, _r(dist.get("p02")), _r(dist.get("p50")), _r(dist.get("p98")),
                         nov.get("max_abs_spearman_vs_existing"),
                         nov.get("abs_spearman_vs_rating"), note])
        L.append(_md_table(
            ["signal", "p02", "p50", "p98", "max|ρ| vs existing", "|ρ| vs rating", "new?"], rows))
        agr = e1.get("openai_vs_openclip_aesthetic_agreement")
        if agr:
            L.append("")
            L.append(f"OpenAI vs OpenCLIP aesthetic-head agreement (diagnostic): "
                     f"Spearman {agr.get('spearman')}, Pearson {agr.get('pearson')} (n={agr.get('n')}).")
    L.append("")

    # --- Exp 2 ---
    L.append("## Exp 2 — Mishot rejection")
    if e2:
        L.append(f"Ground-truth rejects: {e2.get('n_reject')} / {e2.get('n_total')} "
                 f"(cull=reject OR label=Red OR rating≤2).")
        rows = [[k, v.get("roc_auc"), v.get("pr_auc"), v.get("n")]
                for k, v in (e2.get("metrics") or {}).items()]
        L.append(_md_table(["detector", "ROC-AUC", "PR-AUC", "n"], rows))
    L.append("")

    # --- Exp 3 ---
    L.append("## Exp 3 — Diverse high-scored stack picks (MMR vs single-best)")
    if e3:
        L.append(_md_table(
            ["metric", "top-k by quality", "MMR (L/14)"],
            [["mean intra-selection diversity", e3.get("mean_diversity_topk"), e3.get("mean_diversity_mmr")],
             ["mean retained quality (aesthetic)", e3.get("mean_quality_topk"), e3.get("mean_quality_mmr")]]))
        L.append("")
        L.append(f"Diversity gain from MMR: **{e3.get('diversity_gain_pct')}%** over "
                 f"{e3.get('n_stacks')} stacks (k={e3.get('k')}).")
    L.append("")

    # --- Exp 4 ---
    L.append("## Exp 4 — Distinctive bird poses (BioCLIP vs CLIP L/14)")
    if e4:
        L.append(f"Species stacks evaluated: {e4.get('n_species_stacks')} (k={e4.get('k')}). "
                 f"Mean selection overlap L/14 vs BioCLIP: "
                 f"**{e4.get('mean_selection_overlap_l14_vs_bioclip')}**.")
    L.append("")

    # --- Exp 5 ---
    L.append("## Exp 5 — Scene-based sub-stacking (semantic vs visual)")
    if e5:
        L.append(_md_table(
            ["metric", "semantic (CLIP L/14)", "visual (MobileNet)"],
            [["mean silhouette", e5.get("mean_silhouette_semantic"), e5.get("mean_silhouette_visual")]]))
        L.append("")
        L.append(f"Stacks evaluated: {e5.get('n_stacks')} (≥8 members); selected cosine "
                 f"threshold {e5.get('selected_threshold')} (swept "
                 f"{', '.join(sorted((e5.get('threshold_sweep') or {}).keys()))}).")
    L.append("")

    # --- Exp 6 ---
    L.append("## Exp 6 — CLIP-query color labels")
    if e6:
        L.append(f"Evaluated {e6.get('n_evaluated')} labeled images; overall agreement with human "
                 f"labels: **{e6.get('overall_agreement')}**.")
        pl = e6.get("per_label") or {}
        rows = [[lab, v.get("precision"), v.get("recall"), v.get("support")] for lab, v in pl.items()]
        if rows:
            L.append("")
            L.append(_md_table(["label", "precision", "recall", "support"], rows))
        L.append("")
        L.append(f"_{e6.get('note', '')}_")
    L.append("")

    # --- Exp 7 ---
    L.append("## Exp 7 — Keyword accuracy")
    if e7:
        jac = e7.get("jaccard_vs_b32_baseline") or {}
        L.append(_md_table(
            ["model", "Jaccard vs B/32 baseline"],
            [[m, v] for m, v in jac.items()]))
        L.append("")
        L.append(f"OpenAI vs OpenCLIP L/14 keyword Jaccard: **{e7.get('jaccard_openai_vs_openclip')}**. "
                 f"SigLIP2 vs OpenAI L/14: **{e7.get('jaccard_siglip2_vs_openai_l14')}**. "
                 f"Human-truth F1: {e7.get('f1_vs_human')} (n_user_truth={e7.get('n_human_truth')}). "
                 f"{e7.get('note', '')}")
        spot = e7.get("spot_check") or []
        if spot:
            L.append("")
            L.append("Spot-check (file → B/32 | OpenAI L/14 | OpenCLIP L/14):")
            for s in spot[:6]:
                L.append(f"- `{s.get('file')}`: {s.get('b32_baseline')} | "
                         f"{s.get('openai_l14')} | {s.get('openclip_l14')}")
    L.append("")

    # --- Exp 8 ---
    L.append("## Exp 8 — Grouping quality (EXIF-burst ground truth)")
    if e8:
        L.append(f"Burst gap: **{e8.get('gap_seconds')}s**; thresholds swept: "
                 f"{e8.get('thresholds')}.")
        L.append("")
        rank = e8.get("ranking_by_burst_ari") or []
        if rank:
            L.append(_md_table(
                ["space", "mean ARI (burst GT)", "best threshold"],
                [[r.get("space"), r.get("mean_ari"), r.get("best_threshold")] for r in rank],
            ))
        L.append("")
        for code, info in (e8.get("spaces") or {}).items():
            bt = info.get("best_threshold") or {}
            if not bt:
                continue
            L.append(f"**{code}** @ thr {bt.get('threshold')}: ARI={bt.get('mean_ari')}, "
                     f"AMI={bt.get('mean_ami')}, false-merge={bt.get('mean_false_merge_rate')}, "
                     f"false-split={bt.get('mean_false_split_rate')}, silhouette={bt.get('mean_silhouette')}; "
                     f"stack-id ARI (biased)={info.get('mean_ari_vs_existing_stacks_bias_flagged')}.")
        L.append("")
        L.append(f"_{(e8.get('spaces') or {}).get('mobilenet_v2_imagenet_gap', {}).get('note', '')}_")
    L.append("")

    # --- Recommendations ---
    L.append("## Recommendations (per use case × tower × head)")
    L.append(_recommendations(e1, e2, e3, e4, e5, e6, e7, e8))
    L.append("")
    L.append("> Tower-mismatch caveat: the LAION aesthetic head is valid on **OpenAI** CLIP "
             "embeddings; `aes_openclip` numbers are diagnostic only.")

    md = "\n".join(L)
    common.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (common.RESULTS_DIR / "SUMMARY.md").write_text(md, encoding="utf-8")
    _write_html(md)
    logger.info("Wrote SUMMARY.md and SUMMARY.html to %s", common.RESULTS_DIR)
    return md


def _recommendations(e1, e2, e3, e4, e5, e6, e7, e8=None) -> str:
    recs = []

    # signal novelty — only OpenAI-tower signals are promotable; *_openclip aesthetic
    # is a tower-mismatch diagnostic (LAION head invalid on OpenCLIP embeddings),
    # so any "novelty" there is an artifact, not a usable signal.
    new_signals = [s for s, n in (_g(e1, "novelty") or {}).items()
                   if n.get("is_new_signal") and not s.endswith("_openclip")]
    if new_signals:
        recs.append(["Score signal", "OpenAI L/14 + aesthetic/CLIP-IQA",
                     f"PROMOTE-candidate: new signal(s) {new_signals} (low corr vs existing, "
                     f"non-trivial corr vs human rating)."])
    else:
        recs.append(["Score signal", "OpenAI L/14 + aesthetic/CLIP-IQA",
                     "WATCH: signals largely track existing scores (aesthetic/exposure ρ≈0.5) "
                     "and correlate only weakly with human rating; no clearly novel keeper signal. "
                     "(`aes_openclip` low-corr is a tower-mismatch artifact, not a real signal.)"])

    # mishot
    metrics = (e2 or {}).get("metrics") or {}
    best = max(((k, v.get("roc_auc")) for k, v in metrics.items() if not k.startswith("baseline") and v.get("roc_auc")),
               key=lambda kv: kv[1], default=(None, None))
    base = max(((k, v.get("roc_auc")) for k, v in metrics.items() if k.startswith("baseline") and v.get("roc_auc")),
               key=lambda kv: kv[1], default=(None, None))
    if best[1]:
        verdict = "PROMOTE" if (base[1] is None or best[1] >= base[1]) else "DROP/keep ARNIQA"
        recs.append(["Mishot rejection", best[0],
                     f"{verdict}: best CLIP detector ROC-AUC {best[1]} vs baseline {base[0]}={base[1]}."])

    # diversity
    gain = (e3 or {}).get("diversity_gain_pct")
    if gain is not None:
        verdict = "PROMOTE" if gain > 10 else "WATCH"
        recs.append(["Diverse stack picks", "OpenAI L/14 + MMR",
                     f"{verdict}: MMR adds {gain}% intra-selection diversity vs top-k-by-quality."])

    # birds
    ov = (e4 or {}).get("mean_selection_overlap_l14_vs_bioclip")
    if ov is not None:
        recs.append(["Bird poses", "BioCLIP vs CLIP L/14",
                     f"INFO: selection overlap {ov}; "
                     f"{'towers agree' if ov > 0.6 else 'towers pick different poses (complementary)'}."])

    # substack
    ssem = (e5 or {}).get("mean_silhouette_semantic")
    svis = (e5 or {}).get("mean_silhouette_visual")
    if ssem is not None and svis is not None:
        sel = str((e5 or {}).get("selected_threshold"))
        sw = ((e5 or {}).get("threshold_sweep") or {}).get(sel, {})
        n_sem = sw.get("n_stacks_split_semantic")
        n_vis = sw.get("n_stacks_split_visual")
        recs.append(["Scene sub-stacking", "CLIP L/14 vs MobileNet",
                     f"WATCH: at thr {sel}, semantic splits few stacks ({n_sem}) but cleanly "
                     f"(silhouette {ssem}); visual splits many ({n_vis}) at {svis}. CLIP semantic "
                     f"is conservative (groups near-identical scenes) — useful for scene-level "
                     f"sub-stacks, not frame-level dedup."])

    # color labels
    agr = (e6 or {}).get("overall_agreement")
    if agr is not None:
        verdict = "PROMOTE" if agr > 0.6 else ("WATCH" if agr > 0.4 else "DROP/refine rubric")
        recs.append(["Color labels", "OpenAI L/14 + rubric",
                     f"{verdict}: {agr} agreement with human labels (rubric heuristic, label-skewed)."])

    # keywords
    jac = (e7 or {}).get("jaccard_vs_b32_baseline") or {}
    if jac:
        sig_j = jac.get("siglip2")
        recs.append(["Keyword accuracy", "SigLIP2 / CLIP L/14 / B/32",
                     f"INFO: Jaccard vs B/32 baseline {jac}; SigLIP2={sig_j}. "
                     f"SigLIP2 uses per-tag sigmoid (roadmap method)."])

    # grouping
    rank = (e8 or {}).get("ranking_by_burst_ari") or []
    if rank:
        top = rank[0]
        mobilenet = next((r for r in rank if r.get("space") == "mobilenet_v2_imagenet_gap"), None)
        dino = next((r for r in rank if r.get("space") == "dinov2_reg_base_image"), None)
        top_ari = top.get("mean_ari")
        mob_ari = mobilenet.get("mean_ari") if mobilenet else None
        if top.get("space") == "dinov2_reg_base_image" and mob_ari is not None and top_ari is not None:
            if top_ari >= mob_ari:
                verdict = "ADOPT-candidate: DINOv2 beats MobileNet on burst-GT ARI"
            else:
                verdict = "VALIDATE: DINOv2 below MobileNet on burst-GT ARI"
        else:
            verdict = f"INFO: best space {top.get('space')} ARI={top_ari}"
        recs.append(["Grouping (stacks)", top.get("space"),
                     f"{verdict}; ranking head: {rank[:3]}. "
                     f"DINOv2 ARI={dino.get('mean_ari') if dino else None} @ thr {dino.get('best_threshold') if dino else None}."])

    return _md_table(["use case", "tower × head", "verdict"], recs)


def _write_html(md: str):
    # minimal markdown -> HTML (headings, tables, lists, inline code)
    lines = md.splitlines()
    out = ["<!doctype html><meta charset='utf-8'><title>CLIP L/14 spike</title>",
           "<style>body{font-family:system-ui,Segoe UI,Arial;max-width:1000px;margin:2rem auto;"
           "padding:0 1rem;line-height:1.5}table{border-collapse:collapse;margin:1rem 0}"
           "th,td{border:1px solid #ccc;padding:4px 8px;font-size:14px}th{background:#f4f4f4}"
           "code{background:#f0f0f0;padding:1px 4px;border-radius:3px}h2{border-bottom:1px solid #eee;"
           "padding-top:.5rem}blockquote{color:#555;border-left:3px solid #ccc;padding-left:1rem}</style>"]
    in_table = False

    def esc(s):
        s = html.escape(s)
        import re
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)

    for ln in lines:
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            out.append("<tr>" + "".join(f"<{tag}>{esc(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if ln.startswith("### "):
            out.append(f"<h3>{esc(ln[4:])}</h3>")
        elif ln.startswith("## "):
            out.append(f"<h2>{esc(ln[3:])}</h2>")
        elif ln.startswith("# "):
            out.append(f"<h1>{esc(ln[2:])}</h1>")
        elif ln.startswith("> "):
            out.append(f"<blockquote>{esc(ln[2:])}</blockquote>")
        elif ln.startswith("- "):
            out.append(f"<li>{esc(ln[2:])}</li>")
        elif ln.strip():
            out.append(f"<p>{esc(ln)}</p>")
    if in_table:
        out.append("</table>")
    (common.RESULTS_DIR / "SUMMARY.html").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    build()
