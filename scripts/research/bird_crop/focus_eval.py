"""Phase 4 — can cheap signals decide whether a bird crop is in focus?

Phase 2b showed that a bbox crop is 2.42x-17.51x more sensitive to subject-only
degradation than the whole frame, but only with learned IQA models that each cost
a GPU pass. This phase asks whether two zero-inference signals can do the job:

1. **Classical focus measures** on the crop (``focus_measures``), and
2. **The camera's own AF intent** (``af_metadata``) — where it tried to focus.

The evaluation avoids one specific trap
---------------------------------------
The only label available without human verdicts is *AF-vs-bird disagreement*: the
camera focused somewhere other than the detected bird. That is a usable proxy for
real misfocus, but it means a decision rule that **consumes** the AF cue cannot be
scored against it — the rule would be predicting its own input.

So the arms are split:

* **Arm A (non-circular).** How well do *image-only* focus measures predict AF
  disagreement? This is a fair test, and it doubles as a real-data check of the
  study's premise: does measuring on the crop predict better than on the frame?
* **Arm B.** The combined rule is emitted with its component statistics and is
  **not** scored against the AF proxy it uses (circular). When
  ``reports/bird-crop/labels/label_set.csv`` is filled, the rule is scored
  against within-burst verdicts (``reject`` as the positive class). Agent-derived
  labels are tagged as such — not human ground truth.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.bird_crop.focus_eval \\
        --image-ids-file reports/bird-crop/study_image_ids.txt
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from scripts.research.bird_crop import (
    af_metadata,
    bursts,
    crops,
    focus_measures,
    labels,
    prod,
)
from scripts.research.bird_crop.bbox import padded_box, parse_bbox

logger = logging.getLogger("bird_crop.focus_eval")

#: Working resolution for the decode. Matches ``degradation_eval`` so the two
#: phases measure the same pixels.
DEFAULT_WORK_LONG_EDGE = 3000

#: Long edge each measure is finally computed at, for both crop and full frame.
DEFAULT_LONG_EDGE = 512

#: Crop padding variant, matching production's stored ``bird_bbox`` pad.
DEFAULT_CROP_VARIANT = "crop"


def roc_auc(positive: Sequence[float], negative: Sequence[float]) -> Optional[float]:
    """Probability a random *positive* outranks a random *negative*.

    Rank-based (the Mann-Whitney relationship) rather than a sklearn import, and
    tie-aware: many of these measures produce exact ties on flat crops, and
    counting a tie as a win would flatter the measure. 0.5 means no separation.
    """
    pos = [v for v in positive if v is not None and np.isfinite(v)]
    neg = [v for v in negative if v is not None and np.isfinite(v)]
    if not pos or not neg:
        return None
    allv = np.concatenate([np.asarray(pos, float), np.asarray(neg, float)])
    order = allv.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # Average ranks within tie groups so ties score 0.5 rather than 1.0.
    _, inv, counts = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    ranks = (sums / counts)[inv]
    n_pos = len(pos)
    u = ranks[:n_pos].sum() - n_pos * (n_pos + 1) / 2.0
    return round(float(u / (n_pos * len(neg))), 4)


def _measure_one(row: dict, *, work_long_edge: int, long_edge: int, crop_variant: str):
    """Focus measures on the bird crop and on the whole frame, for one image."""
    path = row.get("file_path")
    if not path:
        return None
    box = parse_bbox(row.get("bird_bbox"))
    if box is None:
        return None
    try:
        oriented = crops.load_oriented(path)
    except Exception as exc:  # noqa: BLE001 — one unreadable file must not stop the sweep
        logger.warning("decode failed id=%s: %s", row.get("id"), exc)
        return None

    oriented = crops.resize_to_long_edge(oriented, work_long_edge)
    box = crops.rescale_box(box, *oriented.size)
    spec = crops.parse_variant(crop_variant)
    crop_img = oriented.crop(padded_box(box, pad=spec.pad))

    def _measures(img):
        arr = np.asarray(
            crops.resize_to_long_edge(img, long_edge).convert("L"), dtype=np.float64
        )
        return focus_measures.compute_all(arr)

    return {"crop": _measures(crop_img), "full": _measures(oriented)}


def run(
    *,
    image_ids: Optional[Sequence[int]] = None,
    image_ids_file: Optional[str] = None,
    folders: Optional[Sequence[int]] = None,
    limit: int = 0,
    work_long_edge: int = DEFAULT_WORK_LONG_EDGE,
    long_edge: int = DEFAULT_LONG_EDGE,
    crop_variant: str = DEFAULT_CROP_VARIANT,
) -> dict:
    rows = bursts.load_boxed_rows(folders=folders, limit=limit, image_ids=image_ids)
    logger.info("Focus study on %d image(s)", len(rows))

    af_meta = af_metadata.read_af_batch([r["file_path"] for r in rows if r.get("file_path")])
    coverage = af_metadata.availability(af_meta.values())

    per_image: list[dict] = []
    for idx, row in enumerate(rows, start=1):
        measured = _measure_one(
            row, work_long_edge=work_long_edge, long_edge=long_edge, crop_variant=crop_variant
        )
        if measured is None:
            continue
        meta = af_meta.get(row.get("file_path") or "", {})
        agreement = af_metadata.af_bird_agreement(
            af_metadata.af_box_in_display_space(meta), parse_bbox(row.get("bird_bbox"))
        )
        per_image.append({
            "image_id": row["id"],
            "model": meta.get("Model"),
            "focus_distance": meta.get("FocusDistance"),
            "af_area_mode": meta.get("AFAreaMode"),
            "agreement": agreement,
            **measured,
        })
        if idx % 25 == 0 or idx == len(rows):
            logger.info("measured %d/%d images", idx, len(rows))

    with_af = [r for r in per_image if r["agreement"] is not None]
    agree = [r for r in with_af if r["agreement"]["centre_inside"]]
    disagree = [r for r in with_af if not r["agreement"]["centre_inside"]]
    logger.info(
        "AF available for %d/%d; centre inside bird box on %d (%.1f%%)",
        len(with_af), len(per_image), len(agree),
        100.0 * len(agree) / len(with_af) if with_af else 0.0,
    )

    return {
        "config": {
            "n_images": len(per_image),
            "long_edge": long_edge,
            "work_long_edge": work_long_edge,
            "crop_variant": crop_variant,
            "measures": list(focus_measures.MEASURES),
            "noise_fooled": list(focus_measures.NOISE_FOOLED),
            "tracks_blur": list(focus_measures.TRACKS_BLUR),
            "folders": list(folders) if folders else "all",
            "image_ids_file": image_ids_file,
            "n_pinned_ids": len(image_ids) if image_ids is not None else None,
            "n_af_available": len(with_af),
            "n_af_agree": len(agree),
            "n_af_disagree": len(disagree),
        },
        "af_coverage": coverage,
        "arm_a_predicts_af_disagreement": _arm_a(agree, disagree),
        "arm_b_rule_proposal": _arm_b(with_af),
    }


def _arm_a(agree: list[dict], disagree: list[dict]) -> dict:
    """Do image-only measures separate AF-agreement from AF-disagreement?

    Non-circular: nothing here reads the AF cue, it is only the label. AUC > 0.5
    means the measure scores *higher* when the camera did focus on the bird, which
    is the expected direction if the measure detects real softness.
    """
    out: dict = {}
    for source in ("crop", "full"):
        for name in focus_measures.MEASURES:
            auc = roc_auc(
                [r[source][name] for r in agree],
                [r[source][name] for r in disagree],
            )
            med_a = _median([r[source][name] for r in agree])
            med_d = _median([r[source][name] for r in disagree])
            out[f"{source}/{name}"] = {
                "auc": auc,
                "median_af_agree": med_a,
                "median_af_disagree": med_d,
                "noise_fooled": name in focus_measures.NOISE_FOOLED,
            }
    out["_crop_vs_full"] = _crop_beats_full(out)
    return out


def _crop_beats_full(cells: dict) -> dict:
    """Per measure, how much better the crop predicts than the whole frame.

    This is the study's premise tested against a *real* signal rather than
    synthetic degradation: if cropping matters, measuring on the crop should
    separate real camera misses better.
    """
    deltas = {}
    for name in focus_measures.MEASURES:
        c = (cells.get(f"crop/{name}") or {}).get("auc")
        f = (cells.get(f"full/{name}") or {}).get("auc")
        if c is None or f is None:
            continue
        # Distance from 0.5 is the discriminative power; direction is irrelevant.
        deltas[name] = round(abs(c - 0.5) - abs(f - 0.5), 4)
    wins = sum(1 for v in deltas.values() if v > 0)
    return {
        "delta_abs_auc_crop_minus_full": deltas,
        "crop_wins": wins,
        "n_measures": len(deltas),
    }


def _arm_b_vs_labels(flagged_ids: Sequence[int], with_af_ids: Sequence[int]) -> dict:
    """Score Arm B flags against within-burst verdicts (reject = positive).

    Not scored against AF disagreement (circular). Empty / incomplete label sets
    yield ``available: False`` so the proposal stays unscored.
    """
    if not labels.LABEL_CSV.exists():
        return {
            "available": False,
            "reason": "label_set.csv missing — fill verdicts to validate Arm B",
        }
    try:
        rows = labels.load(require_complete=True)
    except (OSError, ValueError) as exc:
        return {"available": False, "reason": str(exc)}

    provenance = labels.ground_truth_provenance()
    verdict_of = {r.image_id: r.verdict for r in rows}
    eligible = [i for i in with_af_ids if i in verdict_of]
    if not eligible:
        return {
            "available": False,
            "reason": "no overlap between AF-available images and labelled set",
        }

    flagged = [i for i in flagged_ids if i in verdict_of]
    n_eligible = len(eligible)
    n_reject = sum(1 for i in eligible if verdict_of[i] == "reject")
    base_rate = n_reject / n_eligible if n_eligible else 0.0

    tp = sum(1 for i in flagged if verdict_of[i] == "reject")
    fp = len(flagged) - tp
    fn = sum(
        1 for i in eligible if verdict_of[i] == "reject" and i not in set(flagged)
    )
    precision = tp / len(flagged) if flagged else None
    recall = tp / (tp + fn) if (tp + fn) else None
    lift = (precision / base_rate) if (precision is not None and base_rate > 0) else None

    return {
        "available": True,
        "ground_truth_kind": provenance.get("kind"),
        "ground_truth_sidecar": provenance.get("sidecar"),
        "positive_class": "reject",
        "n_eligible": n_eligible,
        "n_flagged": len(flagged),
        "n_reject_eligible": n_reject,
        "base_reject_rate": round(base_rate, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision_vs_reject": None if precision is None else round(precision, 4),
        "recall_vs_reject": None if recall is None else round(recall, 4),
        "precision_lift_vs_base": None if lift is None else round(lift, 4),
        "note": (
            "Agent-derived labels are not human ground truth; treat lift as "
            "directional only. Do not productionize on this alone."
            if provenance.get("kind") == "agent-derived"
            else "Scored against human within-burst verdicts."
        ),
    }


def _arm_b(with_af: list[dict]) -> dict:
    """Propose a combined rule; score against label_set when complete.

    Scoring against AF disagreement would be circular: the rule consumes that
    signal. Label-set scoring (reject = positive) is the non-circular gate.
    """
    if not with_af:
        return {"available": False, "reason": "no image had usable AF geometry"}

    # Best available image-only measure by the non-circular arm is chosen outside;
    # here we use laplacian_variance on the crop because it is the incumbent metric
    # (modules/technical_failures/classical_metrics.py) and so the cheapest to ship.
    values = [r["crop"]["laplacian_variance"] for r in with_af]
    finite = sorted(v for v in values if v is not None and np.isfinite(v))
    if not finite:
        return {"available": False, "reason": "no finite laplacian_variance values"}
    p10 = float(np.percentile(finite, 10))

    soft = [r for r in with_af if r["crop"]["laplacian_variance"] <= p10]
    af_out = [r for r in with_af if not r["agreement"]["centre_inside"]]
    both = [r for r in soft if not r["agreement"]["centre_inside"]]
    flagged_ids = [int(r["image_id"]) for r in both]
    with_af_ids = [int(r["image_id"]) for r in with_af]
    vs_labels = _arm_b_vs_labels(flagged_ids, with_af_ids)

    if vs_labels.get("available"):
        validation = (
            f"Scored against {vs_labels.get('ground_truth_kind')} labels "
            f"(reject = positive): precision "
            f"{vs_labels.get('precision_vs_reject')}, recall "
            f"{vs_labels.get('recall_vs_reject')}, lift vs base reject rate "
            f"{vs_labels.get('precision_lift_vs_base')}. "
            f"{vs_labels.get('note')}"
        )
    else:
        validation = (
            "NOT scored against AF disagreement (circular — AF is an input). "
            f"Label validation unavailable: {vs_labels.get('reason')}"
        )

    return {
        "available": True,
        "rule": (
            "flag when crop laplacian_variance <= p10 AND the AF centre falls "
            "outside the bird box"
        ),
        "threshold_laplacian_variance_p10": round(p10, 4),
        "n_with_af": len(with_af),
        "n_soft_crop": len(soft),
        "n_af_outside_bird": len(af_out),
        "n_flagged_by_both": len(both),
        "flag_rate": round(len(both) / len(with_af), 4),
        "flagged_image_ids": flagged_ids,
        "vs_labels": vs_labels,
        "validation": validation,
    }


def _median(values: Sequence[Optional[float]]) -> Optional[float]:
    finite = [v for v in values if v is not None and np.isfinite(v)]
    return round(float(np.median(finite)), 6) if finite else None


def render_markdown(payload: dict) -> str:
    cfg = payload["config"]
    arm_a = payload["arm_a_predicts_af_disagreement"]
    arm_b = payload["arm_b_rule_proposal"]
    cvf = arm_a.get("_crop_vs_full", {})

    lines = [
        "# Bird crop focus — classical measures and camera AF intent",
        "",
        "> Ground truth: **derived**. The label is AF-vs-bird disagreement, which is "
        "the camera's intent, not a human verdict. It conflates genuine misfocus with "
        "the detector picking the wrong bird in a multi-bird frame (only the top-1 box "
        "is stored) and with focus-recompose. No accuracy claim is made here.",
        "",
        f"Images: **{cfg['n_images']}** · AF geometry available on "
        f"**{cfg['n_af_available']}** "
        f"({cfg['n_af_agree']} agree / {cfg['n_af_disagree']} disagree) · "
        f"measured at long edge **{cfg['long_edge']}** · crop variant "
        f"`{cfg['crop_variant']}`",
        "",
        "## AF metadata coverage",
        "",
        "| Camera | images | with AF area | with focus distance |",
        "|---|---|---|---|",
    ]
    for model, row in payload.get("af_coverage", {}).items():
        lines.append(
            f"| {model} | {row['n']} | {row['af_area']} | {row['focus_distance']} |"
        )

    lines += [
        "",
        "## Arm A — do image-only measures predict where the camera focused?",
        "",
        "Non-circular: no measure below reads AF data; it is only the label. "
        "AUC 0.5 = no separation. `noise?` marks measures that noise inflates "
        "(see `focus_measures.NOISE_FOOLED`).",
        "",
        "| Measure | AUC (crop) | AUC (full frame) | crop better by | tracks blur? | noise? |",
        "|---|---|---|---|---|---|",
    ]
    deltas = cvf.get("delta_abs_auc_crop_minus_full", {})
    tracks = cfg.get("tracks_blur", [])
    for name in cfg["measures"]:
        c = (arm_a.get(f"crop/{name}") or {}).get("auc")
        f = (arm_a.get(f"full/{name}") or {}).get("auc")
        d = deltas.get(name)
        lines.append(
            f"| `{name}` | {_fmt(c)} | {_fmt(f)} | {_fmt(d)} | "
            f"{'yes' if name in tracks else '**no**'} | "
            f"{'yes' if name in cfg.get('noise_fooled', []) else ''} |"
        )

    lines += [
        "",
        f"Crop separates better than the full frame for **{cvf.get('crop_wins')} of "
        f"{cvf.get('n_measures')}** measures.",
        "",
        "> **Read the `tracks blur?` column before the AUC column.** A measure that "
        "does not fall when detail is destroyed cannot support a claim about focus, "
        "however well it separates the two groups — it is separating them for some "
        "other reason (scene complexity, subject size, contrast). `local_entropy` is "
        "the case in point: blurring a pattern *raises* it "
        "(`test_entropy_does_not_track_blur`), so a high AUC from it is a confound, "
        "not a focus signal.",
        "",
        "## Arm B — proposed decision rule",
        "",
    ]
    if not arm_b.get("available"):
        lines.append(f"Unavailable: {arm_b.get('reason')}")
    else:
        lines += [
            f"**Rule:** {arm_b['rule']}",
            "",
            f"- `laplacian_variance` p10 threshold: **{arm_b['threshold_laplacian_variance_p10']}**",
            f"- images with AF geometry: {arm_b['n_with_af']}",
            f"- soft crops (bottom decile): {arm_b['n_soft_crop']}",
            f"- AF centre outside the bird box: {arm_b['n_af_outside_bird']}",
            f"- flagged by **both** conditions: {arm_b['n_flagged_by_both']} "
            f"({100 * arm_b['flag_rate']:.1f}%)",
            "",
            f"> {arm_b['validation']}",
        ]
        vs = arm_b.get("vs_labels") or {}
        if vs.get("available"):
            lines += [
                "",
                "### Vs within-burst labels (reject = positive)",
                "",
                f"Ground truth: **{vs.get('ground_truth_kind')}**"
                + (
                    f" (`{vs.get('ground_truth_sidecar')}`)"
                    if vs.get("ground_truth_sidecar")
                    else ""
                )
                + ".",
                "",
                f"- eligible (AF ∩ labelled): {vs.get('n_eligible')}",
                f"- flagged among eligible: {vs.get('n_flagged')}",
                f"- base reject rate: {vs.get('base_reject_rate')}",
                f"- precision: **{vs.get('precision_vs_reject')}** "
                f"(lift ×{vs.get('precision_lift_vs_base')} vs base)",
                f"- recall: **{vs.get('recall_vs_reject')}** "
                f"(TP {vs.get('true_positives')} / FN {vs.get('false_negatives')})",
                "",
                f"> {vs.get('note')}",
            ]

    lines += [
        "",
        "---",
        "",
        "Generated by `scripts.research.bird_crop.focus_eval`. Production was read "
        "read-only; nothing was written to it.",
        "",
    ]
    return "\n".join(lines)


def _fmt(v) -> str:
    return "—" if v is None else f"{v}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--folders", default="", help="Comma-separated folder_id list")
    parser.add_argument("--limit", type=int, default=0, help="Max images (0 = all)")
    parser.add_argument(
        "--image-ids-file",
        default=None,
        help=(
            "Pin the population to an explicit list of production image ids, "
            "replacing --folders/--limit. Use this so the focus arm measures the "
            "same images as every other track."
        ),
    )
    parser.add_argument("--long-edge", type=int, default=DEFAULT_LONG_EDGE)
    parser.add_argument("--work-long-edge", type=int, default=DEFAULT_WORK_LONG_EDGE)
    parser.add_argument("--crop-variant", default=DEFAULT_CROP_VARIANT)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    prod.configure_logging(args.verbose)
    prod.assert_prod()

    folders = [int(x) for x in args.folders.split(",") if x.strip()] or None
    image_ids = None
    limit = args.limit
    if args.image_ids_file:
        from scripts.research.bird_crop.pin_study_set import read_ids

        image_ids = read_ids(Path(args.image_ids_file))
        limit = 0
        logger.info(
            "Pinned to %d image id(s) from %s (--limit ignored)",
            len(image_ids), args.image_ids_file,
        )

    payload = run(
        image_ids=image_ids,
        image_ids_file=args.image_ids_file,
        folders=folders,
        limit=limit,
        work_long_edge=args.work_long_edge,
        long_edge=args.long_edge,
        crop_variant=args.crop_variant,
    )
    prod.write_json("focus.json", payload)
    prod.write_text("focus.md", render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
