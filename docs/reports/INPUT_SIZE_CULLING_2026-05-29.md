# Pipeline input-size signal quality study

> **Status:** Research harness (run offline; do not change production defaults from this doc alone).  
> **Date:** 2026-05-29 (extended 2026-05-31).  
> **Harness:** [scripts/research/clip_culling/](../../scripts/research/clip_culling/) — `input_size_*.py` modules.  
> **Artifacts:** [reports/clip-culling/input-size/](../../reports/clip-culling/input-size/) (`native_input_sizes.json`, `eval_summary.json`, `SUMMARY.md`, `UNIFIED_INPUT_POLICY.md`).  
> **Preliminary results:** [INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md).  
> **Unified policy (draft):** [UNIFIED_INPUT_POLICY_2026-05-31.md](UNIFIED_INPUT_POLICY_2026-05-31.md).

## Question

Does increasing the pixel budget before each vision model improve **culling**, **IQA scoring**, **keyword diversity**, and **caption quality** across the full pipeline?

## How to run

WSL + `~/.venvs/tf`, E2E Postgres `image_scoring_test` @5433, seeded corpus (`seed_e2e_subset`).

```bash
# Full pipeline study (Phases 1–3 + eval)
setsid bash scripts/research/clip_culling/run_input_size_study.sh \
  >> reports/clip-culling/input-size/study_nohup.log 2>&1 &

# Or step-by-step:
python -m scripts.research.clip_culling.input_size_native

python -m scripts.research.clip_culling.input_size_embed --track embedding \
  --long-edges 128,224,384,512,768 --source thumb,file \
  --models clip_b32,openai,openclip,dinov2,siglip2

python -m scripts.research.clip_culling.input_size_embed --track iqa \
  --long-edges 224,384,512,768 --source thumb --subset 500 \
  --models liqe,topiq,arniqa,spaq,ava

python -m scripts.research.clip_culling.input_size_tagging_eval --sweep

python -m scripts.research.clip_culling.input_size_embed --track caption \
  --long-edges 224,384,512,768 --source thumb,file

python -m scripts.research.clip_culling.input_size_eval --all
python -m scripts.research.clip_culling.report_input_size
```

Optional Phase 5 (ViT preprocess override):

```bash
python -m scripts.research.clip_culling.input_size_embed --track embedding \
  --models openclip,openai,siglip2 --preprocess-size 336 \
  --long-edges 512,768 --source thumb,file
```

Environment overrides for runner: `MODELS=...`, `PHASE=1|2|3|all|eval`, `EDGES=...`.

## Metrics

| Track | Metric | Better when |
|-------|--------|-------------|
| Embeddings | Burst-GT **mean ARI** | Higher |
| Embeddings | **Keep−reject gap**, **pair margin** | Higher |
| IQA | Mishot **ROC-AUC**, rating **Spearman** | Higher |
| IQA | **Within-burst score std**, ρ vs production | Higher / stable |
| Tagging | **Jaccard vs B/32**, **tag entropy** | Stable or higher |
| Caption | **Burst caption uniqueness**, keyword overlap | Higher |

Baseline for deltas: **long_edge=512**, **source=thumb**.

## Decision rules

See [UNIFIED_INPUT_POLICY.md](../../reports/clip-culling/input-size/UNIFIED_INPUT_POLICY.md) after a full run.

## Related

- [INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md) — status memo  
- [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](CULLING_MODEL_RECOMMENDATION_2026-05-29.md) — tower selection  
- [MODEL_INPUT_SPECIFICATIONS.md](../technical/MODEL_INPUT_SPECIFICATIONS.md) — production IQA resize rules
