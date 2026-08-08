---
type: Report
title: Session record — bird-crop study close-out (labelling, Track A, Arm B)
description: The Cursor-agent half of the 2026-08-05 bird-crop close-out — multi-agent labelling results, sequential Track A recovery, Arm B evaluation against agent labels, and the todos left open at pause.
resource: docs/reports/SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md
tags: [session, research, bird-detection, focus, labelling, multi-agent, crop, iqa]
timestamp: 2026-08-05T21:46:47-05:00
okf_version: 0.1
---

# Session record — bird-crop close-out: labelling, Track A, Arm B

> **Status:** session record, not a spec. This is the **Cursor-agent half** of the 2026-08-05
> bird-crop work; the Claude Code half is
> [`SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](SESSION_BIRD_CROP_FOCUS_2026-08-05.md). Both ran against
> the same pinned 236-image set on the same day. Start at the day hub:
> [`RESEARCH_SESSIONS_2026-08-05.md`](RESEARCH_SESSIONS_2026-08-05.md).
>
> The authoritative technical write-ups remain
> [`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](BIRD_BBOX_CROP_STUDY_2026-08-01.md) and
> [`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md).
> Production was untouched: `technical_failures.enabled` remains `false`, no DDL, no migration.

## Session metadata

| Field | Value |
|---|---|
| **Session timestamp** | 2026-08-05 21:46:47 −0500 |
| **Agent** | Cursor Agent |
| **Model** | Cursor Grok 4.5 |
| **Primary repo** | `image-scoring-backend` |
| **Related repo** | `image-scoring-skills` (labelling harness) |
| **Related issue** | [#317](https://github.com/synthet/image-scoring-backend/issues/317) |
| **Raw source** | [`../raw/2026-08-05-bird-crop-closeout-cursor.md`](../raw/2026-08-05-bird-crop-closeout-cursor.md) |
| **Commit state at write time** | uncommitted |

## Goal

Close out the pinned bird-bbox crop study after Phases 2 / 2b / 3 / 4 and the multi-agent labelling
pass: finish **Track A** (classical degradation), refresh the memos, add label-based accuracy where it
is not circular, do transcript hygiene, and version both repos under `Closes #317`.

## Multi-agent labelling — the study's only non-circular ground truth

Run through the `/bird-crop-label` harness in **`image-scoring-skills`** (fan-out → merge, `burst-judge`
persona, UUID-named sheets and verdicts).

| Aspect | Result |
|---|---|
| Coverage | **236 images / 54 bursts** — the full pin |
| Verdict distribution | **60 best · 105 good · 71 reject** |
| Judges used | Claude ×2, Cursor ×2, Antigravity ×1 |
| Judge excluded | **Codex** — failed the unreadable-sheet trust gate |
| Canonical sidecar | `label_set_judges-57c86c08-6a1e-41d0-88b7-bf9d5e0a2f59.json` (UUID-only policy) |
| Geometry `PHASE=1` verdict | **add complementary**, delta AUC **0.2175** |

Merge bugs found and fixed during the pass: a bare `END` token, trailing rationale text bleeding into
verdicts, and a stale non-UUID sidecar being picked up.

**These labels are agent-derived, not human.** Every downstream accuracy claim inherits that caveat.

## Work done in this session

### 1. Track A — classical degradation, recovered by serialising it

The original all-four-models run was interrupted by a WSL restart and **wrote nothing**:
`degradation_eval` persists only after all models finish, so an interrupt discards completed measures.

Relaunched as **one model per invocation** so `_merge_with_existing` persists after each. At the pause
check (~21:44):

| Measure | State |
|---|---|
| `laplacian_variance` | **finished and merged** (`liqe` / `topiq` / `arniqa` carried forward intact) |
| `tenengrad` | ~50/236 in flight |
| `dog_energy`, `haar_energy` | queued |

Wrapper `run_trackA_sequential.sh`; log `reports/bird-crop/trackA.log`. The first merged row is
tabulated in the [companion record](SESSION_BIRD_CROP_FOCUS_2026-08-05.md) — `laplacian_variance` is
competitive with the GPU models on blur and motion, and **inverts on noise** (ρ = +0.996).

### 2. Arm B evaluated against the agent labels

Implemented `_arm_b_vs_labels` in `scripts/research/bird_crop/focus_eval.py` — reject treated as the
positive class, results tagged agent-derived. Unit tests in
`tests/test_bird_crop_focus_arm_b_labels.py` (3 passed). The focus re-run itself is **still pending**
until Track A completes.

Arm B is the proposed rule *soft crop ∧ AF centre outside the box*, originally left unscored because
scoring it against the AF proxy would be circular. Agent labels break that circularity — at the cost of
not being human.

### 3. CSV tables exporter

`scripts/research/bird_crop/export_results.py` → six CSVs plus a README in
`reports/bird-crop/tables/`. Fixed a species-tercile shape bug; the README now warns readers to check
`tracks_blur` before quoting any AUC. Provenance note corrected from "empty human verdicts" to
agent-derived labels.

### 4. Hygiene

- Root `2026-*.txt` transcript dumps moved to `.agent/scratch/session-transcripts/` in both repos.
- Non-canonical `label_set_judges-*.json` archived to `.agent/scratch/bird-crop-label-sidecars/`;
  only `57c86c08…` kept.
- Keep-awake held for the duration of the long runs.
- One dump reappeared at repo root after the sweep
  (`2026-08-03-220609-cusersdmnsycursorplanspinnedphase2reswe.txt`) and was still there at pause.

### 5. Open question, discussed but not implemented

*"Can we use a 100% unscaled bird crop for the focus algorithms?"* — the current path is
`work_long_edge=3000` with measurement at `long_edge=512`. Native-resolution measurement is feasible for
the intensive / mean-normalised classical measures, with cost and kernel-scale caveats. No code change
was made here; the Claude Code session **did** restructure `modules/focus_quality.py` along exactly this
line and measured roughly a 3× lift in blur discrimination (+0.144 → +0.464).

## Open todos at pause

| ID | Status | Next action |
|---|---|---|
| `finish-track-a` | In progress | Let sequential Track A finish; confirm merge; `PHASE=report`; re-run `export_results` |
| `update-focus-memo` | Pending | Fold Track A ratios in against 2.42×–17.51×; record labelling provenance and AUC churn; append `docs/log.md` |
| `labels-accuracy-pass` | Pending | Re-run `focus_eval` for Arm B vs agent labels; note geometry IQA-rank already done (0.2175); skip circular `pick_review` as accuracy |
| `transcript-hygiene` | Mostly done | Move the leftover root `2026-08-03-220609-…txt` to scratch |
| `version-harness` | Pending | Commit backend bird-crop work (tables, exporter, Arm B) and the skills `/bird-crop-label` harness; `Closes #317`; exclude `student_scorer` and root transcripts |

## Key paths

| Path | Role |
|---|---|
| `reports/bird-crop/REPORT.md` | Consolidated verdicts |
| `reports/bird-crop/degradation.{json,md}` | Track A + learned IQA (merge-protected) |
| `reports/bird-crop/trackA.log` | Sequential Track A log |
| `reports/bird-crop/labels/label_set.csv` | Agent-derived verdicts |
| `reports/bird-crop/tables/` | Machine-readable CSV exports |
| `scripts/research/bird_crop/focus_eval.py` | Phase 4 + Arm B vs labels |
| [`../guides/BIRD_CROP_LABELLING.md`](../guides/BIRD_CROP_LABELLING.md) | Labelling runbook |

## Caveats carried forward

- **Agent-derived ground truth is not human ground truth.** Do not productionize crop IQA, AF, or Arm B
  on this basis alone.
- Do not quote the geometry AUC as more precise than "clears 0.03".
- **Do not re-run `build_label_set.py`** — it would regenerate the pinned sheet.
- The Antigravity brain-summary AUC of **0.3477 is superseded** by **0.2175**. Anything still citing
  0.3477 is stale.

## Resolved after the pause (2026-08-08)

Every todo above is closed. Recorded here rather than by rewriting the table, so the pause snapshot stays
readable as what it was.

| ID | Outcome |
|---|---|
| `finish-track-a` | Complete — 7 models on the pinned 236. `haar_energy` needed two extra attempts (host sleep killed the WSL VM both times, costing only that model); `Carried forward 6 previously measured model(s)`, no merge rejections |
| `update-focus-memo` | Done — Track A ratios folded in beside the learned models (`dog_energy` **8.80×** blur tops the study), noise ladder flagged Suspect for 3 of 4 measures |
| `labels-accuracy-pass` | Done, and the answer is negative: Arm B precision **0.1429** vs base reject rate **0.2963** — lift **×0.48**, recall **0.0156** |
| `transcript-hygiene` | Done — both root dumps moved to gitignored scratch |
| `version-harness` | Backend work committed on `research/bird-crop-focus-317` under `Closes #317`; `student_scorer` and the root transcripts excluded |

The `labels-accuracy-pass` result is the one that matters: the rule this session proposed does not work, and
saying so is the deliverable. Full reasoning in
[`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) § *Arm B*.

## See also

- [`RESEARCH_SESSIONS_2026-08-05.md`](RESEARCH_SESSIONS_2026-08-05.md) — day hub for both concurrent workstreams
- [`SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](SESSION_BIRD_CROP_FOCUS_2026-08-05.md) — Claude Code half
- [`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](BIRD_BBOX_CROP_STUDY_2026-08-01.md) — study close-out memo
- [`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) — Phase 4 memo

# Citations

Raw session source archived unmodified under [`../raw/`](../raw/README.md):

[1] [2026-08-05-bird-crop-closeout-cursor.md](../raw/2026-08-05-bird-crop-closeout-cursor.md) — Cursor Agent (Grok 4.5) bird-crop close-out session scratch
