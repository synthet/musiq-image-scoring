# Model Summary

This project uses a hybrid ensemble of models to assess image quality from multiple
perspectives. The live scorer is the registry-driven `MultiModelHost`
(`modules/engines/host.py`): each model registers an `IScoringModel` wrapper, and
production vs. shadow membership is decided by `scoring.models` in `config.json` (see
[Multi-model scoring](MULTI_MODEL_SCORING.md)). `GET /api/models` returns the live set.

## 1. Google MUSIQ (Multi-scale Image Quality Transformer)
*TensorFlow Implementation*

The backbone of the scoring system. Processing multi-scale inputs to capture global and local details.

**Live variants** (registered by `modules/engines/factory.py`, fused — production):

| Variant | Dataset | Range | Role |
|---------|---------|-------|------|
| **SPAQ** | SPAQ | 0-100 | **Discrimination**. Smartphone photography dataset. |
| **AVA** | AVA | 1-10 | **Legacy Aesthetic**. Professional curation dataset. |

**Deprecated variants (not wired):** `KONIQ` (KonIQ-10k) and `PAQ2PIQ` (PaQ-2-PiQ)
are no longer registered into the live scorer. `make_musiq_wrappers` skips them with
a warning, and their score ranges are retained in `modules/engines/musiq_model.py`
only so historical `image_model_scores` rows still normalize.

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

## 4. ARNIQA (no-reference distortion-focused IQA)
*PyTorch Implementation (via `pyiqa`) — fused (production)*

**Status: Active (fused — production)**
Promoted from shadow into the live fusion (May 2026) after a full-corpus backfill
(61,350 images, 0 failures) and percentile calibration. Config
`scoring.models.arniqa: {enabled: true, shadow: false}`. ARNIQA targets *technical*
distortions — blur, noise, compression — and is ~uncorrelated with aesthetic
signals (Spearman ≈0.01 vs AVA, ≈0.54 vs TOPIQ), so it contributes to **general**
and **technical** composites only (intentionally absent from **aesthetic**).
- **Range**: 0.0 - 1.0 (higher is better; percentile anchors `p02≈0.467 / p98≈0.746`
  from the full-corpus distribution).
- **Fusion weights**: general 0.10, technical 0.25 (see [WEIGHTED_SCORING_STRATEGY.md](WEIGHTED_SCORING_STRATEGY.md)).
- **Head**: pyiqa default `arniqa` (KonIQ in-the-wild regression head, best fit for
  general photography); switchable via `scoring.arniqa.metric` (e.g. `arniqa-spaq`).
- **License**: Apache-2.0.
- **Module**: `modules/engines/arniqa_model.py` (wraps `modules/arniqa.py`).

## 5. QPT V2 (Quality-aware Pre-Training V2)
*PyTorch implementation (disabled — not registered)*

**Status: Disabled (WIP) — not in the live registry until #185**
`QptV2ModelWrapper` is not registered at import time; scoring does not load or run QPT V2.
Upstream
(`KeiChiTse/QPT-V2`) published **checkpoints only** (`iqa.pth`, `iaa.pth`, `vqa_*.pth`);
the inference code is an open upstream TODO. We reconstruct the HiViT-T architecture
locally in `modules/qpt_v2_arch.py` (derived from the `iqa.pth` state dict, strict-loads
all 172 tensors). Drop `iqa.pth` at `scoring.qpt_v2.checkpoint_path` (default
`models/qpt_v2.pth`) to activate.
- **Caveat**: the upstream inference recipe (preprocessing, pooling, merge order) is
  undocumented. Scores are directionally meaningful (blur lowers them) but **unvalidated
  and uncalibrated**; raw output is roughly `[-0.25, 0]`, *not* 0–1. Re-register in
  `modules/engines/__init__.py` after validation (#185). See
  [QPT-V2 issue #2](https://github.com/KeiChiTse/QPT-V2/issues/2).
- **Module**: `modules/engines/qpt_v2_model.py` (wraps `modules/qpt_v2.py`,
  arch in `modules/qpt_v2_arch.py`).

## 6. LLM-judge engines (Cursor / Claude)
*Optional, disabled by default*

`cursor` and `claude` are LLM-as-judge scoring engines that lazy-load their optional SDKs
and are disabled by default (`enabled: false`). When enabled they return an overall score
plus an optional multi-dimensional rubric carried in `scores_json`.

## 7. Model Correlation
*Based on internal testing (v2.5.0)*

- **High Correlation**: KONIQ <-> SPAQ (They generally agree).
- **Moderate**: KONIQ <-> PAQ2PIQ.
- **Low Correlation**: Technical Models <-> Aesthetic Models (AVA/LIQE). This is expected; a blur can be artistic (Good Aesthetic) but technically poor (Low Sharpness). The weighted score balances this.

## Deprecated: VILA (Vision-Language Aesthetics)

**Status: DISABLED (v2.5.1+)** — Replaced by LIQE.

Originally integrated for semantic scoring, but removed due to persistent instability with TensorFlow Hub loading and dependencies. Documentation preserved in [docs/archive/vila/](../archive/vila/).
