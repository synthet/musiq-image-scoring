# Code Review — 2026-04-15 Changes

**Range reviewed:** `aaeca35..61c36b1` on `master` (47 commits, 79 files, +3068 / -2998)
**Reviewer:** Automated audit via Claude Code, filed 2026-04-16
**Scope:** All commits landed on 2026-04-15. Excludes the current dirty working tree.

Severity tags: `[blocker]` `[should-fix]` `[nit]` `[follow-up]`.

---

## Summary

Yesterday was a mixed day. There are several genuinely good fixes (job_type stability, metadata_runner path validation, MUSIQ import hardening, conflict-marker CI guard), but they are bundled with two problematic commits that leaked local/scratch material into `master`:

- `a6fdb34` ("Reapply local changes without SQL backup") — a 1508/2884 kitchen-sink commit that deletes four maintenance scripts while simultaneously adding scratch junk and a personal-path script.
- `61c0738` ("chore: release v7.4.0") — bundles a **5 MB binary cache file** (`thumbnails/feature_cache/feature_cache.npz`, 327 B → 4,978,221 B) into the release commit.

Both should be cleaned up before v7.5. Several merge-marker PRs (#82, #83, #85) are symptoms of the same underlying hygiene gap that the new CI guard in PR #86 is meant to close — the guard itself looks correct but arrives after the damage.

---

## Findings by theme

### 1. MUSIQ import hardening (PRs #80, #81)

**Commits:** `5d81ada`, `d57f20f`

`modules/scoring.py:17-34`
- `[good]` Canonical package import `from scripts.python.run_all_musiq_models import MultiModelMUSIQ` replaces `sys.path` hacking. Verified `scripts/python/run_all_musiq_models.py` exists; PEP 420 namespace packages apply (no `__init__.py` needed).
- `[good]` On `ImportError`, `_musiq_import_error` is captured and both `run_scoring_job` and `run_rescore_job` now fail the job explicitly (`db.update_job_status(job_id, "failed", msg)` + `job_completed` broadcast) instead of silently using a stub class.
- `[nit]` d57f20f leaves the (now-unreachable) `_musiq_import_error` branch duplicated across two methods. A shared `_guard_musiq_loaded(job_id, log) -> bool` helper would remove the copy-paste.

### 2. Pipeline job_type stability (PR #72)

**Commit:** `22da47f` + merge-marker fix `4d8c1b1`

`modules/db.py:4229,4298-4380 update_job_status()`
- `[good]` Preserves the root `job_type` across phase transitions instead of overwriting with `job_type_for_phase_dispatch(pc)` — correct for multi-phase pipeline runs.
- `[good]` Drops the post-update `SELECT job_type` round-trip; returns `root_job_type` captured at the start.
- `[good]` `phase_id = COALESCE(?, phase_id)` (via `4d8c1b1`) protects against `pid=None` blanking a valid phase binding.
- `[should-fix]` Test updates in `tests/test_multi_phase_job_postgres.py` and `tests/test_multi_phase_job_workflow.py` assert the new behavior but I did not see an explicit assertion that `job_type` **does not change** mid-run for a pipeline kicked off with a specific phase set. Recommend adding one case: submit pipeline → advance phases → assert `jobs.job_type == 'pipeline'` at every step.

### 3. Indexing log persistence (PRs #75, #78, #79)

**Commits (chronological):** `2c40681`, `f1e78b9`, `1c40ac5`, `efb4791`, `862a08d`

`modules/indexing_runner.py:193-210 _persist_log()`
- `[should-fix]` This block was rewritten **five times** in one day across three PRs. The final form hedges both ways: prefer `db.update_job_log`, fall back to raw SQL for non-running jobs, and to `update_job_status("running", log=...)` for running ones. It works, but `db.update_job_log` is now always present (verify and then drop the `hasattr` guard). Leaving it in invites future confusion.
- `[good]` The core semantic intent — "do not force a terminal job back to `running` just to persist a late log message" — is correct and matches the RUN_ORCHESTRATION_AUDIT findings. Keep.
- `[follow-up]` The repeated rewrites suggest this code path needs a unit test. Add one asserting: terminal job + log persist → log field updated, status unchanged.

### 4. Maintenance / status recalculation hardening (PR #74)

**Commits:** `292c4a4`, `0bebe0c`

`modules/api.py:6170,6458-6474 recalculate_status_from_data`
- `[good]` Defensive read of `summary["per_image_changes"]["total_rows_changed_estimate"]` replaced with `.get(...) or 0`, avoiding `KeyError` when the inner summarizer bails early.
- `[good]` Audit-row failures no longer poison the main response; they append a structured warning to `summary["warnings"]`.
- `[nit]` `summary: Dict[str, Any] = {}` at function top + `summary_payload = summary if isinstance(summary, dict) else {}` is redundant belt-and-suspenders. The `isinstance` check is dead now that summary is typed.

### 5. Capability-aware run report fetch (PR #73)

**Commit:** `14145b5`

`frontend/src/api/runs.ts:87-115`, `frontend/src/components/runs/ReportPanel.tsx:228-260`
- `[good]` Clean approach: new `RunReportResponse { available, report?, reason?, message? }` wrapper, back-compat unwrap of legacy `JobExecutionReport` shape, and a 404-to-`available:false` mapping so non-pipeline runs render an unobtrusive "Report unavailable" chip instead of a red error.
- `[good]` `enabled: reportSupported` prevents needless 404s for run types that don't produce reports.
- `[nit]` No test added for the unwrap/fallback logic in `runs.ts`. A vitest around `runsApi.getReport` mock paths would be worth it given the three-way branching.

### 6. Metadata runner path handling (PR #70)

**Commit:** `7342549`

`modules/metadata_runner.py:176-247`
- `[good]` Per-image `local_path = utils.convert_path_to_local(original_path)` + existence check before EXIF/XMP work. Images with missing local paths are marked `FAILED` with a descriptive `error` string instead of crashing the whole run. This matches the RUN_ORCHESTRATION_AUDIT path-validation-gap finding.
- `[good]` Hoists the `from modules import utils` to the top of the file (was a nested import).
- `[nit]` The `db.set_image_phase_status(...)` call is wrapped in a bare `except Exception: pass`. If the DB write fails, we silently leak a partial-processed image. At least log it.

### 7. One-off repair script (PR #77)

**Commit:** `370a758`

`scripts/maintenance/repair_job_1138_pipeline_state.py` (new, 355 lines)
- `[good]` Script is idempotent (`Rerun-safe: if already corrected, updates are no-ops`), transactional, and dry-run-friendly.
- `[should-fix]` The filename hard-codes the job ID (`repair_job_1138_...`) but the script accepts `argparse`. Recommend renaming to `repair_pipeline_job_phase_drift.py` and making `--job-id` required — otherwise this dies as soon as the next drifted job appears. As-is it's a one-shot artifact that will stay in `scripts/maintenance/` forever with "1138" in the name.
- `[nit]` `TARGET_JOB_ID = 1138` as a module constant is only used as an argparse default. Moving it into `parser.add_argument("--job-id", type=int, required=True)` makes the intent explicit.

### 8. Merge-marker cleanup + CI guard (PRs #82, #83, #85, #86)

**Commits:** `4d8c1b1`, `db51b96`, `b1273ba`, `af81f60`

- `[verified-clean]` `b1273ba` resolution in `modules/api.py:6153` correctly drops duplicate `dry_run=` and `heal_thumbnails_global=request.heal_thumbnails_global` (both were in the rejected branch; `HealPhaseRequest` has no `heal_thumbnails_global` field — confirmed by `grep` showing zero remaining references). The `n_resets = data.get("resets_performed", 0)` line was dead code (no subsequent use); removal is fine.
- `[verified-clean]` `4d8c1b1` picked the `COALESCE(?, phase_id)` side — correct; the HEAD side would have blanked `phase_id` when `pid=None`.
- `[good]` `af81f60` `scripts/check_conflict_markers.sh` pattern `^(<<<<<<<|>>>>>>>|={7}$)` is correct. Scoped to `modules/tests/scripts/` with source-file extensions — sensible to avoid false positives in wiki dividers.
- `[should-fix]` The GitHub Action uses `runs-on: ubuntu-latest` which ships `ripgrep`, but the script `set -euo pipefail` will hard-fail if a runner ever misses it. Either gate with `command -v rg` or fall back to `grep -E`.
- `[follow-up]` The workflow triggers on `pull_request` and `merge_group` only. It will **not** catch a direct push to `master`. If direct-to-master is possible in this repo (yesterday's PRs suggest it is not, but check), extend with `push: { branches: [master] }`.

### 9. `a6fdb34` "Reapply local changes without SQL backup" — `[blocker]`

This single commit is the main concern of this review. It bundles multiple unrelated changes:

**Legitimate content (worth keeping, but should have been its own PR):**
- New `modules/workflow_healing.py` (217 lines) replaces `modules/folder_quality_schedule.py` (268 lines) + 4 maintenance scripts (`folder_data_quality_report.py` −469, `queue_scoring_incomplete_by_folder.py` −295, `repair_thumbnail_path_columns.py` −61, `schedule_folder_quality_fix_runs.py` −243, `backfill_folder_phase_aggregates.py` −29, `fix_job_phases_terminal_running.sql` −42).
- Substantial refactors to `frontend/src/components/runs/RunsToolsTab.tsx` (−345), `frontend/src/hooks/usePipelineToolAction.ts` (−200 net), `frontend/src/constants/pipelineTools.ts` (−100 net), `modules/api.py` (267 line churn), `modules/db.py` (662 line churn).

**Junk that should NOT be in the repo — recommend reverting the additions:**
| File | Size | Problem |
|------|------|---------|
| `_db_methods.txt` | 32 KB, UTF-16 binary | Dump of db.py method signatures; dev scratch |
| `analyze_dump.py` | 39 lines | **Contains hardcoded personal path** `c:\Users\dmnsy\.claude\projects\d--Projects-image-scoring-backend\3d8d3903-c0d3-45d9-8a54-73dece21c79c.jsonl` (a Claude Code transcript UUID). Privacy/info-leak. |
| `fix_all_backups_state.json` | 13 lines | Local script state (`H_junk: done`, `H_meta_z6ii: failed`...). Should be runtime state, not tracked. |
| `docker_refresh_db.bat` | 48 lines | Local dev convenience; may be legitimate but add to `tools/` with a README entry, not repo root. |
| `image-scoring-backend.sln` | 47 lines | Visual Studio solution file — fine if the team uses VS, but add to repo-root conventions doc or move to `.ide/`. |
| `artifact/scratch/break_image*.py`, `test_neighbors.py`, `verify_policy.py` | ~90 lines | Throwaway scripts. `artifact/` is not an established repo convention. |
| `scratch/check_folder_state.py`, `test_db_format.py`, `verify_audit.py`, `verify_final_checks.py`, `verify_repair.py` | ~250 lines | All clearly dev scratch. `scratch/` directory had no prior tracked content. |

**Recommendation:** Cherry-pick the `workflow_healing.py` refactor into a dedicated PR with a real commit message. File `git rm` PRs for `_db_methods.txt`, `analyze_dump.py`, `fix_all_backups_state.json`, `scratch/`, `artifact/scratch/`. Either justify `docker_refresh_db.bat` and `image-scoring-backend.sln` with a README note or remove them too.

### 10. Release commits v7.3.0 / v7.4.0 — `[blocker]`

**`aaeca35` chore: release v7.3.0** — a 6367/322-line "release commit" is actually a feature dump, not a version bump. Normal release commit = version.py + CHANGELOG.md + maybe static assets. Everything else should have been merged via feature PRs first.

**`61c0738` chore: release v7.4.0** — otherwise normal, but commits `thumbnails/feature_cache/feature_cache.npz` **(327 B → 4,978,221 B)**. This is a **5 MB ML feature cache** being tracked in git. It will grow with every touch. Add `thumbnails/feature_cache/` to `.gitignore` and `git rm --cached` the file. Consider `git filter-repo` if repo size matters.

### 11. Frontend bundle drift

Working tree still has `static/app/assets/index-BxSCy5JP.css` and `index-fUQr6KKJ.js` as modified/deleted while newer `index-BxXg3rOS.js` / `index-CnvFmigM.css` are untracked. Historical pattern in the 2026-04-15 diff also shows old bundles left around (`index-DJhyuXi-.js`). Either commit the new bundle or exclude the `static/app/assets/` hashed files from tracking and regenerate on release. (Not blocking today's review — it's the working tree — but same category of hygiene issue.)

### 12. Docs

- `[good]` `62e8668` adds `docs/technical/MCP_DEBUGGING_TOOLS.md` postgres query patterns (+100 lines). Useful.
- `[good]` `3397b68` adds git pull merge-conflict troubleshooting — appropriate given the day's theme.

---

## Test gaps to fill

1. `test_indexing_runner_persist_log_terminal_state` — asserts terminal-job log writes do not flip `status` back to `running`.
2. `test_update_job_status_preserves_root_job_type` — submit pipeline, advance phases, assert `jobs.job_type` unchanged.
3. `test_runs_api_get_report_fallbacks` — vitest for the three branches of `runsApi.getReport` (new shape / legacy shape / 404).
4. `test_metadata_runner_missing_local_path` — image row with unreachable path → phase `FAILED` + error message, next image still processed.

Suggested command: `python -m pytest tests/test_phases.py tests/test_multi_phase_job_workflow.py tests/test_multi_phase_job_postgres.py -v`

---

## Rollback / follow-ups

- **Revert candidates if hygiene PRs land:** the junk-file additions inside `a6fdb34` (use `git rm`, not a full revert — the `workflow_healing.py` refactor is worth keeping).
- **Remove from tracking:** `thumbnails/feature_cache/feature_cache.npz` + add path to `.gitignore`.
- **Rename for reuse:** `scripts/maintenance/repair_job_1138_pipeline_state.py` → generic `repair_pipeline_job_phase_drift.py`.
- **Consolidate:** `IndexingRunner._persist_log` branching can be collapsed once `db.update_job_log` is confirmed always-available.

---

## Verdict

The day's functional changes are net-positive and mostly defensible. The process hygiene is not: two commits (`a6fdb34`, `61c0738`) alone account for most of the risk. Priority is **cleanup of the junk/binary additions**, not reverting behavior changes. The new CI conflict-marker guard is a welcome addition but should be widened to `push: master` if direct pushes are possible.
