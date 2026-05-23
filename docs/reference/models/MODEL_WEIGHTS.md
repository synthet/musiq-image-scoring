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

1. Install the inference package:
   ```
   pip install git+https://github.com/KeiChiTse/QPT-V2
   ```
2. Download the HiViT-T checkpoint from the [GitHub releases](https://github.com/KeiChiTse/QPT-V2).
3. Place the file at `models/qpt_v2.pth` relative to the repo root,
   **or** set `scoring.qpt_v2.checkpoint_path` in `config.json` to an absolute path.

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

