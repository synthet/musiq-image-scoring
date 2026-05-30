# Input-size signal quality study (culling + IQA)

> **Status:** Research harness (run offline; do not change production defaults from this doc alone).  
> **Date:** 2026-05-29.  
> **Harness:** [scripts/research/clip_culling/](../../scripts/research/clip_culling/) — `input_size_*.py` modules.  
> **Artifacts:** [reports/clip-culling/input-size/](../../reports/clip-culling/input-size/) (`native_input_sizes.json`, `eval_summary.json`, `SUMMARY.md`).

## Question

Does increasing the pixel budget before each vision model (thumbnail long edge or capped full-file decode) improve **near-duplicate discrimination** for culling embeddings and **mishot / rating signal** for IQA scorers?

## How to run

WSL + `~/.venvs/tf`, E2E Postgres `image_scoring_test` @5433, seeded corpus (`seed_e2e_subset`).

```bash
# Phase 0 — native preprocess sizes
python -m scripts.research.clip_culling.input_size_native

# Phase 1 — embed at multiple long edges (NPZ cache, no new DB spaces)
python -m scripts.research.clip_culling.input_size_embed --track embedding \
  --long-edges 128,224,384,512,768 --source thumb,file --models all

# IQA subset (faster)
python -m scripts.research.clip_culling.input_size_embed --track iqa \
  --long-edges 224,384,512,768 --source thumb --subset 500 \
  --models liqe,topiq,arniqa

# Metrics
python -m scripts.research.clip_culling.input_size_eval --all
python -m scripts.research.clip_culling.report_input_size
```

Optional Phase 2 (ViT preprocess override):

```bash
python -m scripts.research.clip_culling.input_size_embed --track embedding \
  --models openclip_l14,openai_l14,dinov2 --preprocess-size 336 \
  --long-edges 512 --source thumb
```

## Metrics

| Track | Metric | Better when |
|-------|--------|-------------|
| Embeddings | Burst-GT **mean ARI** (exp8 logic) | Higher |
| Embeddings | **Keep−reject gap** (pick/review harness) | Higher |
| Embeddings | **Pair margin** (median dist diff-burst − same-burst) | Higher |
| IQA | Mishot **ROC-AUC** (exp2 GT) | Higher |
| IQA | \|Spearman\| vs human **rating** | Stable or higher |

Baseline for deltas: **long_edge=512**, **source=thumb** (matches stored thumbnails and prior spike).

## Expected outcomes (hypothesis)

1. **ViT-224 towers** (OpenCLIP/OpenAI L/14, SigLIP2): flat curves above 224 unless `--preprocess-size` is raised.  
2. **MobileNet**: only **224×224** enters the model (clustering path); long-edge sweep affects upsampling before that resize.  
3. **DINOv2 / LIQE / TOPIQ**: gains may appear between 384–768 until native `max_dimension` / timm `input_size`.  
4. **`file` > `thumb` at same long_edge** → thumbnail `MAX_SIZE` (512) is the bottleneck, not the tower.

## Decision rules

See [reports/clip-culling/input-size/SUMMARY.md](../../reports/clip-culling/input-size/SUMMARY.md) after a full run. Cross-check [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](CULLING_MODEL_RECOMMENDATION_2026-05-29.md) for model choice; this study only addresses **input resolution**, not which tower to adopt.

## Related

- [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](CULLING_MODEL_RECOMMENDATION_2026-05-29.md) — tower selection  
- [MODEL_INPUT_SPECIFICATIONS.md](../technical/MODEL_INPUT_SPECIFICATIONS.md) — production IQA resize rules  
- [reports/clip-culling/SUMMARY.md](../../reports/clip-culling/SUMMARY.md) — prior CLIP L/14 + DINOv2 spike
