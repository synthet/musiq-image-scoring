# Pipeline input-size study — preliminary results & extended plan

> **Status:** Harness extended (Phases 1–6 design); Phase 0 complete; NPZ/eval grid pending full run.  
> **Date:** 2026-05-30 (updated 2026-05-31).  
> **Supersedes nothing** — complements [INPUT_SIZE_CULLING_2026-05-29.md](INPUT_SIZE_CULLING_2026-05-29.md) (runbook) and [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](CULLING_MODEL_RECOMMENDATION_2026-05-29.md) (tower choice at fixed resolution).

## Executive summary

The **pipeline-wide input-size study** harness covers culling embeddings, IQA scorers, keywords, and BLIP captions. Phase 0 (native preprocess sizes) is complete. **No embedding NPZ caches or eval metrics exist yet** — repeated background runs died during the first MobileNet embed (~64/2126 images) with no Python traceback.

**Goal:** find the ideal upstream pixel budget (thumbnail, file decode, RAW→JPEG square size, optional ViT preprocess override) so the pipeline produces the **most valuable and diverse outputs** (burst stacks, scores, keywords, captions, semantic search).

**Actionable finding from Phase 0 alone:** ViT culling towers consume **224×224** after library preprocess; DINOv2 **518×518**; LIQE **518** max long edge; TOPIQ/ARNIQA **1024**; BLIP **~384**; thumbnails **512×512 max**.

**Do not change production defaults** until [UNIFIED_INPUT_POLICY_2026-05-31.md](UNIFIED_INPUT_POLICY_2026-05-31.md) sign-off after a full eval run.

---

## Question (extended)

Does increasing pixel budget before each vision model improve:

| Output | Primary metrics |
|--------|-----------------|
| Burst stacks / culling | Burst-GT ARI, pick gap, pair margin |
| Quality scores | Mishot ROC-AUC, rating Spearman, within-burst score spread |
| Keywords | Taxonomy Jaccard vs B/32, tag entropy, within-burst duplication |
| Captions (BLIP) | Burst caption uniqueness, keyword token overlap |
| Semantic search | Pair margin on embedding spaces |

---

## Full model inventory

| Model | Native input | Config knob | Study track |
|-------|--------------|-------------|-------------|
| MobileNetV2 GAP | 224×224 | hardcoded clustering | embedding (optional; defer TF GPU) |
| OpenCLIP / OpenAI L/14, SigLIP2, CLIP B/32 | 224 preprocess | `--preprocess-size` (Phase 5) | embedding + tagging |
| DINOv2-reg | 518×518 | culling space | embedding |
| LIQE | max long edge 518 | `scoring.liqe_max_dimension` | iqa |
| TOPIQ / ARNIQA | max long edge 1024 | `scoring.topiq_max_dimension`, `scoring.arniqa.max_dimension` | iqa @ 768, 1024 |
| MUSIQ SPAQ / AVA | square JPEG @ `raw_conversion.max_resolution` | `raw_conversion.max_resolution` | iqa @ 224,384,512,768 |
| BLIP caption | ~384 HF processor | `tagging` CaptionGenerator | caption |
| BioCLIP 2 (optional) | ~224 open_clip | bird phase | Phase 4 optional |

Out of scope: Q-Align (absent), QPT V2 (unregistered), LLM API judges.

---

## What was delivered (harness)

| Component | Path |
|-----------|------|
| Native size probe (+ BLIP, BioCLIP) | `input_size_native.py` |
| Embed / IQA / caption sweep | `input_size_embed.py` (`--track embedding\|iqa\|caption`) |
| Keyword sweep from embedding NPZ | `input_size_tagging_eval.py` |
| Multi-track eval | `input_size_eval.py` (`--all` includes tagging + caption) |
| SUMMARY + unified policy | `report_input_size.py` → `UNIFIED_INPUT_POLICY.md` |
| Resumable batch runner | `run_input_size_study.sh` (PyTorch default; `PHASE=1\|2\|3\|all`) |
| Unit tests | `tests/test_clip_culling_input_size.py` |

Artifacts: [reports/clip-culling/input-size/](../../reports/clip-culling/input-size/).

---

## Phase 0 results — native input sizes

Source: [native_input_sizes.json](../../reports/clip-culling/input-size/native_input_sizes.json).

See prior table in run status section; BLIP and BioCLIP probes added in harness update (2026-05-31).

---

## Run status (2026-05-30)

| Item | Result |
|------|--------|
| E2E DB `image_scoring_test` @5433 | **Ready** — 2,126 seed images |
| `native_input_sizes.json` | **Written** |
| NPZ embedding caches | **0 / 50** (5 PyTorch models × 5 edges × 2 sources; MobileNet optional) |
| Tagging / caption NPZ | **0** (depends on embedding / caption sweeps) |
| `eval_summary.json` / `SUMMARY.md` / `UNIFIED_INPUT_POLICY.md` | Placeholder until NPZ grid completes |

---

## Metrics grid (all tracks)

| Track | Metric | Module |
|-------|--------|--------|
| Embeddings | Burst-GT mean ARI, keep−reject gap, pair margin | `input_size_eval.py` |
| IQA | Mishot ROC-AUC, rating Spearman, burst score std, ρ vs production | `input_size_eval.py` |
| Tagging | Jaccard vs B/32, tag entropy, within-burst tag Jaccard | `input_size_tagging_eval.py` |
| Caption | Burst caption uniqueness, keyword token Jaccard | `input_size_eval.py` |

Baseline: **`long_edge=512`, `source=thumb`**.

---

## Execution plan

### Phase 1 — Culling + base IQA (priority)

```bash
cd /mnt/d/Projects/image-scoring-backend
source ~/.venvs/tf/bin/activate
export POSTGRES_DB=image_scoring_test POSTGRES_PORT=5433
setsid bash scripts/research/clip_culling/run_input_size_study.sh PHASE=1 \
  >> reports/clip-culling/input-size/study_nohup.log 2>&1 &
```

Default `MODELS=clip_b32,openai,openclip,dinov2,siglip2` (MobileNet omitted). Target **50** embedding NPZ + IQA subset (liqe, topiq, arniqa).

### Phase 2 — Extended scoring

```bash
PHASE=2 bash scripts/research/clip_culling/run_input_size_study.sh
```

TOPIQ/ARNIQA @ 768, 1024; SPAQ/AVA @ 224, 384, 512, 768 (square pad).

### Phase 3 — Keywords + captions

```bash
PHASE=3 bash scripts/research/clip_culling/run_input_size_study.sh
```

Tagging NPZ from embedding caches; BLIP @ 224, 384, 512, 768 × thumb/file.

### Phase 5 — ViT preprocess override (conditional)

Only if L/14 curves flat above 224:

```bash
python -m scripts.research.clip_culling.input_size_embed --track embedding \
  --models openclip,openai,siglip2 --preprocess-size 336 \
  --long-edges 512,768 --source thumb,file
```

### Phase 6 — Synthesis

```bash
python -m scripts.research.clip_culling.input_size_eval --all
python -m scripts.research.clip_culling.report_input_size
```

Outputs: [SUMMARY.md](../../reports/clip-culling/input-size/SUMMARY.md), [UNIFIED_INPUT_POLICY.md](../../reports/clip-culling/input-size/UNIFIED_INPUT_POLICY.md), wiki [UNIFIED_INPUT_POLICY_2026-05-31.md](UNIFIED_INPUT_POLICY_2026-05-31.md).

---

## Decision rules (extended)

1. **file > thumb** at same long_edge → raise thumbnail `MAX_SIZE` before per-model tuning.
2. **Flat above 224** on ViT towers → thumb increases wasted unless preprocess bump (Tier E).
3. **MobileNet flat above 224** → only clustering resize matters.
4. **IQA:** higher `max_dimension` only if mishot ROC-AUC or burst spread improves.
5. **Keywords flat above 224** → tagging needs preprocess bump, not thumb alone.
6. **BLIP peaks at ~384** → verify caption diversity before global thumb raise.
7. **MUSIQ flat above 512** → keep `raw_conversion.max_resolution=512`.
8. **Conflicting optima** → weight culling + mishot over keyword entropy unless Jaccard drops >5%.

---

## Related documents

- [INPUT_SIZE_CULLING_2026-05-29.md](INPUT_SIZE_CULLING_2026-05-29.md) — runbook
- [UNIFIED_INPUT_POLICY_2026-05-31.md](UNIFIED_INPUT_POLICY_2026-05-31.md) — tiered pixel policy (draft)
- [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](CULLING_MODEL_RECOMMENDATION_2026-05-29.md) — tower choice
- [reports/clip-culling/input-size/PRELIMINARY_RESULTS.md](../../reports/clip-culling/input-size/PRELIMINARY_RESULTS.md) — artifact copy
