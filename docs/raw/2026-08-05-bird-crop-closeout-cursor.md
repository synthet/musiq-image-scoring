---
type: Archive
title: "Raw session — bird-crop study close-out (Cursor, 2026-08-05)"
description: "Immutable Cursor Agent session scratch for the bird-crop close-out: multi-agent labelling, sequential Track A recovery, Arm B vs labels, CSV exporter. Ingested into docs/reports/SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md."
resource: docs/raw/2026-08-05-bird-crop-closeout-cursor.md
tags: [raw, session, bird-detection, focus, labelling]
timestamp: 2026-08-05T00:00:00Z
okf_version: 0.1
---

# Session summary — bird-crop study close-out

| Field | Value |
|---|---|
| **Session timestamp** | `2026-08-05T21:46:47-05:00` |
| **Agent** | Cursor Agent |
| **Model** | Cursor Grok 4.5 |
| **Primary repo** | `image-scoring-backend` |
| **Related repos** | `image-scoring-skills` (labelling harness), plan under `.cursor/plans/` |
| **Transcript (this chat)** | `agent-transcripts/8f2173f2-d324-49e4-940d-fa0601f8e93b/` |

---

## Goal

Finish the pinned bird-bbox crop study close-out after Phase 2 / 2b / 3 / 4 and multi-agent labelling: complete Track A (classical degradation), refresh memos, optional label-based accuracy metrics, hygiene, and version both repos (`Closes #317`).

## What was already done before / during this thread

### Study harness (pinned re-sweep)

- Orchestrator wired to `--image-ids-file` / pinned set (`reports/bird-crop/study_image_ids.txt`, **236** ids).
- Population assert in `bursts.load_boxed_rows` (no silent drop via `image_exif` join).
- PHASE=2, 2b, 3 completed on the pin; mixed-population NPZs quarantined earlier.
- Close-out memo: `docs/reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md`.
- Headline verdicts: IQA complementary (**2.42×–17.51×**); captions +0.105; species +0.018; culling **no benefit**.

### Multi-agent labelling (`image-scoring-skills`)

- `/bird-crop-label` harness: fan-out, merge, `burst-judge` persona, UUID sheet/verdict filenames.
- Final labels: **236** images / **54** bursts — **60** best · **105** good · **71** reject.
- Judges: Claude ×2, Cursor ×2, Antigravity ×1; **Codex excluded** (unreadable-sheet trust gate).
- Canonical sidecar: `label_set_judges-57c86c08-6a1e-41d0-88b7-bf9d5e0a2f59.json` (UUID-only policy).
- Geometry PHASE=1: **add complementary**, delta AUC **0.2175** (agent-derived; do not over-quote).
- Merge bugs fixed: bare `END`, trailing rationale, stale non-UUID sidecar.

### Phase 4 focus

- Classical measures + AF metadata: **no benefit** vs AF-proxy (blur-tracking ~chance).
- AF coverage 216/236; centre-in-box 73.1%.
- Memo: `docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`.
- Arm B rule proposed (soft crop ∧ AF outside box); originally unscored (circular vs AF).

### CSV tables exporter

- `scripts/research/bird_crop/export_results.py` → `reports/bird-crop/tables/` (6 CSVs + README).
- Species tercile exporter bug fixed; README warns to read `tracks_blur` before AUC.
- Provenance note updated to agent-derived labels (not “empty human verdicts”).

## Work done in this Cursor session

1. **Plan iteration** — Folded Antigravity labelling summary (historical only; discarded stale AUC 0.3477 / bare `label_set_judges.json` / Codex-as-active). Folded tables-exporter status; Track A progress updates.
2. **Execution started** on attached plan (do not edit plan file).
3. **Track A classical degradation**
   - Original all-four-models run was interrupted (WSL restart / pause); no mid-run write.
   - Relaunched **sequential one-model-at-a-time** so `_merge_with_existing` persists after each model.
   - At last pause check (`2026-08-05` ~21:44): **`laplacian_variance` finished and merged** (liqe/topiq/arniqa intact); **`tenengrad` ~50/236** in flight; `dog_energy` / `haar_energy` still queued. Wrapper: `/tmp/run_trackA_sequential.sh`, log `reports/bird-crop/trackA.log`.
4. **Arm B vs labels** — Implemented `_arm_b_vs_labels` in `focus_eval.py` (reject = positive; tags agent-derived); unit tests in `tests/test_bird_crop_focus_arm_b_labels.py` (3 passed). Focus re-run still pending until Track A finishes.
5. **Hygiene**
   - Moved root `2026-*.txt` dumps → `.agent/scratch/session-transcripts/` (backend + skills).
   - Archived non-canonical `label_set_judges-*.json` → `.agent/scratch/bird-crop-label-sidecars/`; kept `57c86c08…`.
   - Keep-awake started/confirmed during long runs.
   - Later dump reappeared at root: `2026-08-03-220609-cusersdmnsycursorplanspinnedphase2reswe.txt` (still at root at pause; move on next resume).
6. **User Q&A (not fully implemented)** — “Can we use 100% unscaled bird crop for focus algs?” Discussion started from current path (`work_long_edge=3000`, measure `long_edge=512`); native crop is feasible for classical measures (intensive / mean-normalized), with cost and kernel-scale caveats — no code change yet.

## Remaining todos (as of pause)

| ID | Status | Next action |
|---|---|---|
| `finish-track-a` | In progress | Let sequential Track A finish; confirm merge; `PHASE=report`; re-run `export_results` |
| `update-focus-memo` | Pending | Track A ratios vs 2.42×–17.51×; labelling provenance; AUC churn; `docs/log.md` |
| `labels-accuracy-pass` | Pending | Re-run `focus_eval` for Arm B vs agent labels; document geometry IQA-rank already done (0.2175); skip circular `pick_review` as accuracy |
| `transcript-hygiene` | Mostly done | Move leftover root `2026-08-03-220609-…txt` to scratch |
| `version-harness` | Pending | Commit backend bird-crop (+ tables/export/Arm B); skills `/bird-crop-label`; `Closes #317`; no student_scorer / root transcripts |

## Key paths

| Path | Role |
|---|---|
| `reports/bird-crop/REPORT.md` | Consolidated verdicts |
| `reports/bird-crop/degradation.{json,md}` | Track A + learned IQA (merge-protected) |
| `reports/bird-crop/trackA.log` | Sequential Track A log |
| `reports/bird-crop/labels/label_set.csv` | Agent-derived verdicts |
| `reports/bird-crop/tables/` | Machine-readable CSV exports |
| `scripts/research/bird_crop/focus_eval.py` | Phase 4 + Arm B vs labels |
| `docs/guides/BIRD_CROP_LABELLING.md` | Labelling runbook |
| `docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md` | Focus memo (needs Track A refresh) |

## Caveats carried forward

- Agent-derived GT ≠ human; do not productionize crop IQA / AF / Arm B on this alone.
- Do not quote geometry AUC as more precise than “clears 0.03”.
- Do not re-run `build_label_set.py`.
- Antigravity brain summary AUC **0.3477** is superseded by **0.2175**.

## Pauses

User paused twice while Track A ran; sequential relaunch after WSL/process loss is the recovery pattern that stuck (laplacian merge confirmed).
