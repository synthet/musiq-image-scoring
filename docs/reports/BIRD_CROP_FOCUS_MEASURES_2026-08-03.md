---
type: Report
title: Bird-crop focus decision — classical measures and camera AF intent
description: Can zero-inference signals decide whether a bird crop is in focus? Classical focus measures sit at chance against real camera misses; the camera's own AF geometry turns out to be available and informative.
resource: docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md
tags: [research, bird-detection, focus, iqa, exif, autofocus, crop]
timestamp: 2026-08-03T00:00:00Z
okf_version: 0.1
---

# Bird-crop focus decision — classical measures and camera AF intent

> **Status:** point-in-time research memo, not a product spec. Production was read **read-only**; every artifact lands under `reports/`. Phase 4 of the bird-bbox crop study ([close-out memo](BIRD_BBOX_CROP_STUDY_2026-08-01.md), issue [#317](https://github.com/synthet/image-scoring-backend/issues/317)). Nothing here changes production: `technical_failures.enabled` remains `false`, no DDL, no migration.

## The question

The crop study established that a bbox crop is **2.42×–17.51×** more sensitive to subject-only degradation than the whole frame — but measured that only with learned IQA models (LIQE / TOPIQ / ARNIQA), each of which costs a GPU pass. Nothing turned that into an explainable, cheap decision about whether a given bird crop is acceptably sharp.

Prompted by a focus-detection literature survey (`deep-research-focus.md`), this phase tested two zero-inference signals:

1. **Classical focus measures** on the crop — Laplacian variance, Tenengrad, DoG, Haar wavelet energy, entropy, Canny edge density.
2. **The camera's own AF metadata** — where it actually tried to focus, and how far away.

## Headline

**Classical focus measures do not predict real misfocus on this library, and the AF-conjunction rule built on them is worse than chance.** Every measure that actually responds to blur sits at chance against real camera misses — even though the same measures show the crop's sensitivity advantage clearly on *constructed* degradation. The camera's AF geometry is available far more widely than the literature suggested and is a genuinely independent cue, but combining it with a sharpness threshold did not produce a usable decision rule.

| Finding | Evidence |
|---|---|
| Blur-tracking measures are at chance against real camera misses | Best AUC 0.5295 (`haar_energy`); `laplacian_variance` **0.4772** |
| The proposed Arm B rule is **worse than the base rate** | precision **0.1429** vs base reject rate **0.2963** — lift **×0.48**, recall **0.0156** (TP 1 / FP 6 / FN 63) |
| …yet the same measures carry the crop premise on constructed blur | `dog_energy` **8.80×**, `haar_energy` **7.20×** crop sensitivity — above LIQE's 3.61× |
| …and are unusable on noise | 3 of 4 flagged **Suspect**; `laplacian_variance` scores ρ **+0.996** on the whole-frame noise ladder |
| Crop sharpness says nothing about whether the camera found the bird | `crop/laplacian_variance` median 779.6 (AF agreed) vs 789.1 (AF disagreed) |
| The one measure above the bar is a confound | `local_entropy` AUC 0.6082 — but it provably moves the **wrong way** under blur |
| AF geometry is widely available | **216 / 236** pinned images (91.5%); Z6ii 101/101, Z8 115/127, D300 0/8 |
| AF and the bird detector usually agree | **158 / 216 = 73.1%** of AF centres fall inside the detected bird box |

## Arm A — do image-only measures predict where the camera focused?

Non-circular by construction: no measure reads AF data; AF disagreement is only the label. AUC 0.5 is chance.

| Measure | AUC (crop) | AUC (full frame) | crop better by | tracks blur? | noise-fooled? |
|---|---|---|---|---|---|
| `laplacian_variance` | 0.4772 | 0.4646 | −0.0126 | yes | yes |
| `tenengrad` | 0.4650 | 0.4983 | +0.0333 | yes | yes |
| `dog_energy` | 0.5012 | 0.5404 | −0.0392 | yes | yes |
| `haar_energy` | 0.5295 | 0.5280 | +0.0015 | yes | yes |
| `local_entropy` | **0.6082** | 0.5198 | +0.0884 | **no** | no |
| `canny_edge_density` | 0.5080 | 0.5614 | −0.0534 | yes | yes |

**Read the `tracks blur?` column before the AUC column.** A measure that does not fall when detail is destroyed cannot support a claim about focus, however well it separates the groups. `local_entropy` is the case in point: blurring a two-level pattern creates intermediate grey levels and *raises* entropy (pinned by `test_entropy_does_not_track_blur`). Its separation reflects scene complexity or subject size, not sharpness.

Crop measured better than the full frame for only 3 of 6 measures, and the margins are inside the noise — so on *real* misses, this phase found no evidence for the crop advantage that synthetic degradation shows so strongly.

### Why the negative is plausible rather than a harness fault

The measures do work: on synthetic blur they collapse by orders of magnitude (a smooth ramp goes from 0.019 to 4435 in Laplacian variance when noise is added; a checkerboard drops from 94,628 to 0.75 under σ=3 blur). What they cannot do is tell a *deliberately* soft bird from a sharp one in a real photograph, where subject texture, contrast, and background clutter vary far more than focus does.

## Arm B — proposed decision rule, and why it fails

> **Rule:** flag when crop `laplacian_variance` ≤ p10 **and** the AF centre falls outside the bird box.

- p10 threshold: **327.74**
- images with AF geometry: 216
- soft crops (bottom decile): 22
- AF centre outside the bird box: 58
- flagged by **both**: **7 (3.2%)**

The rule could not be scored when this memo was first written: the only label then available was AF
disagreement, which is an *input* to the rule, so scoring against it would have been predicting its own
input. The `agent-derived` label set closed that gap. The answer is a clean negative.

| | Value |
|---|---|
| Ground truth | `agent-derived` (`label_set_judges-57c86c08-….json`), positive class `reject` |
| Eligible (AF ∩ labelled) | 216 |
| Flagged | 7 · TP **1** / FP **6** / FN **63** |
| Precision | **0.1429** |
| Base reject rate | **0.2963** |
| Lift vs base | **×0.48** |
| Recall | **0.0156** |

**Flagging on this rule is worse than flagging at random.** A coin weighted to the base rate would be
right 29.6% of the time; the rule is right 14.3% of the time, and it finds 1 of the 64 rejects. The
conjunction is the problem: it fires on 7 of 216 images, so it is simultaneously too rare to be useful
and too wrong to be trusted. This is consistent with Arm A rather than a surprise — a rule built on a
measure that sits at chance cannot become accurate by intersecting it with a second cue.

The agent-derived caveat cuts both ways and is worth stating plainly: correlated judge errors could
depress a genuinely good rule. But the failure here is not marginal — a ×0.48 lift at 1.6% recall is not
the shape of a rule that a better label set rescues.

## What the AF metadata turned out to be

The literature survey warned that Nikon Z-series bodies do not reliably expose focus data. **That is not true for this library.** A Z8 NEF returns:

```
AFAreaXPosition 3388   AFAreaYPosition 2317
AFAreaWidth      218   AFAreaHeight     218
AFImageWidth    8256   AFImageHeight   5504
FocusDistance   3.43 m AFAreaMode      "Wide (L)"
```

Across the whole boxed library (100% NEF): **Z8 61.1% + Z6ii 24.5% = 85.6%** carry AF region geometry. The older DSLRs (D90 13.5%, D300 0.9%) carry `FocusDistance` only. Ironically the *newer* mirrorless bodies are the well-covered ones.

**Coordinate spaces differ and this is the trap.** `images.bird_bbox` is stored in EXIF-**oriented** (display) space; Nikon writes AF coordinates in **sensor** space. A missing rotation would not crash — it would silently report disagreement on every portrait frame and make the AF cue look worthless. All 8 EXIF orientations are reconciled and unit-tested.

## Ground-truth standing

| Tag | Meaning |
|---|---|
| `constructed` | True by construction (known degradation strength). Used by Track A. |
| `derived` | AF disagreement — the camera's intent, not a human verdict. Everything in Arm A. |
| `agent-derived` | Within-burst verdicts from a vision-LLM panel, **not human**. The only non-circular label available for Arm B. |

The AF proxy is `derived` and imperfect: it conflates genuine misfocus with the detector picking the wrong bird in a multi-bird frame (only the top-1 box is stored) and with focus-recompose technique.

`agent-derived` is a weaker warrant than it looks. The verdicts came from a five-judge panel (Claude ×2, Cursor ×2, Antigravity ×1; Codex excluded for failing the unreadable-sheet trust gate), and the judges saw the same contact sheets, so their errors are correlated rather than independent. It breaks Arm B's circularity — no judge saw AF data — but it does not substitute for human ground truth. **Every accuracy figure below inherits that caveat.**

## What was built

| Component | Purpose |
|---|---|
| `scripts/research/bird_crop/focus_measures.py` | Six pure-function measures + `MEASURES`, `NOISE_FOOLED`, `TRACKS_BLUR` registries. Haar hand-rolled in numpy — no PyWavelets dependency for a spike. |
| `scripts/research/bird_crop/af_metadata.py` | Batched exiftool read; pure `af_box_in_display_space` (all 8 orientations, `AFImageWidth` fallback) and `af_bird_agreement` (centre-inside, IoU, distance). |
| `scripts/research/bird_crop/focus_eval.py` | Phase 4 evaluator; tie-aware `roc_auc`; writes `reports/bird-crop/focus.{json,md}`. |
| `degradation_eval.py` | Classical measures registered as `CLASSICAL_MODELS`, scored on the array directly. |
| `run_bird_crop_study.sh`, `report.py` | `PHASE=4`; a **Focus (classical + AF)** verdict row. |
| `tests/test_bird_crop_focus_measures.py`, `tests/test_bird_crop_af_metadata.py` | 61 tests pinning behaviour **and** documented failure modes. |

### Two traps designed around

1. **Classical measures bypass the temp-JPEG path.** `degradation_eval.score_pil` writes a temp JPEG because every production IQA engine takes a path. JPEG compression discards exactly the high-frequency content a Laplacian reads, so routing classical measures through it would measure the codec. They score the in-memory array.
2. **Noise inflation is reported, not hidden.** Five of six measures rise under noise on a defocused region. That is a property of the measures, recorded in `NOISE_FOOLED` and surfaced as a column, not smoothed away.

### Behaviours found by measurement, not assumption

- **Canny edge density is non-monotonic at low blur** — density *rises* from 0.2499 (σ 0.5) to 0.2608 (σ 1.0) before collapsing, because Canny smooths internally. That disqualifies it for mild misfocus, which is the case that matters most.
- **`canny_edge_density` is noise-fooled too** — my initial `NOISE_FOOLED` list omitted it; a smooth-ramp probe (0.0 → 0.31) corrected it.
- **`degradation_eval` silently clobbered other models' results.** Running with `--models laplacian_variance` rewrote the whole file, discarding liqe/topiq/arniqa. Fixed with `_merge_with_existing`, which carries forward prior models when the population and geometry match and refuses (naming mismatched fields) when they don't.

## Track A — the same measures on constructed ground truth

Arm A asked whether classical measures predict *real* camera misses and found chance. Track A asks the
different question the crop study asked of the learned models: when the subject is degraded by a **known**
amount, does the crop notice more than the full frame? Same 236 images, same blur / motion / noise ladders,
same `crop_sensitivity_ratio`.

| Measure | blur | motion | noise |
|---|---|---|---|
| `liqe` *(learned)* | 3.61× | 2.42× | 17.51× |
| `topiq` *(learned)* | 2.91× | 3.12× | 7.00× |
| `arniqa` *(learned)* | 3.93× | 3.75× | 11.80× |
| `laplacian_variance` | 3.17× | 3.30× | ⚠ 0.00× |
| `tenengrad` | 4.63× | 4.44× | 0.51× |
| `haar_energy` | **7.20×** | **6.35×** | ⚠ 0.11× |
| `dog_energy` | **8.80×** | **6.52×** | ⚠ 0.47× |

**On blur and motion the classical measures match or beat the learned models** — `dog_energy` at 8.80× is
the highest crop advantage in the whole study, above LIQE's 3.61×. A zero-inference measure carries the
crop premise as well as a GPU pass does, for the degradations it can see.

**On noise they invert and must not be used.** The harness self-check marks
`laplacian_variance/noise`, `dog_energy/noise` and `haar_energy/noise` as **Suspect** because they cannot
rank even the *whole-frame* noise ladder — `laplacian_variance` scores ρ = **+0.996** on it, i.e. the
"sharpness" reading climbs monotonically as grain is added. That is the `NOISE_FOOLED` property measured
directly rather than argued from theory, and it is why `modules/focus_quality.py` estimates sensor noise
and subtracts it before reading sharpness at all.

### Track A does not soften Arm A

The two arms disagree because they answer different questions against different ground truth, and holding
both is the point of the design:

- **Constructed** (Track A): given a *known* degradation, the crop response is large and orderly. 8.80×.
- **Derived** (Arm A): given a *real* photograph, no measure separates the camera's hits from its misses.
  Best blur-tracking AUC **0.5295**.

A measure can be exquisitely sensitive to added blur and still be useless for deciding whether a bird was
in focus, because in real frames subject texture, contrast and background clutter vary far more than focus
does. Quoting 8.80× as evidence for a focus check would be reading the constructed number as if it were
the derived one.

## What remains

1. **Human verdicts.** The label set is filled — 236 rows, 60 best / 105 good / 71 reject — but the verdicts are **agent-derived**, so the human gate is still open. It was enough to score Arm B directionally, and it returned a negative; a human set would be needed to overturn that, not merely to confirm it. See [the labelling runbook](../guides/BIRD_CROP_LABELLING.md).
2. **Do not productionize this rule.** A crop-Laplacian threshold, alone or intersected with AF geometry, does not earn its place on this evidence. Should some future rule prove out against human verdicts, productionizing means AF columns on `image_exif`, an Alembic migration, and the [cross-repo contract change](../../.agent/workflows/cross_repo_contract_change.md) procedure.

What the phase *does* leave behind is `modules/focus_quality.py`: a noise-aware blur estimate that replaced `1 - laplacian_variance / 500` in `technical_failures`. That formula could not work — on a defocused region σ=15 grain moved Laplacian variance from 0.019 to 4435, so a blurred high-ISO frame scored as tack sharp. Fixing it is a bug fix, not a productionization of any finding here; `technical_failures.enabled` remains `false`.

## Artifacts

| Artifact | Contents |
|---|---|
| `reports/bird-crop/focus.{json,md}` | Arm A AUCs, AF coverage, Arm B rule scored against the labels |
| `reports/bird-crop/REPORT.md` | Consolidated verdicts, now including Focus |
| `reports/bird-crop/degradation.{json,md}` | Track A — all 7 models on the pinned 236 |
| `reports/bird-crop/tables/*.{csv,tsv}` | Every number above, machine-readable — including `focus_arm_b_rule` with its `ground_truth_kind` column |

## See also

- Session record (Phase 4 build + Cursor addendum): [`SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](SESSION_BIRD_CROP_FOCUS_2026-08-05.md)
- Dual-arc hub: [`RESEARCH_SESSIONS_2026-08-05.md`](RESEARCH_SESSIONS_2026-08-05.md)
