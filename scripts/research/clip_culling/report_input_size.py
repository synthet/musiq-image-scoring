#!/usr/bin/env python3
"""Generate SUMMARY.md from input-size eval JSON.

    python -m scripts.research.clip_culling.report_input_size
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from scripts.research.clip_culling import common

logger = logging.getLogger("clip_culling.report_input_size")


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


def build_summary_md(payload: dict) -> str:
    lines = [
        "# Input-size signal study — summary",
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
        lines.append("| model | source | long_edge | ROC-AUC | PR-AUC | |ρ| vs rating (Spearman) |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for r in sorted(iqa_runs, key=lambda x: -((x.get("mishot") or {}).get("roc_auc") or -1)):
            m = r.get("mishot") or {}
            c = r.get("rating_corr") or {}
            sp = c.get("spearman")
            sp_s = "" if sp is None else f"{abs(sp):.4f}"
            lines.append(
                f"| {r['model']} | {r['source']} | {r['long_edge']} | "
                f"{m.get('roc_auc', '')} | {m.get('pr_auc', '')} | {sp_s} |"
            )
        lines.append("")

    lines.append("## Interpretation (quick)")
    lines.append("")
    lines.append("1. **Flat ARI above 224** on ViT-L/14 / SigLIP2 → thumbnail >224 rarely helps unless preprocess size increases.")
    lines.append("2. **file > thumb** at same long_edge → raise `MAX_SIZE` in thumbnails or align backfill to thumbs.")
    lines.append("3. **MobileNet** only sees 224×224 after clustering resize — sweep affects upsampling quality, not native resolution.")
    lines.append("")
    return "\n".join(lines)


def main():
    path = common.INPUT_SIZE_DIR / "eval_summary.json"
    if not path.exists():
        logger.error("Missing %s — run input_size_eval first", path)
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    md = build_summary_md(payload)
    out = common.INPUT_SIZE_DIR / "SUMMARY.md"
    out.write_text(md, encoding="utf-8")
    logger.info("Wrote %s", out)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
