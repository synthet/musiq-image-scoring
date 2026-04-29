# Weighted Scoring Strategy (Hybrid Pipeline)

## Overview

The image quality assessment system uses a **Hybrid Pipeline** combining Google's MUSIQ (Technical) and LIQE (Aesthetic/Semantic). This strategy leverages the strengths of specific models to filter technically flawed images while rewarding aesthetically pleasing ones.

## Score Weights (v2.5.2)

The final "Representative Score" is a weighted average of 5 models:

| Model | Weight | Role | Description |
|-------|--------|------|-------------|
| **KONIQ** | **30%** | Technical Reliability | Best general purpose technical scorer. High reliability. |
| **SPAQ** | **25%** | Technical Discrimination | Excellent at distinguishing fine technical details (sharpness, noise). |
| **PAQ2PIQ** | **20%** | Artifact Detection | Specialized in detecting compression artifacts and local defects. |
| **LIQE** | **15%** | Aesthetic/Semantic | State-of-the-art PyTorch model using CLIP. Understands "content" and aesthetics. |
| **AVA** | **10%** | Legacy Aesthetic | Older aesthetic model. Kept for continuity but de-emphasized. |
| **VILA** | **0%** | Disabled | Disabled in v2.5.1 due to stability issues. |

## Scoring Logic

1.  **Normalization**: All scores are normalized to a 0.0 - 1.0 range.
    *   SPAQ/KONIQ/PAQ2PIQ (0-100) -> /100
    *   AVA (1-10) -> (x-1)/9
    *   LIQE (0-1) -> Direct (already normalized)

2.  **Weighted Calculation**:
    ```python
    final_score = (
        (koniq_score * 0.30) +
        (spaq_score * 0.25) +
        (paq2piq_score * 0.20) +
        (liqe_score * 0.15) +
        (ava_score * 0.10)
    )
    ```

3.  **Outlier Detection**:
    *   If a model deviates significantly (> 2 standard deviations) from the consensus, it is flagged as an outlier.
    *   Robust metrics (Median, Trimmed Mean) are calculated alongside the weighted mean for reference.

## Rationale (Why this distribution?)

1.  **Technical First (75%)**: The primary goal is to filter technically flawed images (blurred, noisy, bad exposure). MUSIQ models (KONIQ, SPAQ, PAQ2PIQ) excel here.
2.  **Aesthetic Second (25%)**: Once technical quality is assured, we use LIQE (15%) and AVA (10%) to judge composition and beauty. LIQE is significantly more advanced than AVA.
3.  **VILA Removal**: VILA was removed from the active pipeline to improve system stability without sacrificing accuracy, as LIQE fills the semantic niche better.

## Related Documents

- [Docs index](../README.md)
- [Model weights](../reference/models/MODEL_WEIGHTS.md)
- [Suggested scoring adjustments](../planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md)
- [Multi-model scoring](MULTI_MODEL_SCORING.md)
- [Models summary](MODELS_SUMMARY.md)

