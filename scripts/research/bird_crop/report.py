"""Step 4 — consolidate the bird-crop study into one report with per-phase verdicts.

Reads whatever result JSONs exist under ``reports/bird-crop/`` and emits
``reports/bird-crop/REPORT.md``. Missing phases are reported as missing rather than
silently omitted, so the report always states what has and has not been measured.

Every metric is tagged with the standing of its ground truth, because that is the
crux of this study:

===============  =============================================================
``human``        human within-burst verdicts — non-circular, the only basis for
                 an accuracy claim
``agent-derived`` vision-LLM within-burst consensus. Independent of the scoring
                  pipeline under test, but still model-derived and not a human
                  accuracy claim
``constructed``  ground truth by construction (known degradation strength) or
                 unbiased (EXIF capture-time bursts)
``derived``      compared against pipeline-produced columns (``rating``,
                 ``pick_status``, BLIP captions). Describes agreement with the
                 incumbent stack; **cannot** establish accuracy
===============  =============================================================

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.research.bird_crop.report
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Optional

from scripts.research.bird_crop import prod

logger = logging.getLogger("bird_crop.report")

#: Verdict vocabulary, mirroring the culling recommendation memos' ADOPT/KEEP/HOLD.
REPLACE = "replace full-frame"
COMPLEMENT = "add as complementary signal"
NO_BENEFIT = "no benefit"
UNMEASURED = "not yet measured"


def _read(name: str) -> Optional[dict]:
    path = prod.REPORTS_DIR / name
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def _fmt(value: Any) -> str:
    return "—" if value is None else str(value)


# ---------------------------------------------------------------------------
# Per-phase verdicts
# ---------------------------------------------------------------------------
def verdict_quality(degradation: Optional[dict]) -> tuple[str, str]:
    """Quality scoring: judged on constructed ground truth (degradation ladders)."""
    if not degradation or not degradation.get("verdict"):
        return UNMEASURED, "Run `degradation_eval` (phase 2b)."
    ratios = [
        v["crop_sensitivity_ratio"]
        for model, per_kind in degradation["verdict"].items()
        if not model.startswith("_")
        for v in per_kind.values()
        if v.get("crop_sensitivity_ratio") is not None
    ]
    if not ratios:
        return UNMEASURED, "No usable sensitivity ratios."
    worst, best = min(ratios), max(ratios)
    if worst < 1.2:
        return (
            NO_BENEFIT,
            f"Crop sensitivity ratio as low as {worst}x — the full frame already "
            "sees subject degradation, so cropping adds little.",
        )
    return (
        COMPLEMENT,
        f"Crop is {worst}x-{best}x more sensitive to subject-only degradation than "
        "the full frame. Crop measures whether the *bird* is sharp; the full frame "
        "measures whether the *photo* is clean. These are different signals, so the "
        "indicated change is to add a crop-based score alongside the existing one, "
        "not to replace it.",
    )


def verdict_geometry(geometry: Optional[dict]) -> tuple[str, str]:
    """Bbox geometry as a free signal, qualified by label provenance."""
    if not geometry:
        return UNMEASURED, "Run `geometry_eval` (phase 1)."
    le = geometry.get("label_eval") or {}
    if le.get("status") != "ok":
        bias = geometry.get("bias_probe") or {}
        edge = (bias.get("frame_edge_effect") or {})
        touch, no_touch = edge.get("mean_score_touching"), edge.get("mean_score_not_touching")
        detail = (
            f"Bias probe only (derived labels). Frame-edge contact: mean score "
            f"{_fmt(touch)} when the bird is clipped vs {_fmt(no_touch)} when it is not."
        )
        return UNMEASURED, detail + " Fill in the label set for an accuracy verdict."
    ground_truth_kind = le.get("ground_truth_kind", "human")
    label_basis = (
        "agent-derived labels" if ground_truth_kind == "agent-derived" else "human labels"
    )
    cm = le.get("combined_model") or {}
    delta = cm.get("delta_auc_from_adding_geometry")
    if delta is None:
        return UNMEASURED, "Combined model did not converge; check label coverage."
    if delta >= 0.03:
        return (
            COMPLEMENT,
            f"Geometry adds {delta} ROC-AUC over score-alone on {label_basis}, clearing "
            "the 0.03 gate. Worth exposing as first-class features — and it costs no "
            "inference, since the box is already stored.",
        )
    return (
        NO_BENEFIT,
        f"Geometry adds only {delta} ROC-AUC over score-alone, below the 0.03 gate.",
    )


def verdict_species(species: Optional[dict]) -> tuple[str, str]:
    """Species: cropping is already live, so the question is whether to keep it."""
    if not species:
        return UNMEASURED, "Run `species_crop_eval` (phase 3)."
    cov = species.get("coverage") or {}
    ent = cov.get("normalised_entropy")
    comp = species.get("comparison")
    if not comp:
        return (
            UNMEASURED,
            f"Coverage described only (normalised entropy {_fmt(ent)}). Run without "
            "`--coverage-only` to compare crop against whole image.",
        )
    o = comp.get("overall") or {}
    d_agree = o.get("agreement_delta_crop_minus_whole")
    d_conf = o.get("confidence_delta_crop_minus_whole")
    detail = (
        f"Within-burst agreement changes by {_fmt(d_agree)} and mean top-1 confidence "
        f"by {_fmt(d_conf)} when cropping (crop minus whole image); labels flip on "
        f"{_fmt(o.get('label_flip_rate'))} of images. Candidate-list normalised entropy "
        f"is {_fmt(ent)}."
    )
    if d_agree is not None and d_agree > 0.02:
        return (
            REPLACE,
            detail + " Higher agreement means frames of the same bird seconds apart get "
            "one name more often, which is what cropping was introduced to fix — keep "
            "it. Note a confidence drop is not evidence of a worse label: confidence is "
            "a softmax over the candidate list, and correctness still needs the human "
            "label set or an expert check.",
        )
    if d_agree is not None and d_agree < -0.02:
        return NO_BENEFIT, detail + " Cropping *reduces* within-burst agreement."
    return COMPLEMENT, detail + " No material change in agreement either way."


#: Below this, a crop-vs-full-frame difference is noise rather than signal. Matches
#: the tolerance ``verdict_species`` applies to within-burst agreement.
_MATERIAL_DELTA = 0.02


def _read_eval_summary() -> Optional[dict]:
    """Load ``input_size_eval``'s output, if the eval has been run."""
    from scripts.research.clip_culling import common

    path = common.INPUT_SIZE_DIR / "eval_summary.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def verdict_embedding(summary: Optional[dict]) -> Optional[tuple[str, str]]:
    """Culling verdict from burst pair-margin — crop sources versus the full frame.

    Pair margin is the separation between same-burst and different-burst distances,
    grouped by EXIF capture time. That makes it *constructed* ground truth, unlike
    ``pick_review``, which scores against pipeline-produced ``rating``/``cull_decision``
    and is therefore circular. Returns ``None`` when the eval has not run, so the
    caller can fall back to describing the NPZ cache.
    """
    runs = (summary or {}).get("embedding", {}).get("runs") or []
    margins: dict[tuple[str, int], dict[str, float]] = {}
    for r in runs:
        pm = (r.get("pair_margin") or {}).get("pair_margin")
        if pm is None:
            continue
        margins.setdefault((r["model"], r["long_edge"]), {})[r["source"]] = float(pm)

    deltas, crop_wins = [], 0
    for cell in margins.values():
        full = cell.get("file")
        crops = {s: v for s, v in cell.items() if s.startswith("crop")}
        if full is None or not crops:
            continue
        best = max(crops.values())
        deltas.append(best - full)
        if best > full:
            crop_wins += 1
    if not deltas:
        return None

    mean_delta = round(sum(deltas) / len(deltas), 4)
    detail = (
        f"Burst pair-margin over {len(deltas)} model x long-edge cell(s): the best "
        f"crop source beats the full frame in {crop_wins} of them, mean delta "
        f"{mean_delta:+.4f} (same-burst vs different-burst separation). "
    )
    if mean_delta >= _MATERIAL_DELTA:
        return COMPLEMENT, detail + "Cropping materially improves burst separation."
    if mean_delta <= -_MATERIAL_DELTA:
        return NO_BENEFIT, detail + "Cropping materially degrades burst separation."
    return (
        NO_BENEFIT,
        detail + f"That is below the +/-{_MATERIAL_DELTA} materiality bar, so cropping "
        "buys the culling embeddings nothing; the crop payoff is in the IQA track, "
        "not here.",
    )


def verdict_caption(summary: Optional[dict]) -> Optional[tuple[str, str]]:
    """Caption verdict from within-burst caption uniqueness (crop vs full frame).

    Ground truth is ``derived``: BLIP captions are pipeline output, so this measures
    whether cropping changes what BLIP says, not whether it is more correct.
    """
    runs = (summary or {}).get("caption", {}).get("runs") or []
    cells: dict[int, dict[str, float]] = {}
    for r in runs:
        uniq = (r.get("metrics") or {}).get("burst_caption_uniqueness")
        if uniq is None:
            continue
        cells.setdefault(r["long_edge"], {})[r["source"]] = float(uniq)

    deltas = []
    for cell in cells.values():
        full = cell.get("file")
        crops = {s: v for s, v in cell.items() if s.startswith("crop")}
        if full is None or not crops:
            continue
        deltas.append(max(crops.values()) - full)
    if not deltas:
        return None

    mean_delta = round(sum(deltas) / len(deltas), 4)
    detail = (
        f"Within-burst caption uniqueness over {len(deltas)} long-edge(s): best crop "
        f"source minus full frame is {mean_delta:+.4f}. "
    )
    if mean_delta >= _MATERIAL_DELTA:
        return COMPLEMENT, detail + "Cropping makes BLIP distinguish frames within a burst more."
    if mean_delta <= -_MATERIAL_DELTA:
        return NO_BENEFIT, detail + "Cropping makes BLIP captions *less* distinct within a burst."
    return NO_BENEFIT, detail + "No material change; captions are unaffected by cropping."


#: An AUC this far from 0.5 counts as real separation. Deliberately generous
#: relative to _MATERIAL_DELTA: the label here is the camera's intent, which is a
#: noisier target than a constructed degradation, so a small edge still matters.
_MATERIAL_AUC = 0.05


def verdict_focus(focus: Optional[dict]) -> Optional[tuple[str, str]]:
    """Do zero-inference signals separate real (AF-proxy) misfocus?

    Reads Arm A only — the non-circular arm, where image-only measures predict AF
    disagreement. The combined rule in Arm B consumes the AF cue and so cannot be
    scored against it; it stays a proposal until human verdicts exist.
    """
    arm = (focus or {}).get("arm_a_predicts_af_disagreement") or {}
    cfg = (focus or {}).get("config") or {}
    if not arm:
        return None

    tracks_blur = set(cfg.get("tracks_blur") or ())
    best_name, best_edge, best_auc = None, 0.0, None
    # Only measures that actually respond to blur can support a claim about focus.
    # A measure that separates the groups for some other reason (scene complexity,
    # subject size) would otherwise decide this verdict, which is how the first run
    # of this phase read as a success on `local_entropy` at AUC 0.61.
    best_blur_name, best_blur_edge, best_blur_auc = None, 0.0, None
    for name in cfg.get("measures") or ():
        auc = (arm.get(f"crop/{name}") or {}).get("auc")
        if auc is None:
            continue
        edge = abs(auc - 0.5)
        if edge > best_edge:
            best_name, best_edge, best_auc = name, edge, auc
        if name in tracks_blur and edge > best_blur_edge:
            best_blur_name, best_blur_edge, best_blur_auc = name, edge, auc

    if best_name is None:
        return None

    cvf = arm.get("_crop_vs_full") or {}
    detail = (
        f"Over {cfg.get('n_af_available')} image(s) with AF geometry, the best "
        f"blur-tracking measure on the crop is `{best_blur_name}` at AUC "
        f"{best_blur_auc} (0.5 = chance). Crop separates better than the full frame "
        f"for {cvf.get('crop_wins')}/{cvf.get('n_measures')} measures. "
    )
    if best_blur_edge >= _MATERIAL_AUC:
        return (
            COMPLEMENT,
            detail + "A cheap classical measure predicts real (AF-proxy) misfocus, so "
            "it is worth having alongside the learned scorers.",
        )

    # Nothing that responds to blur separated the groups. Say so plainly, and name
    # any better-scoring measure only as the confound it is.
    tail = (
        f"That is inside the +/-{_MATERIAL_AUC} materiality bar, so classical focus "
        "measures do not predict real misfocus on this population. "
    )
    if best_name not in tracks_blur and best_edge >= _MATERIAL_AUC:
        tail += (
            f"`{best_name}` scores higher (AUC {best_auc}) but does not track blur at "
            "all, so its separation reflects something else — scene complexity or "
            "subject size — not focus."
        )
    return NO_BENEFIT, detail + tail


def verdict_from_npz(track: str) -> tuple[str, str]:
    """Embedding / caption tracks: report whether the sweep has produced runs yet."""
    from scripts.research.clip_culling import common

    npz_dir = common.INPUT_SIZE_NPZ_DIR
    if not npz_dir.exists():
        return UNMEASURED, "No NPZ cache; run phase 2."
    crop_runs, full_runs = [], []
    for p in sorted(npz_dir.glob(f"{track}_*.npz")):
        parts = p.stem[len(track) + 1:].rsplit("_", 2)
        if len(parts) != 3:
            continue
        source = parts[1]
        (crop_runs if source.startswith("crop") else full_runs).append(p.name)
    if not crop_runs:
        return UNMEASURED, f"No crop runs for the {track} track yet; run phase 2."
    return (
        UNMEASURED,
        f"{len(crop_runs)} crop run(s) and {len(full_runs)} full-frame run(s) cached. "
        "Run `input_size_eval --all` and read "
        "`reports/clip-culling/input-size/` for the metrics; a verdict needs the "
        "grouping and pick-review numbers from there.",
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render(payload: dict) -> str:
    geometry = payload["geometry"]
    degradation = payload["degradation"]
    species = payload["species"]

    q_verdict, q_detail = verdict_quality(degradation)
    g_verdict, g_detail = verdict_geometry(geometry)
    s_verdict, s_detail = verdict_species(species)
    # Prefer measured eval metrics; fall back to describing the NPZ cache when the
    # eval has not been run, so the report never implies a verdict it does not have.
    summary = _read_eval_summary()
    e_verdict, e_detail = verdict_embedding(summary) or verdict_from_npz("embedding")
    c_verdict, c_detail = verdict_caption(summary) or verdict_from_npz("caption")
    f_verdict, f_detail = verdict_focus(payload.get("focus")) or (
        UNMEASURED, "No focus study yet; run phase 4."
    )
    geometry_ground_truth = (
        ((geometry or {}).get("label_eval") or {}).get(
            "ground_truth_kind", "human / derived"
        )
    )

    lines = [
        "# Bird bbox crop study — consolidated report",
        "",
        "> **Status:** point-in-time research memo, not a product spec. "
        "Production was read read-only throughout; nothing in this study writes to it.",
        "",
        "## Verdicts",
        "",
        "| Phase | Verdict | Ground truth | Basis |",
        "|---|---|---|---|",
        f"| Quality scoring (IQA) | **{q_verdict}** | constructed | {q_detail} |",
        f"| Bbox geometry (free signal) | **{g_verdict}** | {geometry_ground_truth} | {g_detail} |",
        f"| Species (BioCLIP) | **{s_verdict}** | derived | {s_detail} |",
        f"| Culling embeddings | **{e_verdict}** | constructed | {e_detail} |",
        f"| Captions (BLIP) | **{c_verdict}** | derived | {c_detail} |",
        f"| Focus (classical + AF) | **{f_verdict}** | derived | {f_detail} |",
        "",
        "### Ground-truth standing",
        "",
        "| Tag | Meaning |",
        "|---|---|",
        "| `human` | Human within-burst verdicts. Non-circular; the only basis for an accuracy claim. |",
        "| `agent-derived` | Vision-LLM consensus; independent of the scoring pipeline under test, but not human ground truth. |",
        "| `constructed` | True by construction (known degradation strength) or unbiased (EXIF capture-time bursts). |",
        "| `derived` | Compared against pipeline-produced columns (`rating`, `pick_status`, BLIP captions). Measures agreement with the incumbent stack, **not** accuracy. |",
        "",
    ]

    if geometry:
        bias = geometry.get("bias_probe") or {}
        lines += [
            "## The premise, measured",
            "",
            f"Corpus: **{_fmt(bias.get('n'))}** images with a real bird box.",
            "",
            "| Full-frame resize | bird long side p10 | p50 | p90 |",
            "|---|---|---|---|",
        ]
        for key, res in (bias.get("subject_resolution") or {}).items():
            edge = key.replace("full_frame_resize_to_", "")
            lines.append(
                f"| {edge} px | {_fmt(res.get('p10'))} | {_fmt(res.get('p50'))} | "
                f"{_fmt(res.get('p90'))} |"
            )
        af = bias.get("area_frac") or {}
        lines += [
            "",
            f"`area_frac` p10/p50/p90: **{_fmt(af.get('p10'))} / {_fmt(af.get('p50'))} / "
            f"{_fmt(af.get('p90'))}** — the median bird occupies a single-digit "
            "percentage of the frame, which is why full-frame downscaling loses it.",
            "",
        ]

    if degradation and degradation.get("verdict"):
        lines += [
            "## Degradation sensitivity (constructed ground truth)",
            "",
            "| Model | Degradation | Full-frame drop | Crop drop | Ratio |",
            "|---|---|---|---|---|",
        ]
        for model, per_kind in degradation["verdict"].items():
            if model.startswith("_"):
                continue
            for kind, v in per_kind.items():
                lines.append(
                    f"| {model} | {kind} | {_fmt(v.get('subject_degraded_full_frame_drop'))} | "
                    f"{_fmt(v.get('subject_degraded_crop_drop'))} | "
                    f"**{_fmt(v.get('crop_sensitivity_ratio'))}x** |"
                )
        lines.append("")

    lines += [
        "## Detail reports",
        "",
        "| Report | Present |",
        "|---|---|",
        f"| `geometry.md` | {'yes' if geometry else 'no'} |",
        f"| `degradation.md` | {'yes' if degradation else 'no'} |",
        f"| `species_crop.md` | {'yes' if species else 'no'} |",
        f"| `focus.md` | {'yes' if payload.get('focus') else 'no'} |",
        "| `reports/clip-culling/input-size/` | embedding / iqa / caption sweep output |",
        "",
        "## Caveats",
        "",
        "- **No human quality ground truth exists in the database.** `rating` and "
        "`label` are computed by `snorm.compute_all()` (`modules/pipeline.py:652`), "
        "`pick_status` by `cull_decision_to_pick_status()` "
        "(`modules/selection_policy.py:89`), and `title`/`description` are BLIP output "
        "(`modules/tagging.py:1569`). Any metric against those columns measures "
        "agreement with the incumbent stack, so it would penalise exactly the new "
        "information cropping adds. Hence the label set and the constructed metrics.",
        "- **The boxed population is still growing.** A `bird_bbox` backfill has been "
        "running during this study, so absolute counts and percentiles drift between "
        "runs; re-run once it settles before quoting final figures.",
        "- **`cropctx` is a no-op on this library.** The computed-context variant "
        "expands only 5 of ~25k boxes at 224 px (198 at 512 px) because 45MP frames "
        "already yield native boxes far larger than any model input. It is excluded "
        "from the default sweep and retained only for long edges >= 768.",
        "- **Only the top-1 box is stored.** `bird_bbox` holds a single object, so "
        "multi-bird frames are represented by their highest-confidence bird only.",
        "",
        "---",
        "",
        "Generated by `scripts.research.bird_crop.report`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    prod.configure_logging(args.verbose)

    payload = {
        "geometry": _read("geometry.json"),
        "degradation": _read("degradation.json"),
        "species": _read("species_crop.json"),
        "focus": _read("focus.json"),
    }
    missing = [k for k, v in payload.items() if v is None]
    if missing:
        logger.warning("Missing phase result(s): %s — reported as not yet measured.", missing)

    prod.write_text("REPORT.md", render(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
