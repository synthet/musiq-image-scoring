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

## Related Documents

- [Docs index](../../README.md)
- [Weighted scoring strategy](../../technical/WEIGHTED_SCORING_STRATEGY.md)
- [Multi-model scoring](../../technical/MULTI_MODEL_SCORING.md)
- [Technical summary](../../architecture/technical-summary.md)
- [Suggested scoring adjustments](../../planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md)

