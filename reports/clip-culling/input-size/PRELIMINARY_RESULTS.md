# Pipeline input-size study — preliminary results (artifact copy)

**Canonical wiki page:** [docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](../../../docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md)

**Unified policy (draft):** [docs/reports/UNIFIED_INPUT_POLICY_2026-05-31.md](../../../docs/reports/UNIFIED_INPUT_POLICY_2026-05-31.md)

## Status (2026-05-31)

| Done | Pending |
|------|---------|
| Harness extended (embedding, iqa, tagging, caption tracks) | Embedding NPZ grid |
| `native_input_sizes.json` (+ BLIP/BioCLIP probes) | `eval_summary.json` full metrics |
| Runner: PyTorch default, `PHASE=1\|2\|3\|all` | Phase 1–3 WSL detached run |
| Unit tests (10+) | Production config changes |

## Phase 0 headline

| Tower / path | Native input |
|--------------|--------------|
| OpenCLIP / OpenAI L/14, SigLIP2, CLIP B/32, MobileNet | **224** |
| DINOv2 (timm) | **518** |
| BLIP caption | **~384** |
| Thumbnails (production) | **512** max |
| LIQE / TOPIQ / ARNIQA | **518 / 1024 / 1024** max long edge |
| MUSIQ SPAQ/AVA | **512** square JPEG default |

## Tracks

| Track | Command hint |
|-------|--------------|
| Embedding | `input_size_embed --track embedding --models openclip,openai,dinov2,siglip2,clip_b32` |
| IQA extended | `PHASE=2 run_input_size_study.sh` |
| Tagging | `input_size_tagging_eval --sweep` |
| Caption | `input_size_embed --track caption --long-edges 224,384,512,768` |
| Eval + policy | `input_size_eval --all` → `report_input_size` |

## Next run (recommended)

Skip MobileNet; use `setsid` in WSL:

```bash
source ~/.venvs/tf/bin/activate
export POSTGRES_DB=image_scoring_test POSTGRES_PORT=5433
cd /mnt/d/Projects/image-scoring-backend
setsid bash scripts/research/clip_culling/run_input_size_study.sh \
  >> reports/clip-culling/input-size/study_nohup.log 2>&1 &
```

Or single phase:

```bash
PHASE=1 bash scripts/research/clip_culling/run_input_size_study.sh
```

See full analysis and extended plan in the wiki doc above.
