# Model Input Specifications

This document describes the input format, score ranges, and constraints for the neural network models used in the Vexlum Scoring project.

## Overview

| Model Family | Models | Framework | Input Type |
|-------------|--------|-----------|------------|
| MUSIQ | SPAQ, AVA, KonIQ, PaQ2PiQ | TensorFlow | JPEG bytes |
| LIQE | LIQE | PyTorch (PyIQA) | PIL Image tensor |

---

## 1. MUSIQ Models (SPAQ, AVA, KonIQ, PaQ2PiQ)

**Reference:** [MUSIQ: Multi-scale Image Quality Transformer (arxiv.org/abs/2108.05997)](https://arxiv.org/abs/2108.05997)

### Input Format

- **Type:** Raw JPEG bytes (TensorFlow Hub `image_bytes_tensor`)
- **Parameter name:** `image_bytes_tensor` (MUSIQ)
- **Preprocessing:** None required. The model handles variable sizes and aspect ratios internally.

### Documentation

- MUSIQ is designed to process **native resolution images with varying sizes and aspect ratios**
- No fixed-shape constraint; avoids CNN-style resize/crop that degrades quality
- Multi-scale patch-based Transformer with hash-based 2D spatial embedding

### Model Score Ranges (Raw Output)

| Model | Raw Range | Source | Notes |
|-------|-----------|--------|-------|
| SPAQ | 0–100 | SPAQ dataset | |
| AVA | 1–10 | AVA dataset | |
| KonIQ | 0–100 | KONIQ-10k | |
| PaQ2PiQ | 0–100 | PAQ2PIQ | |

**Normalization:** `(score - min) / (max - min)` → 0–1 for weighted scoring.

### Source Variability

Different sources (TensorFlow Hub, Kaggle Hub, local .npz) may produce slightly different raw ranges. Normalization must be applied per-source. The project uses `model_ranges` in `run_all_musiq_models.py` for consistent 0–1 mapping.

---

## 2. LIQE Model

**Reference:** [LIQE: Blind Image Quality Assessment via Vision-Language Correspondence (CVPR 2023)](https://github.com/zwx8981/LIQE)

### Input Format

- **Type:** Tensor from PIL Image (via PyIQA)
- **PIL mode:** RGB
- **Resize rule:** If `max(img.size) > 518`, resize to 518px on longest edge (BICUBIC). High-resolution images left unscaled can produce incorrect "noise" scores (~1.0).

### Score Range

- **Raw range:** 1.0–5.0
- **Normalization:** `(score - 1) / 4` → 0–1

### Implementation

See `modules/liqe.py` for the current implementation, including the 518px downscale logic.

---

## 2.1 Canonical Normalization Reference

**Single source of truth: `modules/score_normalization.py`**

### Step 1: Theoretical Normalization (model output → DB storage)

| Model | Raw Range | Normalization Formula | Stored in DB |
|-------|-----------|----------------------|--------------|
| LIQE | 1–5 | `(score - 1) / 4` → 0–1 | `score_liqe` (0–1) |
| AVA | 1–10 | `(score - 1) / 9` → 0–1 | `score_ava` (0–1) |
| SPAQ | 0–100 | `score / 100` → 0–1 | `score_spaq` (0–1) |

### Step 2: Percentile Rescaling (DB score → composite input) — v5.0.0

Individual model scores have vastly different effective ranges on real data.
Before computing composites, each model score is rescaled using empirical p2/p98 anchors:

`rescaled = clamp((score - p02) / (p98 - p02), 0, 1)`

| Model | p02 | p98 | Effective Range |
|-------|-----|-----|-----------------|
| LIQE | 0.360 | 0.998 | Skewed high (median 0.78) |
| AVA | 0.303 | 0.506 | Very narrow |
| SPAQ | 0.267 | 0.745 | Moderate |

Anchors are stored in `config.json` under `percentile_anchors` and can be updated
as the corpus grows.

### Step 3: Composite Formulas (v5.0.0)

Applied to percentile-rescaled scores:

- **Technical** = 1.0 × LIQE
- **Aesthetic** = 0.55 × AVA + 0.45 × SPAQ
- **General** = 0.45 × LIQE + 0.30 × AVA + 0.25 × SPAQ

### Rating Thresholds (v5.0.0)

| Rating | General Score Threshold |
|--------|------------------------|
| 5 Stars | ≥ 0.90 (~2% of corpus) |
| 4 Stars | ≥ 0.72 (~17%) |
| 3 Stars | ≥ 0.50 (~45%) |
| 2 Stars | ≥ 0.30 (~28%) |
| 1 Star | < 0.30 (~8%) |

**Important:** When passing DB scores as external_scores (e.g. backfill), always include `normalized_score` since DB stores 0–1. Passing only `score` causes run_all_models to treat values as raw and incorrectly re-normalize.

---

## 3. Database Storage

From `DB_SCHEMA.md`:

| Column | Stored Value | Note |
|--------|--------------|------|
| `score_general` | 0–1 | Normalized weighted score |
| `score_technical` | 0–1 | Normalized weighted score |
| `score_aesthetic` | 0–1 | Normalized weighted score |
| `score_spaq` | Normalized 0–1 | From `get_ind_score` → `normalized_score` |
| `score_ava` | Normalized 0–1 | Same |
| `score_koniq` | Normalized 0–1 | Same |
| `score_paq2piq` | Normalized 0–1 | Same |
| `score_liqe` | Normalized 0–1 | Same |

---

## 4. NEF Conversion to Model Input

For RAW files (NEF, etc.), the pipeline converts to JPEG before feeding to models. See [RAW_PROCESSING_GUIDE.md](RAW_PROCESSING_GUIDE.md) for conversion methods and [scripts/research_models.py](../../scripts/research_models.py) for the assessment of optimal input parameters.

### Pipeline preprocessing (v5.0.0+)

Preprocessing is **config-driven** via `config.json` → `raw_conversion`:

| Key | Default | Description |
|-----|---------|-------------|
| `method` | `"rawpy_half"` | Preferred RAW conversion: `"exiftool_jpgfromraw"` or `"rawpy_half"`. Fallback is tried if preferred fails. |
| `max_resolution` | `512` | Resize to fit then pad to this size (224–2048). Same for all models. |
| `jpeg_quality` | `85` | JPEG quality for preprocessed file (50–100). |

- **RAW:** Convert using `raw_conversion.method` order, then resize + pad to `max_resolution`, save at `jpeg_quality`.
- **Resize:** Bicubic to fit within `max_resolution`, pad with black to square.
- **Cache:** Preprocessed JPEGs cached in `.cache/preprocessed_512/` when `preprocessing.cache_enabled` is true.
- **Where:** `MultiModelMUSIQ.preprocess_image()`; `ScoringWorker` runs it once and uses the same path for LIQE and MUSIQ. LIQE applies its 518px-longest-edge rule only when input is larger than 518 (so 512 is passed through).

---

## 5. What Was Missed, Next Steps, Per-Model Settings

### What was missed (before config wiring)

- **`raw_conversion` in config was not used:** Preprocessing used a hardcoded 512 and fixed conversion order (exiftool → rawpy). This is now fixed: `preprocess_image()` reads `raw_conversion.method`, `max_resolution`, and `jpeg_quality` from `config.json`.
- **Single resolution for all models:** The pipeline still produces **one** preprocessed image per file and feeds it to SPAQ, AVA, and LIQE. There is no per-model resolution or conversion yet.
- **Research vs pipeline:** `scripts/research_models.py` recommends resolution/conversion from variance analysis; that recommendation is not applied automatically—you set `raw_conversion` in config after reviewing `research_summary.md`.

### Next steps

1. **Run research with real scores** (no `--dry-run`) on a representative set of NEFs; use `research_summary.md` recommended `max_resolution` and `method`.
2. **Set config** from that recommendation, e.g. `raw_conversion: { "method": "rawpy_half", "max_resolution": 384 }` (or 512).
3. **Optional: per-model preprocessing** — To use different resolution/conversion per model, add config (e.g. `scoring.model_preprocessing`) and change the pipeline to preprocess once per model; not implemented yet.

### How to use best conversion and resolution for SPAQ, AVA, LIQE

**Current (single shared input):**

- Set **one** best-fit in `config.json` → `raw_conversion`:
  - **Conversion:** `"method": "rawpy_half"` for best quality where rawpy works, or `"exiftool_jpgfromraw"` for Nikon Z8/Z9 HE*.
  - **Resolution:** `"max_resolution": 512` (default) or the value from `research_summary.md` (e.g. 384). SPAQ, AVA, and LIQE all receive the same preprocessed image.
- LIQE’s 518px rule in `modules/liqe.py` only shrinks images **larger** than 518; 512×512 input is passed through.

**Optional future: per-model settings**

To use different resolution per model (e.g. 384 for SPAQ/AVA, 518 for LIQE), the pipeline would need config such as `scoring.model_preprocessing` with per-model `resolution` (and optionally `conversion`), and `ScoringWorker` would preprocess once per model and pass the corresponding path to each. Not implemented yet; use one global `raw_conversion` for all three models.

### Research findings (from scripts/research_models.py + analyze_research.py)

| Model | Recommended resolution | Rationale |
|-------|------------------------|-----------|
| SPAQ | 224 or 512 | Lowest variance across variants in small run; 512 aligns with pipeline default and MUSIQ native-resolution design. |
| AVA | original or 384–512 | High Spearman vs original (1.0 at 384/512/518); lowest std at "original" in small run. |
| LIQE | 512 or 518 | 518px is LIQE’s internal max dimension; 512 passes through unchanged. No LIQE data in Windows run (DLL). |

**Validation:** Run `python scripts/validate_research_config.py --count 15` after setting `raw_conversion` to verify Spearman rank correlation (old vs new scores) ≥ 0.95. Requires DB and resolved NEF paths.
