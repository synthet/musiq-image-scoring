# Wiki Log

Chronological record of wiki operations. Append-only.

Parse with: `grep "^## \[" docs/log.md | tail -10`

---

## [2026-05-29] created | Input-size culling + IQA research harness

Added `scripts/research/clip_culling/input_size_{native,embed,eval}.py`, `report_input_size.py`, `common.load_pil_resized`, optional `--preprocess-size` on OpenCLIP/timm towers. NPZ caches under `reports/clip-culling/input-size/`. Doc: [reports/INPUT_SIZE_CULLING_2026-05-29.md](reports/INPUT_SIZE_CULLING_2026-05-29.md). Tests: `tests/test_clip_culling_input_size.py`.

## [2026-05-29] created | Application config reference and API split

Added [technical/CONFIG.md](technical/CONFIG.md) (canonical config keys, merge order, deprecated paths). Split `GET /api/config` (public `ConfigResponse`) from `GET /api/config/full` (merged JSON). Fixed Gradio settings merge (`merge_and_save_config_section`), `system.allowed_paths` in path security, and `validate_config` for `database.engine: api`. Updated [config.example.json](../config.example.json) and OpenAPI artifacts.

## [2026-05-29] updated | DINOv2/SigLIP2 culling spike (exp8)

Ran [scripts/research/clip_culling/](../../scripts/research/clip_culling/) against `image-scoring-postgres-e2e`: persisted `dinov2_reg_base_image` (timm DINOv2 base) and `siglip2_base_image`; added exp8 grouping vs EXIF-burst GT. **DINOv2 burst-GT ARI 0.377 &lt; MobileNet 0.423**; OpenCLIP L/14 best at 0.450. Updated [reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md](reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md) and [reports/clip-culling/SUMMARY.md](../../reports/clip-culling/SUMMARY.md).

## [2026-05-29] created | Culling model recommendation memo

Added [reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md](reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md) — synthesizes the 2026-05-28 CLIP L/14 spike and roadmap: DINOv2-reg base for grouping (validate first), keep ARNIQA/IQA for rejection, MMR + scores for stack selection. Linked from [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) Research inputs.

## [2026-05-26] created | External CLI review agent infra (subagent-orchestrator)

Onboarded sibling `subagent-orchestrator` MCP (`imgscore-subagent-orchestrator`), rule `external-cli-subagents`, skill `subagent-review`, slash commands `/check-subagents` and `/run-*-review`, and subagents `external-*`. See [technical/EXTERNAL_CLI_REVIEWS.md](technical/EXTERNAL_CLI_REVIEWS.md).

## [2026-05-27] moved | Auto-drive fix summary into docs/reports

Moved operator summary from repo-root `AUTO_DRIVE_FIX_SUMMARY.md` to [reports/AUTO_DRIVE_FIX_SUMMARY.md](reports/AUTO_DRIVE_FIX_SUMMARY.md); linked from [reports/INDEX.md](reports/INDEX.md) and [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md).

## [2026-05-24] updated | Design token docs and CI notice

Pointed [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md) at **image-scoring-ui** canonical doc and `@synthet/image-scoring-design` 1.0.0; updated [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [design/INDEX.md](design/INDEX.md) (UI surfaces table), [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) (Design tokens section), and [`.github/workflows/cross-repo-sync-notice.yml`](../.github/workflows/cross-repo-sync-notice.yml) for design-package bumps.

## [2026-05-24] created | New models summary page

Added [NEW_MODELS_SUMMARY.md](NEW_MODELS_SUMMARY.md) — consolidated overview of new/roadmap models (ARNIQA, DINOv2, SigLIP2, QPT-V2, OpenCLIP alternate), calibration #185 status, and #220 implementation phases. Linked from [INDEX.md](INDEX.md), [planning/INDEX.md](planning/INDEX.md), and [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md).

## [2026-05-24] created | QPT V2 validation gates plan

Added [planning/models/QPT_V2_VALIDATION_GATES.md](planning/models/QPT_V2_VALIDATION_GATES.md) — shadow validation gates (1–3, 5), upstream status, score_range bug, script plan, promotion criteria (#185). Linked from [planning/INDEX.md](planning/INDEX.md) and [CALIBRATION_LAYER_185_STATUS.md](planning/models/CALIBRATION_LAYER_185_STATUS.md).

## [2026-05-23] updated | Indexed pipeline model roadmap in main docs index

Added [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) to the **Models And Scoring** section of [INDEX.md](INDEX.md) (was previously linked only from [planning/INDEX.md](planning/INDEX.md) and [log.md](log.md)). Verified the doc's license claims (ARNIQA Apache-2.0, QualiCLIP CC-BY-NC) against [reports/DEEP_RESEARCH_REPORT.md](reports/DEEP_RESEARCH_REPORT.md) and confirmed all referenced research reports exist.

## [2026-05-23] updated | Current production models in pipeline recommendations

Added **Current production models** section to [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) (scoring, culling, keywords, bird species, embedding spaces).

## [2026-05-23] updated | Model use-case tables in pipeline recommendations

Added [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) section **Model use cases by task** (scoring, stacks, stack picker, keywords) and **Add or replace?** column on implementation phases.

## [2026-05-23] added | Pipeline model roadmap (Phase 0 docs)

Ingested [reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md](reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md) from deep-research-report (10). Expanded [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) with decision matrix, OpenCLIP L/14 alternate track, CLIP culling workflow rules, and implementation phases. Updated [planning/INDEX.md](planning/INDEX.md) and [reports/INDEX.md](reports/INDEX.md).

## [2026-05-22] added | Frontend UX/UI Visual Specification

Added `docs/design/FRONTEND_VISUAL_SPEC.md` documenting the React frontend visual styling (typography, layout, Map UI overrides) building on top of the VS Code Dark+ `DESIGN_SYSTEM.md`. Updated `docs/design/INDEX.md`.

## [2026-05-20] updated | GitHub backlog inventory and epics

Cross-repo issue inventory: new labels `type:epic` and `status:obsolete`, nine epic parents (#198–#203 backend, #108–#110 gallery), sub-issue links, label hygiene (#169–#175), tier-1 closes (#145, #122–#123), tier-2 obsolete markers, body refinements. Docs: [backlog-inventory-2026-05.md](project/backlog-inventory-2026-05.md); scripts `audit_backlog_issues.py`, `apply_backlog_inventory.py`, `refine_issue_bodies.py`; backlog-queue skill and [00-backlog-workflow.md](project/00-backlog-workflow.md) updated.

## [2026-05-18] added | Culling stack analytics API and docs

`modules/culling_analytics/`, REST `/api/analytics/culling` (+ session and per-stack routes), [CULLING_ANALYTICS.md](technical/CULLING_ANALYTICS.md), diagnostic SQL under `scripts/sql/culling_analytics_diagnostics/`. Gallery: Culling insights panel + stack banner ([06-culling-stack-analytics.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/06-culling-stack-analytics.md) in sibling repo).

## [2026-05-16] added | Technical failure detection MVP (#143)

Classical metrics in `modules/technical_failures/`, Postgres `image_technical_failures`, scoring integration, image detail API field `technical_failure_detection`.

## [2026-05-15] updated | Agent infra refinement pass (Firebird marker retirement)

Rewrote [.cursorrules](../.cursorrules) as a thin IDE stub pointing at `CLAUDE.md`, `.cursor/rules/`, and [`docs/CANONICAL_SOURCES.md`](CANONICAL_SOURCES.md). Retired the `firebird` pytest marker: removed from [`pytest.ini`](../pytest.ini) and added `tests/archive_firebird` to `norecursedirs`; dropped `not firebird` from the fast-test command across [`AGENTS.md`](../AGENTS.md), [`CLAUDE.md`](../CLAUDE.md), [`TESTING.md`](TESTING.md), [`.agent/COMMANDS.md`](../.agent/COMMANDS.md), [`.agent/subagents/README.md`](../.agent/subagents/README.md), [`.agent/workflows/run_tests.md`](../.agent/workflows/run_tests.md), [`.claude/agents/imgscore-mcp-debug.md`](../.claude/agents/imgscore-mcp-debug.md), [`.claude/skills/wsl-tf-python-runner/SKILL.md`](../.claude/skills/wsl-tf-python-runner/SKILL.md), [`.claude/skills/imgscore-mcp-debug/SKILL.md`](../.claude/skills/imgscore-mcp-debug/SKILL.md), and [`.claude/rules/agent-canonical-sources.mdc`](../.claude/rules/agent-canonical-sources.mdc). Updated `CLAUDE.md` Electron integration block to reflect PostgreSQL primary (Firebird decommissioned in gallery). Created [`.agent/AGENT_INFRA_STATUS.json`](../.agent/AGENT_INFRA_STATUS.json) and refreshed [`.agent/AGENT_INFRA_INVENTORY.md`](../.agent/AGENT_INFRA_INVENTORY.md) header / deprecated rows. Deleted untracked `.agent/scratch/` (already in `.gitignore`). Historical references to the marker remain in `CHANGELOG.md`, `notebooklm_docs.md`, planning specs.

## [2026-05-16] updated | Agent infrastructure inventory and workflows

Added [.agent/AGENT_INFRA_INVENTORY.md](../.agent/AGENT_INFRA_INVENTORY.md), [.agent/AGENT_INFRA_STATUS.json](../.agent/AGENT_INFRA_STATUS.json), [.agent/COMMANDS.md](../.agent/COMMANDS.md), [.agent/SAFETY.md](../.agent/SAFETY.md), [.agent/subagents/README.md](../.agent/subagents/README.md); new/rewrote [.agent/workflows/](../.agent/workflows/) (verify/run/debug/cross-repo/MCP safety/export bundle). New [.cursor/rules/agent-canonical-sources.mdc](../.cursor/rules/agent-canonical-sources.mdc); expanded [.cursor/rules/image-scoring-mcp.mdc](../.cursor/rules/image-scoring-mcp.mdc) (read-only triage, high-risk tools, Postgres-primary Firebird note); mirrored to [.claude/rules/](../.claude/rules/). Regenerated MCP tool inventory (**53** tools) in [AGENTS.md](../AGENTS.md) and [technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md). Linked infra from [AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md), [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md).

## [2026-05-16] updated | Documentation hubs and canonical source map

Reworked backend documentation hubs for a PostgreSQL + pgvector primary architecture: [README.md](README.md), [INDEX.md](INDEX.md), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE.md](DATABASE.md), [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [TESTING.md](TESTING.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), and [features/implemented/INDEX.md](features/implemented/INDEX.md). Updated [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md) from a Firebird-first schema page into a PostgreSQL authority map/table catalog, and refreshed [architecture/pipeline-architecture.md](architecture/pipeline-architecture.md) to describe the current phase/run model with backend-owned schema and API contracts. Companion gallery docs were updated in the sibling repository during the same pass.

## [2026-05-15] created | Phase status decoupling spec

Added [`features/implemented/10-phase-status-decoupling.md`](features/implemented/10-phase-status-decoupling.md) to document the migration from history-based phase status to the strict data-driven cache approach with split UI telemetry. Indexed in [`features/implemented/INDEX.md`](features/implemented/INDEX.md).

## [2026-05-13] updated | RCA correction in ELECTRON_SYNC_IMPORT_AND_PHASES.md

Corrected the **Known issues** section after a deeper repro. The original "scoring runner short-circuits when given explicit image_ids" diagnosis was wrong — the webui runs in WSL where `/mnt/d/...` paths resolve, so `scoring.py:256`'s `os.path.exists(fp)` is not the bug. Replicating with a single-stage scoring submit (job 2374, `skip_existing=false`, same 733 ids) succeeded fully — 38 min runtime, all 733 scored. The actual bug only manifests for **scoring run as a middle stage of a multi-stage WorkflowRun with `skip_existing=true`** (run 2365 path). `jobs.log` is NULL for 2365 so root cause is not yet pinned; updated [#156](https://github.com/synthet/image-scoring-backend/issues/156). Also clarified [#157](https://github.com/synthet/image-scoring-backend/issues/157): the "culling short-circuit" was downstream of #156 (no scores → nothing to cluster); separately, `SelectionRunner.start_batch` documents in code that it ignores `resolved_image_ids`, and interrupted selection jobs leave IPS rows stuck in `running` with no auto-reconciliation.

## [2026-05-10] updated | Electron sync import and pipeline phase semantics

Reflected gallery v7.7 bundle (G1/G5/G6) and backend G7 in [technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md): post-import pipeline scheduling now pre-seeds **`image_phase_status`** rows in the API-success branch (G5); `db.get_image_phase_statuses` LEFT JOINs from `pipeline_phases` so all enabled phases are always returned with `not_started` defaults (G7); gallery sidebar reads real IPS via `getImagePhaseStatuses` (G6). New **Known issues** section captures three independent bugs observed during run 2365 end-to-end monitoring on 2026-05-10: scoring runner short-circuit (`images_in_scope=0` with explicit ids), culling runner same pattern (likely cascades from scoring), and `job_phases` counter flush only at phase finalize (Runs UI shows `0 / 0` during active phases).

## [2026-05-10] updated | watch_run_http CLI

`scripts/watch_run_http.py`: handle `GET /api/runs/*/stages` JSON **array** in `--verbose`; line-buffer **`flush=True`**; **`--base-url`** / **`--port`** restored; **`--wsl-gateway`** for WSL→Windows Web UI; [DIAGNOSTICS.md](DIAGNOSTICS.md) examples updated.

## [2026-05-10] created | watch_run_http CLI

Added [`scripts/watch_run_http.py`](../scripts/watch_run_http.py) — stdlib HTTP poll of `GET /api/jobs/{run_id}` until terminal status; optional `--verbose` merges `GET /api/runs/{id}/stages`. Documented under [DIAGNOSTICS.md](DIAGNOSTICS.md) § Watch a run.

## [2026-05-10] created | Electron sync import and pipeline phase semantics

Added [technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md) — maps gallery **Sync from device** to Postgres **`image_phase_status`**, **`jobs`**, and product stage names; clarifies **`indexing`** (Discovery) vs later phases; notes Image Inspector vs gallery heuristics; indexed from [technical/INDEX.md](technical/INDEX.md). Companion (gallery): [06-sync-from-device-workflow.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/06-sync-from-device-workflow.md).

## [2026-05-07] created | Run options mode matrix + audit findings

Added [technical/RUN_OPTIONS_MODE_MATRIX.md](technical/RUN_OPTIONS_MODE_MATRIX.md) — four **New Run** (ScopeSelector) options vs canonical `run_mode`, flag matrix, dispatcher→runner wiring, orchestrator scope, deliberate gaps (culling queues, bird_species overwrite), Runs **Heal** tools pinned to `validate_and_repair`, and **2026-05-07 audit** (validation-repair `run_mode` fix in `modules/api.py`). Indexed from [technical/INDEX.md](technical/INDEX.md), [INDEX.md](INDEX.md), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [technical/RUNS_WALKTHROUGH.md](technical/RUNS_WALKTHROUGH.md), [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md), [technical/API_CONTRACT.md](technical/API_CONTRACT.md).

## [2026-04-25] ingested | AI agent infrastructure (doctor + bundles + hub docs)

Cross-referenced infrastructure work from the agent run summarized in `cursor_ai_coding_agent_infrastructure`: linked hub pages in [INDEX.md](INDEX.md) (new **Infra and diagnostics** section), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md) (diagnostics row), [WIKI_SCHEMA.md](WIKI_SCHEMA.md) (repo-root hub pages), [README.md](README.md) (INFRA_QUICKSTART bullet). Hub pages: [DEVELOPMENT.md](DEVELOPMENT.md), [TESTING.md](TESTING.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), [DATABASE.md](DATABASE.md), [ARCHITECTURE.md](ARCHITECTURE.md), [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md), [EXPORT_PIPELINE.md](EXPORT_PIPELINE.md), [EMBEDDINGS.md](EMBEDDINGS.md); code: `scripts/doctor.py`, `scripts/export_debug_bundle.py`, `modules/doctor_cli.py`, `modules/debug_bundle_export.py`; [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md).

## [2026-04-25] created | Feature catalog (implemented)

Added [`features/implemented/INDEX.md`](features/implemented/INDEX.md) plus nine routed summary pages (`01`–`09`) for shipped API/pipeline/UI/MCP surfaces; linked from [`README.md`](README.md), [`INDEX.md`](INDEX.md), and [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md). **image-scoring-gallery:** added parallel [`features/implemented/`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/) hub + desktop/DB/API pages and [`01-nef-raw-fallback.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/01-nef-raw-fallback.md).

## [2026-04-25] reorganize | Docs tree (gallery-aligned)

Restructured `docs/` for clearer agent navigation: `docs/plans/` → `docs/planning/` + `docs/features/planned/` (embeddings), `docs/getting-started/` + `docs/setup/` → `docs/guides/`, moved high-level architecture pages from `docs/technical/` into `docs/architecture/` (`system-overview`, `pipeline-architecture`, `project-structure`, `technical-summary`). Added [`CANONICAL_SOURCES.md`](CANONICAL_SOURCES.md) and restored [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md). Renamed import enrichment spec to [`planning/import-phase-enrichment.md`](planning/import-phase-enrichment.md). Archived legacy code-design reviews and April 2026 runs RCA/FIX plan under [`archive/reports/`](archive/reports/). Removed stub [`engineering/`](engineering/) index. Updated **image-scoring-gallery** GitHub links to new backend paths. Cursor/Claude rules: `.cursor/rules/documentation.mdc`, widened `.cursor/rules/spec-and-planning.mdc` globs, `.claude/rules/documentation.mdc`, `.agent/skills/docs-wiki/SKILL.md`, [`CLAUDE.md`](../CLAUDE.md) Documentation section.

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

**Phase 4 keywords:** Added [PHASE4_KEYWORDS_HUB.md](planning/database/PHASE4_KEYWORDS_HUB.md). Moved execution/snapshot Phase 4 docs to [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md); updated [PHASE4_STATUS_SUMMARY.md](planning/database/PHASE4_STATUS_SUMMARY.md), [PHASE4_KEYWORDS_DEPRECATION.md](planning/database/PHASE4_KEYWORDS_DEPRECATION.md), [NEXT_STEPS.md](planning/database/NEXT_STEPS.md), [PHASE4C_SOFT_DEPRECATION_PLAN.md](planning/database/PHASE4C_SOFT_DEPRECATION_PLAN.md), [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md), [planning/INDEX.md](planning/INDEX.md), [archive/INDEX.md](archive/INDEX.md), root [CLAUDE.md](../CLAUDE.md).

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

Moved loose drafts into raw archive: [gradio-serving-comparison.md](raw/gradio-serving-comparison.md), [investigation_culling_no_stacks_2026-03-15.md](raw/investigation_culling_no_stacks_2026-03-15.md). Added wiki pages [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md), [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md). Updated [INDEX.md](INDEX.md), [reports/INDEX.md](reports/INDEX.md), [ARCHITECTURE.md](architecture/system-overview.md), [CULLING_FEATURE.md](technical/CULLING_FEATURE.md), [CHANGELOG.md](../CHANGELOG.md), [raw/README.md](raw/README.md).

---

## [2026-04-13] create | Wiki Schema

Established LLM wiki system. Created [WIKI_SCHEMA.md](WIKI_SCHEMA.md) (conventions, page types, operations), this log file, and slash commands (`/wiki-ingest`, `/wiki-query`, `/wiki-lint`). Added wiki maintenance rules to CLAUDE.md. Pages touched: [WIKI_SCHEMA.md](WIKI_SCHEMA.md), [INDEX.md](INDEX.md), [README.md](README.md), [CLAUDE.md](../CLAUDE.md).
