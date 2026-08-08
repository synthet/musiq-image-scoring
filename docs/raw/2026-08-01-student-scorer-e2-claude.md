---
type: Archive
title: "Raw session — student scorer E2 P0 render resume and ConvNeXt train (Claude, 2026-08-01)"
description: "Immutable Claude Code session scratch for the student-scorer E2 arc: P0 render resume fix, 66k render cache, and the first ConvNeXt train attempt. Ingested into docs/research/SESSION_STUDENT_SCORER_E2_2026-08-05.md."
resource: docs/raw/2026-08-01-student-scorer-e2-claude.md
tags: [raw, session, student-scorer, render, training]
timestamp: 2026-08-01T00:00:00Z
okf_version: 0.1
---

# Session summary — E2 P0 render resume → E2 ConvNeXt train

| Field | Value |
|---|---|
| Session ID | `0ce4df02-51e7-499e-809b-6a5314810ce6` |
| Session start | 2026-08-01 10:32:59 -05:00 |
| Summary written | 2026-08-05 21:46:34 -05:00 |
| Agent | Claude Code (CLI) |
| Model | Opus 5 (`claude-opus-5`) |
| Invoked from | `D:\Projects\image-scoring-model` |
| **Work target** | **`D:\Projects\image-scoring-backend`** (a different repo) |
| Driving plan | `C:\Users\dmnsy\.claude\plans\c-users-dmnsy-cursor-plans-resume-e2-ren-parallel-marble.md` |
| Contract | `.agent/scratch/e2_autonomous_run_contract.md` (backend repo) |
| Manifest | `msm_8ef568a5db3d9f79` |

> Scratch note, not a deliverable. `.agent/scratch/` is git-ignored in this repo.

---

## Objective

Finish a paused E2 student-scorer run: fix render resume, complete the P0 render cache for manifest
`msm_8ef568a5db3d9f79`, run the E2 ConvNeXt-Tiny train, and record gate results — pass or fail.

## Decisions the user made (via AskUserQuestion)

| Decision | Choice | Consequence |
|---|---|---|
| Orphaned JPEGs (files with no index row) | **Re-render them** | Skip test requires an index row, so orphans get re-decoded with their true `resolved_method` instead of being mislabeled |
| Supervision | **Checkpoint after render** | Stop and report `render_summary.json` before committing GPU time |
| Already-running train | **Leave it, monitor and record** | No code changes; append results when `report.json` lands |
| Budget overrun | **Let early-stopping decide, report overrun** | Do not intervene at the contract's 4 h train cap; report actual wall time honestly |
| GPU contention (`bird_crop.degradation_eval`, PID 1813) | **Leave it alone** | Not this session's job; noted as a timing caveat |

---

## Work completed

### 1. Render resume fix — `scripts/research/student_scorer/render_p0.py`

The only production file modified. Four changes:

- `INDEX_FLUSH_EVERY = 500` — periodic index flush instead of one write at the end
- Skip existing output **only when `existing_method` is known** — orphaned JPEGs get re-decoded
- New `_write_index_atomic` — tmp file + `replace()`, crash-safe
- `ThreadPoolExecutor` replacing `ProcessPoolExecutor`; `--workers` default 12

Two tests added in `tests/test_student_scorer_render_p0.py`:
`test_orphan_jpeg_without_index_row_is_rerendered` and `test_index_is_flushed_periodically`.

**Why threads beat processes here:** rawpy/LibRaw and the `exiftool` subprocess both release the GIL,
so `ThreadPoolExecutor` scaled **7.7×** where spawn-based `ProcessPoolExecutor` thrashed ~15 GB of
WSL RAM.

### 2. The fix proved itself under real conditions

WSL restarted between sessions and hard-killed the render mid-flight. The index held at exactly
**44,000 rows** — a clean `INDEX_FLUSH_EVERY = 500` multiple. Before the fix, that kill would have
cost the entire render. 67 orphaned JPEGs (44,067 files vs 44,000 rows) were re-decoded with their
true methods rather than mislabeled.

### 3. Render complete

Final `render_summary.json`:

| Metric | Value |
|---|---|
| `n_index` | 66,485 (66,485 unique ids) |
| `ok` | 66,473 |
| `missing_source` | 9 |
| `error` | 3 |
| `exiftool:JpgFromRaw` | 35,935 |
| `rawpy_half` | 30,538 |
| `skipped_existing` | *bucket absent* |
| Blank sha256 | 0 |
| Cache size | 2.7 GB |
| `wall_seconds` (this leg) | 4,489.7 (~3 h cumulative — essentially the whole render budget) |

### 4. The 3 decode errors are source-data failures, not a code defect

All three are Z8 NEFs from `180-600mm/2026/2026-04-09` (`DSC_0004`, `DSC_0017`, `DSC_0086`),
full-size ~31 MB. `exiftool -b -JpgFromRaw` returns **0 bytes** on each; LibRaw reports
`data corrupted`. **Both** decode paths fail, and production uses the same paths — so this is not a
preprocess divergence, and the contract's escalate rule does not fire.

### 5. Train phase found already underway (launched outside the session)

Launcher: `.agent/scratch/run_e2_train.sh`.

- **Smoke — complete.** `--limit 500 --epochs 2` → `n_train` 439, `n_val` 61, `status: trained`,
  `device: cuda`. `n_skipped_renders: 12` matches the render's 12 non-ok rows **exactly**, confirming
  the dataset layer consumes the new index correctly. All three gates fail (expected at that scale).
- **Full seed-42 — in flight.** `--epochs 20 --num-workers 8`, ~5.2 GB GPU at ~96%.

Epoch-time baseline: `run_config.json` 17:55:22 → `best.pt` 18:13:43 = **~18.4 min/epoch** including
the 4,426-image val eval → **~6.1 h for 20 epochs** against the contract's 4 h cap.

---

## State at time of writing (2026-08-05 21:46)

The original full-train process (PID 2158) **died and was relaunched** at 21:11:46 via
`.agent/scratch/run_e2_full_only.sh`. Current state of
`artifacts/student_scorer/msm_8ef568a5db3d9f79/runs/E2_s42/`:

| File | mtime | Meaning |
|---|---|---|
| `run_config.json` | 21:11:48 | Relaunch start |
| `best.pt` | 21:29:07 | Epoch 0 of the relaunched run (~17.3 min) |
| `report.json` | 17:55:16 | **Still the smoke's** — full run has not finished |
| `run.json` | 17:55:16 | **Still the smoke's** |

Live process: PID 1215 (+ 8 dataloader workers). Log `e2_full_train.log` contains only three
`FutureWarning`s about deprecated `torch.cuda.amp.autocast` / `GradScaler`.

**The full train has not produced a recordable result yet.** Nothing has been appended to
`STUDENT_SCORER_RESULTS.md` or `docs/log.md`.

---

## Three properties of `train_image_model.py` that shape monitoring

1. **No per-epoch output.** `history` accumulates in memory; the log stays silent until the final
   JSON dump at the end of the run.
2. **`best.pt` is not a heartbeat.** It is rewritten *only* on val improvement
   (`train_image_model.py:463-480`), so a plateau is indistinguishable from a stall by mtime alone.
   Liveness must come from the process and GPU.
3. **No resume.** A kill loses `history` and `report.json`; only `best.pt` survives. WSL has already
   restarted twice this week — and the full train has now died once — so this is the dominant risk.

Also relevant: smoke and full train share `runs/E2_s42/`, so the smoke's `run_config.json` was
already overwritten, and `best.pt` / `report.json` / `run.json` will be too.

---

## Errors hit and how they were fixed

| Problem | Cause | Fix |
|---|---|---|
| Launch attempt 1 died silently, no log | `&` backgrounded the whole `&&` chain, which died with the parent shell | Rewrite as a script file |
| Launch attempt 2: `L=C:/Program Files/Git/mnt/c/...` and all newlines flattened | Git Bash MSYS path conversion **plus** newline flattening inside `wsl -e bash -lc '...'` | `MSYS_NO_PATHCONV=1 wsl -e bash /mnt/c/.../launch_render.sh` — succeeded (PID 750) |
| Background monitors repeatedly killed | Agent teardown reaped them | Loaded `Monitor` via ToolSearch with `persistent: true`; render was unaffected either way |
| False "process dead" signal | `tr -d \" \"` inside single quotes → malformed args, swallowed by `2>/dev/null` | Re-verified with `pgrep -af "train_image_model"` — process was alive at 96% GPU |
| `date` read 17:52 while file mtimes read 22:30 | WSL clock jumped backward after sleep/resume | Treat file mtimes as the authoritative timeline |

---

## Remaining work

1. Monitor the relaunched train read-only until `report.json` mtime exceeds 17:55:16 **and**
   `run.json` shows `status: trained` with `limit: null, epochs: 20` (the smoke's `limit: 500` must
   not be what gets recorded).
2. Transcribe from `report.json`: `best_epoch`, `best_val_masked_teacher_loss`, full `history`, the
   three gate values (`composite_spearman` ≥0.95, `median_teacher_spearman` ≥0.90,
   `composite_mae_nonsaturated` ≤0.03), `all_required_passed` / `required_failed`,
   `fidelity_val.derived.all.per_head`, `fidelity_test` / `fidelity_ood_test` (report-only, never
   selection), `fidelity_val.resolved_method_subgroup`, and `n_skipped_renders` (expect 12).
   The subgroup split is **newly meaningful** — both methods now carry exact labels and clear
   `min_subgroup_n: 30`, so `subgroup_spearman_drop_max: 0.05` is checkable for the first time. That
   is the direct payoff of the orphan re-render fix.
3. Append to `docs/research/STUDENT_SCORER_RESULTS.md`: one table row, run ID
   **`2026-08-05-e2-convnext`** (columns `Run ID | Experiment | Manifest | Protocol | Val summary |
   Gates | Notes`), plus a dated `## 2026-08-05 — E2 ConvNeXt-Tiny (P0, last_stage)` subsection.
   Never edit prior rows. Append one `## [2026-08-05] add | …` entry to `docs/log.md`.

**Gate failure is recorded as failure.** E0/E1 both failed all three gates; if E2 does too, that is
the result, not a reason to retune. Retuning would be a new contract.

Per the contract's crash policy: a `best.pt` without a matching `report.json` is never reported as a
completed run, and metrics are never reconstructed from the checkpoint.

## Out of scope

E3–E6 · rank/human losses · calibration · `export_checkpoint` · shadow enablement · re-split · any
edit to production fusion, anchors, or `docs/technical/API_CONTRACT.md` · adding logging or resume to
`train_image_model.py` (considered and declined — it cannot help the in-flight run).
