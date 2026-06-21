## Summary

**Conditional Phase 5:** ViT preprocess-size override sweep — only if OpenCLIP/OpenAI/SigLIP2 burst-ARI curves are **flat above 224** at `long_edge=512` thumb in Phase 1.

Part of epic #260.

## Acceptance criteria

- [ ] Phase 1 eval reviewed; flat ViT-224 curves documented in issue comment (or issue closed as skipped)
- [ ] If triggered: NPZ namespace `*_preprocess336.npz` for `openclip`, `openai`, `siglip2` @ `512,768` × `thumb,file`
- [ ] Keyword eval re-run on preprocess336 NPZ
- [ ] Δ ARI / Jaccard vs baseline recorded in `SUMMARY.md`

## How to run (if triggered)

```bash
python -m scripts.research.clip_culling.input_size_embed --track embedding \
  --models openclip,openai,siglip2 --preprocess-size 336 \
  --long-edges 512,768 --source thumb,file
python -m scripts.research.clip_culling.input_size_tagging_eval --sweep --force
python -m scripts.research.clip_culling.input_size_eval --all
python -m scripts.research.clip_culling.report_input_size
```

## If skipped

Comment on this issue with Phase 1 curves showing why preprocess bump is not warranted; close as `not planned` or leave on Backlog for re-check after tower changes (#220).
