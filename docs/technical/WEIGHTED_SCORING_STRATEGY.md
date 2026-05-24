# Weighted Scoring Strategy (Hybrid Pipeline)

## Overview

The image quality assessment system fuses a registry of models into three composites —
**technical**, **aesthetic**, and **general**. Weights and model membership are
config-driven (`scoring.fusion` and `scoring.models` in `config.json`); the committed
defaults live in `DEFAULT_COMPOSITE_WEIGHTS` / `DEFAULT_PERCENTILE_ANCHORS` in
[`modules/score_normalization.py`](../../modules/score_normalization.py).

## Composite Weights ("moderate" profile, May 2026)

Adopted after a model-score quality analysis over the 61,350-image corpus. `topiq` was
promoted into all three composites so **technical is no longer a LIQE alias**; `arniqa`
joined **general + technical** (May 2026) after a full-corpus backfill + calibration —
it is a technical NR-IQA signal (~uncorrelated with aesthetic), so it is intentionally
**not** in the aesthetic composite. `qpt_v2` stays shadow (not fused) pending upstream
inference code; KONIQ/PaQ2PiQ are excluded from fusion (~38% missing coverage).

| Composite | Weights (applied to **percentile-rescaled** scores) |
|-----------|------------------------------------------------------|
| **Technical** | TOPIQ 0.30 · ARNIQA 0.25 · SPAQ 0.25 · LIQE 0.20 |
| **Aesthetic** | AVA 0.40 · SPAQ 0.50 · LIQE 0.10 |
| **General** | LIQE 0.35 · SPAQ 0.30 · TOPIQ 0.13 · ARNIQA 0.10 · AVA 0.12 |

## Scoring Logic

1.  **Normalization**: Each model's raw output is mapped to 0.0 - 1.0 by its wrapper
    (`IScoringModel.normalize`).

2.  **Percentile rescaling**: Normalized scores are stretched against empirical
    `p02`/`p98` anchors so models with narrow native ranges (e.g. AVA) still discriminate
    before weighting (`rescale_percentile` in `score_normalization.py`). Current anchors:
    LIQE `0.311/0.998`, AVA `0.301/0.524`, SPAQ `0.257/0.760`, TOPIQ `0.390/0.709`,
    ARNIQA `0.467/0.746`.

3.  **Weighted calculation**: Each composite is a weighted mean of the rescaled scores,
    **re-normalized over the models actually present** so a missing model does not pull the
    composite toward 0 (`compute_composites`).

4.  **Rating + label**: The rescaled `general` score maps to a 1-5 star rating; technical
    and aesthetic composites drive the Lightroom color label.

## Rationale (Why this distribution?)

1.  **De-single-source technical**: blending TOPIQ + SPAQ with LIQE removes the
    redundancy where technical ≈ LIQE (Pearson ~0.98), widening discrimination at the top.
2.  **Aesthetic leans on SPAQ**: SPAQ separates the corpus better than AVA in raw form, so
    aesthetic weights SPAQ above AVA while keeping AVA for aesthetic semantics.
3.  **General stays balanced**: LIQE leads but SPAQ/TOPIQ/AVA each contribute, keeping
    `general` a balanced blend rather than a LIQE proxy.
4.  **VILA removed** in v2.5.1 for stability; LIQE fills the semantic niche.

## Related Documents

- [Docs index](../README.md)
- [Model weights](../reference/models/MODEL_WEIGHTS.md)
- [Suggested scoring adjustments](../planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md)
- [Multi-model scoring](MULTI_MODEL_SCORING.md)
- [Models summary](MODELS_SUMMARY.md)

