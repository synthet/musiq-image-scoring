#!/usr/bin/env python3
"""Generate SUMMARY.md and UNIFIED_INPUT_POLICY.md from input-size eval JSON.

    python -m scripts.research.clip_culling.report_input_size
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from scripts.research.clip_culling import common

logger = logging.getLogger("clip_culling.report_input_size")

BASELINE_LONG_EDGE = 512
BASELINE_SOURCE = "thumb"


def _best_ari(run: dict) -> str:
    bt = (run.get("grouping") or {}).get("best_threshold") or {}
    v = bt.get("mean_ari")
    return "" if v is None else f"{v:.4f}"


def _gap(run: dict) -> str:
    v = (run.get("pick_review") or {}).get("keep_reject_gap")
    return "" if v is None else f"{v:.2f}"


def _margin(run: dict) -> str:
    v = (run.get("pair_margin") or {}).get("pair_margin")
    return "" if v is None else f"{v:.4f}"


def _best_run(runs: list[dict], key_fn, reverse: bool = True) -> dict | None:
    valid = [r for r in runs if key_fn(r) is not None]
    if not valid:
        return None
    return sorted(valid, key=key_fn, reverse=reverse)[0]


def build_summary_md(payload: dict) -> str:
    lines = [
        "# Pipeline input-size study — summary",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} — "
        "E2E corpus, NPZ caches under `reports/clip-culling/input-size/npz/`.",
        "",
        "Baseline for deltas: **long_edge=512**, **source=thumb**.",
        "",
    ]
    emb = payload.get("embedding") or {}
    runs = emb.get("runs") or []
    if runs:
        lines.append("## Embedding track — burst-GT grouping (best mean ARI)")
        lines.append("")
        lines.append("| model | source | long_edge | mean ARI | keep−rej gap | pair margin | Δ ARI vs 512 thumb |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in sorted(runs, key=lambda x: (-((x.get("grouping", {}).get("best_threshold") or {}).get("mean_ari") or -1),)):
            d = r.get("delta_vs_baseline_512_thumb") or {}
            lines.append(
                f"| {r['model']} | {r['source']} | {r['long_edge']} | {_best_ari(r)} | "
                f"{_gap(r)} | {_margin(r)} | {d.get('mean_ari', '')} |"
            )
        lines.append("")
        lines.append("### Top configs by mean ARI")
        lines.append("")
        for item in (emb.get("ranking_by_mean_ari") or [])[:10]:
            lines.append(
                f"- **{item['model']}** `{item['source']}` @ {item['long_edge']}px → ARI {item.get('mean_ari')}"
            )
        lines.append("")

    iqa = payload.get("iqa") or {}
    iqa_runs = iqa.get("runs") or []
    if iqa_runs:
        lines.append("## IQA track — mishot detection & rating correlation")
        lines.append("")
        lines.append("| model | source | long_edge | ROC-AUC | PR-AUC | |ρ| vs rating | burst std | ρ vs prod |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in sorted(iqa_runs, key=lambda x: -((x.get("mishot") or {}).get("roc_auc") or -1)):
            m = r.get("mishot") or {}
            c = r.get("rating_corr") or {}
            bs = r.get("burst_spread") or {}
            ps = r.get("production_stability") or {}
            sp = c.get("spearman")
            sp_s = "" if sp is None else f"{abs(sp):.4f}"
            lines.append(
                f"| {r['model']} | {r['source']} | {r['long_edge']} | "
                f"{m.get('roc_auc', '')} | {m.get('pr_auc', '')} | {sp_s} | "
                f"{bs.get('mean_within_burst_std', '')} | {ps.get('spearman_vs_production', '')} |"
            )
        lines.append("")

    tag = payload.get("tagging") or {}
    tag_runs = tag.get("runs") or []
    if tag_runs:
        lines.append("## Tagging track — keyword accuracy & diversity")
        lines.append("")
        lines.append("| model | source | long_edge | Jaccard vs B/32 | mean tags | tag entropy | within-burst Jaccard |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in sorted(
            tag_runs,
            key=lambda x: -((x.get("metrics") or {}).get("jaccard_vs_b32_baseline") or -1),
        ):
            m = r.get("metrics") or {}
            lines.append(
                f"| {r['model']} | {r['source']} | {r['long_edge']} | "
                f"{m.get('jaccard_vs_b32_baseline', '')} | {m.get('mean_tags_per_image', '')} | "
                f"{m.get('tag_entropy', '')} | {m.get('within_burst_tag_jaccard', '')} |"
            )
        lines.append("")

    cap = payload.get("caption") or {}
    cap_runs = cap.get("runs") or []
    if cap_runs:
        lines.append("## Caption track — BLIP diversity & keyword overlap")
        lines.append("")
        lines.append("| source | long_edge | burst uniqueness | keyword Jaccard | mean words |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in sorted(
            cap_runs,
            key=lambda x: -((x.get("metrics") or {}).get("burst_caption_uniqueness") or -1),
        ):
            m = r.get("metrics") or {}
            lines.append(
                f"| {r['source']} | {r['long_edge']} | "
                f"{m.get('burst_caption_uniqueness', '')} | {m.get('mean_keyword_token_jaccard', '')} | "
                f"{m.get('mean_caption_words', '')} |"
            )
        lines.append("")

    lines.append("## Interpretation (quick)")
    lines.append("")
    lines.append("1. **Flat ARI above 224** on ViT-L/14 / SigLIP2 → thumbnail >224 rarely helps unless preprocess size increases.")
    lines.append("2. **file > thumb** at same long_edge → raise `MAX_SIZE` in thumbnails or align backfill to thumbs.")
    lines.append("3. **MobileNet** only sees 224×224 after clustering resize — sweep affects upsampling quality, not native resolution.")
    lines.append("4. **Keywords flat above 224** → tagging benefits only from preprocess bump, not thumb alone.")
    lines.append("5. **BLIP peak at ~384** → verify caption diversity curve before raising global thumb size.")
    lines.append("")
    return "\n".join(lines)


def build_unified_policy_md(payload: dict) -> str:
    """Synthesize tiered pixel-budget recommendations from eval_summary.json."""
    emb_runs = (payload.get("embedding") or {}).get("runs") or []
    iqa_runs = (payload.get("iqa") or {}).get("runs") or []
    tag_runs = (payload.get("tagging") or {}).get("runs") or []
    cap_runs = (payload.get("caption") or {}).get("runs") or []

    best_emb = _best_run(
        emb_runs,
        lambda r: (r.get("grouping") or {}).get("best_threshold", {}).get("mean_ari"),
    )
    best_iqa = _best_run(
        iqa_runs,
        lambda r: (r.get("mishot") or {}).get("roc_auc"),
    )
    best_tag = _best_run(
        tag_runs,
        lambda r: (r.get("metrics") or {}).get("jaccard_vs_b32_baseline"),
    )
    best_cap = _best_run(
        cap_runs,
        lambda r: (r.get("metrics") or {}).get("burst_caption_uniqueness"),
    )

    # Baseline thumb@512 rows for file-vs-thumb comparison
    thumb512_emb = [
        r for r in emb_runs
        if r.get("source") == BASELINE_SOURCE and r.get("long_edge") == BASELINE_LONG_EDGE
    ]
    file512_emb = [
        r for r in emb_runs
        if r.get("source") == "file" and r.get("long_edge") == BASELINE_LONG_EDGE
    ]
    file_beats_thumb = False
    if thumb512_emb and file512_emb:
        t_ari = (thumb512_emb[0].get("grouping") or {}).get("best_threshold", {}).get("mean_ari")
        f_ari = (file512_emb[0].get("grouping") or {}).get("best_threshold", {}).get("mean_ari")
        if t_ari is not None and f_ari is not None and f_ari > t_ari + 0.01:
            file_beats_thumb = True

    has_data = bool(emb_runs or iqa_runs or tag_runs or cap_runs)
    tier_a = "512 (production default)"
    if file_beats_thumb:
        tier_a = "768 candidate — file beats thumb at 512 on burst ARI; validate before changing MAX_SIZE"
    elif best_emb and best_emb.get("long_edge", 512) > 512:
        tier_a = f"{best_emb['long_edge']} candidate from best embedding run ({best_emb.get('model')})"

    lines = [
        "# Unified input pixel policy (pipeline-wide)",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} from "
        "`eval_summary.json`. **Do not apply to production without Phase 6 sign-off.**",
        "",
    ]

    if not has_data:
        lines.extend([
            "## Status",
            "",
            "No eval runs present yet. Complete Phase 1–3 NPZ sweeps, then re-run:",
            "",
            "```bash",
            "python -m scripts.research.clip_culling.input_size_eval --all",
            "python -m scripts.research.clip_culling.report_input_size",
            "```",
            "",
            "See [INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](../../../docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md) for runbook.",
            "",
        ])
        return "\n".join(lines)

    lines.extend([
        "## Per-track best configurations",
        "",
        "| Track | Best config | Primary metric | Value |",
        "| --- | --- | --- | --- |",
    ])

    if best_emb:
        bt = (best_emb.get("grouping") or {}).get("best_threshold") or {}
        lines.append(
            f"| Culling embeddings | {best_emb['model']} `{best_emb['source']}` @ {best_emb['long_edge']}px "
            f"| burst mean ARI | {bt.get('mean_ari', 'n/a')} |"
        )
    if best_iqa:
        m = best_iqa.get("mishot") or {}
        lines.append(
            f"| IQA mishot | {best_iqa['model']} `{best_iqa['source']}` @ {best_iqa['long_edge']}px "
            f"| ROC-AUC | {m.get('roc_auc', 'n/a')} |"
        )
    if best_tag:
        tm = best_tag.get("metrics") or {}
        lines.append(
            f"| Keywords | {best_tag['model']} `{best_tag['source']}` @ {best_tag['long_edge']}px "
            f"| Jaccard vs B/32 | {tm.get('jaccard_vs_b32_baseline', 'n/a')} |"
        )
    if best_cap:
        cm = best_cap.get("metrics") or {}
        lines.append(
            f"| Captions (BLIP) | `{best_cap['source']}` @ {best_cap['long_edge']}px "
            f"| burst uniqueness | {cm.get('burst_caption_uniqueness', 'n/a')} |"
        )
    lines.append("")

    lines.extend([
        "## Recommended tiered policy (draft)",
        "",
        "### Tier A — Shared thumbnail (`modules/thumbnails.py` MAX_SIZE)",
        "",
        f"**{tier_a}**",
        "",
        "### Tier B — Culling embedder load cap (`CullingEmbedder.max_load_px`)",
        "",
        "Align with Tier A when using file_path; current default **1024**.",
        "",
        "### Tier C — RAW/scoring square JPEG (`raw_conversion.max_resolution`)",
        "",
    ])

    musiq_runs = [r for r in iqa_runs if r.get("model") in ("spaq", "ava")]
    best_musiq = _best_run(
        musiq_runs,
        lambda r: abs((r.get("rating_corr") or {}).get("spearman") or 0),
    )
    if best_musiq:
        lines.append(
            f"MUSIQ best Spearman @ **{best_musiq['long_edge']}px** ({best_musiq['model']}). "
            "Likely range **512–768** until full grid completes."
        )
    else:
        lines.append("Default **512** until SPAQ/AVA sweep completes.")
    lines.append("")

    lines.extend([
        "### Tier D — Per-model max_dimension (only if Tier C insufficient)",
        "",
        "| Model | Config key | Native cap |",
        "| --- | --- | --- |",
        "| LIQE | `scoring.liqe_max_dimension` | 518 |",
        "| TOPIQ | `scoring.topiq_max_dimension` | 1024 |",
        "| ARNIQA | `scoring.arniqa.max_dimension` | 1024 |",
        "",
        "### Tier E — ViT preprocess override (Phase 5, conditional)",
        "",
        "Only if OpenCLIP/OpenAI/SigLIP2 ARI flat above 224 at Tier A long edge. "
        "Run `--preprocess-size 336` sweep; separate NPZ namespace.",
        "",
        "## Diversity checklist",
        "",
        "Before adopting a higher global pixel budget, confirm:",
        "",
        "- Burst ARI does not regress vs baseline 512 thumb",
        "- Tag entropy does not collapse (keyword track)",
        "- BLIP burst caption uniqueness stable or improves",
        "- IQA mishot ROC-AUC stable or improves",
        "",
        "## Decision rules (extended)",
        "",
        "1. **file > thumb** at same long_edge → fix thumbnail generation before per-model tuning.",
        "2. **ViT-224 flat above 224** → thumb increases wasted unless preprocess bump (Tier E).",
        "3. **MUSIQ flat above 512** → keep `raw_conversion.max_resolution=512`.",
        "4. **Keywords flat above 224** → tagging needs preprocess bump, not thumb alone.",
        "5. **BLIP peaks at 384** → processor downscales; verify caption curve before global thumb raise.",
        "6. **Conflicting optima** → weight culling + mishot over keyword entropy unless Jaccard drops >5%.",
        "",
        "## Production follow-ups (gated)",
        "",
        "- [ ] `modules/thumbnails.py` MAX_SIZE",
        "- [ ] `modules/embedding_extractors.py` max_load_px",
        "- [ ] `config.json` raw_conversion / scoring.*_max_dimension",
        "- [ ] [MODEL_INPUT_SPECIFICATIONS.md](../../docs/technical/MODEL_INPUT_SPECIFICATIONS.md)",
        "",
        "## Related",
        "",
        "- [SUMMARY.md](SUMMARY.md) — full metric tables",
        "- [INPUT_SIZE_CULLING_2026-05-29.md](../../../docs/reports/INPUT_SIZE_CULLING_2026-05-29.md) — runbook",
        "- [INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](../../../docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md) — status memo",
        "",
    ])
    return "\n".join(lines)


def main():
    path = common.INPUT_SIZE_DIR / "eval_summary.json"
    if not path.exists():
        logger.warning("Missing %s — writing placeholder policy from empty payload", path)
        payload = {}
    else:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

    summary_md = build_summary_md(payload)
    policy_md = build_unified_policy_md(payload)

    summary_path = common.INPUT_SIZE_DIR / "SUMMARY.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    logger.info("Wrote %s", summary_path)

    policy_path = common.INPUT_SIZE_DIR / "UNIFIED_INPUT_POLICY.md"
    policy_path.write_text(policy_md, encoding="utf-8")
    logger.info("Wrote %s", policy_path)

    wiki_policy = common.PROJECT_ROOT / "docs" / "reports" / "UNIFIED_INPUT_POLICY_2026-05-31.md"
    wiki_policy.write_text(policy_md, encoding="utf-8")
    logger.info("Wrote wiki mirror %s", wiki_policy)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
