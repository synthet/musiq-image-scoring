# Suggested Adjustments to Scoring Weights

## Evaluation Criteria
*   **Performance:** MUSIQ is now outperformed by models like LIQE, QPT V2, and AesMamba on AVA and technical benchmarks.
*   **LIQE:** Stronger than MUSIQ variants for both technical and aesthetic scoring.
*   **PaQ-2-PiQ:** Still provides technical robustness but should be balanced with newer models.
*   **SPAQ:** Carries less weight in current benchmarks.
*   **General Scoring:** Should reflect a blend of aesthetics and perceptual quality, giving more weight to generalizable models.

## 1. 🧠 General Score (Aesthetic + Technical Blend)

**Recommended Weights:**
*   **30%** LIQE
*   **25%** PaQ-2-PiQ
*   **25%** KonIQ (MUSIQ)
*   **10%** AVA (MUSIQ)
*   **10%** SPAQ (MUSIQ)

**Why:**
LIQE provides strong technical + semantic features. KonIQ is more perceptually robust than AVA. MUSIQ-AVA and SPAQ can still contribute but should be deprioritized.

## 2. 🎨 Aesthetic Score

**Recommended Weights:**
*   **50%** LIQE
*   **30%** AVA (MUSIQ)
*   **10%** KonIQ (MUSIQ)
*   **10%** PaQ-2-PiQ

**Why:**
LIQE has better correlation with AVA (~0.776) than MUSIQ (~0.726). AVA remains important for pure aesthetics. PaQ-2-PiQ plays a minimal aesthetic role, so reduce it further.

## 3. 🛠 Technical Score

**Recommended Weights:**
*   **40%** PaQ-2-PiQ
*   **35%** LIQE
*   **15%** KonIQ (MUSIQ)
*   **10%** SPAQ (MUSIQ)

**Why:**
PaQ-2-PiQ and LIQE remain the best performers for technical perception. KonIQ helps for perceptual artifacts, and SPAQ contributes minimally.

## 🧪 Optional (Future Enhancement)
If you adopt **QPT V2** or **AesMamba**, you can eventually:
*   Use them as a single scorer for General or Aesthetic (weight = 60–70%)
*   Reduce legacy MUSIQ variants to ~5–10% each

## Related Documents

- [Docs index](../../INDEX.md)
- [Model weights](../../reference/models/MODEL_WEIGHTS.md)
- [Weighted scoring strategy](../../technical/WEIGHTED_SCORING_STRATEGY.md)
- [IAA paper analysis](../../reports/IAA_PAPER_ANALYSIS.md)

