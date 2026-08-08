"""Flatten the study's result JSONs into tidy CSV/TSV for spreadsheets and plots.

The markdown reports are written to be *read*; these tables are written to be
*sorted, filtered and joined*. One row per measurement, every identifying column
spelled out, so a sheet can pivot without parsing nested JSON.

Missing phases are skipped with a warning rather than failing the whole export —
the study is run phase by phase, so a partial set of inputs is the normal case.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.bird_crop.export_results            # CSV
    python -m scripts.research.bird_crop.export_results --tsv      # TSV
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from scripts.research.bird_crop import prod

logger = logging.getLogger("bird_crop.export")

OUT_DIR = prod.REPORTS_DIR / "tables"


def _read(name: str) -> Optional[dict]:
    path = prod.REPORTS_DIR / name
    if not path.exists():
        logger.warning("skipping %s — not found (run that phase first)", name)
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("skipping %s — %s", name, exc)
        return None


def _write(name: str, fieldnames: list[str], rows: Iterable[dict], *, tsv: bool) -> Optional[Path]:
    rows = list(rows)
    if not rows:
        logger.warning("no rows for %s — skipped", name)
        return None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.{'tsv' if tsv else 'csv'}"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t" if tsv else ",")
        w.writeheader()
        w.writerows(rows)
    logger.info("Wrote %s (%d rows)", out, len(rows))
    return out


def _n(v: Any) -> Any:
    """Blank rather than the string 'None', so spreadsheets read it as empty."""
    return "" if v is None else v


# ---------------------------------------------------------------------------
# Phase 2b — degradation sensitivity
# ---------------------------------------------------------------------------
def export_degradation_verdict(payload: dict, *, tsv: bool):
    """The headline table: crop vs full-frame sensitivity, one row per model x kind."""
    cfg = payload.get("config") or {}
    rows = []
    for model, per_kind in (payload.get("verdict") or {}).items():
        if model.startswith("_"):
            continue
        for kind, v in per_kind.items():
            mono = v.get("monotonicity_check") or {}
            rows.append({
                "model": model,
                "degradation": kind,
                "subject_full_frame_drop": _n(v.get("subject_degraded_full_frame_drop")),
                "subject_crop_drop": _n(v.get("subject_degraded_crop_drop")),
                "crop_sensitivity_ratio": _n(v.get("crop_sensitivity_ratio")),
                "whole_frame_control_drop": _n(v.get("whole_frame_control_drop")),
                "spearman_subject_full": _n(mono.get("subject_full_spearman")),
                "spearman_subject_crop": _n(mono.get("subject_crop_spearman")),
                "spearman_whole_frame": _n(mono.get("whole_frame_spearman")),
                "n_images": _n(cfg.get("n_images_requested")),
                "long_edge": _n(cfg.get("long_edge")),
                "crop_variant": _n(cfg.get("crop_variant")),
                "image_ids_file": _n(cfg.get("image_ids_file")),
            })
    return _write(
        "degradation_sensitivity",
        ["model", "degradation", "subject_full_frame_drop", "subject_crop_drop",
         "crop_sensitivity_ratio", "whole_frame_control_drop", "spearman_subject_full",
         "spearman_subject_crop", "spearman_whole_frame", "n_images", "long_edge",
         "crop_variant", "image_ids_file"],
        rows, tsv=tsv,
    )


def export_degradation_cells(payload: dict, *, tsv: bool):
    """Every measured cell, so the aggregate above can be audited or re-derived."""
    rows = []
    for model, cells in (payload.get("by_model") or {}).items():
        if not isinstance(cells, dict) or "error" in cells:
            continue
        for key, agg in cells.items():
            kind, region, scored_on = (key.split("/") + ["", ""])[:3]
            rows.append({
                "model": model,
                "degradation": kind,
                "region_degraded": region,
                "scored_on": scored_on,
                "n_images": _n(agg.get("n_images")),
                "mean_spearman": _n(agg.get("mean_spearman")),
                "median_spearman": _n(agg.get("median_spearman")),
                "mean_relative_drop": _n(agg.get("mean_relative_drop")),
                "pct_strongly_monotonic": _n(agg.get("pct_strongly_monotonic")),
            })
    return _write(
        "degradation_cells",
        ["model", "degradation", "region_degraded", "scored_on", "n_images",
         "mean_spearman", "median_spearman", "mean_relative_drop",
         "pct_strongly_monotonic"],
        rows, tsv=tsv,
    )


# ---------------------------------------------------------------------------
# Phase 4 — focus measures and AF metadata
# ---------------------------------------------------------------------------
def export_focus_arm_a(payload: dict, *, tsv: bool):
    cfg = payload.get("config") or {}
    arm = payload.get("arm_a_predicts_af_disagreement") or {}
    tracks = set(cfg.get("tracks_blur") or ())
    noise = set(cfg.get("noise_fooled") or ())
    deltas = (arm.get("_crop_vs_full") or {}).get("delta_abs_auc_crop_minus_full", {})
    rows = []
    for measure in cfg.get("measures") or ():
        for source in ("crop", "full"):
            cell = arm.get(f"{source}/{measure}") or {}
            rows.append({
                "measure": measure,
                "source": source,
                "auc_vs_af_disagreement": _n(cell.get("auc")),
                "median_af_agree": _n(cell.get("median_af_agree")),
                "median_af_disagree": _n(cell.get("median_af_disagree")),
                "crop_minus_full_abs_auc": _n(deltas.get(measure)) if source == "crop" else "",
                "tracks_blur": measure in tracks,
                "noise_fooled": measure in noise,
                "n_af_agree": _n(cfg.get("n_af_agree")),
                "n_af_disagree": _n(cfg.get("n_af_disagree")),
                "long_edge": _n(cfg.get("long_edge")),
                "image_ids_file": _n(cfg.get("image_ids_file")),
            })
    return _write(
        "focus_arm_a_auc",
        ["measure", "source", "auc_vs_af_disagreement", "median_af_agree",
         "median_af_disagree", "crop_minus_full_abs_auc", "tracks_blur",
         "noise_fooled", "n_af_agree", "n_af_disagree", "long_edge", "image_ids_file"],
        rows, tsv=tsv,
    )


def export_focus_arm_b(payload: dict, *, tsv: bool):
    """The Arm B rule and its accuracy, one row.

    ``ground_truth_kind`` rides along deliberately: the rule is currently scored
    against agent-derived verdicts, and a precision quoted without that column
    reads as if it were human-validated.
    """
    arm = payload.get("arm_b_rule_proposal") or {}
    vs = arm.get("vs_labels") or {}
    if not arm.get("available") or not vs.get("available"):
        logger.warning(
            "no rows for focus_arm_b — %s",
            vs.get("reason") or arm.get("reason") or "Arm B unavailable",
        )
        return None
    cfg = payload.get("config") or {}
    row = {
        "rule": arm.get("rule"),
        "threshold_laplacian_variance_p10": _n(arm.get("threshold_laplacian_variance_p10")),
        "ground_truth_kind": _n(vs.get("ground_truth_kind")),
        "positive_class": _n(vs.get("positive_class")),
        "precision_vs_reject": _n(vs.get("precision_vs_reject")),
        "recall_vs_reject": _n(vs.get("recall_vs_reject")),
        "base_reject_rate": _n(vs.get("base_reject_rate")),
        "precision_lift_vs_base": _n(vs.get("precision_lift_vs_base")),
        "true_positives": _n(vs.get("true_positives")),
        "false_positives": _n(vs.get("false_positives")),
        "false_negatives": _n(vs.get("false_negatives")),
        "n_flagged": _n(vs.get("n_flagged")),
        "n_eligible": _n(vs.get("n_eligible")),
        "n_with_af": _n(arm.get("n_with_af")),
        "flag_rate": _n(arm.get("flag_rate")),
        "image_ids_file": _n(cfg.get("image_ids_file")),
    }
    return _write("focus_arm_b_rule", list(row), [row], tsv=tsv)


def export_af_coverage(payload: dict, *, tsv: bool):
    rows = [
        {
            "camera": model,
            "images": row.get("n"),
            "with_af_area": row.get("af_area"),
            "with_focus_distance": row.get("focus_distance"),
            "af_area_pct": round(100.0 * row["af_area"] / row["n"], 1) if row.get("n") else "",
        }
        for model, row in (payload.get("af_coverage") or {}).items()
    ]
    return _write(
        "focus_af_coverage",
        ["camera", "images", "with_af_area", "with_focus_distance", "af_area_pct"],
        rows, tsv=tsv,
    )


# ---------------------------------------------------------------------------
# Phase 2 — embedding / caption eval
# ---------------------------------------------------------------------------
def export_embedding_eval(*, tsv: bool):
    from scripts.research.clip_culling import common

    path = common.INPUT_SIZE_DIR / "eval_summary.json"
    if not path.exists():
        logger.warning("skipping eval_summary.json — not found")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("skipping eval_summary.json — %s", exc)
        return None

    rows = []
    for r in (payload.get("embedding") or {}).get("runs") or []:
        pm = r.get("pair_margin") or {}
        bt = (r.get("grouping") or {}).get("best_threshold") or {}
        rows.append({
            "track": "embedding",
            "model": r.get("model"),
            "source": r.get("source"),
            "long_edge": r.get("long_edge"),
            "n_embeddings": r.get("n_embeddings"),
            "pair_margin": _n(pm.get("pair_margin")),
            "same_burst_median_dist": _n(pm.get("same_burst_median_dist")),
            "diff_burst_median_dist": _n(pm.get("diff_burst_median_dist")),
            "best_ari": _n(bt.get("mean_ari")),
            "best_threshold": _n(bt.get("threshold")),
        })
    for r in (payload.get("caption") or {}).get("runs") or []:
        m = r.get("metrics") or {}
        rows.append({
            "track": "caption",
            "model": r.get("model"),
            "source": r.get("source"),
            "long_edge": r.get("long_edge"),
            "n_embeddings": _n(m.get("n_captions")),
            "pair_margin": "",
            "same_burst_median_dist": "",
            "diff_burst_median_dist": "",
            "best_ari": "",
            "best_threshold": "",
            "burst_caption_uniqueness": _n(m.get("burst_caption_uniqueness")),
            "distinct_caption_frac": _n(m.get("distinct_caption_frac")),
            "mentions_bird_frac": _n(m.get("mentions_bird_frac")),
        })
    return _write(
        "phase2_eval_runs",
        ["track", "model", "source", "long_edge", "n_embeddings", "pair_margin",
         "same_burst_median_dist", "diff_burst_median_dist", "best_ari",
         "best_threshold", "burst_caption_uniqueness", "distinct_caption_frac",
         "mentions_bird_frac"],
        rows, tsv=tsv,
    )


# ---------------------------------------------------------------------------
# Phase 3 — species
# ---------------------------------------------------------------------------
def export_species(payload: dict, *, tsv: bool):
    """Crop vs whole-image BioCLIP, per subject-size tercile plus the overall row.

    Keys are ``tercile_1..3`` and ``overall``; ``_reading`` is prose for humans and
    is skipped. The flip-rate field is named differently on the tercile rows than
    on the overall row, hence the two lookups.
    """
    cfg = payload.get("config") or {}
    rows = []
    for key, v in (payload.get("comparison") or {}).items():
        if key.startswith("_"):
            continue
        agree = v.get("mean_within_burst_agreement") or {}
        conf = v.get("mean_top1_confidence") or {}
        rows.append({
            "row": key,
            "subject_size": _n(v.get("subject_size", "all" if key == "overall" else "")),
            "agreement_crop": _n(agree.get("crop")),
            "agreement_whole": _n(agree.get("whole")),
            "agreement_delta_crop_minus_whole": _n(
                v.get("agreement_delta_crop_minus_whole")
                if v.get("agreement_delta_crop_minus_whole") is not None
                else (round(agree["crop"] - agree["whole"], 4)
                      if agree.get("crop") is not None and agree.get("whole") is not None
                      else None)
            ),
            "confidence_crop": _n(conf.get("crop")),
            "confidence_whole": _n(conf.get("whole")),
            "label_flip_rate": _n(
                v.get("label_flip_rate_crop_vs_whole") or v.get("label_flip_rate")
            ),
            "n_bursts": _n(v.get("n_bursts", cfg.get("n_bursts"))),
            "n_images": _n(v.get("n_images", cfg.get("n_images"))),
        })
    return _write(
        "species_crop_vs_whole",
        ["row", "subject_size", "agreement_crop", "agreement_whole",
         "agreement_delta_crop_minus_whole", "confidence_crop", "confidence_whole",
         "label_flip_rate", "n_bursts", "n_images"],
        rows, tsv=tsv,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--tsv", action="store_true", help="tab-separated instead of comma")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    prod.configure_logging(args.verbose)

    written = []
    degradation = _read("degradation.json")
    if degradation:
        written += [export_degradation_verdict(degradation, tsv=args.tsv),
                    export_degradation_cells(degradation, tsv=args.tsv)]
    focus = _read("focus.json")
    if focus:
        written += [export_focus_arm_a(focus, tsv=args.tsv),
                    export_focus_arm_b(focus, tsv=args.tsv),
                    export_af_coverage(focus, tsv=args.tsv)]
    species = _read("species_crop.json")
    if species:
        written.append(export_species(species, tsv=args.tsv))
    written.append(export_embedding_eval(tsv=args.tsv))

    written = [p for p in written if p]
    logger.info("Exported %d table(s) into %s", len(written), OUT_DIR)
    for p in written:
        print(p)
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
