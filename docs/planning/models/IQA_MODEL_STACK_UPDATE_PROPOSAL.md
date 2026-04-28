# Design Proposal: Modernize the Image Quality & Aesthetic Scoring Stack

## Summary

This proposal recommends replacing the current 5-model weighted ensemble with a smaller, more modern, PyTorch-first stack centered on **QPT V2** for unified image quality and aesthetic scoring, plus one complementary technical-quality model and one lightweight semantic calibrator.

### Recommended production stack

- **Primary:** QPT V2
- **Secondary:** TOPIQ-NR
- **Tertiary:** LIQE

### Recommended target weights

#### General score
- **QPT V2:** 55%
- **TOPIQ-NR:** 30%
- **LIQE:** 15%

#### Aesthetic score
- **QPT V2:** 75%
- **LIQE:** 25%

#### Technical score
- **TOPIQ-NR:** 65%
- **QPT V2:** 35%

### Models to retire
- **AVA** legacy model
- **KONIQ** dedicated production role
- **SPAQ** dedicated production role

### Models to deprecate gradually
- **PAQ2PIQ**
- **LIQE** as a primary pillar, while retaining it as a secondary calibrator

---

## Current State

The current system uses a weighted multi-model approach:

| Model    | Weight | Purpose                    | Framework   |
|----------|--------|----------------------------|-------------|
| KONIQ    | 30%    | Technical reliability      | TensorFlow  |
| SPAQ     | 25%    | Technical discrimination   | TensorFlow  |
| PAQ2PIQ  | 20%    | Artifact/detail detection  | TensorFlow  |
| LIQE     | 15%    | Aesthetic/semantic (CLIP)  | PyTorch     |
| AVA      | 10%    | Legacy aesthetic           | TensorFlow  |

### Problems with the current design

1. **Too many legacy models**  
   The ensemble is still anchored on older dataset-specific predictors rather than newer unified models.

2. **Mixed inference frameworks**  
   The stack mixes TensorFlow and PyTorch, increasing deployment and maintenance complexity.

3. **Overlapping signals**  
   KONIQ, SPAQ, and PAQ2PIQ all contribute related technical-quality information, which reduces interpretability.

4. **Weak aesthetic anchor**  
   AVA is now mostly a legacy aesthetic scorer and adds little value compared with modern unified models.

---

## Goals

- Improve ranking quality for both **technical quality** and **aesthetic appeal**
- Reduce framework complexity by moving toward **all-PyTorch** inference
- Keep inference practical for **local CUDA deployment**
- Preserve explainability with separate technical, aesthetic, and fused scores
- Minimize migration risk through staged rollout

## Non-goals

- Rebuilding the entire scoring pipeline from scratch
- Optimizing for mobile or CPU-only inference
- Replacing all historical scores immediately

---

## Why QPT V2 should be the new anchor

QPT V2 is the strongest candidate to become the center of the new stack because it is a **unified model for both image quality and aesthetics**, rather than a narrow dataset-specific scorer.

### Advantages

- Strong recent benchmark performance on aesthetic tasks
- Designed to model both **quality** and **aesthetic preference**
- Compact enough for practical local GPU inference
- Better architectural fit for a single modern anchor model than older AVA/SPAQ/KONIQ-style components

### Practical implication

QPT V2 can replace most of the current ensemble’s center of gravity while simplifying the score fusion logic.

---

## Why TOPIQ-NR is the best complement

QPT V2 should not be used alone. A complementary technical-quality model helps catch blind spots.

### TOPIQ-NR advantages

- Strong no-reference technical-quality performance
- Better distortion sensitivity than purely semantic or aesthetic models
- Good complement to a unified quality+aesthetic backbone
- Available in the PyTorch ecosystem

### Why not rely only on LIQE

LIQE remains useful, but it is better treated as a **secondary semantic/aesthetic calibrator** rather than the main technical-quality component.

---

## Proposed Target Architecture

### Option A — Recommended default

A **3-model ensemble**:

| Model | Role | Framework | Weight |
|---|---|---:|---:|
| **QPT V2** | Primary unified visual scorer | PyTorch | **55%** |
| **TOPIQ-NR** | Technical reliability / distortion sensitivity | PyTorch | **30%** |
| **LIQE** | Semantic + aesthetic calibration | PyTorch | **15%** |

### Option B — Simpler production cut

A **2-model stack**:

| Model | Role | Framework | Weight |
|---|---|---:|---:|
| **QPT V2** | Main score backbone | PyTorch | **70%** |
| **TOPIQ-NR** | Complementary calibration | PyTorch | **30%** |

### Benefits of the new architecture

- Better alignment with modern IQA/AQA research
- Single-framework deployment path
- Lower maintenance burden
- More interpretable score design

---

## Proposed Score Design

Instead of one opaque weighted blend, split scoring into three explicit outputs.

### 1. Technical score

```text
technical_score =
  0.65 * topiq_nr
+ 0.35 * qpt_v2
```

### 2. Aesthetic score

```text
aesthetic_score =
  0.75 * qpt_v2
+ 0.25 * liqe
```

### 3. General score

```text
general_score =
  0.55 * aesthetic_score
+ 0.45 * technical_score
```

### Why this is better

- Separates **technical** and **aesthetic** concerns
- Makes disagreement between models visible
- Produces a final score that is easier to interpret and debug

---

## Migration Plan

### Phase 1 — Shadow mode

Run the new stack in parallel without changing production outputs.

| Model | Weight |
|---|---:|
| QPT V2 | 35% |
| TOPIQ-NR | 20% |
| LIQE | 10% |
| Old ensemble | 35% |

**Purpose:** validate ranking behavior, score distribution, and latency.

### Phase 2 — Hybrid production

| Model | Weight |
|---|---:|
| QPT V2 | 50% |
| TOPIQ-NR | 25% |
| LIQE | 10% |
| Old ensemble | 15% |

**Purpose:** gradually reduce dependence on legacy models.

### Phase 3 — Full cutover

| Model | Weight |
|---|---:|
| QPT V2 | 55–70% |
| TOPIQ-NR | 20–30% |
| LIQE | 10–15% |

**Purpose:** remove the old ensemble entirely.

---

## Engineering Changes

### 1. Move to all-PyTorch inference

This is one of the largest operational wins.

#### Benefits
- Simpler CUDA deployment
- Easier batching
- Cleaner memory management
- Easier export to ONNX/TensorRT later
- Smaller operational surface area

### 2. Separate inference from score policy

Recommended module layout:

```text
models/        # raw inference wrappers
fusion/        # weighting + score combination
calibration/   # normalization and score mapping
evaluation/    # benchmark and regression scripts
```

This makes it possible to change weights or calibration without rewriting inference code.

### 3. Add a calibration layer

Raw outputs from different models should not be fused directly.

#### Recommended calibration methods
- z-score normalization on a held-out corpus
- percentile normalization
- optional isotonic or logistic calibration against human preference labels

Without this step, historical comparability will be weak.

### 4. Add disagreement diagnostics

Store the following per image:
- per-model scores
- fused score
- disagreement spread
- confidence estimate

This helps identify cases where:
- aesthetics are strong but technical quality is weak
- a semantic model overestimates an image
- distortions are caught by TOPIQ but not by QPT V2

---

## Evaluation Plan

### Core metrics

Track:
- Spearman correlation
- Pearson correlation
- pairwise ranking accuracy
- top-k selection precision
- latency
- VRAM usage
- score stability across similar frames

### Recommended test slices

Because the target use case includes photographic images, evaluate on:
- technically sharp images
- noisy / high-ISO images
- composition-strong but technically imperfect shots
- technically clean but visually dull images
- cropped wildlife / bird closeups
- low-light and backlit scenes

### Adoption criteria

Adopt the new stack only if it improves:
- ranking quality on curated internal sets
- selection precision for best-frame picking
- stability across similar images
- operational simplicity

---

## Risks and Mitigations

### Risk 1: QPT V2 may behave differently on your domain

**Mitigation:** run it in shadow mode and compare rankings on your internal photo corpus before full rollout.

### Risk 2: TOPIQ integration may be inconvenient

**Mitigation:** keep LIQE as a temporary backup secondary model.

### Risk 3: Historical scores may shift significantly

**Mitigation:** add calibration and maintain old/new score logging during rollout.

---

## Alternatives

### Alternative secondary model: QualiCLIP

If TOPIQ-NR is difficult to integrate, use:

| Model | Weight |
|---|---:|
| QPT V2 | 60% |
| QualiCLIP | 25% |
| LIQE | 15% |

This is still a strong PyTorch-first stack, though less distortion-focused than TOPIQ-NR.

### Alternative premium offline mode: Q-Align

Q-Align can be used as an **offline reranker** for high-value evaluation or batch curation, but it is not recommended as the default local production scorer because of heavier runtime requirements.

---

## Final Recommendation

### Adopt this stack
- **QPT V2** as the new anchor model
- **TOPIQ-NR** as the technical complement
- **LIQE** as the lightweight semantic/aesthetic calibrator

### Retire
- AVA
- KONIQ as a production model
- SPAQ as a production model

### Deprecate gradually
- PAQ2PIQ
- LIQE as a core pillar

### Strategic outcome

This change reduces the current heterogeneous, legacy-heavy ensemble into a **modern, PyTorch-first, CUDA-friendly scoring system** with clearer architecture, stronger expected performance, and lower maintenance cost.

