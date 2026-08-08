---
type: Documentation Index
title: Research sessions hub — 2026-08-05
description: Router for the two research workstreams that ran concurrently on 2026-08-05 — bird-crop close-out (#317) and student-scorer E2 (#323) — with the four agent records, headline findings, shared long-job lessons, and what was left open at the ~21:46 pause. The pause snapshot is left unedited; the continuations are recorded under "Arc B resolution (2026-08-06)" and "Arc A resolution (2026-08-08)".
resource: docs/reports/RESEARCH_SESSIONS_2026-08-05.md
tags: [session, index, research, bird-detection, student-scorer, wsl, multi-agent]
timestamp: 2026-08-05T21:46:00-05:00
okf_version: 0.1
---

# Research sessions hub — 2026-08-05

Two research workstreams ran **concurrently** on this machine, competing for the same GPU and the same
WSL instance, each recorded independently by two agents. This page routes to the records and holds what
is common to both.

**Nothing on this page is a production change.** `technical_failures.enabled` stays `false`, the student
scorer stays shadow-only and unwired from fusion, and no DDL or migration was applied.

| Field | Value |
|---|---|
| **Pause window** | ~2026-08-05T21:46−05:00 |
| **Repos** | `image-scoring-backend` (work target); `image-scoring-skills` (labelling harness) |
| **In flight at pause** | Bird-crop Track A sequential classical measures; student-scorer full E2 seed-42 train |

## The records

| Track | Agent / model | Record | Covers |
|---|---|---|---|
| Bird-crop ([#317](https://github.com/synthet/image-scoring-backend/issues/317)) | Claude Code, Opus 5 | [`SESSION_BIRD_CROP_FOCUS_2026-08-05.md`](SESSION_BIRD_CROP_FOCUS_2026-08-05.md) | Pinned Phase 2 re-sweep, Phase 4 classical-focus/AF research, `modules/focus_quality.py`, 15 corrections |
| Bird-crop ([#317](https://github.com/synthet/image-scoring-backend/issues/317)) | Cursor Agent, Grok 4.5 | [`SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md`](SESSION_BIRD_CROP_CLOSEOUT_2026-08-05.md) | Multi-agent labelling, sequential Track A recovery, Arm B vs labels, CSV exporter, open todos |
| Student scorer ([#323](https://github.com/synthet/image-scoring-backend/issues/323)) | Claude Code (Opus 5) **+** Cursor Agent (Grok 4.5) | [`../research/SESSION_STUDENT_SCORER_E2_2026-08-05.md`](../research/SESSION_STUDENT_SCORER_E2_2026-08-05.md) | Render resume fix, 66k P0 cache, train monitoring properties, error table, resume checklist |

The two student-scorer records describe the same work from two angles and agree on every fact checked
against each other, so they are consolidated into one page. Raw sources are archived unmodified under
[`../raw/`](../raw/README.md) — see [Raw sources](#raw-sources-immutable) below.

## Arc A — bird-crop / focus ([#317](https://github.com/synthet/image-scoring-backend/issues/317))

**Question:** does cropping to the detected bird bbox help each pipeline phase, and can a zero-inference
algorithm decide crop focus quality?

| Finding | Value |
|---|---|
| Crop sensitivity for IQA | **2.42×–17.51×** more sensitive to subject-only degradation |
| Captions / species | +0.105 within-burst uniqueness · +0.018 species agreement |
| Culling embeddings | **No benefit** |
| Classical focus measures vs *real* misfocus | **At chance** — best blur-tracking AUC 0.5295; the only measure above the bar (`local_entropy`, 0.6082) provably does not track blur |
| Camera AF geometry | Present on **216/236 (91.5%)**; AF centre inside the bird box **73.1%** of the time |
| Native-resolution subject measurement | Roughly triples blur discrimination: **+0.144 → +0.464** |
| Agent labelling | 236 images / 54 bursts → **60 best · 105 good · 71 reject** |
| Geometry `PHASE=1` | add complementary, delta AUC **0.2175** (supersedes a stale 0.3477) |

**Deliverable:** `modules/focus_quality.py` — algorithmic, no model, no GPU. Immerkær block-percentile
noise, Crete perceptual blur, noise-corrected Laplacian sharpness, and subject ÷ local-background focus
ratio at one native scale. Wired behind the existing disabled `technical_failures` flag.

**Hard caveat:** ground truth is **agent-derived, not human**. Do not productionize crop IQA, AF, or the
Arm B rule on this basis alone. The verdict thresholds in `focus_quality.py` are engineering defaults,
not validated cut-offs. Do not quote the geometry AUC as more precise than "clears 0.03".

| Authoritative page | Role |
|---|---|
| [`BIRD_BBOX_CROP_STUDY_2026-08-01.md`](BIRD_BBOX_CROP_STUDY_2026-08-01.md) | Phase 2 / 2b / 3 close-out memo |
| [`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) | Phase 4 focus / AF memo |
| [`../guides/BIRD_CROP_LABELLING.md`](../guides/BIRD_CROP_LABELLING.md) | Labelling runbook |

**Artefacts:** `reports/bird-crop/` (`REPORT.md`, `degradation.{json,md}`, `labels/`, `tables/`, `trackA.log`).

## Arc B — student scorer E2 ([#323](https://github.com/synthet/image-scoring-backend/issues/323))

**Question:** can one multi-head student model replace the teacher ensemble at fidelity?
Manifest `msm_8ef568a5db3d9f79` · protocol `ssp_429e3332d8ab`.

| Finding | Value |
|---|---|
| E0 / E1 MobileNet embedding baselines | **FAIL** all three fidelity gates (val general Spearman ~0.56–0.60) |
| P0 render cache | Complete — `n_index` 66,485 · ok 66,473 · 9 missing source · 3 errors · ~2.7 GB |
| The 3 errors | Z8 NEFs corrupt at source; both decode paths fail, so not a preprocess divergence |
| Render throughput | `ThreadPoolExecutor` scaled **7.7×** over spawn-based processes |
| E2 full seed-42 train | **Still running at pause — no recordable result** |

**Caveat:** gate failure is recorded as failure — do not retune under the same contract. Do not enable
shadow or change fusion without a new human decision.

| Authoritative page | Role |
|---|---|
| [`../research/SESSION_STUDENT_SCORER_E2_2026-08-05.md`](../research/SESSION_STUDENT_SCORER_E2_2026-08-05.md) | Consolidated session record (render → train) |
| [`../research/STUDENT_SCORER_PROTOCOL.md`](../research/STUDENT_SCORER_PROTOCOL.md) | Locked gates / commands |
| [`../research/STUDENT_SCORER_RESULTS.md`](../research/STUDENT_SCORER_RESULTS.md) | Append-only experiment table |
| [`../research/STUDENT_SCORER_STUDY.md`](../research/STUDENT_SCORER_STUDY.md) | Program overview |
| [`../research/STUDENT_SCORER_E2_CHECKPOINT.md`](../research/STUDENT_SCORER_E2_CHECKPOINT.md) | Older hold-before-GPU checkpoint (superseded for the train narrative) |

**Artefacts:** `artifacts/student_scorer/msm_8ef568a5db3d9f79/` (renders + `runs/E2_s42/`); cache
`~/.cache/student_scorer/…/p0_512/`.

## Arc B resolution (2026-08-06)

Everything above this heading is the **21:46 pause snapshot and is left unedited**. This section
records what happened after it.

**The train that was "still running at pause" was not running much longer.** PID 1215 died at ~22:56
having reached epoch 4 (`val_masked_teacher_loss` 0.0014043). It was the **second** full-train death —
PID 2158 died earlier at epoch 6 — and the cause is not a job fault:

| Evidence | Reading |
|---|---|
| `uptime` → up 2 min | the WSL VM restarted |
| `dmesg` → `journal … uncleanly shut down`, `Time jumped backwards` | abrupt termination, host sleep/resume signature |
| `free -g` → 13 GB of 15 GB free | **not** OOM |
| `e2_full_train.log` unchanged at 916 bytes, no traceback | silent kill, not a Python crash |
| `report.json` / `run.json` still at `17:55:16` | still the *smoke's*; nothing recordable was produced |

Two figures recorded at pause were wrong and are superseded:

- **~18.4 min/epoch → ~6.1 h** was measured while `bird_crop.degradation_eval` contended for the GPU.
  Uncontended, the rate is **~8.8 min/epoch → ~2.9 h for 20 epochs — inside the contract's 4 h cap.**
  Budget was never the blocker.
- **`best.pt` is not resumable.** It carries only `model`, `epoch`, `val_masked_teacher_loss`,
  `teachers`, `arch` — no optimizer, scheduler, scaler, or history. Every death cost the whole run.
  Worse, smoke and both full runs share `runs/E2_s42/`, so PID 2158's better epoch-6 checkpoint
  (0.00131) had already been overwritten by PID 1215's 0.00140.

**Fix — checkpoint resume** in `scripts/research/student_scorer/train_image_model.py`. Adding resume
had been declined earlier because it "cannot help the in-flight run"; with no in-flight run left, that
reason expired. The change writes `runs/<exp>_s<seed>/last.pt` once per epoch via tmp+`replace()` —
the same atomic pattern that held the render index at exactly 44,000 rows through a hard kill —
carrying model, optimizer, scheduler, scaler, `history`, `best_val`, `best_epoch`, `bad_epochs` and
`next_epoch`. An opt-in `--resume` restores them, starts cleanly at epoch 0 when no `last.pt` exists,
and **raises** rather than continue when a `guard` block (manifest, protocol, experiment, seed,
epochs, limit, batch size, grad accum, lr, patience, backbone, fine-tune) disagrees — silently
resuming into a different config would produce a result that cannot be labelled. Tests in
`tests/test_student_scorer_image_dataset.py`.

A resumed run is **not** bit-identical to an uninterrupted one: `set_seed` runs once at start, so the
post-resume shuffle order differs, and dataloader workers put bit-identity out of reach anyway.
Rather than fake reproducibility, the run records `resumed_from_epoch` in both `report.json` and
`run.json`, and the results row states it.

**Verdict:** pending. The relaunched run is recorded in
[`../research/STUDENT_SCORER_RESULTS.md`](../research/STUDENT_SCORER_RESULTS.md) under run ID
`2026-08-05-e2-convnext` once `report.json` lands — **gate failure recorded as failure**, exactly as
E0 and E1 were. Nothing here touches production: no fusion edit, no anchors, no shadow enablement.

## Arc A resolution (2026-08-08)

Track A finished and Arm B was scored. Both had been open since the pause; the numbers changed the memo's
conclusion rather than confirming it.

**Track A completed — 7 models on the pinned 236, merges clean.** `haar_energy` died twice at startup with
the same signature as the E2 trains (`uptime` in minutes; nothing in the log past the first line), and both
times cost only that one model because the sequential wrapper persists after each. A third attempt under a
Windows-side keep-awake finished in 27 min. `trackA.log` shows `Carried forward 6 previously measured
model(s)` and **zero** `replacing it rather than merging` — the merge guard never had to reject a run.

| On constructed degradation | Value |
|---|---|
| `dog_energy` crop sensitivity | **8.80×** blur · 6.52× motion — the highest in the study, above LIQE's 3.61× |
| `haar_energy` | 7.20× blur · 6.35× motion |
| `tenengrad` / `laplacian_variance` | 4.63× / 3.17× blur |
| On the **noise** ladder | 3 of 4 flagged **Suspect** — `laplacian_variance` scores ρ **+0.996**, i.e. sharpness *rises* with grain |

**Arm B was scored, and it fails.** Against the agent-derived labels (reject = positive): precision
**0.1429** against a base reject rate of **0.2963** — a lift of **×0.48** — with recall **0.0156**
(TP 1 / FP 6 / FN 63). The rule fires on 7 of 216 images, so it is at once too rare to be useful and worse
than the base rate when it does fire. That is consistent with Arm A: a rule built on a measure sitting at
chance does not become accurate by intersecting it with a second cue.

**Reading the two together is the finding.** The same measures that are *best in the study* on constructed
blur are *at chance* on real misfocus (best AUC 0.5295). Quoting 8.80× as evidence for a focus check would
be reading the constructed number as if it were the derived one. Details:
[`BIRD_CROP_FOCUS_MEASURES_2026-08-03.md`](BIRD_CROP_FOCUS_MEASURES_2026-08-03.md).

**Verdict:** the research question is answered — negatively for the Arm B rule, positively for the crop
premise on constructed ground truth. #317 closes. Human-label validation and any productionization decision
move to a follow-up; nothing here is productionized, and `technical_failures.enabled` stays `false`.

## What both tracks learned about long jobs

This is the reusable part. Both workstreams lost work to the same causes.

1. **Launch long WSL jobs under `setsid`, log to a durable path.** `/tmp` does not survive a WSL restart,
   and plain backgrounded `wsl -e` runs get killed. A `&`-backgrounded `&&` chain dies with its parent
   shell — write a script file instead.
2. **One invocation per unit of work that only persists at the end.** `degradation_eval` writes after
   *all* models finish, so a restart discarded two completed measures; the sequential wrapper fixed it.
   The render's periodic flush is the same lesson solved the other way — it held at exactly 44,000 rows
   through a hard kill.
3. **Monitor commands run in Git Bash on Windows, not WSL.** A bare `/home/...` or `/mnt/d/...` argument
   gets MSYS-mangled into `C:/Program Files/Git/...`; PIDs seen there are Windows PIDs. Wrap as
   `wsl -e bash -c '…'`, and use `MSYS_NO_PATHCONV=1` when passing paths. Both tracks produced a **false
   "process died"** report this way while the job was fine.
4. **Trust file mtimes over `date`.** The WSL clock jumped backward after sleep/resume.
5. **A checkpoint file is not a heartbeat** when it is written only on improvement. Liveness must come
   from the process and the GPU.
6. **Host sleep kills the WSL VM, and no launch trick survives that — only resume does.** The
   signature is `uptime` in minutes plus `journal … uncleanly shut down` and `Time jumped backwards`
   in `dmesg`, with plenty of free RAM and no traceback in the job log. Both full E2 trains died this
   way. `setsid`, `nohup` and durable logs do not help; a per-epoch resumable checkpoint does. Any job
   whose only durable output is written at the *end*, or whose checkpoint omits optimizer state, is
   one sleep away from losing everything. Corollary: `setsid nohup … &` inside `wsl -e bash -c '…'`
   leaves **no** process at all — the session tears down before the child is reparented. Keep a
   Windows-side `wsl.exe` alive holding the session instead. The cheap prophylactic is
   `scripts/powershell/Keep-Awake.ps1 -Action Start` before launching anything long: `haar_energy` died
   twice this way and finished first try once the host was pinned awake.

## Left open at pause

> Snapshot, kept as it stood at 21:46. Every bird-crop row below is now closed — see
> [Arc A resolution](#arc-a-resolution-2026-08-08); the student-scorer rows are tracked by
> [Arc B resolution](#arc-b-resolution-2026-08-06) and #323.

| Track | Open item |
|---|---|
| Bird-crop | Track A sequential run: `laplacian_variance` merged; `tenengrad`, `dog_energy`, `haar_energy` outstanding |
| Bird-crop | Re-run `export_results.py` after Track A; refresh the Phase 4 memo; Arm B focus re-run |
| Bird-crop | Nothing committed — commit under `Closes #317`, excluding `student_scorer` and root transcripts |
| Student scorer | Confirm the train finished, transcribe `report.json`, append the results row and log entry — **recording a gate failure as a failure** |
| Student scorer | Update issue #323; do not enable shadow or touch fusion without a new human decision |

## Raw sources (immutable)

| File | Source |
|---|---|
| [2026-08-05-bird-crop-closeout-cursor.md](../raw/2026-08-05-bird-crop-closeout-cursor.md) | Cursor bird-crop close-out scratch |
| [2026-08-05-student-scorer-e2-cursor.md](../raw/2026-08-05-student-scorer-e2-cursor.md) | Cursor E2 session scratch |
| [2026-08-01-student-scorer-e2-claude.md](../raw/2026-08-01-student-scorer-e2-claude.md) | Claude E2 render/train scratch |

## See also

- [`INDEX.md`](INDEX.md) — reports index
- [`../research/INDEX.md`](../research/INDEX.md) — research index
- [`../raw/README.md`](../raw/README.md) — raw sources hub
