# Pipeline input-size study — summary

_Generated 2026-05-31T15:46:11Z — E2E corpus, NPZ caches under `reports/clip-culling/input-size/npz/`.

Baseline for deltas: **long_edge=512**, **source=thumb**.

## Interpretation (quick)

1. **Flat ARI above 224** on ViT-L/14 / SigLIP2 → thumbnail >224 rarely helps unless preprocess size increases.
2. **file > thumb** at same long_edge → raise `MAX_SIZE` in thumbnails or align backfill to thumbs.
3. **MobileNet** only sees 224×224 after clustering resize — sweep affects upsampling quality, not native resolution.
4. **Keywords flat above 224** → tagging benefits only from preprocess bump, not thumb alone.
5. **BLIP peak at ~384** → verify caption diversity curve before raising global thumb size.
