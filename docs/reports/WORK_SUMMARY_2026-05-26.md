# Work summary — 2026-05-26

**Operator:** dmnsy (Claude Opus 4.7 assist)
**Session focus:** Two related scoring/pipeline issues — auto-drive reprocessing already-done folders, and ~11k images missing composite aggregates despite per-model scores.

---

## 1. Auto-drive reprocessing investigation (run 3245)

**Trigger:** Run [#3245](http://127.0.0.1:7860/ui/runs/3245), description "Auto-drive queued this folder from the Runs buckets planner.", path `/mnt/d/Photos/Z6ii/28-400mm/2025/2025-03-16` (250 images).

### What was wrong
- All 250 images in scope already had `image_phase_status.status = 'done'` for indexing, metadata, scoring, culling, keywords. Only bird_species had genuine work (248 not_started + 1 missing_data).
- Auto-drive's repair plan still flagged `stale_executor: 1000` (4 phases × 250) and re-queued them.
- Indexing already burned **379 s** rewriting 250 already-indexed rows; metadata, scoring, culling were queued behind it.

### Root cause
`modules/phases_policy.py:74` short-circuits to `executor_version_changed` whenever stored ≠ active version, *before* the per-phase data-validation block runs. Three concrete mismatches make every completed folder look "stale":

1. **metadata / culling** — old `image_phase_status` rows from app_version 1.6.0 persist `executor_version = NULL`; registry says `"1.0.0"` (`modules/phase_executors.py:54, 79`).
2. **scoring** — DB rows persist `SCORING_EXECUTOR_VERSION = "5.0.0"` (`modules/phases.py:62`), but `_get_scorer_version()` returns `scorer.shared_scorer.VERSION` (e.g. `topiq-nr-1`, `arniqa-1`) — never `"5.0.0"`.
3. **indexing** — pre-versioning rows with `executor_version = NULL` flag against the registry's `"1.0.0"`.

### Deliverables
- Full investigation: [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md)
- Operator / fix detail: [AUTO_DRIVE_FIX_SUMMARY.md](AUTO_DRIVE_FIX_SUMMARY.md)
- Short summary: [AUTODRIVE_REPROCESSING_SUMMARY.md](AUTODRIVE_REPROCESSING_SUMMARY.md)

### Fix status (2026-05-27 — shipped)

| Area | Change |
|------|--------|
| Planner policy | `stored_version` must be truthy before `executor_version_changed`; canonical `SCORING_EXECUTOR_VERSION = "5.0.0"` in registry and IPS writes |
| Auto-drive enqueue | `include_stale_executor=False`; only JIT non-empty `stage_queues`; dirty `phase_agg_json` refresh on folder-buckets |
| UI | `planner_next_phases` on bucket API + RunsBucketsPanel; planner counts on run detail |
| Manual submit | Narrow phases via JIT; `400 nothing_to_queue` when empty |

**Verification:** 50 tests in `test_phases_policy`, `test_runs_autodrive` (24), `test_run_phase_planner`, `test_run_submit_prereq_gating`; JIT dry-run on run-3245 folder → `['keywords', 'bird_species']` (not six stages). Restart WebUI before relying on live API behavior.

---

## 2. Empty aggregated scores (image 30323 / library-wide)

**Trigger:** Cursor chat export `cursor_images_with_empty_aggregated_sco.md` flagging image 30323 with empty aggregates despite per-model scores.

### What was verified
- Image 30323: 7 successful `image_model_scores` rows, but `score = 0.0`, `score_general / technical / aesthetic = NULL`.
- Library-wide: **10,879 images** have `image_model_scores.status = 'success'` rows but `score_general` `NULL` or `0`.
- `scripts/analysis/recalc_composite_scores.py` exists, supports `--dry-run` / `--batch-size` / `--folder-path`, `NEW_VERSION = "5.1.0"`. Reads from `image_model_scores`, runs `score_normalization.compute_all`, writes back composites + rating + label. No re-inference.

### Dry-run result (library-wide)

```
Fetched 61553 images in 4.6s
TOPIQ coverage:   61553 / 61553
ARNIQA coverage:  61553 / 61553
Computed 61553 updates in 2.4s
  Changed:   11045
  Unchanged: 50508
```

Rating distribution shift if applied:

| rating | old | new | Δ |
|---|---|---|---|
| 1 | 2,466 | 3,175 | +709 |
| 2 | 7,449 | 9,768 | +2,319 |
| 3 | 22,133 | 27,790 | +5,657 |
| 4 | 16,404 | 18,725 | +2,321 |
| 5 | 2,056 | 2,095 | +39 |

Top |Δgeneral| samples are all `0.0000 → ~0.93` — the previously-NULL composites being filled in for the first time (no real "re-grading", just backfill). The bulk of the rating-count growth is rows that previously had no rating at all.

### Crossover with item 1
`recalc_composite_scores.py` bumps the scoring `executor_version` stamp from `"5.0.0"` to `"5.1.0"`. Under the pre-fix planner, that would re-queue scoring on all changed rows via `stale_executor`. With item 1 shipped, NULL-version false positives are gone and auto-drive ignores executor-only drift (`include_stale_executor=False`).

### Apply result (2026-05-26 22:17 — library-wide)

```
Fetched 61553 images in 4.6s
Computed 61553 updates in 2.4s
  Changed:   11045
  Unchanged: 50508
DB writes completed in 61.1s
```

Verification (post-run):

- Gap closed from **10,879 → 19** (`score_general IS NULL OR = 0` with successful `image_model_scores`).
- Image 30323 (the original report): `score = 0.0` → composites now `general=0.5846 / technical=0.6884 / aesthetic=0.5524`, `rating=3`, `label=Green`.
- **19 stragglers** (post–library-wide recalc) were in `/mnt/d/Photos/Z6ii/40mm/2025/2025-07-31/` — folder scored/indexed **after** the global recalc run, not a `fetch_scored_images` bug. **Resolved 2026-05-27:** folder recalc applied **91** composite updates; library-wide straggler count is now **0**.

---

## Open follow-ups

1. ~~**Run `recalc_composite_scores.py` in batches**~~ — library-wide **2026-05-26** (11,045 rows); folder catch-up **2025-07-31** **2026-05-27** (91 rows). Stragglers closed.
2. **Deploy smoke** — restart WebUI, rebuild `/ui/` if using `static/app/`; `align_auto_drive` plan preview timed out against live API (slow DB); JIT in-process confirms `['keywords', 'bird_species']` for run-3245 folder.
3. **Backfill `executor_version`** — canary **500** applied on `2025-03-16` folder. Library-wide: `python scripts/maintenance/backfill_executor_version_ips.py` (dry-run showed ≥8k/phase at default `--limit 100000`; indexing/scoring/keywords often 0 NULL when data complete).
4. ~~**Regression test for legacy NULL IPS**~~ — done: `test_plan_scope_empty_queues_legacy_null_metadata_and_canonical_scoring` in `tests/test_run_phase_planner.py`.
5. ~~**Plan preview vs auto-drive**~~ — `align_auto_drive` on `POST /api/runs/plan/preview`; New Run scope UI uses it.

**Addressed with item 1 rollout:** stale `phase_agg_json` / `awaiting_indexing` mis-bucket — `refresh_dirty_limit` on `GET /api/runs/folder-buckets` and `_resolve_folder_phase_summary`.

## Files touched / produced

**Investigation session (2026-05-26):**

- **Created:** `docs/reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md`, this file
- **Read:** `modules/run_phase_planner.py`, `phases_policy.py`, `phase_executors.py`, `pipeline.py`, `runs_autodrive.py`, `scoring.py`, `scripts/analysis/recalc_composite_scores.py`

**Rollout (2026-05-27):**

- **Code:** `phases_policy.py`, `phases.py`, `phase_executors.py`, `pipeline.py`, `runs_autodrive.py`, `api.py`, `run_phase_planner.py`, `db_legacy.py`, frontend Runs buckets / run detail panels
- **Tests:** `test_phases_policy.py`, `test_runs_autodrive.py`, `test_run_phase_planner.py`, `test_run_submit_prereq_gating.py`
- **Docs:** `AUTO_DRIVE_FIX_SUMMARY.md`, `AUTODRIVE_REPROCESSING_SUMMARY.md`
- **Diagnostics:** `scripts/diagnostics/capture_run_planner_snapshot.py`
- **Maintenance:** `scripts/maintenance/backfill_executor_version_ips.py`
- **Follow-up session:** plan preview `align_auto_drive`, ScopeSelector repair preview alignment

## Investigation methods used

- MCP tools: `get_run_diagnostics`, `get_job_details`, `get_job_phases`, `get_job_execution_report`, `execute_sql`.
- Repo grep across `modules/` for `executor_version`, `stale_executor`, `SCORING_EXECUTOR_VERSION`, `shared_scorer`.
- WSL command for dry-run: `wsl -e bash -lc 'source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring-backend && python scripts/analysis/recalc_composite_scores.py --dry-run'`.
