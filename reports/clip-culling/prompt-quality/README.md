# CLIP prompt-quality benchmark (v0) — results

**Date:** 2026-06-13 · **Script:** `scripts/research/clip_culling/clip_prompt_quality.py`
**Corpus:** production `image_scoring` @5432, **read-only**, all human-labeled images
(62,932 with `rating` 1–5 + color `label`; 21,466 picked / 13,301 rejected).
**Prompt set:** `v0`, 7 dimensions, 6-template expansion, antonym-softmax @ temp 100.

Auxiliary signal only — *not* a primary IQA model (per the experiment spec).

## What ran

Only CLIP-family spaces whose **text** tower matches the persisted **image**
encoder were scored (mismatch silently corrupts cosine). Spaces present in prod:

| Space | dim | text tower |
|---|---|---|
| `clip_vit_b32_image` | 512 | HF `openai/clip-vit-base-patch32` |
| `openclip_l14_laion2b_image` | 768 | open_clip `ViT-L-14` / `laion2b_s32b_b82k` |
| `bioclip_2_image` | 768 | open_clip `hf-hub:imageomics/bioclip-2` |

**Not testable here:** `openai_clip_vit_l14_image` and `siglip2_base_image` have
**0** rows in prod — they exist only in the stopped E2E spike DB (`@5433`). DINOv2
and MobileNet have no text encoder. To compare those, start + re-seed the E2E
container (`embed_persist`, a GPU job) or backfill them into prod.

## Headline (`clip_quality_v0`)

| Space | spearman(rating) | AUC pick/reject | within-stack concordance | mean picked | mean rejected |
|---|---|---|---|---|---|
| **`clip_vit_b32_image`** | **0.567** | **0.890** | **0.986** | 0.599 | 0.401 |
| `openclip_l14_laion2b_image` | 0.405 | 0.800 | 0.983 | 0.608 | 0.380 |
| `bioclip_2_image` | 0.083 | 0.556 | 0.424 | 0.890 | 0.872 |

**CLIP B/32 (the original OpenAI CLIP) wins decisively** and is also the cheapest
(512-d, already ~94% populated). LAION L/14 is a solid second. **BioCLIP is useless
for generic quality** — its taxonomy-trained text space gives no spread (scores
saturate ~0.88; within-stack worse than random). Drop BioCLIP from quality prompts.

## Per-dimension (CLIP B/32 — best space)

| Dimension | spearman | AUC | within-stack conc. | verdict |
|---|---|---|---|---|
| `clip_quality_v0` | 0.567 | 0.890 | 0.986 | ⭐ best overall |
| `clip_exposure_v0` | 0.527 | 0.873 | 0.617 | strong global, weak intra-stack |
| `clip_focus_v0` | 0.478 | 0.842 | **0.997** | ⭐ best tie-breaker |
| `clip_misshot_v0` | 0.377 | 0.763 | 0.941 | useful |
| `clip_composition_v0` | 0.300 | 0.731 | 0.549 | global only |
| `clip_wildlife_quality_v0` | 0.268 | 0.689 | 0.985 | modest global, strong tie-break |
| `clip_noise_v0` | 0.155 | 0.603 | 0.546 | weak (known CLIP blind spot) |

> within-stack concordance is computed over the ~34 stacks that contain both a
> picked and a rejected frame (7,556 pick×reject pairs); treat it as the
> tie-break metric, AUC/spearman as the global metric.

## Acceptance criteria (from the spec) — met

1. ✅ Rejected score below picked **inside the same cluster** — B/32 `clip_quality`
   concordance 0.986, `clip_focus` 0.997.
2. ✅ Obvious technical failures score lower — AUC 0.890.
3. ✅ Dimensions directionally meaningful — all positive spearman for B/32 & L/14.
4. ✅ Improves tie-breaking — within-stack concordance ≈ 0.99 (quality/focus).
5. ✅ False positives explainable — `top_positive_prompt` / `top_negative_prompt`
   in the CSV (rejects dominated by "out of focus" / "misfocused").

## Recommendation

- Use **CLIP B/32** for the auxiliary prompt-quality signal (cheapest, best,
  already populated). Most reliable dimensions: **quality + focus** (and **wildlife**
  for intra-burst tie-breaks).
- **Drop** BioCLIP for quality prompting and the **noise** dimension (no signal).
- Treat **exposure/composition** as global priors, not intra-stack tie-breakers.
- Only after this: consider persisting scores (`image_prompt_quality_scores`) —
  check `docs/CANONICAL_SOURCES.md` / `DB_SCHEMA.md` first, per the spec.
- Open gap: re-seed E2E (or backfill prod) to benchmark **OpenAI L/14** + **SigLIP2**,
  the two CLIP variants most likely to challenge B/32.

## Update 2026-06-14 — E2E run (OpenAI L/14 + SigLIP2)

The E2E spike DB (`image_scoring_test` @5433) was started; it holds the seeded
**4-folder subset** (62/44/45/676 ≈ 2,126 images) and is the *only* DB with
`openai_clip_vit_l14_image` + `siglip2_base_image`. Runs in `e2e/` and
`folders_prod/` (prod restricted to the same 4 folders, run as the control).

**E2E embeddings are sound** — prod-restricted-to-same-folders reproduces E2E to
3 decimals (B/32 AUC 0.754 = 0.754; OpenCLIP 0.493 ≈ 0.492). So the weak numbers
below are *corpus difficulty*, not a data bug: these 4 folders were hand-picked
for near-duplicate **culling** bursts, so absolute-quality prompts barely separate
them (OpenCLIP L/14 collapses to ~random here yet scores 0.80 on the full corpus).

Same-corpus (4 folders) `clip_quality_v0` AUC — the only fair head-to-head that
includes OpenAI L/14:

| Space | AUC | source |
|---|---|---|
| **`clip_vit_b32_image`** | **0.754** | folders_prod |
| `bioclip_2_image` | 0.672 | folders_prod (full coverage) |
| `openai_clip_vit_l14_image` | 0.613 | e2e (only source) |
| `openclip_l14_laion2b_image` | 0.493 | folders_prod |

**OpenAI L/14 (#1) does not beat B/32** on the only shared corpus (0.613 vs 0.754).
Note openclip↔bioclip swap ranks vs the full corpus — proof this subset is
unrepresentative; **trust the full-corpus table above for ranking.**

**SigLIP2 is untestable in this env** — its text tower needs `GemmaTokenizer`,
which the `~/.venvs/tf` transformers build can't load (image side worked; text
side can't). Would require upgrading the venv's transformers/tokenizers stack.

**Remaining open item:** to get a *full-corpus* OpenAI L/14 vs B/32 verdict,
backfill `openai_clip_vit_l14_image` into prod (GPU job, ~62.9k images) and re-run
the headline table. On current evidence B/32 stays the recommendation.

## Artifacts

- `clip_prompt_quality__<space>.csv` — per-image, all dimensions + debug similarities
- `summary.json` — full metrics
- `run_full.log` — run log
- `e2e/`, `folders_prod/` — 4-folder subset runs (OpenAI L/14 + same-folder control)
