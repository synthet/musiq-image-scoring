---
type: Report
title: Bird-bbox crop study — pinned re-sweep close-out
description: Does a subject-localized crop beat the whole downscaled frame, per pipeline phase? Close-out of the re-sweep on a pinned 236-image population after the first sweep produced four incomparable populations.
resource: docs/reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md
tags: [research, bird-detection, crop, iqa, culling, captions, species, bbox]
timestamp: 2026-08-01T00:00:00Z
okf_version: 0.1
---

# Bird-bbox crop study — pinned re-sweep close-out

> **Status:** point-in-time research memo, not a product spec. Production was read **read-only** throughout; every artifact lands under `reports/`. Tracking issue: [#317](https://github.com/synthet/image-scoring-backend/issues/317).

## Summary

The question: a bird occupies a median **11.7%** of the frame in this library, so when a 45MP frame is downscaled to a model input the subject survives at roughly **78 px** at 224. Does feeding models a `bird_bbox` crop instead of the whole downscaled frame buy anything?

**The answer is phase-dependent, and that is the finding.** Cropping is not a global upgrade — it helps exactly where the signal is about the subject, and does nothing where the signal is about the scene.

| Phase | Verdict | Ground truth | Headline |
|---|---|---|---|
| Quality scoring (IQA) | **add as complementary signal** | constructed | Crop is **2.42×–17.51×** more sensitive to subject-only degradation |
| Captions (BLIP) | **add as complementary signal** | derived | Within-burst caption uniqueness **+0.1052** |
| Species (BioCLIP) | **add as complementary signal** | derived | Agreement +0.0181 overall, but **+0.053 on the smallest-subject tercile** |
| Culling embeddings | **no benefit** | constructed | Burst pair-margin **+0.0028** — below the ±0.02 materiality bar |
| Bbox geometry | **not yet measured** | human | Blocked on human verdicts; bias probe only |

The culling result is the useful negative: crop-vs-full-frame is noise there (best crop source beats the full frame in 6 of 9 model × long-edge cells, by amounts that do not survive rounding), and the tight `crop` variant *loses* to the full frame in 8 of 9 and is never the best source in any cell. Whatever cropping is worth, it is not worth it for grouping burst frames.

## Why this was re-run

The first sweep (2026-07-29) produced numbers that could not be compared to each other.

`input_size_embed._subset_rows` takes a *strided* sample — `rows[::step][:n]` — of the rows that currently have a usable `bird_bbox`, and a `backfill_bird_bbox.py --all-null` job was growing that population throughout the sweep (boxed count 21,194 → 24,562 → 35,322). Every process that started at a different time therefore sampled a **different** 200 images. `--boxed-only` guaranteed the crop and full-frame arms covered the same *number* of images; it never pinned *which*.

Grouping the resulting NPZs by their exact sorted id set gave **four distinct populations**. All 38 files are quarantined in [`npz/archive_mixed_population/`](../../reports/clip-culling/input-size/npz/archive_mixed_population/README.md) — kept rather than deleted, because they cost about four GPU-hours and they are the evidence for the drift itself. They must not be fed to `input_size_eval`.

A second, quieter problem: the old sweep's folder scope (`62,676`) had **zero overlap** with the human label set. Those labels could never have evaluated Phase 2 at all.

## The fix — one pinned population

`reports/bird-crop/study_image_ids.txt` pins **236 production image ids** across **34 folders**, generated from the human label CSV by [`pin_study_set.py`](../../scripts/research/bird_crop/pin_study_set.py). Binding to the label set rather than a folder sample means every track shares one population *and* the within-burst human verdicts, when filled in, will apply to all of them.

Harness changes that make the pin binding rather than advisory:

| Change | Why |
|---|---|
| `run_bird_crop_study.sh` phases 2/2b/3 pass `--image-ids-file`; **`FOLDERS`/`SUBSET` removed entirely** | Those were the levers that recreated the drift. The comparability harness no longer offers them; the underlying CLIs keep them for ad-hoc work. |
| Fail-fast when the pin is missing, before venv/model load | A missing pin otherwise costs hours of GPU time and yields another incomparable population. |
| `bursts.load_boxed_rows(image_ids=…)` | One insertion point for both phase-2b/3 evals. Rejects `folders`/`limit` alongside a pin and raises naming any id that did not survive the `bird_bbox` + `image_exif` filters. |
| `--image-ids-file` on `species_crop_eval` / `degradation_eval`; pin overrides `--limit` | `--limit 120` would strided-sample the pin — the original bug, one layer down. |
| `input_size_eval` invoked with `--from-prod` + `CLIP_CULLING_FOLDERS` derived from the pin | Its defaults are the E2E database and folder scope `62,44,45,676`, which has zero overlap with the pin. Left alone it joins production NPZ ids against the wrong database and finds nothing. |
| `pin_study_set --verify` run as a gate | The check whose absence caused the rework. |

**Verification:** `pin_study_set --verify` reports **100 pinned-track NPZs all carrying the same 236 image ids, 0 mismatched**. `degradation.json` and `species_crop.json` record `image_ids_file` / `n_pinned_ids` / `n_pinned_covered` so each artifact states its own population. Species covered **236 of 236** pinned ids across 54 bursts — the pin and the 3–8 frame burst window agree exactly, since both derive from the same bounds.

## Results

### The premise, measured (Phase 1, whole library)

Re-run after the `bird_bbox` backfill completed, so these are settled figures: **37,417** images with a real box, 29,068 carrying the not-detected sentinel, **0 remaining NULL**.

| Full-frame resize | bird long side p10 | p50 | p90 |
|---|---|---|---|
| 224 px | 42.8 | 77.6 | 157.4 |
| 384 px | 73.4 | 133.1 | 269.7 |
| 512 px | 97.9 | 177.4 | 359.7 |

`area_frac` p10/p50/p90: **0.0399 / 0.1173 / 0.4471**.

### Quality scoring — the strongest result (constructed ground truth)

Degradation is applied at known strength to the subject region only, so this needs no human labels and cannot be circular. Relative score drop, clean → worst:

| Model | Blur | Motion | Noise |
|---|---|---|---|
| liqe | **3.61×** | **2.42×** | **17.51×** |
| topiq | **2.91×** | **3.12×** | **7.00×** |
| arniqa | **3.93×** | **3.75×** | **11.80×** |

Every cell is far above 1.0, which is what would refute the premise. Noise is the extreme case: full-frame LIQE barely moves (0.0224 relative drop) while the crop drops 0.3923 — averaged over 45MP, subject noise is invisible.

This is a **complementary** signal, not a replacement: the crop measures whether the *bird* is sharp, the full frame whether the *photo* is clean. Both are worth having.

### Culling embeddings — no benefit (constructed ground truth)

Burst pair-margin (separation between same-burst and different-burst distances, grouped by EXIF capture time — unbiased, unlike `pick_review`, which scores against pipeline-produced columns and is circular):

| Model | 224 | 384 | 512 |
|---|---|---|---|
| clip_b32 | file 0.2044 / best crop 0.2054 | file 0.2140 / best crop 0.2182 | **file 0.2192** / best crop 0.2192 |
| openclip | **file 0.3398** / best crop 0.3387 | file 0.3353 / best crop 0.3447 | **file 0.3394** / best crop 0.3387 |
| openai | file 0.2414 / best crop 0.2493 | file 0.2693 / best crop 0.2715 | file 0.2711 / best crop 0.2737 |

Mean delta **+0.0028**. Tight `crop` is the best source in **0 of 9** cells and loses to the plain full frame in **8 of 9**; where a crop source leads at all it is `croppad25`/`croppad50`, by amounts inside the noise. Grouping ARI tells the same story inconsistently — clip_b32 gains at 384/512, the L/14 towers lose.

### Captions — cropping changes what BLIP sees (derived)

Within-burst caption uniqueness rises **+0.1052** (best crop source minus full frame, averaged over three long edges) — five times the materiality bar. Cropping makes BLIP distinguish frames within a burst substantially more. Ground truth is `derived`: this measures that BLIP says something *different*, not something more *correct*.

### Species — a size-dependent effect (derived)

Overall: within-burst agreement 0.9172 (crop) vs 0.8991 (whole), delta **+0.0181**; confidence +0.0398; labels flip on 21.2% of images. The overall number understates it, because the effect is concentrated where the premise predicts:

| Subject size | Agreement (crop) | Agreement (whole) | Delta |
|---|---|---|---|
| smallest | 0.9373 | 0.8844 | **+0.0529** |
| middle | 0.9253 | 0.9563 | −0.0310 |
| largest | 0.8889 | 0.8565 | +0.0324 |

Cropping helps most exactly when the bird is small in frame. Confidence rising alongside agreement on the smallest tercile (+0.101) is consistent with the crop removing background cues the classifier was over-trusting.

## Ground-truth standing

| Tag | Meaning |
|---|---|
| `human` | Human within-burst verdicts. Non-circular; **the only basis for an accuracy claim.** |
| `constructed` | True by construction (known degradation strength) or unbiased (EXIF capture-time bursts). |
| `derived` | Compared against pipeline-produced columns (`rating`, `pick_status`, BLIP captions). Measures agreement with the incumbent stack, **not** accuracy. |

## Limits

- **No accuracy claim is made anywhere in this memo.** The 236 `verdict` cells in `reports/bird-crop/labels/label_set.csv` are still empty. Every result above is either constructed ground truth or agreement with the incumbent stack. The geometry phase stays `not yet measured` for exactly this reason.
- **The culling grouping metrics are thin.** The pin spreads 236 images over 34 folders to serve within-burst labelling, so only 8 folders held enough images to evaluate clustering. The pair-margin figure is more trustworthy than ARI here. The old sweep's 200-images-in-2-folders shape gave denser clusters — and incomparable populations.
- **`pick_review` is empty.** `mean_keep_rating` / `mean_reject_rating` come back NaN for the pinned set. That metric is `derived` anyway, so nothing rests on it.
- **Only the top-1 box is stored.** `bird_bbox` holds a single object; multi-bird frames are represented by their highest-confidence bird only.
- **`cropctx` is a no-op on this library** — it expands only 5 of ~25k boxes at 224 px, because 45MP frames already yield native boxes far larger than any model input. Excluded from the sweep; retained for long edges ≥ 768.

## What remains

1. **Fill the human label set** — `reports/bird-crop/labels/label_set.csv`, 236 rows. This is the only gate on an accuracy verdict for bbox geometry, and the only non-circular check on the species and caption results.
2. **Re-run `geometry_eval`** once verdicts exist; it already reads them.
3. Productionizing a crop-based IQA signal is **not** proposed here — this memo measures, it does not design.

## Artifacts

| Artifact | Contents |
|---|---|
| [`reports/bird-crop/REPORT.md`](../../reports/bird-crop/REPORT.md) | Generated consolidated report with per-phase verdicts |
| `reports/bird-crop/{geometry,degradation,species_crop}.{json,md}` | Per-phase detail |
| `reports/bird-crop/study_image_ids.txt` + `_provenance.json` | The pinned population and how it was derived |
| `reports/clip-culling/input-size/eval_summary.json` | Embedding / IQA / caption eval metrics |
| [`npz/archive_mixed_population/`](../../reports/clip-culling/input-size/npz/archive_mixed_population/README.md) | Quarantined pre-pin runs — evidence only, never eval input |

## See also

- Session record (build + corrections + Cursor close-out): [`SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](SESSION_BIRD_CROP_FOCUS_2026-08-05.md)
- Dual-arc hub: [`RESEARCH_SESSIONS_2026-08-05.md`](RESEARCH_SESSIONS_2026-08-05.md)
