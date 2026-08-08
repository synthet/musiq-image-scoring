"""Step 2b — synthetic degradation with ground truth by construction.

The strongest IQA test available without human labels, and a direct test of the
study's central claim.

Take sharp images, apply a **known** degradation ladder, and check whether each
scorer's output tracks the true strength. The trick is applying the degradation
two ways:

* ``subject`` — degrade only the pixels inside the bird box
* ``frame``   — degrade the whole image

and scoring each of those two ways (full frame vs bbox crop). That gives a 2x2
whose expected pattern is explicit and falsifiable:

======================  ==================  ==================
                        scored full-frame   scored on crop
======================  ==================  ==================
subject degraded        **weak** response   strong response
whole frame degraded     strong response    strong response
======================  ==================  ==================

If full-frame scoring turns out to be just as sensitive to subject-only
degradation as crop scoring, the premise of this study is wrong and the rest of
it should be reconsidered. That is the point of running this first.

The ``frame`` ladder doubles as a **self-check**: any scorer that fails to rank a
whole-frame blur ladder monotonically indicates a harness bug, not a finding.

Reads production read-only; writes only into ``reports/bird-crop/``.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate

    # Cheap smoke: 12 images, one model
    python -m scripts.research.bird_crop.degradation_eval --limit 12 --models topiq

    # Default pass
    python -m scripts.research.bird_crop.degradation_eval --limit 120

    # Everything (slow; detach it)
    python -m scripts.research.bird_crop.degradation_eval --limit 400 \\
        --models liqe,topiq,arniqa,spaq,ava

    # The pinned study population every other track measures
    python -m scripts.research.bird_crop.degradation_eval \\
        --image-ids-file reports/bird-crop/study_image_ids.txt
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np

from scripts.research.bird_crop import bursts, crops, focus_measures, prod
from scripts.research.bird_crop.bbox import padded_box, parse_bbox

logger = logging.getLogger("bird_crop.degradation_eval")

#: Degradation ladder. 0 is the untouched original, so every series has a clean
#: anchor and monotonicity is measured against a real baseline.
BLUR_SIGMAS = (0.0, 0.8, 1.6, 3.2, 6.4)
NOISE_SIGMAS = (0.0, 4.0, 8.0, 16.0, 32.0)
MOTION_LENGTHS = (0, 5, 11, 21, 41)

DEGRADATIONS = ("blur", "motion", "noise")
REGIONS = ("subject", "frame")

#: Scored at a single long edge so the only variables are framing and degradation.
DEFAULT_LONG_EDGE = 512

#: Working resolution: each frame is downscaled to this long edge **once**, before
#: any degradation. Degrading a full 45MP frame costs 1.5-3.3 s per rung, and the
#: sweep applies 30 rungs per image, which is prohibitive. 3000 px keeps the median
#: bird box (~25% of frame width) at ~750 px — comfortably above the 512 px model
#: input, so crops are still never upscaled — while cutting degradation cost ~7x.
#: Both arms of every comparison see the identical damaged image, so this changes
#: absolute scale, not the crop-vs-full conclusion.
DEFAULT_WORK_LONG_EDGE = 3000

DEFAULT_MODELS = ("liqe", "topiq")
ALL_MODELS = ("liqe", "topiq", "arniqa", "spaq", "ava")

#: Zero-inference focus measures, scored through the same ladders as the learned
#: models so the two are directly comparable on identical images. See
#: ``focus_measures`` for why they are worth measuring and how noise fools them.
CLASSICAL_MODELS = tuple(focus_measures.MEASURES)

#: Everything ``--models`` accepts.
KNOWN_MODELS = ALL_MODELS + CLASSICAL_MODELS


# ---------------------------------------------------------------------------
# Degradations (operate on a PIL image, optionally masked to the box)
# ---------------------------------------------------------------------------
def _apply_blur(img, strength: float):
    from PIL import ImageFilter

    if strength <= 0:
        return img.copy()
    return img.filter(ImageFilter.GaussianBlur(radius=float(strength)))


def _apply_motion(img, strength: float):
    """Horizontal box blur — a stand-in for panning motion blur.

    Done with a numpy sliding-window mean rather than ``ImageFilter.Kernel``, which
    only accepts 3x3 and 5x5 kernels and so cannot express the longer smears that
    make this ladder useful.
    """
    from PIL import Image

    n = int(strength)
    if n <= 1:
        return img.copy()

    from scipy.ndimage import uniform_filter1d

    arr = np.asarray(img, dtype=np.float32)
    # Vectorised sliding mean along x. uniform_filter1d is a C loop over the whole
    # array; a per-row np.apply_along_axis is ~16k Python calls on a 45MP frame and
    # made the sweep unusably slow. 'reflect' keeps the frame edges from darkening,
    # which would otherwise show up as a vignette the scorer reacts to.
    smeared = uniform_filter1d(arr, size=n, axis=1, mode="reflect")
    return Image.fromarray(np.clip(smeared, 0, 255).astype(np.uint8))


def _apply_noise(img, strength: float):
    if strength <= 0:
        return img.copy()
    from PIL import Image

    arr = np.asarray(img, dtype=np.float32)
    rng = np.random.default_rng(12345)
    noisy = arr + rng.normal(0.0, float(strength), arr.shape)
    return Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))


_DEGRADE: dict[str, Callable[[Any, float], Any]] = {
    "blur": _apply_blur,
    "motion": _apply_motion,
    "noise": _apply_noise,
}

_LADDER: dict[str, tuple[float, ...]] = {
    "blur": BLUR_SIGMAS,
    "motion": tuple(float(x) for x in MOTION_LENGTHS),
    "noise": NOISE_SIGMAS,
}


def degrade(img, kind: str, strength: float, *, region_box: Optional[tuple] = None):
    """Return a copy of *img* degraded by *kind* at *strength*.

    With *region_box* the degradation is composited back into that rectangle only,
    leaving the rest of the frame untouched — that is what isolates "the subject is
    soft" from "the photo is soft".
    """
    fn = _DEGRADE[kind]
    if region_box is None:
        return fn(img, strength)

    out = img.copy()
    if strength <= 0:
        return out
    left, top, right, bottom = region_box
    patch = out.crop((left, top, right, bottom))
    out.paste(fn(patch, strength), (left, top))
    return out


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _get_scorer(model_name: str):
    """Build an IQA scorer, reusing the input-size harness's factory.

    Deliberately delegated rather than reimplemented: the torch scorers take
    ``device`` in the constructor and have no ``load_model``, while MUSIQ needs
    ``load_model(name)`` on a ``MultiModelMUSIQ`` runner. Keeping one factory means
    the crop study cannot drift from the resolution study it is compared against.
    """
    if model_name in CLASSICAL_MODELS:
        # No weights, no device, nothing to unload — the "scorer" is the measure.
        return focus_measures.MEASURES[model_name]

    from scripts.research.clip_culling.input_size_embed import _get_iqa_scorer

    if model_name not in ALL_MODELS:
        raise ValueError(f"Unknown model {model_name!r}; expected one of {KNOWN_MODELS}")
    return _get_iqa_scorer(model_name)




def score_pil(img, scorer, model_name: str, long_edge: int) -> Optional[float]:
    """Score a PIL image at *long_edge*, reusing the harness's temp-JPEG path.

    Every production IQA engine takes a *path*, not a PIL image
    (``modules/engines/base.py:30``), and MUSIQ reads raw file bytes, so the temp
    JPEG is the same manoeuvre ``MultiModelHost._resolve_processing_path`` already
    uses for RAW. The harness helper also applies ``long_edge`` the way each model
    expects (``max_dimension`` for the torch scorers, ``resolution_override`` for
    MUSIQ, which additionally bypasses MUSIQ's crop-blind preprocess cache), so the
    image is resampled exactly once.

    Classical focus measures deliberately **bypass** that temp JPEG. JPEG
    compression discards high-frequency content, which is precisely what a
    Laplacian or gradient measure reads, so routing them through a re-encode would
    measure the codec as much as the lens. They score the array directly.
    """
    try:
        if model_name in CLASSICAL_MODELS:
            # crops.resize_to_long_edge matches clip_culling.common.load_pil_resized,
            # which is how the learned scorers see long_edge, so both arms get the
            # same pixel budget and only the measurement differs.
            resized = crops.resize_to_long_edge(img, long_edge)
            value = scorer(np.asarray(resized.convert("L"), dtype=np.float64))
            return float(value) if np.isfinite(value) else None

        from scripts.research.clip_culling.input_size_embed import _score_iqa_temp_path

        return _score_iqa_temp_path(img, scorer, model_name, long_edge)
    except Exception as exc:  # noqa: BLE001 — one bad score must not kill the sweep
        logger.warning("%s scoring failed: %s", model_name, exc)
        return None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def sensitivity(strengths: Sequence[float], scores: Sequence[Optional[float]]) -> dict:
    """How well a score series tracks the true degradation strength.

    ``spearman`` should be strongly **negative**: more degradation, lower quality.
    ``relative_drop`` is the fall from clean to worst, as a fraction of the clean
    score, which makes magnitudes comparable across models with different ranges.
    """
    pairs = [(s, v) for s, v in zip(strengths, scores) if v is not None and np.isfinite(v)]
    if len(pairs) < 3:
        return {"spearman": None, "relative_drop": None, "n": len(pairs)}

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    # A scorer completely blind to the degradation returns a constant series, for
    # which rank correlation is undefined (and scipy warns). That is a meaningful
    # result, not an error: report no correlation and let relative_drop carry it.
    if len(set(ys)) == 1:
        rho = None
    else:
        from scipy.stats import spearmanr

        rho = spearmanr(xs, ys).correlation

    clean = ys[0] if xs[0] == 0 else None
    drop = None
    if clean not in (None, 0):
        drop = (clean - min(ys)) / abs(clean)
    return {
        "spearman": round(float(rho), 4) if rho is not None and np.isfinite(rho) else None,
        "relative_drop": round(float(drop), 4) if drop is not None else None,
        "n": len(pairs),
    }


def _aggregate(per_image: list[dict]) -> dict:
    """Mean of the per-image sensitivities, plus how many were monotonic."""
    rhos = [r["spearman"] for r in per_image if r.get("spearman") is not None]
    drops = [r["relative_drop"] for r in per_image if r.get("relative_drop") is not None]
    return {
        "n_images": len(per_image),
        "mean_spearman": round(float(np.mean(rhos)), 4) if rhos else None,
        "median_spearman": round(float(np.median(rhos)), 4) if rhos else None,
        "mean_relative_drop": round(float(np.mean(drops)), 4) if drops else None,
        # A correct scorer should call more degradation "worse", i.e. rho <= -0.9.
        "pct_strongly_monotonic": (
            round(100.0 * float(np.mean([r <= -0.9 for r in rhos])), 1) if rhos else None
        ),
    }


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------
def run(
    *,
    models: Sequence[str],
    limit: int,
    long_edge: int,
    folders: Optional[Sequence[int]],
    kinds: Sequence[str],
    crop_variant: str = "crop",
    work_long_edge: int = DEFAULT_WORK_LONG_EDGE,
    image_ids: Optional[Sequence[int]] = None,
    image_ids_file: Optional[str] = None,
) -> dict:
    rows = bursts.load_boxed_rows(folders=folders, image_ids=image_ids)
    boxed = [r for r in rows if parse_bbox(r.get("bird_bbox")) is not None]
    if image_ids is not None and len(boxed) != len(rows):
        # The SQL only asks whether bird_bbox has an 'x1' key; parse_bbox also
        # validates the geometry. A pinned run must not quietly measure fewer.
        unparseable = sorted(
            r["id"] for r in rows if parse_bbox(r.get("bird_bbox")) is None
        )
        raise SystemExit(
            f"{len(unparseable)} pinned image id(s) have a bird_bbox that does not "
            f"parse into a usable box (e.g. {unparseable[:10]}). Re-generate the "
            "pinned set with `python -m scripts.research.bird_crop.pin_study_set --force`."
        )
    rows = boxed
    if limit and limit > 0 and len(rows) > limit:
        step = max(1, len(rows) // limit)
        rows = rows[::step][:limit]
    logger.info("Degradation study on %d image(s), models=%s", len(rows), list(models))

    results: dict = {
        "config": {
            "models": list(models),
            "n_images_requested": len(rows),
            "long_edge": long_edge,
            "work_long_edge": work_long_edge,
            "crop_variant": crop_variant,
            "ladders": {k: list(_LADDER[k]) for k in kinds},
            "folders": list(folders) if folders else "all",
            "image_ids_file": image_ids_file,
            "n_pinned_ids": len(image_ids) if image_ids is not None else None,
        },
        "by_model": {},
    }

    for model_name in models:
        try:
            scorer = _get_scorer(model_name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not load %s: %s", model_name, exc)
            results["by_model"][model_name] = {"error": str(exc)}
            continue

        # cell key: "{kind}/{region}/{scored_on}"
        cells: dict[str, list[dict]] = {}
        for idx, row in enumerate(rows, start=1):
            prepared = _prepare(row, crop_variant=crop_variant, work_long_edge=work_long_edge)
            if prepared is None:
                continue
            oriented, region_box, crop_rect = prepared

            for kind in kinds:
                ladder = _LADDER[kind]
                for region in REGIONS:
                    box_arg = region_box if region == "subject" else None
                    full_scores, crop_scores = [], []
                    for strength in ladder:
                        damaged = degrade(oriented, kind, strength, region_box=box_arg)
                        # No pre-resize: score_pil applies long_edge the way each
                        # model expects, so the image is resampled exactly once.
                        full_scores.append(score_pil(damaged, scorer, model_name, long_edge))
                        crop_scores.append(
                            score_pil(damaged.crop(crop_rect), scorer, model_name, long_edge)
                        )
                    cells.setdefault(f"{kind}/{region}/full", []).append(
                        sensitivity(ladder, full_scores)
                    )
                    cells.setdefault(f"{kind}/{region}/crop", []).append(
                        sensitivity(ladder, crop_scores)
                    )
            if idx % 10 == 0 or idx == len(rows):
                logger.info("[%s] %d/%d images", model_name, idx, len(rows))

        results["by_model"][model_name] = {k: _aggregate(v) for k, v in sorted(cells.items())}
        _unload(scorer)

    results["verdict"] = _verdict(results)
    return results


def _prepare(row: dict, *, crop_variant: str, work_long_edge: int):
    """Decode one image, downscale to the working resolution, and compute rectangles.

    The box is rescaled **after** the working-resolution downscale, so coordinates
    always match the pixels actually being degraded.
    """
    path = row.get("file_path")
    if not path or not os.path.exists(path):
        return None
    try:
        oriented = crops.load_oriented(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("decode failed id=%s: %s", row.get("id"), exc)
        return None

    oriented = crops.resize_to_long_edge(oriented, work_long_edge)

    box = parse_bbox(row.get("bird_bbox"))
    if box is None:
        return None
    box = crops.rescale_box(box, *oriented.size)

    # Degrade exactly the tight box; crop with the variant's padding. Keeping them
    # different is deliberate: the crop is what a model would really be fed.
    region_box = padded_box(box, pad=0.0)
    spec = crops.parse_variant(crop_variant)
    crop_rect = padded_box(box, pad=spec.pad)
    return oriented, region_box, crop_rect


def _unload(scorer) -> None:
    for name in ("unload", "unload_model", "close"):
        fn = getattr(scorer, name, None)
        if callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass
            return


def _verdict(results: dict) -> dict:
    """Compare crop vs full-frame sensitivity to *subject-only* degradation.

    The falsifiable core: if cropping does not buy materially more sensitivity
    here, the study's premise fails.

    **Effect size is measured with ``relative_drop``, not Spearman.** Spearman
    saturates at -1.0 for every cell — the ladder is monotonic and all these
    scorers respond monotonically — so it cannot distinguish "noticed slightly"
    from "noticed a lot". It is retained as the direction/sanity check;
    ``relative_drop`` (how far the score actually falls from clean to worst) is
    what separates the cells.
    """
    out: dict = {}
    for model_name, cells in results["by_model"].items():
        if not isinstance(cells, dict) or "error" in cells:
            continue
        per_kind = {}
        for kind in DEGRADATIONS:
            subj_full = cells.get(f"{kind}/subject/full") or {}
            subj_crop = cells.get(f"{kind}/subject/crop") or {}
            frame_full = cells.get(f"{kind}/frame/full") or {}
            full_drop = subj_full.get("mean_relative_drop")
            crop_drop = subj_crop.get("mean_relative_drop")
            if full_drop is None or crop_drop is None:
                continue
            per_kind[kind] = {
                "subject_degraded_full_frame_drop": full_drop,
                "subject_degraded_crop_drop": crop_drop,
                # >1 means the crop responds more strongly than the full frame.
                "crop_sensitivity_ratio": (
                    round(crop_drop / full_drop, 2) if full_drop else None
                ),
                "whole_frame_control_drop": frame_full.get("mean_relative_drop"),
                "monotonicity_check": {
                    "subject_full_spearman": subj_full.get("mean_spearman"),
                    "subject_crop_spearman": subj_crop.get("mean_spearman"),
                    "whole_frame_spearman": frame_full.get("mean_spearman"),
                },
            }
        if per_kind:
            out[model_name] = per_kind
    out["_reading"] = (
        "crop_sensitivity_ratio > 1 means the crop responds more strongly than the "
        "full frame to the *bird alone* being degraded, supporting the study's "
        "premise; ~1 would refute it. Spearman is only a direction check and "
        "saturates at -1.0, so it is not used for effect size. "
        "whole_frame_* is the harness self-check: it must be strongly negative and "
        "monotonic for every model regardless of framing."
    )
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def render_markdown(payload: dict) -> str:
    cfg = payload["config"]
    lines = [
        "# Bird crop vs full frame — synthetic degradation sensitivity",
        "",
        "> Ground truth **by construction**: the degradation strength is known, so "
        "this needs no human labels and cannot be circular.",
        "",
        f"Images: **{cfg['n_images_requested']}** · scored at long edge "
        f"**{cfg['long_edge']}** · working resolution **{cfg.get('work_long_edge')}** · "
        f"crop variant **{cfg['crop_variant']}** · models {cfg['models']}",
        "",
        "## Verdict — sensitivity to subject-only degradation",
        "",
        "Effect size is the **relative score drop** from clean to worst. Spearman is "
        "not used here: it saturates at -1.0 in every cell, so it confirms direction "
        "but cannot separate \"noticed slightly\" from \"noticed a lot\".",
        "",
        "`crop_sensitivity_ratio > 1` supports the premise; ~1 would refute it.",
        "",
        "| Model | Degradation | Full-frame drop | Crop drop | Sensitivity ratio | Whole-frame control |",
        "|---|---|---|---|---|---|",
    ]
    verdict = payload.get("verdict", {})
    for model_name, per_kind in verdict.items():
        if model_name.startswith("_"):
            continue
        for kind, v in per_kind.items():
            lines.append(
                f"| {model_name} | {kind} | "
                f"{v['subject_degraded_full_frame_drop']} | "
                f"{v['subject_degraded_crop_drop']} | "
                f"**{v['crop_sensitivity_ratio']}x** | {v['whole_frame_control_drop']} |"
            )

    mono = [
        (m, k, v["monotonicity_check"])
        for m, per_kind in verdict.items()
        if not m.startswith("_")
        for k, v in per_kind.items()
    ]
    # Only a near-zero or positive correlation indicates a broken harness. A
    # correlation that is negative but shallow means the model genuinely responds
    # weakly to that degradation — a property of the model, and itself a finding.
    broken = [
        f"{m}/{k}"
        for m, k, c in mono
        if c.get("whole_frame_spearman") is not None and c["whole_frame_spearman"] > -0.5
    ]
    weak = [
        f"{m}/{k} (ρ={c['whole_frame_spearman']})"
        for m, k, c in mono
        if c.get("whole_frame_spearman") is not None
        and -0.9 < c["whole_frame_spearman"] <= -0.5
    ]
    lines += ["", "### Harness self-check", ""]
    if broken:
        lines.append(
            f"⚠️ **Suspect**: {broken} — a scorer that cannot rank a *whole-frame* "
            "degradation ladder at all points to a harness bug rather than a finding."
        )
    else:
        lines.append(
            "Passed: every model ranks the whole-frame ladder in the right direction, "
            "so the degradation ladders and scoring path are behaving."
        )
    if weak:
        lines.append("")
        lines.append(
            f"Weak but correctly-signed whole-frame response: {weak}. That is a "
            "property of the model (limited sensitivity to that degradation), not a "
            "harness problem — LIQE in particular responds only weakly to noise."
        )

    lines += ["", "## Full cell detail", "", "| Model | kind/region/scored-on | mean ρ | mean rel. drop | % monotonic | n |", "|---|---|---|---|---|---|"]
    for model_name, cells in payload["by_model"].items():
        if not isinstance(cells, dict) or "error" in cells:
            lines.append(f"| {model_name} | — | error: {cells.get('error')} | | | |")
            continue
        for cell, agg in cells.items():
            lines.append(
                f"| {model_name} | `{cell}` | {agg['mean_spearman']} | "
                f"{agg['mean_relative_drop']} | {agg['pct_strongly_monotonic']} | {agg['n_images']} |"
            )

    lines += [
        "",
        "### Ladders",
        "",
    ]
    for kind, ladder in cfg["ladders"].items():
        lines.append(f"- **{kind}**: {ladder}")
    lines += [
        "",
        "---",
        "",
        "Generated by `scripts.research.bird_crop.degradation_eval`. "
        "Production was read read-only; nothing was written to it.",
        "",
    ]
    return "\n".join(lines)


#: Config fields that must match for two runs' models to sit in one table. If any
#: differs, the runs measured different things and merging them would invent a
#: comparison that was never made.
_COMPARABLE_KEYS = (
    "n_images_requested", "n_pinned_ids", "image_ids_file", "long_edge",
    "work_long_edge", "crop_variant", "ladders", "folders",
)


def _merge_with_existing(payload: dict) -> dict:
    """Carry forward models measured by an earlier run on the same population.

    Without this, ``--models laplacian_variance`` silently discards the liqe /
    topiq / arniqa results a previous pass wrote, because the whole file is
    rewritten. That is the same class of silent loss the pinned population exists
    to prevent, and it is easy to trigger: the natural way to add a model is to
    run it alone. Merging is refused when the two runs are not comparable.
    """
    existing = _read_existing_degradation()
    if not existing:
        return payload

    old_cfg, new_cfg = existing.get("config") or {}, payload.get("config") or {}
    mismatched = [k for k in _COMPARABLE_KEYS if old_cfg.get(k) != new_cfg.get(k)]
    if mismatched:
        logger.warning(
            "Existing degradation.json measured a different setup (%s differ); "
            "replacing it rather than merging.", ", ".join(mismatched),
        )
        return payload

    carried = [m for m in existing.get("by_model", {}) if m not in payload.get("by_model", {})]
    if not carried:
        return payload

    merged = dict(payload)
    merged["by_model"] = {**existing["by_model"], **payload["by_model"]}
    merged["verdict"] = _verdict(merged)
    logger.info("Carried forward %d previously measured model(s): %s", len(carried), carried)
    return merged


def _read_existing_degradation() -> Optional[dict]:
    import json

    path = prod.REPORTS_DIR / "degradation.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help=(
            f"Comma list. Learned IQA: {ALL_MODELS}. Zero-inference focus measures "
            f"(no GPU): {CLASSICAL_MODELS}. Default: {','.join(DEFAULT_MODELS)}"
        ),
    )
    parser.add_argument("--limit", type=int, default=120, help="Images to sample (0 = all; slow)")
    parser.add_argument("--long-edge", type=int, default=DEFAULT_LONG_EDGE)
    parser.add_argument(
        "--work-long-edge",
        type=int,
        default=DEFAULT_WORK_LONG_EDGE,
        help=(
            "Downscale each frame to this long edge once before degrading "
            "(default: {}). Keeps crops above the model input while making the "
            "sweep affordable; 0 uses native resolution (slow)."
        ).format(DEFAULT_WORK_LONG_EDGE),
    )
    parser.add_argument("--folders", default="", help="Comma-separated folder_id list")
    parser.add_argument(
        "--image-ids-file",
        default=None,
        help=(
            "Pin the population to an explicit list of production image ids, one per "
            "line, replacing --folders/--limit selection. Use this so the degradation "
            "arm measures the same images as the embedding, IQA, caption and species "
            "tracks. Generate with scripts/research/bird_crop/pin_study_set.py."
        ),
    )
    parser.add_argument(
        "--kinds",
        default=",".join(DEGRADATIONS),
        help=f"Degradations to apply, from {DEGRADATIONS}",
    )
    parser.add_argument("--crop-variant", default="crop", help="Crop variant to score (default: crop)")
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Re-render the markdown report from the saved degradation.json; run no models.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    prod.configure_logging(args.verbose)

    if args.render_only:
        import json

        src = prod.REPORTS_DIR / "degradation.json"
        if not src.exists():
            raise SystemExit(f"No saved results at {src}; run the sweep first.")
        with open(src, encoding="utf-8") as f:
            payload = json.load(f)
        prod.write_text("degradation.md", render_markdown(payload))
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in models if m not in KNOWN_MODELS]
    if unknown:
        raise SystemExit(f"Unknown model(s) {unknown}; expected from {list(KNOWN_MODELS)}")
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    bad_kinds = [k for k in kinds if k not in DEGRADATIONS]
    if bad_kinds:
        raise SystemExit(f"Unknown degradation(s) {bad_kinds}; expected from {list(DEGRADATIONS)}")
    try:
        crops.parse_variant(args.crop_variant)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    prod.assert_prod()
    folders = [int(x) for x in args.folders.split(",") if x.strip()] or None

    image_ids = None
    limit = args.limit
    if args.image_ids_file:
        from scripts.research.bird_crop.pin_study_set import read_ids

        image_ids = read_ids(Path(args.image_ids_file))
        # The pinned list *is* the population; --limit would strided-sample it,
        # which is the exact bug the pin exists to prevent.
        limit = 0
        logger.info(
            "Pinned to %d image id(s) from %s (--limit ignored)",
            len(image_ids), args.image_ids_file,
        )

    payload = run(
        models=models,
        limit=limit,
        long_edge=args.long_edge,
        folders=folders,
        kinds=kinds,
        crop_variant=args.crop_variant,
        work_long_edge=args.work_long_edge,
        image_ids=image_ids,
        image_ids_file=args.image_ids_file,
    )
    payload = _merge_with_existing(payload)
    prod.write_json("degradation.json", payload)
    prod.write_text("degradation.md", render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
