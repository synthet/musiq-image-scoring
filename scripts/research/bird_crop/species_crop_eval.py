"""Step 3 — does cropping actually help BioCLIP species classification?

Species is the one place cropping is **already live** in production
(``modules/bird_species.py`` crops to ``bird_bbox`` before BioCLIP), and it is the
one place the result is unresolved. A 2026-07-26 session found that cropping
improved *consistency* — a 7-frame burst went from five different labels to one —
while mean species confidence **fell 0.44 -> 0.40**, and one group settled on an
implausible label (Pinyon Jay, a blue corvid, for a slate-grey raptor).

Two competing explanations, and this script separates them:

1. the crop is hurting classification, or
2. the crop is fine and ``data/bird_species_list.txt`` simply does not contain the
   birds in this library, so BioCLIP is forced into a wrong answer.

Explanation 2 is checked **first and for free** (``--coverage-only``), because if
the candidate list is the bottleneck then tuning crops here is wasted effort.

What is measured, per subject-size tercile:

* **within-burst label agreement** — frames of the same bird 2 s apart should get
  the same species. Needs no ground truth, and is the metric the earlier session
  saw improve.
* **mean top-1 confidence** — the number that regressed.
* **flip rate** — how often crop and whole-image disagree, which localises where
  the crop changes the answer.

Reuses ``BioCLIPClassifier`` directly, toggling the detector per arm, so this
measures the real production path rather than a reimplementation.

Reads production read-only; writes only into ``reports/bird-crop/``.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate

    # Free: is the species list even the right list?
    python -m scripts.research.bird_crop.species_crop_eval --coverage-only

    # Compare crop vs whole-image on burst frames (GPU)
    python -m scripts.research.bird_crop.species_crop_eval --limit 60

    # Same, on the pinned study population every other track measures
    python -m scripts.research.bird_crop.species_crop_eval \\
        --image-ids-file reports/bird-crop/study_image_ids.txt
"""

from __future__ import annotations

import argparse
import collections
import logging
import os
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from scripts.research.bird_crop import bursts, prod
from scripts.research.bird_crop.bbox import parse_bbox

logger = logging.getLogger("bird_crop.species_crop_eval")

SPECIES_KEYWORD_PREFIX = "species:"


# ---------------------------------------------------------------------------
# Coverage — is data/bird_species_list.txt the right candidate list?
# ---------------------------------------------------------------------------
def species_list_coverage() -> dict:
    """Describe the assigned-species distribution, and be explicit about its limits.

    **This cannot tell you whether the candidate list contains the birds in the
    library.** Assigned labels are produced *by* BioCLIP *from* this list, so
    "100% of tags come from the list" is tautological and "every candidate was
    assigned at least once" is the expected outcome of argmax over 360 classes on
    ~37k images even if the classifier were guessing. Using assigned labels to
    validate the list is the same circularity that makes ``images.rating``
    unusable as ground truth (see ``labels``).

    What it *can* show is how **concentrated** the distribution is. A classifier
    with genuine signal should concentrate on the species actually present; one
    that is guessing spreads mass thinly across the list. Combined with the
    confidence figures from the crop/whole comparison, that is suggestive — but
    only the human label set or an expert check can settle correctness.
    """
    from modules.bird_species import _load_default_species

    candidates = _load_default_species()
    cand_norm = {c.strip().lower() for c in candidates if c.strip()}

    rows = prod.select(
        "SELECT COALESCE(kd.keyword_display, kd.keyword_norm) AS keyword, COUNT(*) AS n "
        "FROM image_keywords ik "
        "JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id "
        "WHERE kd.keyword_norm LIKE %s "
        "GROUP BY 1 ORDER BY n DESC",
        [f"{SPECIES_KEYWORD_PREFIX}%"],
    )

    assigned: dict[str, int] = {}
    for r in rows:
        name = (r["keyword"] or "")[len(SPECIES_KEYWORD_PREFIX):].strip()
        if name:
            assigned[name] = assigned.get(name, 0) + int(r["n"])

    assigned_norm = {k.lower(): v for k, v in assigned.items()}
    off_list = {k: v for k, v in assigned_norm.items() if k not in cand_norm}
    unused = sorted(cand_norm - set(assigned_norm))

    total_tags = sum(assigned_norm.values()) or 1
    ranked = sorted(assigned_norm.items(), key=lambda kv: -kv[1])
    counts = np.asarray([n for _, n in ranked], dtype=float)

    # Concentration: how much of the library's species mass sits in the top slice.
    # Flat = consistent with guessing; peaked = consistent with real signal.
    share = counts / counts.sum() if counts.sum() else counts
    top20_share = round(float(share[:20].sum()) * 100, 1) if share.size else None
    entropy = float(-(share * np.log(np.maximum(share, 1e-12))).sum()) if share.size else 0.0
    max_entropy = float(np.log(len(cand_norm))) if cand_norm else 1.0

    return {
        "n_candidates": len(cand_norm),
        "n_distinct_species_assigned": len(assigned_norm),
        "n_assigned_off_candidate_list": len(off_list),
        "off_list_examples": sorted(off_list.items(), key=lambda kv: -kv[1])[:10],
        "n_candidates_never_assigned": len(unused),
        "n_tags": int(total_tags),
        "top20_share_pct": top20_share,
        "normalised_entropy": round(entropy / max_entropy, 4) if max_entropy else None,
        "top_assigned": ranked[:15],
        "interpretation": (
            "NOT evidence that the candidate list matches the library. Labels are "
            "generated by BioCLIP from this list, so both 'every tag is on the list' "
            "and 'every candidate got used' are expected by construction — the second "
            "especially, since argmax over "
            f"{len(cand_norm)} classes across {int(total_tags)} tags will touch every "
            "class even when guessing. Read normalised_entropy instead: near 1.0 means "
            "the mass is spread almost uniformly across the list (consistent with "
            "guessing), well below 1.0 means it concentrates on particular species "
            "(consistent with real signal). Correctness still requires the human label "
            "set or an expert check."
        ),
    }


# ---------------------------------------------------------------------------
# Crop vs whole-image classification
# ---------------------------------------------------------------------------
def _make_classifier(*, use_detector: bool):
    """Build a BioCLIPClassifier with the detector forced on or off.

    Forces ``_detector_state`` rather than mutating ``config.json``: the state is the
    documented memoisation hook (``None`` / ``"enabled"`` / ``"disabled"``), so
    pinning it to ``"disabled"`` gives a clean whole-image arm with no global
    side effects.
    """
    from modules.bird_species import BioCLIPClassifier

    clf = BioCLIPClassifier()
    clf.load_model()
    if not use_detector:
        clf._detector_state = "disabled"
        clf.detector = None
    else:
        detector = clf._ensure_detector()
        if detector is None:
            raise RuntimeError(
                "Bird detector unavailable, so the crop arm cannot run. Check "
                "config 'bird_detection' and that ultralytics is installed."
            )
    return clf


def _tercile_bounds(values: Sequence[float]) -> tuple[float, float]:
    import statistics

    if len(values) < 3:
        return (0.0, 0.0)
    q = statistics.quantiles(sorted(values), n=3, method="inclusive")
    return (q[0], q[1])


def _tercile_of(value: float, bounds: tuple[float, float]) -> int:
    low, high = bounds
    return 1 if value <= low else (2 if value <= high else 3)


def run(
    *,
    limit: int,
    folders: Optional[Sequence[int]],
    min_burst: int,
    max_burst: int,
    top_k: int,
    image_ids: Optional[Sequence[int]] = None,
    image_ids_file: Optional[str] = None,
) -> dict:
    from modules.bird_species import _load_default_species

    candidates = _load_default_species()
    if not candidates:
        raise RuntimeError("Species candidate list is empty; nothing to classify against.")

    rows = bursts.load_boxed_rows(folders=folders, image_ids=image_ids)
    all_fracs = [
        box.area_frac
        for box in (parse_bbox(r.get("bird_bbox")) for r in rows)
        if box is not None
    ]
    bounds = _tercile_bounds(all_fracs)

    burst_of = bursts.group_bursts(rows)
    grouped = bursts.bursts_by_id(rows, burst_of, min_size=min_burst, max_size=max_burst)

    # Take whole bursts until the image budget is used, so within-burst agreement
    # is always computed over complete bursts.
    selected: dict[int, list[dict]] = {}
    used = 0
    for bid in sorted(grouped):
        frames = grouped[bid]
        if limit and used + len(frames) > limit:
            continue
        selected[bid] = frames
        used += len(frames)
        if limit and used >= limit:
            break
    if not selected:
        raise RuntimeError("No eligible bursts within the image budget.")
    logger.info("Species comparison on %d burst(s) / %d image(s)", len(selected), used)

    # A pinned id still drops out here if its burst falls outside the size window,
    # so report coverage instead of letting the memo imply all of them were measured.
    n_pinned_covered: Optional[int] = None
    if image_ids is not None:
        covered = {f["id"] for frames in selected.values() for f in frames}
        n_pinned_covered = len(covered)
        dropped = sorted(set(int(i) for i in image_ids) - covered)
        if dropped:
            logger.warning(
                "%d pinned id(s) are outside %d-%d frame bursts and are not measured "
                "here (e.g. %s): %d of %d pinned images covered.",
                len(dropped), min_burst, max_burst, dropped[:10],
                n_pinned_covered, len(image_ids),
            )

    arms = {}
    for arm, use_detector in (("crop", True), ("whole", False)):
        clf = _make_classifier(use_detector=use_detector)
        preds: dict[int, tuple[str, float]] = {}
        n_boxed = 0
        for bid, frames in selected.items():
            for frame in frames:
                path = frame.get("file_path")
                if not path or not os.path.exists(path):
                    continue
                try:
                    res = clf.classify(path, candidates, threshold=0.0, top_k=top_k)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("classify failed id=%s: %s", frame.get("id"), exc)
                    continue
                if not res:
                    continue
                preds[frame["id"]] = (res[0][0], float(res[0][1]))
                last_bbox = getattr(clf, "last_bbox", None)
                if use_detector and isinstance(last_bbox, dict) and "x1" in last_bbox:
                    n_boxed += 1
        arms[arm] = preds
        logger.info(
            "[%s] classified %d image(s)%s",
            arm, len(preds), f", {n_boxed} with a fresh box" if use_detector else "",
        )
        _release(clf)

    return {
        "config": {
            "n_bursts": len(selected),
            "n_images": used,
            "burst_size_range": [min_burst, max_burst],
            "top_k": top_k,
            "n_candidates": len(candidates),
            "folders": list(folders) if folders else "all",
            "image_ids_file": image_ids_file,
            "n_pinned_ids": len(image_ids) if image_ids is not None else None,
            "n_pinned_covered": n_pinned_covered,
        },
        "coverage": species_list_coverage(),
        "comparison": _compare(selected, arms, bounds),
    }


def _release(clf) -> None:
    try:
        import torch

        clf.model = None
        clf.detector = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def _compare(
    selected: dict[int, list[dict]],
    arms: dict[str, dict[int, tuple[str, float]]],
    bounds: tuple[float, float],
) -> dict:
    """Within-burst agreement, confidence, and flip rate, split by subject size."""
    out: dict = {}
    per_tercile: dict[int, dict[str, list]] = collections.defaultdict(
        lambda: {"agreement": {"crop": [], "whole": []}, "conf": {"crop": [], "whole": []}, "flips": []}
    )

    for frames in selected.values():
        fracs = [
            box.area_frac
            for box in (parse_bbox(f.get("bird_bbox")) for f in frames)
            if box is not None
        ]
        if not fracs:
            continue
        import statistics

        tercile = _tercile_of(statistics.median(fracs), bounds)
        bucket = per_tercile[tercile]

        for arm in ("crop", "whole"):
            labels = [arms[arm][f["id"]][0] for f in frames if f["id"] in arms[arm]]
            if len(labels) >= 2:
                # Fraction of frames carrying the burst's modal label: 1.0 means the
                # whole burst agreed.
                modal = collections.Counter(labels).most_common(1)[0][1]
                bucket["agreement"][arm].append(modal / len(labels))
            bucket["conf"][arm].extend(
                arms[arm][f["id"]][1] for f in frames if f["id"] in arms[arm]
            )

        for f in frames:
            iid = f["id"]
            if iid in arms["crop"] and iid in arms["whole"]:
                bucket["flips"].append(arms["crop"][iid][0] != arms["whole"][iid][0])

    for tercile in sorted(per_tercile):
        b = per_tercile[tercile]
        out[f"tercile_{tercile}"] = {
            "subject_size": {1: "smallest", 2: "middle", 3: "largest"}[tercile],
            "mean_within_burst_agreement": {
                arm: _mean(b["agreement"][arm]) for arm in ("crop", "whole")
            },
            "mean_top1_confidence": {arm: _mean(b["conf"][arm]) for arm in ("crop", "whole")},
            "label_flip_rate_crop_vs_whole": _mean(b["flips"]),
            "n_bursts": len(b["agreement"]["crop"]),
            "n_images": len(b["flips"]),
        }

    overall_agree = {
        arm: _mean([v for t in per_tercile.values() for v in t["agreement"][arm]])
        for arm in ("crop", "whole")
    }
    overall_conf = {
        arm: _mean([v for t in per_tercile.values() for v in t["conf"][arm]])
        for arm in ("crop", "whole")
    }
    out["overall"] = {
        "mean_within_burst_agreement": overall_agree,
        "mean_top1_confidence": overall_conf,
        "agreement_delta_crop_minus_whole": _delta(overall_agree),
        "confidence_delta_crop_minus_whole": _delta(overall_conf),
        "label_flip_rate": _mean([v for t in per_tercile.values() for v in t["flips"]]),
    }
    out["_reading"] = (
        "Higher within-burst agreement is better: frames of the same bird seconds "
        "apart should get one name. Confidence is a softmax over the candidate list, "
        "so it measures how peaked that distribution is, NOT correctness — a "
        "confidence drop with an agreement rise is consistent with the crop removing "
        "background cues the classifier was over-trusting. Neither metric can "
        "establish accuracy; only the human label set or an expert check can."
    )
    return out


def _mean(values) -> Optional[float]:
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    arr = arr[np.isfinite(arr)]
    return round(float(arr.mean()), 4) if arr.size else None


def _delta(pair: dict) -> Optional[float]:
    a, b = pair.get("crop"), pair.get("whole")
    return round(a - b, 4) if a is not None and b is not None else None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_markdown(payload: dict) -> str:
    cov = payload["coverage"]
    lines = [
        "# BioCLIP species — crop vs whole image",
        "",
        "## 1. Is the candidate list the bottleneck?",
        "",
        "Checked first because a zero-shot classifier can only return a name from its "
        "candidate list. If the birds in the library are not on the list, no amount of "
        "crop tuning can produce a right answer.",
        "",
        "> ⚠️ **This check cannot answer that question, and the numbers below are "
        "easy to over-read.** Labels are produced by BioCLIP *from* this list, so they "
        "cannot be used to validate it — the same circularity that rules out "
        "`images.rating` as ground truth. Treat this as a description of the label "
        "distribution, not as evidence.",
        "",
        f"- Candidate list: **{cov['n_candidates']}** names (`data/bird_species_list.txt`)",
        f"- Distinct species assigned across **{cov['n_tags']}** tags: "
        f"**{cov['n_distinct_species_assigned']}**",
        f"- Candidates never assigned: **{cov['n_candidates_never_assigned']}** "
        "(expected to be ~0 by construction; not a coverage signal)",
        f"- Top-20 species share: **{cov['top20_share_pct']}%** · "
        f"normalised entropy **{cov['normalised_entropy']}** "
        "(near 1.0 = mass spread ~uniformly, consistent with guessing; "
        "well below 1.0 = concentrated, consistent with real signal)",
        "",
        f"> {cov['interpretation']}",
        "",
    ]
    if cov["top_assigned"]:
        lines += ["Most-assigned species:", ""]
        lines += [f"  - {name} — {n}" for name, n in cov["top_assigned"][:10]]
        lines.append("")

    comp = payload.get("comparison")
    if not comp:
        lines += [
            "## 2. Crop vs whole image",
            "",
            "> Not run (coverage-only pass). Re-run without `--coverage-only`.",
            "",
        ]
    else:
        cfg = payload["config"]
        lines += [
            "## 2. Crop vs whole image",
            "",
            f"{cfg['n_bursts']} bursts / {cfg['n_images']} images, "
            f"{cfg['n_candidates']} candidate species.",
            "",
            "| Subject size | Agreement (crop) | Agreement (whole) | Confidence (crop) | Confidence (whole) | Flip rate | bursts |",
            "|---|---|---|---|---|---|---|",
        ]
        for key in sorted(k for k in comp if k.startswith("tercile_")):
            t = comp[key]
            a, c = t["mean_within_burst_agreement"], t["mean_top1_confidence"]
            lines.append(
                f"| {t['subject_size']} | {a['crop']} | {a['whole']} | "
                f"{c['crop']} | {c['whole']} | {t['label_flip_rate_crop_vs_whole']} | "
                f"{t['n_bursts']} |"
            )
        o = comp["overall"]
        lines += [
            "",
            f"**Overall** — agreement {o['mean_within_burst_agreement']['crop']} (crop) vs "
            f"{o['mean_within_burst_agreement']['whole']} (whole), "
            f"delta **{o['agreement_delta_crop_minus_whole']}**; "
            f"confidence {o['mean_top1_confidence']['crop']} vs "
            f"{o['mean_top1_confidence']['whole']}, "
            f"delta **{o['confidence_delta_crop_minus_whole']}**; "
            f"labels flip on **{o['label_flip_rate']}** of images.",
            "",
            f"> {comp['_reading']}",
            "",
        ]

    lines += [
        "---",
        "",
        "Generated by `scripts.research.bird_crop.species_crop_eval`. "
        "Production was read read-only; nothing was written to it.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="Only run the free species-list coverage check; load no models.",
    )
    parser.add_argument("--limit", type=int, default=60, help="Approx image budget (whole bursts)")
    parser.add_argument("--folders", default="", help="Comma-separated folder_id list")
    parser.add_argument(
        "--image-ids-file",
        default=None,
        help=(
            "Pin the population to an explicit list of production image ids, one per "
            "line, replacing --folders/--limit selection. Use this so the species arm "
            "measures the same images as the embedding, IQA, caption and degradation "
            "tracks. Generate with scripts/research/bird_crop/pin_study_set.py."
        ),
    )
    parser.add_argument("--min-burst", type=int, default=3)
    parser.add_argument("--max-burst", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=1)
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
        # The pinned list *is* the budget; keeping --limit would sub-sample it.
        limit = 0
        logger.info(
            "Pinned to %d image id(s) from %s (--limit ignored)",
            len(image_ids), args.image_ids_file,
        )

    if args.coverage_only:
        payload = {"config": {"coverage_only": True}, "coverage": species_list_coverage()}
    else:
        payload = run(
            limit=limit,
            folders=folders,
            min_burst=args.min_burst,
            max_burst=args.max_burst,
            top_k=args.top_k,
            image_ids=image_ids,
            image_ids_file=args.image_ids_file,
        )

    prod.write_json("species_crop.json", payload)
    prod.write_text("species_crop.md", render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
