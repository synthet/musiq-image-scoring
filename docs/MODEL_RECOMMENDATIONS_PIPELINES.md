# Model Recommendations for Pipeline Additions

**See also:** [NEW_MODELS_SUMMARY.md](NEW_MODELS_SUMMARY.md) — consolidated overview of new/roadmap models, QPT-V2 status, and #220 phases.

## Summary

This document records the recommended model additions for the Vexlum Scoring
pipelines based on the current repository shape and local hardware constraints.

Target hardware:

- NVIDIA GeForce RTX 4060 Laptop GPU
- 8 GB VRAM

Chosen posture:

- Local-GPU realistic
- Controlled keyword taxonomy
- Permissive-license preferred
- English-only prompts (no multilingual CLIP tower required today)
- Recommendation-only until each phase lands in code (see [Implementation phases](#implementation-phases))

**Research inputs:**

- [CLIP_MODELS_CULLING_SCORING_2026-05-23.md](reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md) — CLIP-family comparison for culling signals and prompt design
- [AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md](reports/AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md) — industry culling pipeline patterns
- [DEEP_RESEARCH_REPORT.md](reports/DEEP_RESEARCH_REPORT.md) — IQA candidates (ARNIQA, QualiCLIP, TOPIQ)

## Current production models

What the codebase runs **today** (see [`config.example.json`](../config.example.json); your `config.json` may differ). Roadmap targets start in [Decision matrix](#decision-matrix).

### Quality scoring (`scoring` phase)

| Model | Framework | Checkpoint / ID | Default in `config.example` | Role |
|-------|-----------|-----------------|-----------------------------|------|
| **MUSIQ → SPAQ** | TensorFlow | MUSIQ SPAQ via `MultiModelMUSIQ` | **On** (fused) | Technical / general quality |
| **MUSIQ → AVA** | TensorFlow | MUSIQ AVA | **On** (fused) | Aesthetic / general quality |
| **LIQE** | PyTorch (`pyiqa` `liqe`) | pyiqa pretrained | **On** (fused) | Technical + aesthetic (CLIP-based IQA) |
| **TOPIQ-NR** | PyTorch (`pyiqa` `topiq_nr`) | pyiqa pretrained | **On** (fused) | No-reference technical quality |
| **QPT-V2** | PyTorch | `models/qpt_v2.pth` | **Shadow only** | Experimental unified quality+aesthetic |
| **Cursor** (LLM judge) | API | e.g. `composer-2.5` | **Off** | Optional editorial judgment |
| **Claude** (LLM judge) | API | e.g. `claude-opus-4-7` | **Off** | Optional editorial judgment |

**Fusion** (`scoring.fusion` in example): `general` = LIQE + AVA + SPAQ; `technical` = LIQE; `aesthetic` = AVA + SPAQ.

**In `MultiModelMUSIQ` but not in the default registry** (no production run unless you extend `musiq_names`): **KONIQ**, **PAQ2PIQ** (DB columns `score_koniq`, `score_paq2piq` may still hold legacy values). **VILA** is optional in the MUSIQ script, not registered by default.

Code: [`modules/engines/factory.py`](../modules/engines/factory.py), [`modules/engines/host.py`](../modules/engines/host.py), [`scripts/python/run_all_musiq_models.py`](../scripts/python/run_all_musiq_models.py).

### Culling / stacks (`culling` phase)

| Model | Framework | Embedding space | Role |
|-------|-----------|-----------------|------|
| **MobileNetV2** (ImageNet GAP) | TensorFlow/Keras | `mobilenet_v2_imagenet_gap` (1280-d) | **Default** similarity clustering, stack building, representative selection (often combined with composite scores) |

Code: [`modules/clustering.py`](../modules/clustering.py).

### Keywords and captions (`keywords` phase)

| Model | Framework | ID | Role |
|-------|-----------|-----|------|
| **CLIP ViT-B/32** | HuggingFace | `openai/clip-vit-base-patch32` (`tagging.clip_model`) | Zero-shot **keywords**; persists **`clip_vit_b32_image`** (512-d) |
| **BLIP base** | HuggingFace | `Salesforce/blip-image-captioning-base` | **Captions**; persists **`blip_vit_b16_image`** (768-d) when `embeddings.persist_blip_image` is true |

Code: [`modules/tagging.py`](../modules/tagging.py).

### Bird species (`bird_species` phase, after keywords)

| Model | Framework | ID | Role |
|-------|-----------|-----|------|
| **BioCLIP 2** | OpenCLIP | `hf-hub:imageomics/bioclip-2` | Zero-shot species on bird-keyword images; **`bioclip_2_image`** (512-d) |

Code: [`modules/bird_species.py`](../modules/bird_species.py).

### Stored embedding spaces (summary)

| Space code | Source | Dim |
|------------|--------|-----|
| `mobilenet_v2_imagenet_gap` | Culling / backfill | 1280 |
| `clip_vit_b32_image` | Tagging (CLIP) | 512 |
| `blip_vit_b16_image` | Tagging (BLIP vision tower) | 768 |
| `bioclip_2_image` | Bird species | 512 |

Registry: [`modules/embedding_spaces.py`](../modules/embedding_spaces.py). Similar search: [`modules/similar_search.py`](../modules/similar_search.py).

### Optional / off by default

| Component | What runs |
|-----------|-----------|
| **Technical failures** (`technical_failures.enabled: false`) | Classical blur/exposure metrics only; `use_clip_iqa` / `use_pyiqa` false in example |
| **Embedding map** (`embedding_map.enabled: false`) | UMAP or t-SNE on stored vectors (not a vision model) |
| **Roadmap models** | ARNIQA, DINOv2, SigLIP2, OpenCLIP L/14 — not in production paths yet ([#220](https://github.com/synthet/image-scoring-backend/issues/220)) |

### Current models mapped to tasks

| Task | Models used now |
|------|-----------------|
| **Technical score** | SPAQ, LIQE, TOPIQ-NR (+ classical metrics if technical_failures enabled) |
| **Aesthetic score** | AVA, LIQE, SPAQ (via `scoring.fusion`) |
| **Human perception / editorial** | User rating/label; optional Cursor/Claude if enabled |
| **Cluster into stacks** | **MobileNetV2** embeddings only |
| **Best in stack / sort** | Stack representative logic + **composite scores** (`score_general`, etc.) |
| **Tags / keywords** | **CLIP B/32**; BLIP for captions; BioCLIP for `species:*` on birds |

---

## Decision matrix

Production defaults below assume **RTX 4060 Laptop, 8 GB VRAM**. Raw zero-shot CLIP is **not** a drop-in replacement for MUSIQ/LIQE/TOPIQ for aesthetic or technical IQA (see CLIP report executive summary).

| Pipeline | Production target | Interim / plumbing | Shadow or optional | Not default now |
|----------|-------------------|--------------------|--------------------|-----------------|
| **Scoring (IQA)** | Keep MUSIQ, LIQE, TOPIQ-NR ensemble | — | **ARNIQA** (technical NR) | Raw CLIP margin as IQA; Q-Align; QPT-V2 until stable |
| **Culling (visual similarity)** | **DINOv2-reg base** embeddings | **`clip_vit_b32_image`** (already backfilled) via `clustering.embedding_space` | OpenCLIP ViT-L/14 768-d A/B | MobileNetV2 long-term; MetaCLIP (NC license) |
| **Keywords (controlled tags)** | **SigLIP2 base** (per-tag thresholds) | Current CLIP B/32 + expand vocabulary | RAM++ tag discovery | Softmax-over-25-tags as sole signal; Florence-2 captions as primary output |

| Model | License | ~VRAM (fp16, single model) | Best task fit |
|-------|---------|----------------------------|---------------|
| ARNIQA | Apache-2.0 | Moderate (torch.hub / pyiqa) | Technical no-reference IQA |
| DINOv2-reg base | Apache-2.0 | Fits 8 GB batch culling | Visual similarity, near-dup stacks |
| SigLIP2 base | Apache-2.0 | Fits 8 GB | Controlled keyword scoring |
| OpenCLIP ViT-L/14 `laion2b_s32b_b82k` | MIT (repo) | ~0.8 GB image tower fp16 | CLIP retrieval, shared 768-d culling+keywords |
| MetaCLIP ViT-H/14 | CC-BY-NC | Too large for 8 GB co-load | Classification / NC-only swap-in |
| QualiCLIP | Non-commercial | Moderate | Strong IQA but license blocks default |

## CLIP-family alternate (OpenCLIP ViT-L/14)

Use this track when you want **one** shared CLIP image tower (768-d, `image_embeddings_768`) for both culling similarity and keyword zero-shot on 8 GB VRAM, instead of separate DINOv2 + SigLIP2 loaders.

| Aspect | OpenCLIP L/14 unified | DINOv2 + SigLIP2 (default above) |
|--------|----------------------|----------------------------------|
| VRAM | One model, reuse across phases | Two models; load sequentially per phase |
| Culling | Strong published retrieval (LAION-2B L/14) | Stronger pure visual similarity (self-supervised) |
| Keywords | L/14 zero-shot >> B/32 | SigLIP2 per-tag scoring fits controlled taxonomy |
| License | MIT OpenCLIP | Apache-2.0 both |
| Dependency | `open-clip-torch` (already in `requirements_wsl_gpu.txt`) | `timm` / HF for DINO; HF for SigLIP2 |

**When to prefer OpenCLIP L/14:** English-only, minimize distinct GPU models, or A/B shows DINO false-splits on semantic bursts.

**When to prefer DINOv2 + SigLIP2:** Permissive-license default, controlled keywords without CLIP softmax coupling, culling without text-alignment bias.

**Scoring add-ons on OpenCLIP (optional, shadow only):**

- **LAION aesthetic predictor** — small MLP on L/14 embeddings (true aesthetic dimension; not in CLIP report).
- **CLIP prompt margin** — `mean(positive prompts) − w·mean(negative prompts)` per [CLIP report workflow](reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md#scoring-and-culling-workflow-design); semantic/defect signal only.

**MetaCLIP:** Eligible if non-commercial is acceptable; published edge is often zero-shot *classification*, not retrieval. ViT-H/14 does not fit 8 GB. English-only product does not need MetaCLIP 2 multilingual towers.

### Culling workflow rules (from CLIP report)

Apply to any CLIP-based culling or prompt-margin scoring:

1. **L2-normalized cosine** for cross-image ranking and threshold tuning.
2. **Positive and negative prompt banks** (margin score), not a single “good photo” prompt.
3. **Softmax** only within a closed candidate set (e.g. pick best of N tags), not as an absolute reject threshold.
4. **Re-tune** `clustering.default_threshold` and `culling.sub_cluster_distance_threshold` after changing embedding space (MobileNet-tuned values do not transfer).

## Model use cases by task

Models below are **new or newly emphasized** in this roadmap. Existing production scorers (MUSIQ, LIQE, TOPIQ-NR, SPAQ, AVA, KONIQ, etc.) are unchanged unless noted. They remain the primary **technical + aesthetic** ensemble; new models mostly **add** signals or **replace config defaults** for culling/keywords—not delete old data.

**Fit legend:** **Primary** = intended use · **Secondary** = possible with calibration · **Weak** = poor match · **—** = not applicable

### Recommended / phased (issues #220)

| Model | What it is | Technical score | Aesthetic score | Human perception / editorial | Cluster into stacks | Best in stack / sort within stack | Tags / keywords |
|-------|------------|-----------------|-----------------|------------------------------|---------------------|-----------------------------------|-----------------|
| **ARNIQA** | No-reference IQA (distortion-focused, PyTorch) | **Primary** — blur, noise, compression | Weak | Secondary after local calibration vs keepers | — | **Secondary** — rank burst frames by technical quality | — |
| **DINOv2-reg base** | Self-supervised ViT embeddings (visual, not text-aligned) | — | — | — | **Primary** — cosine distance → stacks / near-dups | **Secondary** — centroid representative; pair with IQA for “best keeper” | — |
| **SigLIP2 base** | Image–text model; per-pair similarity (sigmoid) | Weak — defect prompts only | Weak–secondary — beauty prompts need tuning | Secondary — rubric prompts + thresholds | Secondary — semantic clustering possible; not default vs DINO | Secondary — sort by prompt score if rubric is stable | **Primary** — controlled tags, per-tag thresholds |
| **CLIP ViT-B/32** (interim) | Current keyword tower; `clip_vit_b32_image` in DB | Weak — prompt defect proxies | Weak | Weak — prompt margin + calibration | **Secondary** (Phase 1) — culling reads stored 512-d vectors | Secondary — centroid + existing `score_*` | **Current default** — ~25 tags, softmax across set |
| **RAM++** | Open-vocabulary tagger | — | — | Discovery only | — | — | **Shadow** — suggest tags outside taxonomy |

### CLIP-family alternates (optional Phase 5 / A/B)

| Model | What it is | Technical | Aesthetic | Human perception | Stacks | Stack picker / sort | Tags |
|-------|------------|-----------|-----------|------------------|--------|---------------------|------|
| **OpenCLIP ViT-L/14** (`laion2b_s32b_b82k`) | Stronger CLIP tower (768-d) | Secondary — prompt margin | Secondary — literal prompt fit | Secondary — calibrated margin | **Primary** (CLIP track) — retrieval clustering | Secondary — centroid + margin or LAION score | **Primary** (CLIP track) — zero-shot tags |
| **LAION aesthetic predictor** | MLP on L/14 embeddings | Weak | **Primary** (CLIP add-ons) | Secondary | — | **Primary** with L/14 — sort by aesthetic | — |
| **CLIP prompt margin** | L/14 or B/32, no extra weights | **Secondary** — pos/neg prompts | Weak | Secondary | — | **Secondary** — rank in stack | — |
| **MetaCLIP / MetaCLIP 2** | Curated / multilingual CLIP (NC) | Same as CLIP | Same as CLIP | Multilingual: secondary | Secondary — classification-biased | Same as CLIP | Secondary |
| **OpenCLIP ViT-H/14** | Largest open CLIP in reports | Same as CLIP | Same as CLIP | Same as CLIP | Strong retrieval — **not** for 8 GB laptop | Same | Same |

### Mentioned, not recommended as defaults

| Model | What it is | Technical | Aesthetic | Human perception | Stacks | Stack picker / sort | Tags |
|-------|------------|-----------|-----------|------------------|--------|---------------------|------|
| **QualiCLIP** | NR-IQA (CLIP-based, NC license) | **Primary** if licensed | Secondary | Secondary | — | Secondary | — |
| **Q-Align** | Large MLLM quality | Possible | Possible | Possible | — | Possible | — |
| **QPT-V2** | Unified quality+aesthetic (research) | Future | Future | Future | — | — | — |
| **Florence-2** | Vision-language generalist | Weak | Weak | Weak | Weak | Weak | Secondary — captions / open-vocab, not controlled taxonomy |

### How tasks map in this product

| Task | Typical signal today | Roadmap adds |
|------|----------------------|--------------|
| **Technical quality** | MUSIQ, LIQE, TOPIQ, SPAQ, KONIQ, … | **ARNIQA** (shadow → optional composite) |
| **Aesthetic / appeal** | Ensemble + `score_general` | **LAION aesthetic** (optional on L/14); not raw CLIP alone |
| **Human keeper judgment** | Rating, label, review; optional LLM judges | Calibrated margins + ensemble; no single model replaces taste |
| **Cluster into stacks** | MobileNetV2 1280-d + cosine threshold | **CLIP B/32** (interim) → **DINOv2**; optional **OpenCLIP L/14** |
| **Best in stack / sort** | `stack_representative_strategy` + scores | Richer embeddings + **ARNIQA** / aesthetic / margin for ordering |
| **Keywords / labels** | CLIP B/32 + BLIP captions | **SigLIP2** (production); **RAM++** (suggestions) |

### Practical combinations

1. **Stacks** — Embedding model only (DINOv2 target, or CLIP B/32 interim): group by visual similarity. Re-tune thresholds per embedding space.
2. **Pick winner in stack** — Usually **two signals**: (a) cluster membership via embeddings, (b) rank with **technical** (ARNIQA + existing IQA) and/or **aesthetic** (ensemble or LAION head). Embeddings alone miss storytelling (e.g. wings-up vs wings-down).
3. **Sort a folder** — Existing composite scores + optional ARNIQA; CLIP margin for semantic rejects (blur, wrong subject), not global beauty alone.
4. **Tags** — **SigLIP2** for curated lists; **RAM++** to discover missing tags; **BLIP** remains for captions, not the controlled-taxonomy writer.

**Bottom line:** New models are specialists. DINOv2/OpenCLIP → **grouping**. ARNIQA/LAION/ensemble → **scoring and within-stack ranking**. SigLIP2/RAM++ → **keywords**. Raw CLIP is **not** a full human-perception or IQA replacement for MUSIQ/LIQE/TOPIQ without shadow validation.

## Implementation phases

**Tracking issue:** [image-scoring-backend#220](https://github.com/synthet/image-scoring-backend/issues/220)

| Phase | Scope | Add or replace? | Code? |
|-------|--------|-----------------|-------|
| 0 | This doc + ingested CLIP report + wiki links | N/A | Docs only (done) |
| 1 | `clustering.embedding_space` → existing `clip_vit_b32_image`; threshold tuning harness | **Switch** culling input to existing CLIP vectors (no new model). MobileNet path and data **kept** as fallback. | Yes |
| 2 | ARNIQA shadow engine → `image_model_scores` | **Add** shadow scorer. MUSIQ/LIQE/TOPIQ **unchanged** until promotion. | **Done** ✅ (calibration pending) |
| 3 | DINOv2-reg base space, backfill, culling default after validation | **Add** embedding space; **replace default** culling space after validation. MobileNet + CLIP data **kept**. | Yes |
| 4 | SigLIP2 keyword scorer (shadow → production), vocabulary expansion | **Add** scorer; shadow then **replace default** tag writer. CLIP + BLIP **kept** behind config. | Yes |
| 5 | Optional OpenCLIP L/14 unified track if A/B requires | **Add** space/model; **replace** DINO/SigLIP defaults only if A/B wins. | Yes |

## Recommended Models

### Scoring Pipeline: ARNIQA

**Status: implemented as a shadow engine** (#220 phase 2). ARNIQA is registered at
import time in `modules/engines/__init__.py` and runs via `pyiqa` (`modules/arniqa.py`
+ `modules/engines/arniqa_model.py`). Default config `scoring.models.arniqa:
{enabled: false, shadow: true}` — scores persist to `image_model_scores` but are
**not fused**. Remaining work is the calibration phase below (percentile anchors on
the local corpus) before any promotion into composites.

Add ARNIQA as a technical/no-reference image quality signal.

Rationale:

- Runs locally on a laptop GPU.
- Fits the existing PyTorch model path.
- Provides an additional technical quality signal beyond the current LIQE,
  TOPIQ, SPAQ, and AVA mix.
- Apache-2.0 licensing makes it preferable to non-commercial alternatives for
  a default recommendation.

Recommended use:

- Introduce as a shadow score first.
- Calibrate score distribution on the local photo library before using it in
  composite scoring.
- Treat it primarily as a technical quality input, not an aesthetic or editorial
  judgment signal.

### Culling Pipeline: DINOv2 With Registers Base

Add DINOv2 with registers base as the preferred future visual embedding model
for culling.

Rationale:

- Better suited than MobileNetV2 for modern visual similarity and variant
  grouping.
- Practical for an 8 GB RTX 4060 laptop GPU.
- Apache-2.0 licensing.
- Useful for near-duplicate detection, sub-clustering, representative selection,
  and diversity-aware pick logic.

Recommended use:

- Add as a new embedding space rather than replacing existing MobileNetV2 data
  in place.
- Keep MobileNetV2 as a fallback while DINO embeddings are backfilled.
- Use DINO embeddings as the primary visual similarity channel for future
  culling calibration.

### Keywords Pipeline: SigLIP2 Base

Add SigLIP2 base as the preferred controlled zero-shot keyword scorer.

Rationale:

- Runs locally on the target GPU.
- Fits the current zero-shot keyword workflow better than larger captioning or
  generative models.
- Supports controlled taxonomy scoring and semantic image/text embeddings.
- Apache-2.0 licensing.

Recommended use:

- Replace or shadow the current CLIP keyword scorer for controlled keyword
  lists.
- Score candidate tags independently with stable thresholds rather than relying
  on softmax behavior across the whole candidate set.
- Reuse embeddings for semantic search only after the embedding space and text
  encoder pairing are explicit.

### Optional Keyword Shadow: RAM++

Use RAM++ only as an optional shadow/discovery model for keyword suggestions.

Rationale:

- Useful for discovering tags missing from the controlled taxonomy.
- Not recommended as the default metadata writer because the chosen product
  goal is controlled tags.

Recommended use:

- Run in shadow mode.
- Compare suggested tags against the existing taxonomy.
- Promote accepted suggestions into curated keyword lists manually or through a
  review workflow.

## Models Not Recommended as Defaults

### Q-Align

Do not add as a default model now.

Reason:

- Large multimodal-model approach is too heavy and slow for the default laptop
  GPU path.
- 8 GB VRAM makes this a poor first production target without quantization and
  careful benchmarking.

### QPT-V2

Do not add as a default model now.

**Validation plan:** [planning/models/QPT_V2_VALIDATION_GATES.md](planning/models/QPT_V2_VALIDATION_GATES.md) — shadow gates, probe/degradation scripts, promotion criteria (#185).

Reason:

- Promising research direction, but not recommended until inference code and
  checkpoints are stable enough for straightforward local integration.

### QualiCLIP

Do not add as a default model now.

Reason:

- Strong technical quality candidate, but non-commercial licensing makes it a
  worse default under the permissive-license preference.

### Florence-2

Do not add as a default model now.

Reason:

- Better fit for captioning, dense labels, and open-vocabulary extraction than
  for the selected controlled-keyword goal.
- Current pipeline posture does not prioritize generated captions as the main
  keyword output.

## Validation Plan

Before enabling any recommended model in production scoring, culling, or keyword
metadata writes:

1. Run a 50-image local validation set covering sharp images, blurry images,
   high-ISO images, wildlife bursts, landscapes, portraits, and RAW-derived
   thumbnails.
2. Confirm each model runs without out-of-memory failures on the RTX 4060 Laptop
   GPU with conservative batch sizes.
3. Persist new outputs in shadow mode first so existing scores, stack decisions,
   and keywords remain unchanged.
4. Compare ARNIQA score distribution against existing LIQE, TOPIQ, SPAQ, and AVA
   scores before changing composite weights.
5. Compare DINOv2 culling clusters against current MobileNetV2 stacks, focusing
   on false merges and false splits in burst/action sequences.
6. Compare SigLIP2 keyword output against current CLIP output on the existing
   controlled keyword list, then tune thresholds on local images.
7. Promote models from shadow to production only after threshold calibration and
   spot review of representative failures.
