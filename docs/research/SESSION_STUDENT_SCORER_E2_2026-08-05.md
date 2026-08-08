---
type: Report
title: Session record — student scorer E2, P0 render complete and ConvNeXt train in flight
description: Consolidated record of the 2026-08-05 E2 session from both agents — the render resume fix that survived a WSL kill, the finished 66k P0 cache, and a full seed-42 train that had not produced a recordable result at pause.
resource: docs/research/SESSION_STUDENT_SCORER_E2_2026-08-05.md
tags: [session, research, student-scorer, e2, render, training, wsl, gpu]
timestamp: 2026-08-05T21:46:46-05:00
okf_version: 0.1
---

# Session record — student scorer E2: P0 render → ConvNeXt train

> **Status:** session record, not a result. **The full E2 train had not finished at write time**, so no
> gate outcome is recorded here. Authoritative gates live in
> [`STUDENT_SCORER_PROTOCOL.md`](STUDENT_SCORER_PROTOCOL.md); the append-only run register is
> [`STUDENT_SCORER_RESULTS.md`](STUDENT_SCORER_RESULTS.md).
> Day hub: [`../reports/RESEARCH_SESSIONS_2026-08-05.md`](../reports/RESEARCH_SESSIONS_2026-08-05.md).
>
> [`STUDENT_SCORER_E2_CHECKPOINT.md`](STUDENT_SCORER_E2_CHECKPOINT.md) is the **hold-before-GPU**
> snapshot. This page supersedes the narrative for everything after that checkpoint — smoke and full
> train — but not the checkpoint's own render figures.

## Session metadata

This page consolidates **two independent records of the same work**, written minutes apart by two agents.

| Field | Claude Code record | Cursor record |
|---|---|---|
| **Agent / model** | Claude Code (CLI), Opus 5 (`claude-opus-5`) | Cursor Agent, Grok 4.5 |
| **Session** | `0ce4df02-51e7-499e-809b-6a5314810ce6`, started 2026-08-01 10:32:59 −05:00 | written 2026-08-05 21:46:46 −05:00 |
| **Invoked from** | `D:\Projects\image-scoring-model` | `D:\Projects\image-scoring-model` |
| **Raw source** | [`../raw/2026-08-01-student-scorer-e2-claude.md`](../raw/2026-08-01-student-scorer-e2-claude.md) | [`../raw/2026-08-05-student-scorer-e2-cursor.md`](../raw/2026-08-05-student-scorer-e2-cursor.md) |

**Work target for both: `D:\Projects\image-scoring-backend`** — a different repo from the one they were
invoked in. Manifest `msm_8ef568a5db3d9f79` · protocol `ssp_429e3332d8ab` · contract
`.agent/scratch/e2_autonomous_run_contract.md` · tracking issue
[#323](https://github.com/synthet/image-scoring-backend/issues/323).

The two records agree on every fact checked against each other; where only one carries a detail, this
page keeps it.

## Where the program stood entering this session

- Phase 0–2 scaffold complete: audit, frozen manifest, evaluators, shadow-only student modules **not**
  enabled in fusion.
- **E0 and E1 MobileNet embedding baselines FAILED all three fidelity gates** (val general Spearman
  ~0.56–0.60) — recorded in [`STUDENT_SCORER_RESULTS.md`](STUDENT_SCORER_RESULTS.md).
- E2 pipeline code landed: `render_p0.py`, `image_dataset.py`, `torch_losses.py`, a real
  `train_image_model.py` loop, tests, protocol notes, and the autonomous-run contract.

## 1. The render resume fix

`scripts/research/student_scorer/render_p0.py` was the **only production file modified**. Four changes:

| Change | Effect |
|---|---|
| `INDEX_FLUSH_EVERY = 500` | Periodic index flush instead of one write at the end |
| Skip existing output **only when `existing_method` is known** | Orphaned JPEGs get re-decoded with their true `resolved_method` instead of being mislabeled `skipped_existing` |
| New `_write_index_atomic` | tmp file + `replace()`, crash-safe |
| `ThreadPoolExecutor` (default `--workers 12`) replacing `ProcessPoolExecutor` | **7.7× scaling** — rawpy/LibRaw and the `exiftool` subprocess both release the GIL, while spawn-based processes thrashed ~15 GB of WSL RAM |

Tests added in `tests/test_student_scorer_render_p0.py`:
`test_orphan_jpeg_without_index_row_is_rerendered`, `test_index_is_flushed_periodically`.

**The fix proved itself the same week.** WSL restarted and hard-killed the render mid-flight. The index
held at exactly **44,000 rows** — a clean `INDEX_FLUSH_EVERY` multiple. Before the fix that kill would
have cost the entire render. The 67 orphaned JPEGs (44,067 files vs 44,000 rows) were re-decoded with
their true methods.

## 2. Render complete

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
| Cache size | ~2.7 GB under `~/.cache/student_scorer/msm_8ef568a5db3d9f79/p0_512/` |
| `wall_seconds` (final leg) | 4,489.7 (~75 min); **~3 h cumulative against a 3 h render budget** |

**The 3 decode errors are source-data failures, not a code defect.** All three are Z8 NEFs from
`180-600mm/2026/2026-04-09` (`DSC_0004`, `DSC_0017`, `DSC_0086`), ~31 MB each. `exiftool -b -JpgFromRaw`
returns **0 bytes** and LibRaw reports `data corrupted`. Both decode paths fail, and production uses the
same paths — so this is not a preprocess divergence and the contract's escalate rule does not fire.

## 3. Train phase

- **Smoke — complete.** `--limit 500 --epochs 2` → `n_train` 439, `n_val` 61, `status: trained`,
  `device: cuda`. `n_skipped_renders: 12` matches the render's 12 non-ok rows **exactly**, confirming the
  dataset layer consumes the new index correctly. All three gates fail — expected at that scale, and the
  run is not gate-readable by design.
- **Full seed-42 — in flight at pause.** `--epochs 20 --num-workers 8`, ~5.2 GB GPU at ~96%.

> **Correction (2026-08-06).** The epoch-time baseline recorded here at pause was ~**18.4 min/epoch**
> → ~6.1 h for 20 epochs, i.e. past the contract's 4 h cap. That figure was taken while a separate
> `bird_crop.degradation_eval` job contended for the GPU. Measured on the uncontended relaunch —
> 21:11:46 start, epoch 4 checkpoint at 21:55:41 — the real rate is ~**8.8 min/epoch** → **~2.9 h for
> 20 epochs, inside the 4 h cap**. The budget was never the blocker; surviving a WSL restart is.
> See [Arc B resolution](../reports/RESEARCH_SESSIONS_2026-08-05.md#arc-b-resolution-2026-08-06).

An earlier full-train process (PID 2158) **died after reaching epoch 6** (`val_loss` ~0.00131) and was
relaunched at 21:11:46 via `run_e2_full_only.sh`. **That relaunch (PID 1215) then died too**, at
~22:56, having reached epoch 4 (`val_loss` 0.0014043) — killed by a WSL restart, not a job fault
(`uptime` 2 min · `journal … uncleanly shut down` · `Time jumped backwards` · 13 GB RAM free · no
traceback in the log). State of
`artifacts/student_scorer/msm_8ef568a5db3d9f79/runs/E2_s42/` at 21:46:

| File | mtime | Meaning |
|---|---|---|
| `run_config.json` | 21:11:48 | Relaunch start |
| `best.pt` | 21:29:07 | Epoch 0/1 of the relaunched run, val masked teacher loss 0.00150 |
| `report.json` | 17:55:16 | **Still the smoke's** |
| `run.json` | 17:55:16 | **Still the smoke's** |

Live process PID 1215 plus 8 dataloader workers. **Nothing had been appended to
`STUDENT_SCORER_RESULTS.md` or `docs/log.md`.**

## Three properties of `train_image_model.py` that shape monitoring

1. **No per-epoch output.** `history` accumulates in memory; the log stays silent until the final JSON
   dump at the end of the run.
2. **`best.pt` is not a heartbeat.** It is rewritten *only* on val improvement
   (`train_image_model.py:463-480`), so a plateau is indistinguishable from a stall by mtime alone.
   Liveness must come from the process and the GPU.
3. **No resume.** A kill loses `history` and `report.json`; only `best.pt` survives. WSL restarted twice
   in one week and the full train has already died once, so this is the dominant risk.

Smoke and full train share `runs/E2_s42/`, so the smoke's artifacts are progressively overwritten.

## Decisions locked (user, via AskUserQuestion)

| Topic | Choice | Consequence |
|---|---|---|
| Orphaned JPEGs | **Re-render** | True `resolved_method` instead of a mislabel; makes the subgroup split checkable |
| Supervision | **Checkpoint after render** | Report `render_summary.json` before committing GPU time (later resumed past that gate) |
| Already-running train | **Leave it; monitor and record** | No code changes; append when `report.json` lands |
| Budget overrun | **Let early-stopping decide, report the overrun** | No intervention at the 4 h cap; report actual wall time honestly |
| GPU contention with `bird_crop.degradation_eval` | **Leave it alone** | Noted as a timing caveat, not this session's job |
| Head order | `meta["teachers"]` (alphabetical), not `DEFAULT_TEACHERS` | — |
| Gate composites | **Derived** from teacher heads; direct aux heads reported for E0/E1 comparability | — |
| Frozen contract | **Do not** fix `musiq_version: "unknown"` | Fixing it would invalidate the protocol |

**Out of scope:** E3–E6 · rank/human losses · calibration · `export_checkpoint` · shadow enablement ·
re-split · any edit to production fusion, anchors, or `docs/technical/API_CONTRACT.md` · adding logging
or resume to `train_image_model.py` (considered and declined — it cannot help the in-flight run).

## Errors hit and how they were fixed

| Problem | Cause | Fix |
|---|---|---|
| Launch attempt 1 died silently, no log | `&` backgrounded the whole `&&` chain, which died with the parent shell | Rewrite as a script file |
| Launch attempt 2 mangled to `L=C:/Program Files/Git/mnt/c/...`, newlines flattened | Git Bash MSYS path conversion **plus** newline flattening inside `wsl -e bash -lc '...'` | `MSYS_NO_PATHCONV=1 wsl -e bash /mnt/c/.../launch_render.sh` |
| Background monitors repeatedly killed | Agent teardown reaped them | Load `Monitor` with `persistent: true` |
| False "process dead" signal | `tr -d \" \"` inside single quotes → malformed args swallowed by `2>/dev/null` | Re-verify with `pgrep -af "train_image_model"` — it was alive at 96% GPU |
| `date` read 17:52 while file mtimes read 22:30 | WSL clock jumped backward after sleep/resume | **Treat file mtimes as the authoritative timeline** |
| Full train died twice mid-run (PID 2158 @ epoch 6, PID 1215 @ epoch 4), losing `history` both times | Host sleep/resume kills the WSL VM; `train_image_model.py` had **no resume**, and `best.pt` carries no optimizer/scheduler/scaler/history | Added `last.pt` (atomic tmp+replace, written every epoch) and an opt-in `--resume` that refuses a guard mismatch — see [Arc B resolution](../reports/RESEARCH_SESSIONS_2026-08-05.md#arc-b-resolution-2026-08-06) |
| `setsid nohup … &` inside `wsl -e bash -c '…'` left no process | The `wsl -e` session tears down before the detached child is reparented | Keep a Windows-side `wsl.exe` alive holding the session (harness-tracked background run) instead of fire-and-forget detaching |

## Resume checklist

1. Confirm the train is alive or finished: `pgrep -af train_image_model`. Read
   `runs/E2_s42/report.json` and require `report.json` mtime > 17:55:16 **and** `run.json` showing
   `status: trained` with `limit: null, epochs: 20` — the smoke's `limit: 500` must not be what gets
   recorded.
2. If dead mid-run, relaunch `run_e2_full_only.sh` under `nohup` / `setsid`, LF line endings,
   `PYTHONUNBUFFERED=1`.
3. Transcribe from `report.json`: `best_epoch`, `best_val_masked_teacher_loss`, full `history`, the three
   gate values (`composite_spearman` ≥ 0.95, `median_teacher_spearman` ≥ 0.90,
   `composite_mae_nonsaturated` ≤ 0.03), `all_required_passed` / `required_failed`,
   `fidelity_val.derived.all.per_head`, `fidelity_test` / `fidelity_ood_test` (report-only, never
   selection), `fidelity_val.resolved_method_subgroup`, and `n_skipped_renders` (expect 12).
   The **subgroup split is newly meaningful** — both methods now carry exact labels and clear
   `min_subgroup_n: 30`, so `subgroup_spearman_drop_max: 0.05` is checkable for the first time. That is
   the direct payoff of the orphan re-render fix.
4. Append one row to [`STUDENT_SCORER_RESULTS.md`](STUDENT_SCORER_RESULTS.md) under run ID
   **`2026-08-05-e2-convnext`** plus a dated `## 2026-08-05 — E2 ConvNeXt-Tiny (P0, last_stage)`
   subsection. Never edit prior rows. Append one entry to [`../log.md`](../log.md).
5. Update issue [#323](https://github.com/synthet/image-scoring-backend/issues/323) and optionally
   [`STUDENT_SCORER_E2_CHECKPOINT.md`](STUDENT_SCORER_E2_CHECKPOINT.md).
6. **Do not enable shadow or change fusion without a new human decision.**

**Gate failure is recorded as failure.** E0 and E1 both failed all three gates; if E2 does too, that is
the result, not a reason to retune. Retuning would be a new contract. Per the contract's crash policy, a
`best.pt` without a matching `report.json` is never reported as a completed run, and metrics are never
reconstructed from the checkpoint.

## Artifacts

| Path | Role |
|---|---|
| `artifacts/student_scorer/msm_8ef568a5db3d9f79/renders/` | `render_index.json`, `render_summary.json` |
| `~/.cache/student_scorer/msm_8ef568a5db3d9f79/p0_512/` | P0 JPEG cache (~2.7 GB) |
| `artifacts/student_scorer/msm_8ef568a5db3d9f79/runs/E2_s42/` | `best.pt`, smoke-era `report.json` / `run.json` |
| `.agent/scratch/e2_autonomous_run_contract.md` | Run contract |
| `.agent/scratch/e2_full_train.log` | Full-train log |
| `.agent/scratch/run_e2_full_only.sh` | Relaunch script |

## See also

- [`../reports/RESEARCH_SESSIONS_2026-08-05.md`](../reports/RESEARCH_SESSIONS_2026-08-05.md) — day hub
- [`STUDENT_SCORER_STUDY.md`](STUDENT_SCORER_STUDY.md) · [`STUDENT_SCORER_PROTOCOL.md`](STUDENT_SCORER_PROTOCOL.md) · [`STUDENT_SCORER_RESULTS.md`](STUDENT_SCORER_RESULTS.md)

# Citations

Raw session sources archived unmodified under [`../raw/`](../raw/README.md):

[1] [2026-08-01-student-scorer-e2-claude.md](../raw/2026-08-01-student-scorer-e2-claude.md) — Claude Code (Opus 5) E2 render → train session scratch
[2] [2026-08-05-student-scorer-e2-cursor.md](../raw/2026-08-05-student-scorer-e2-cursor.md) — Cursor Agent (Grok 4.5) E2 session scratch
