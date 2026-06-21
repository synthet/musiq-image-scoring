## Summary

Run **Phase 2** extended scoring sweep: TOPIQ/ARNIQA @768/1024 and MUSIQ SPAQ/AVA square-pad grid.

**Depends on:** Phase 1 complete (or at least IQA harness verified on E2E).

Part of epic #260.

## Acceptance criteria

- [ ] TOPIQ + ARNIQA NPZ @ `768`, `1024` (subset 500, `thumb`)
- [ ] SPAQ + AVA NPZ @ `224,384,512,768` (square `resolution_override`, subset 500)
- [ ] `eval_summary.json` includes `burst_spread` and `production_stability` metrics per IQA run
- [ ] `SUMMARY.md` IQA table includes burst std and ρ vs production columns

## How to run

```bash
PHASE=2 bash scripts/research/clip_culling/run_input_size_study.sh
python -m scripts.research.clip_culling.input_size_eval --iqa
python -m scripts.research.clip_culling.report_input_size
```

## Docs

- [`INPUT_SIZE_CULLING_2026-05-29.md`](docs/reports/INPUT_SIZE_CULLING_2026-05-29.md)
