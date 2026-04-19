# Wiki Log

Chronological record of wiki operations. Append-only.

Parse with: `grep "^## \[" docs/log.md | tail -10`

---

## [2026-04-18] review | `/ui/runs` deep code & design review

Added [reports/UI_RUNS_CODE_REVIEW_2026-04-18.md](reports/UI_RUNS_CODE_REVIEW_2026-04-18.md) — end-to-end review of the Runs feature (React SPA pages, `/api/jobs/recent`, `/api/runs/*`, `db.py` helpers, orchestration globals, WebSocket store). 30 findings documented. Top risks: cancel silently ignores indexing/metadata/bird_species runners; Active/Queued tabs client-filter only top 120 rows and can drop live jobs; enqueue-vs-`create_job_phases` race; `pause_run` check-then-write can overwrite terminal status; `resume_job_phases` wipes `error_message`; queued-cancel returns "canceled" while only flipping a flag; `/stages/{code}/retry` writes illegal `pending` transition. Also documented enum drift (`canceled`/`cancelled`, StageState), `useWebSocket` whole-store subscription perf issue, and double-JSON payload hack hiding root cause. Indexed in [reports/INDEX.md](reports/INDEX.md).

---

## [2026-04-16] review | Code review of 2026-04-15 commits

Added [reports/CODE_REVIEW_2026-04-15.md](reports/CODE_REVIEW_2026-04-15.md) — review of 47 commits in `aaeca35..61c36b1`. Green: job_type stability (PR #72), MUSIQ import hardening (PRs #80, #81), capability-aware run report (PR #73), metadata_runner path validation (PR #70), conflict-marker CI guard (PR #86). Blockers: `a6fdb34` bundles legit `workflow_healing.py` refactor with junk/scratch files (`_db_methods.txt`, `analyze_dump.py` with hardcoded personal path, `fix_all_backups_state.json`, `scratch/`, `artifact/scratch/`); `61c0738` release commits a 5 MB `thumbnails/feature_cache/feature_cache.npz` binary. Follow-ups: hygiene cleanup PR, widen CI guard to `push: master`, add tests for indexing log persistence + job_type preservation + runs report fallback. Indexed in [reports/INDEX.md](reports/INDEX.md) and [INDEX.md](INDEX.md).

---

## [2026-04-17] ingest | Run orchestration audit

Added [reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md](reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md) — snapshot of bugs/gaps in job+phase orchestration from webui.log + Postgres (`jobs`, `job_phases`, `image_phase_status`). Covers `MultiModelMUSIQ.load_model` AttributeError regression, dispatcher treating runner-busy as terminal failure, 137 stale `running` phase rows (75 >1h), 2 stuck `running` jobs, 40 maintenance-closed stale jobs, path validation happening post-create, `cancelled/canceled` spelling split, 12,363 empty stacks, MCP SSE event-loop stalls up to 147s. Indexed in [reports/INDEX.md](reports/INDEX.md) and [INDEX.md](INDEX.md).

---

## [2026-04-13] reorganize | Wiki graph — Phase 4, reports, testing

**Phase 4 keywords:** Added [PHASE4_KEYWORDS_HUB.md](plans/database/PHASE4_KEYWORDS_HUB.md). Moved execution/snapshot Phase 4 docs to [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md); updated [PHASE4_STATUS_SUMMARY.md](plans/database/PHASE4_STATUS_SUMMARY.md), [PHASE4_KEYWORDS_DEPRECATION.md](plans/database/PHASE4_KEYWORDS_DEPRECATION.md), [NEXT_STEPS.md](plans/database/NEXT_STEPS.md), [PHASE4C_SOFT_DEPRECATION_PLAN.md](plans/database/PHASE4C_SOFT_DEPRECATION_PLAN.md), [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md), [plans/INDEX.md](plans/INDEX.md), [archive/INDEX.md](archive/INDEX.md), root [CLAUDE.md](../CLAUDE.md).

**Reports:** Added [DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md); moved `docs/reports/debugging-sessions/` → [archive/reports/debugging-sessions/](archive/reports/debugging-sessions/INDEX.md). Moved `docs/project/SPECS_LAST_48H_*` → [RELEASE_HANDOFF_2026-04-10_2026-04-11.md](reports/RELEASE_HANDOFF_2026-04-10_2026-04-11.md). Updated [reports/INDEX.md](reports/INDEX.md), [INDEX.md](INDEX.md), [engineering/INDEX.md](engineering/INDEX.md).

**Testing:** Folded meta tracker into [WSL_TESTS.md](testing/WSL_TESTS.md) / [TEST_STATUS.md](testing/TEST_STATUS.md); archived pointer [archive/testing/DOCUMENTATION_ISSUES.md](archive/testing/DOCUMENTATION_ISSUES.md). Updated [testing/INDEX.md](testing/INDEX.md).

---

## [2026-04-13] update | Single project-local `.venv`

[ENVIRONMENTS.md](setup/ENVIRONMENTS.md): document one repo-root `.venv` for optional Windows-native use and optional WSL research; warn against mixing Windows and WSL interpreters in the same folder. [setup_wsl_research_env.sh](../scripts/setup_wsl_research_env.sh) now defaults to `$ROOT/.venv` (replaces `.venv_wsl`). [requirements_research.txt](../requirements/requirements_research.txt) usage comment aligned.

---

## [2026-04-13] update | Remove raw markdown sources

Removed `docs/raw/gradio-serving-comparison.md` and `docs/raw/investigation_culling_no_stacks_2026-03-15.md`; curated content remains in [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md) and [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md). Updated [raw/README.md](raw/README.md), [INDEX.md](INDEX.md), report pages, [CHANGELOG.md](../CHANGELOG.md).

---

## [2026-04-13] ingest | Gradio serving note + culling investigation

Moved loose drafts into raw archive: [gradio-serving-comparison.md](raw/gradio-serving-comparison.md), [investigation_culling_no_stacks_2026-03-15.md](raw/investigation_culling_no_stacks_2026-03-15.md). Added wiki pages [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md), [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md). Updated [INDEX.md](INDEX.md), [reports/INDEX.md](reports/INDEX.md), [ARCHITECTURE.md](technical/ARCHITECTURE.md), [CULLING_FEATURE.md](technical/CULLING_FEATURE.md), [CHANGELOG.md](../CHANGELOG.md), [raw/README.md](raw/README.md).

---

## [2026-04-13] create | Wiki Schema

Established LLM wiki system. Created [WIKI_SCHEMA.md](WIKI_SCHEMA.md) (conventions, page types, operations), this log file, and slash commands (`/wiki-ingest`, `/wiki-query`, `/wiki-lint`). Added wiki maintenance rules to CLAUDE.md. Pages touched: [WIKI_SCHEMA.md](WIKI_SCHEMA.md), [INDEX.md](INDEX.md), [README.md](README.md), [CLAUDE.md](../CLAUDE.md).
