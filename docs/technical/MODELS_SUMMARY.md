# Model Summary

This project uses a hybrid ensemble of models to assess image quality from multiple
perspectives. The live scorer is the registry-driven `MultiModelHost`
(`modules/engines/host.py`): each model registers an `IScoringModel` wrapper, and
production vs. shadow membership is decided by `scoring.models` in `config.json` (see
[Multi-model scoring](MULTI_MODEL_SCORING.md)). `GET /api/models` returns the live set.

## 1. Google MUSIQ (Multi-scale Image Quality Transformer)
*TensorFlow Implementation*

The backbone of the scoring system. Processing multi-scale inputs to capture global and local details.

| Variant | Dataset | Range | Role |
|---------|---------|-------|------|
| **KONIQ** | KonIQ-10k | 0-100 | **Reliability**. Large dataset of in-the-wild images. |
| **SPAQ** | SPAQ | 0-100 | **Discrimination**. Smartphone photography dataset. |
| **PAQ2PIQ**| PaQ-2-PiQ | 0-100 | **Detail**. Massive dataset, good for artifacts. |
| **AVA** | AVA | 1-10 | **Legacy Aesthetic**. Professional curation dataset. |

## 2. LIQE (Language-Image Quality Evaluator)
*PyTorch Implementation*

**Status: Active (fused — production)**
A state-of-the-art model (2023) that uses CLIP (Contrastive Language-Image Pre-training) to understand the *content* of an image, not just its pixels. Carries the largest `general` weight; see [Weighted scoring strategy](WEIGHTED_SCORING_STRATEGY.md) for current weights.
- **Strengths**: Understands "semantic" quality (e.g., a "good photo of a dog" vs just "sharp pixels").
- **Range**: 0.0 - 1.0
- **Speed**: Moderate (runs as subprocess).

## 3. TOPIQ (Top-down Image Quality)
*PyTorch Implementation (via `pyiqa`)*

**Status: Active (fused — production)**
A no-reference IQA model promoted into the live fusion after the May 2026 corpus
analysis. It contributes to all three composites under the "moderate" profile
(technical 0.35, general 0.15) so the technical score is no longer a LIQE alias.
- **Range**: 0.0 - 1.0 (percentile anchors `p02≈0.39 / p98≈0.71`)
- **Module**: `modules/engines/topiq_model.py` (wraps `modules/topiq.py`).

## 4. QPT V2 (Quality-aware Pre-Training V2)
*PyTorch Implementation (shadow)*

**Status: Shadow (not fused)**
Registered as a shadow model (`scoring.models.qpt_v2: {enabled: false, shadow: true}`):
it runs and stores scores into `image_model_scores` but is excluded from fusion. Upstream
inference code (`KeiChiTse/QPT-V2`) is not yet published, so the wrapper reports
`available=false` and produces no rows until the package ships. Calibration anchors are
blocked on that release (#185).
- **Module**: `modules/engines/qpt_v2_model.py` (wraps `modules/qpt_v2.py`).

## 5. LLM-judge engines (Cursor / Claude)
*Optional, disabled by default*

`cursor` and `claude` are LLM-as-judge scoring engines that lazy-load their optional SDKs
and are disabled by default (`enabled: false`). When enabled they return an overall score
plus an optional multi-dimensional rubric carried in `scores_json`.

## 6. Model Correlation
*Based on internal testing (v2.5.0)*

- **High Correlation**: KONIQ <-> SPAQ (They generally agree).
- **Moderate**: KONIQ <-> PAQ2PIQ.
- **Low Correlation**: Technical Models <-> Aesthetic Models (AVA/LIQE). This is expected; a blur can be artistic (Good Aesthetic) but technically poor (Low Sharpness). The weighted score balances this.

## Deprecated: VILA (Vision-Language Aesthetics)

**Status: DISABLED (v2.5.1+)** — Replaced by LIQE.

Originally integrated for semantic scoring, but removed due to persistent instability with TensorFlow Hub loading and dependencies. Documentation preserved in [docs/archive/vila/](../archive/vila/).
