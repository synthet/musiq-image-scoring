# Current Model Weights and Scoring Logic

Composite weights for the **"moderate" profile** (adopted May 2026). Weights apply to
percentile-rescaled scores and are re-normalized over the models actually present.

### 1. General Score
* **38%** LIQE
* **32%** SPAQ (MUSIQ)
* **15%** TOPIQ
* **15%** AVA (MUSIQ)

### 2. Aesthetic Score
* **50%** SPAQ (MUSIQ)
* **40%** AVA (MUSIQ)
* **10%** LIQE

### 3. Technical Score
* **35%** TOPIQ
* **35%** LIQE
* **30%** SPAQ (MUSIQ)

### Percentile anchors (`p02` / `p98`)

| Model | p02 | p98 |
|-------|-----|-----|
| LIQE  | 0.311 | 0.998 |
| AVA   | 0.301 | 0.524 |
| SPAQ  | 0.257 | 0.760 |
| TOPIQ | 0.390 | 0.709 |

*Note: These are the committed defaults in
[`modules/score_normalization.py`](../../../modules/score_normalization.py)
(`DEFAULT_COMPOSITE_WEIGHTS` / `DEFAULT_PERCENTILE_ANCHORS`). Override per-deployment via
`scoring.fusion` and `percentile_anchors` in `config.json`. KONIQ and PaQ-2-PiQ are legacy
MUSIQ variants excluded from the default fusion (~38% missing coverage on the corpus).*

## QPT V2 (shadow — not yet in active ensemble)

QPT V2 (Quality-aware Pre-Training V2, ACM MM 2024) uses a HiViT-T backbone
(~19M parameters) pre-trained with masked image modeling. It is registered as a
**shadow** model (`scoring.models.qpt_v2: {enabled: false, shadow: true}`) — it
runs and stores scores but is excluded from composite fusion until promoted in #185.

### Checkpoint acquisition

> ⚠️ **Runs locally, but unvalidated.** Upstream [KeiChiTse/QPT-V2](https://github.com/KeiChiTse/QPT-V2)
> published **checkpoints only** (inference code is still an open TODO). The architecture is
> reconstructed locally in `modules/qpt_v2_arch.py` from the `iqa.pth` state dict and
> strict-loads all 172 tensors. The undocumented inference recipe means scores are
> directionally meaningful but **uncalibrated** — keep `qpt_v2` in shadow (see #185).

1. Download the task checkpoint from the repo's `checkpoints/` directory
   (`iqa.pth` for image quality, `iaa.pth` for aesthetics) — these are git-lfs files
   in-repo (~75 MB), not under GitHub releases. Direct URL:
   `https://media.githubusercontent.com/media/KeiChiTse/QPT-V2/master/checkpoints/iqa.pth`.
2. Place the file at `models/qpt_v2.pth` relative to the repo root (git-ignored),
   **or** set `scoring.qpt_v2.checkpoint_path` in `config.json` to an absolute path.
3. That's it — `QptV2Scorer` reports `available=true` and produces shadow scores.

### Target weights (post-calibration, issue #185)

| Dimension | QPT V2 | TOPIQ-NR | LIQE |
|-----------|--------|----------|------|
| General   | 55%    | 30%      | 15%  |
| Aesthetic | 75%    | —        | 25%  |
| Technical | 35%    | 65%      | —    |

Score range: **0.0 – 1.0** (verify empirically once inference code is released).

## Related Documents

- [Docs index](../../README.md)
- [Weighted scoring strategy](../../technical/WEIGHTED_SCORING_STRATEGY.md)
- [Multi-model scoring](../../technical/MULTI_MODEL_SCORING.md)
- [Technical summary](../../architecture/technical-summary.md)
- [Suggested scoring adjustments](../../planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md)

