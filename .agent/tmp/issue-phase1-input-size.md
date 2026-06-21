## Summary

Run **Phase 1** of the pipeline input-size study: PyTorch embedding NPZ grid + base IQA subset on E2E corpus (`image_scoring_test` @5433).

Part of epic #260.

## Acceptance criteria

- [ ] `native_input_sizes.json` present (Phase 0; re-run if stale)
- [ ] **50** embedding NPZ files: `clip_b32`, `openai`, `openclip`, `dinov2`, `siglip2` × long edges `128,224,384,512,768` × sources `thumb,file`
- [ ] IQA subset (500 images): `liqe`, `topiq`, `arniqa` @ `224,384,512,768` on `thumb`
- [ ] `input_size_eval --embedding --iqa` produces `eval_summary.json` with non-empty runs
- [ ] `report_input_size` writes `SUMMARY.md` with embedding + IQA tables (not placeholder-only)

## How to run

```bash
source ~/.venvs/tf/bin/activate
export POSTGRES_DB=image_scoring_test POSTGRES_PORT=5433
cd /mnt/d/Projects/image-scoring-backend
setsid bash scripts/research/clip_culling/run_input_size_study.sh PHASE=1 \
  >> reports/clip-culling/input-size/study_nohup.log 2>&1 &
```

Default `MODELS` omits MobileNet (TF GPU contention). Override: `MODELS=mobilenet,...` if needed.

## Notes

Prior run died at `mobilenet/thumb/le=128` (~64/2126) with no traceback. Use `setsid` in WSL, not Cursor background from Windows.

## Docs

- [`INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md`](docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md)
