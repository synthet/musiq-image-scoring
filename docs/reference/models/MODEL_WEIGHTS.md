# Current Model Weights and Scoring Logic

Here are the models and weights currently used in your project to calculate the scores:

### 1. General Score
* **25%** PaQ-2-PiQ
* **25%** LIQE
* **20%** AVA (MUSIQ)
* **20%** KonIQ (MUSIQ)
* **10%** SPAQ (MUSIQ)

### 2. Aesthetic Score
* **40%** AVA (MUSIQ)
* **30%** KonIQ (MUSIQ)
* **20%** SPAQ (MUSIQ)
* **10%** PaQ-2-PiQ

### 3. Technical Score
* **35%** PaQ-2-PiQ
* **35%** LIQE
* **15%** KonIQ (MUSIQ)
* **15%** SPAQ (MUSIQ)

*Note: These values are hardcoded defaults in `scripts/python/run_all_musiq_models.py` (and `modules/scoring.py`) since your `config.json` does not specify any overrides.*

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

