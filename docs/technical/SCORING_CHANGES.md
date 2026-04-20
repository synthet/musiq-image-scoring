# Image Scoring Pipeline V2: Changes Summary

## 1. Overview
The image scoring pipeline has been updated based on comprehensive research into model performance, correlation, and resource efficiency. The new system prioritizes **LIQE** for technical quality and a weighted blend of **AVA** and **SPAQ** for aesthetic quality, while deprecating older, less efficient models.

## 2. Model Changes

| Model | Status | Role | Reason |
| :--- | :--- | :--- | :--- |
| **LIQE** | **Active** | **Technical Quality** | Best correlation with human perceived quality/sharpness. |
| **AVA** | **Active** | **Aesthetic Quality** | Strong baseline for artistic composition ratings. |
| **SPAQ** | **Active** | **Hybrid Quality** | Bridges technical and smartphone-style aesthetic preferences. |
| **KoNIQ-10k** | *Removed* | N/A | High resource usage, high latency, redundant signal. |
| **PaQ2PiQ** | *Removed* | N/A | Lower correlation than LIQE/SPAQ ensemble. |

## 3. New Scoring Formulas

The **General Score** (0.0 - 1.0) is now a weighted average:

$$
\text{Score}_{\text{General}} = 0.50 \times \text{LIQE} + 0.30 \times \text{AVA} + 0.20 \times \text{SPAQ}
$$

### Component Breakdowns

*   **Technical Score**:
    *   `100% LIQE` (Normalized)
*   **Aesthetic Score**:
    *   `60% AVA` (Normalized) + `40% SPAQ` (Normalized)

*Note: All raw model outputs are normalized to a 0-1 range before combining.*

## 4. Preprocessing Standards

To ensure consistency with the models' training data and optimal inference performance:

*   **Resolution**: Fixed **512x512** pixels.
*   **Scaling**: **Bicubic** interpolation.
*   **Padding**: Images are **letterboxed** (padded with black) to maintain aspect ratio within the 512x512 square, rather than stretching or cropping.
*   **Source**: Prioritizes embedded JPEGs (ExifTool) for speed, falling back to `rawpy` preview extraction if needed.

## 5. Database Updates
*   **Recalculation**: The `recalc_scores.py` script has updated **38,853** images in the library.
*   **Backup**: A database backup was automatically created before applying these changes.
