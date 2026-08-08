---
type: Report
title: Session record — bird-crop Phase 2 re-sweep, Phase 4 focus research, and the algorithmic focus scorer
description: What one Claude Code session built, measured, and got wrong across the pinned crop re-sweep, the classical-focus/AF study, and modules/focus_quality.py.
resource: docs/reports/SESSION_BIRD_CROP_FOCUS_2026-08-05.md
tags: [session, research, bird-detection, focus, iqa, exif, autofocus, crop, technical-failures]
timestamp: 2026-08-05T21:50:00-05:00
okf_version: 0.1
---

# Session record — bird-crop re-sweep → focus research → algorithmic scorer

> **Status:** session record, not a spec. It summarizes decisions, measurements, and corrections so the next
> agent does not re-derive them. The authoritative technical write-ups are
> [`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](BIRD_BBOX_CROP_STUDY_2026-08-01.md) and
> [`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md).
> Hub: [`RESEARCH_SESSIONS_2026-08-05.md`](RESEARCH_SESSIONS_2026-08-05.md).
> Production was untouched: `technical_failures.enabled` remains `false`, no DDL, no migration.

## Session metadata

| Field | Value |
|---|---|
| **Session ID** | `135af92f-8d2a-4f7d-9ca0-b2b92d99f212` |
| **Agent** | Claude Code (CLI), interactive |
| **Model** | Opus 5 — `claude-opus-5` |
| **Record written** | 2026-08-05 21:46:44 −0500 |
| **Work dates covered** | 2026-08-01 → 2026-08-05 (one continued session, context compacted twice) |
| **Repository** | `image-scoring-backend`, branch `master` |
| **Working directory** | `D:\Projects\image-scoring-backend` |
| **Related issue** | [#317](https://github.com/synthet/image-scoring-backend/issues/317) |
| **Commit state at write time** | **all work uncommitted**; `scripts/research/bird_crop/` untracked since before the session |

## What was asked, in order

1. Finish the pinned **Phase 2 re-sweep** — the first sweep produced four mutually incomparable
   populations; wire the orchestrator and evaluators to a 236-id pin, re-run, verify, write a close-out memo.
2. Explain what belongs in the `verdict` column of the human label set.
3. Write a **labelling runbook** with every path, file, and action item.
4. Investigate `deep-research-focus.md` — **can a different algorithm decide bird-crop focus quality?**
5. **Implement** a production algorithmic blur/focus/noise scorer.

Interstitial: save the activity as markdown + a GitHub issue; summarize the branch; summarize the
conversation; export results as CSV/TSV when ready.

Decisions the user made when asked: wait for the bbox backfill before re-running; keep the full sweep
grid; research phase first with production gated on results; **both** classical measures and AF metadata;
ground truth = constructed degradation **and** real-misfocus proxy.

One mid-flight design correction from the user, which was right and changed the architecture:
**"can we use 100% not scaled crop image of a bird before processing?"**

## What was built

### Phase 2 re-sweep — restoring comparability

| File | Change |
|---|---|
| `scripts/research/bird_crop/bursts.py` | `load_boxed_rows(image_ids=…)` — the single shared loader for phases 2b/3, so one insertion point pins both |
| `scripts/research/bird_crop/pin_study_set.py` | `folders_for()`, `--print-folders`, `--ids-file`; `--verify` honours the pin |
| `scripts/research/bird_crop/run_bird_crop_study.sh` | `IDS_FILE` override; **`FOLDERS`/`SUBSET` removed entirely** — they were what recreated the drift; fail-fast before venv load |
| `scripts/research/bird_crop/report.py` | `_read_eval_summary`, `verdict_embedding`, `verdict_caption`, `verdict_focus` |

### Phase 4 — classical focus measures + camera AF intent

| File | Contents |
|---|---|
| `scripts/research/bird_crop/focus_measures.py` | `laplacian_variance`, `tenengrad`, `dog_energy`, `haar_energy` (hand-rolled numpy — PyWavelets absent), `local_entropy`, `canny_edge_density`; registries `MEASURES`, `NOISE_FOOLED`, `TRACKS_BLUR` |
| `scripts/research/bird_crop/af_metadata.py` | Batched exiftool read; pure `_orient_point` (all 8 EXIF orientations); `af_box_in_display_space`, `af_bird_agreement`, `availability` |
| `scripts/research/bird_crop/focus_eval.py` | Tie-aware `roc_auc`, both evaluation arms, rule proposal (deliberately unscored), markdown renderer |
| `scripts/research/bird_crop/degradation_eval.py` | Classical branch bypassing the temp-JPEG path; `_merge_with_existing` / `_COMPARABLE_KEYS` |
| `scripts/research/bird_crop/export_results.py` | CSV/TSV exporter, 6 tables to `reports/bird-crop/tables/` |

### The deliverable — `modules/focus_quality.py`

Algorithmic, no model, no GPU.

| Signal | Algorithm | Why |
|---|---|---|
| Noise | Immerkær (1996), block-wise at p10 | Its 3×3 mask annihilates intensity surfaces up to quadratic, so the response is noise, not content |
| Blur | Crete et al. (2007) | Bounded [0,1] and a *ratio* — needs no per-image calibration, the exact thing `1 - lapvar/500` lacked |
| Sharpness | Noise-corrected Laplacian variance | White noise inflates filtered variance by exactly `20σ²` for the 3×3 kernel; subtract it |
| Focus | Subject ÷ local-background sharpness at one native scale | A ratio cancels ISO, lens, light, scene texture |

Wired into `modules/technical_failures/` behind the existing disabled flag: `classical_metrics.py` gained a
shared `_focus_metrics(gray, box)` used by **both** the cv2 and PIL paths (they previously duplicated the
formula and its bug); `schemas.py` split into persisted / extra / all key sets; `calibration.py` gained a
`noise` weight.

### Tests

`tests/test_bird_crop_pin.py` (13), `tests/test_bird_crop_report.py` (10),
`tests/test_bird_crop_focus_measures.py` (32), `tests/test_bird_crop_af_metadata.py` (29),
`tests/test_focus_quality.py` (26), plus 2 appended to `tests/test_technical_failures_classical.py`.

**Full fast subset: 2482 passed, 272 skipped, 134 deselected, 0 failed** (472.57 s). Ruff clean.

## What was measured

**Comparability restored.** 100 NPZs, one 236-id population, 0 mismatched. Crop verdicts are
phase-dependent: IQA 2.42×–17.51× more sensitive to subject-only degradation; culling shows no benefit.

**Classical measures are at chance against *real* misfocus.** Best blur-tracking AUC **0.5295**;
`laplacian_variance` **0.4772**. The only measure above the bar, `local_entropy` (0.6082), provably does not
track blur — it is a confound, not a result.

**Camera AF geometry is available and informative.** Present on **216/236 (91.5%)** of the pinned set
despite literature pessimism about Z-series bodies; the AF centre falls inside the detected bird box
**73.1%** of the time. Not validatable as ground truth until human verdicts exist.

**Measuring the subject natively roughly triples blur discrimination:** mean blur response
**+0.144 → +0.464**. `open_image_for_ml` already returns the full 8256×5504 embedded JPEG, so 100% costs
nothing extra — forcing `rawpy` gains no pixels, costs 6–12× more, and **fails outright on Z8 files**.
Letting large subjects shrink their context ring rather than resample moved native measurement from 3/8 to
6/8 real images.

**Track A, first model in (2026-08-05 21:37).** On the same 236 images and the same ladders as the GPU models:

| model | kind | full-frame drop | crop drop | ratio | ρ (crop) |
|---|---|---|---|---|---|
| liqe | blur | 0.1495 | 0.5390 | 3.61 | −0.978 |
| topiq | blur | 0.1203 | 0.3495 | 2.91 | −0.952 |
| arniqa | blur | 0.0238 | 0.0936 | 3.93 | −0.505 |
| **laplacian_variance** | **blur** | **0.2405** | **0.7612** | **3.17** | **−0.992** |
| laplacian_variance | motion | 0.2143 | 0.7071 | 3.30 | **−1.000** |
| laplacian_variance | **noise** | 0.0033 | **0.0000** | **0.00** | **+0.996** |

Two readings. On **blur and motion the free CPU measure is competitive with the GPU models** — largest
absolute response in the table and the cleanest monotonicity (ρ = −1.000 on motion, against arniqa's
−0.505). On **noise it inverts**: ρ = **+0.996** means it reports *increasing* sharpness as grain rises.
That is the predicted failure mode, now quantified, and the direct justification for subtracting `20σ²`
before judging sharpness.

## Corrections made during the session

Recorded because each was found by measurement, and each would otherwise be re-derived.

| What | Correction |
|---|---|
| `input_size_eval` was never wired to the pin | Defaulted to the E2E DB (port 5433) and folder scope with **zero overlap**. Fixed via `--print-folders` + `--from-prod`. |
| `report.py` could not answer 2 of 5 phases | `verdict_from_npz` only counted files; now reads `eval_summary.json`. |
| I flagged a 97-second crop run as broken | It was OS page-cache warming. Scores genuinely differed (topiq corr 0.943). |
| My first file-vs-crop comparison was buggy | Keyed on `f.files[0]` = `image_ids`, so arrays were identical. The IQA key is `embeddings`. |
| Said "7 of 9" tight-crop losses | Verified **8 of 9**. |
| `NOISE_FOOLED` omitted `canny_edge_density` | A smooth-ramp probe (0.0 → 0.31) corrected it. |
| `verdict_focus` overstated the result | Reported "complementary" off `local_entropy`, which does not track blur. Added `TRACKS_BLUR`; now reads "no benefit" and names the confound. |
| `degradation_eval` silently clobbered other models | Added `_merge_with_existing`; the natural way to add a model is to run it alone, which discarded the rest. |
| Species CSV export assumed a `by_tercile` shape that does not exist | Fixed against the real `tercile_1..3` nesting. |
| **`analyze()` resized the whole frame then cropped** | **User caught this.** Restructured to native subject + same-scale context ring. |
| Crete perceptual blur is **not** noise-robust | At σ=15 it ranked a defocused ramp (0.1053) *sharper* than real texture (0.1139). Median pre-denoise restores order (0.1948 vs 0.1153); `_verdict` therefore checks noise **before** blur. Module docstring corrected. |
| Immerkær overestimates on texture | 13.2 on a *noiseless* checkerboard. Block-percentile (32×32, p10) cut σ=0 error 2.16 → 0.00 and σ=10 error 11.81 → 9.45. |
| A test failed on checkerboard aliasing | Period-6 pattern aliased against Crete's 9-tap kernel; replaced with band-limited random texture. |
| **Adding `noise` to `TECHNICAL_FAILURE_METRIC_KEYS` would have silently broken DB writes** | `_write_image_technical_failures` builds its row from that tuple against a **hand-written INSERT with 5 fixed placeholders**, and swallows failures with `logger.warning`. Split into persisted/extra/all; added a test that parses the INSERT and asserts the placeholder count. |
| My Track A monitor reported a false "exited" | It ran in Git Bash, where `/mnt/d/...` does not exist and the PID was a Windows PID. Two further attempts hit MSYS path mangling. Track A was never affected. |
| The 4-model Track A run died and lost finished work | `degradation_eval` writes only after **all** models finish, so a WSL restart at ~18:56 discarded two completed measures. The replacement wrapper runs one model per invocation. |

## Environment notes worth keeping

- Long WSL jobs must be launched under `setsid` **and** log to a durable path — `/tmp` does not survive a
  WSL restart, and plain backgrounded `wsl -e` runs get killed.
- `Monitor` commands run in **Git Bash on Windows**, not WSL. Wrap as `wsl -e bash -c '…'`; a bare
  `/home/...` argument gets MSYS-mangled to `C:/Program Files/Git/home/...`.
- Prefer one invocation per model for anything that only persists at the end.

## State at write time

**In flight:** `.agent/scratch/run_trackA_sequential.sh` (wrapper PID 963, started 21:11) — one
`degradation_eval` invocation per classical measure. `laplacian_variance` finished 21:37 and correctly
carried forward `['liqe', 'topiq', 'arniqa']`. `tenengrad`, `dog_energy`, `haar_energy` remain, ~26 min each.
A concurrent student-scorer training run (`.agent/scratch/run_e2_full_only.sh`) competes for CPU.

**Next:** re-run `export_results.py` once Track A completes so the degradation tables carry the classical
rows; then commit — nothing from this session is committed yet.

**Gated, not done:** productionizing the scorer (bbox parameter for `detect_technical_failures`, AF columns
on `image_exif` + Alembic migration, gallery notification per
[`cross_repo_contract_change.md`](../../.agent/workflows/cross_repo_contract_change.md)). The verdict
thresholds in `focus_quality.py` are engineering defaults, not validated cut-offs — the module scores blur
and noise, which are physically well-defined, and reports `focus_ratio` as a relative observation only.

## The Cursor half of the same day

A parallel Cursor Agent (Grok 4.5) session closed out the study on the same pinned set: the multi-agent
labelling pass (**236 images / 54 bursts** → 60 best · 105 good · 71 reject, geometry delta AUC
**0.2175** superseding a stale 0.3477), the sequential Track A recovery, `_arm_b_vs_labels`, the CSV
tables exporter, and the todo list left open at pause.

That record lives in [`SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md`](SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md)
— kept as its own page rather than duplicated here, so the two accounts cannot drift apart. Both are
routed from [`RESEARCH_SESSIONS_2026-08-05.md`](RESEARCH_SESSIONS_2026-08-05.md).

## Resolved after the pause (2026-08-08)

The "State at write time" section above is left as it stood. What it was waiting on has since happened:

- **Track A completed** — 7 models on the pinned 236, merges clean. `haar_energy` died twice at startup to
  the same host-sleep signature that killed the E2 trains, costing only that model each time because the
  sequential wrapper persists per invocation.
- **The classical measures top the study on constructed degradation** — `dog_energy` **8.80×** and
  `haar_energy` **7.20×** crop sensitivity to subject-only blur, above LIQE's 3.61×. On the noise ladder
  three of four are flagged **Suspect**: `laplacian_variance` scores ρ **+0.996**, sharpness rising with grain.
- **Arm B was scored and fails** — precision **0.1429** against a base reject rate of **0.2963** (lift
  **×0.48**, recall **0.0156**) on the agent-derived labels. The proposed rule is worse than the base rate.
- **Committed** on `research/bird-crop-focus-317` under `Closes #317`; tables exported as CSV and TSV.

The "Gated, not done" paragraph still stands unchanged — productionization remains gated, and the Arm B
result makes that gate firmer rather than looser.
