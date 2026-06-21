## Summary

Optional: complete **MobileNet** embedding grid for input-size study (production default clustering tower). Deferred from Phase 1 due to TF GPU crash on RTX 4060 Laptop.

Part of epic #260.

## Acceptance criteria

- [ ] 10 NPZ files: `mobilenet` × `128,224,384,512,768` × `thumb,file`
- [ ] Eval row in `SUMMARY.md`; compare ARI vs OpenCLIP L/14 at same long_edge
- [ ] Run recipe documented (CPU-only or `TF_FORCE_GPU_ALLOW_GROWTH` if GPU)

## How to run

```bash
# CPU-only option
CUDA_VISIBLE_DEVICES="" python -m scripts.research.clip_culling.input_size_embed \
  --track embedding --models mobilenet \
  --long-edges 128,224,384,512,768 --source thumb,file
```

Or `MODELS=mobilenet` in `run_input_size_study.sh` after PyTorch phases complete.

## Notes

Prior failure: process exit ~64/2126 images, no traceback. Isolate from PyTorch towers.
