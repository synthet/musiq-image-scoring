## Summary

Run **Phase 3** keyword + BLIP caption sweeps and fold results into multi-track eval.

**Depends on:** Phase 1 embedding NPZ (for tagging sweep).

Part of epic #260.

## Acceptance criteria

- [ ] `input_size_tagging_eval --sweep` writes `tagging_*.npz` for `clip_b32`, `openai`, `openclip`, `siglip2` where embedding NPZ exist
- [ ] BLIP caption NPZ: `224,384,512,768` × `thumb,file` (`--track caption`)
- [ ] `eval_summary.json` includes `tagging` and `caption` sections
- [ ] `SUMMARY.md` includes tagging + caption tables

## How to run

```bash
PHASE=3 bash scripts/research/clip_culling/run_input_size_study.sh
python -m scripts.research.clip_culling.input_size_eval --all
python -m scripts.research.clip_culling.report_input_size
```

## Metrics

| Track | Primary |
|-------|---------|
| Tagging | Jaccard vs B/32, tag entropy, within-burst tag Jaccard |
| Caption | Burst caption uniqueness, keyword token overlap |
