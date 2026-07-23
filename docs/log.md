# Wiki Log

Chronological record of wiki operations. Append-only.

Parse with: `grep "^## \[" docs/log.md | tail -10`

---

## [2026-07-22] edit | MCP usage/reliability audit

Published [reports/MCP_USAGE_RELIABILITY_AUDIT_2026-07.md](reports/MCP_USAGE_RELIABILITY_AUDIT_2026-07.md): transcript heatmap (SQL-heavy, skip-search), live probe matrix, fix for compact_worker `datetime` JSON serialization crashes. Updated [reports/INDEX.md](reports/INDEX.md).

## [2026-07-21] edit | Onboard Graphify (soft agent integration)

Wired [Graphify](https://github.com/Graphify-Labs/graphify) as deferred CLI + soft rule (no alwaysApply): [graphify.mdc](../.cursor/rules/graphify.mdc), [AGENTS.md § Graphify](../AGENTS.md), install-tiers/mcp-code-intelligence/agent-search routing, `.graphifyignore`, optional `graphify-be` in mcp.example.json. Gallery twin. Artifacts gitignored under `graphify-out/`.

## [2026-07-21] edit | Framework onboard (Spec Kit + Karpathy + disciplined skills)

Cherry-picked post-0.1.0 synthet-code-framework gaps: `/clarify` `/tasks` `/analyze`, SPEC_KIT_ADOPTION, karpathy-coding rule/skill, TDD/debug/verification/skill-authoring/commit-and-push; updated [ai-workflow/README.md](../docs/ai-workflow/README.md) SDLC loop and [framework-adoption-port-manifest](../docs/raw/framework-adoption-port-manifest.md). Issues #301 / gallery #159.

## [2026-07-04] edit | Framework alignment (Cursor-first, hub layout)

Aligned with [synthet-code-framework](https://github.com/synthet/synthet-code-framework): updated [framework-adoption-port-manifest](../docs/raw/framework-adoption-port-manifest.md) (13→7 skill map, verify commands), [docs/ai-workflow/README.md](../docs/ai-workflow/README.md) Framework alignment section, `safety-and-secrets` rule, gallery infra parity coordination.

## [2026-07-04] edit | CLI hub install tiers + agent environment

Added [install-tiers.md](../.cursor/skills/agent-cli-hub/references/install-tiers.md) and [agent-environment.md](../.cursor/skills/agent-cli-hub/references/agent-environment.md) under agent-cli-hub; fixed fff **project-level** (`fff-be`) doc drift across CLI skills; extended [validate_cli_hub_skills.py](../scripts/validate_cli_hub_skills.py). Cross-repo parity with image-scoring-gallery hub layout.

## [2026-07-03] edit | Lean CLAUDE.md and refresh .cursorrules

Trimmed root [CLAUDE.md](../CLAUDE.md) from ~274 lines to lean orientation (~74 lines): corrected `modules/api/` and `modules/db/` paths, MCP keys (`is-be-mcp` / `is-be-live`), added **image-scoring-ui** sibling, delegated keyword/embedding/DB-refactor detail to planning docs. Refreshed [.cursorrules](../.cursorrules) with WSL test venv, `launch.py`, PROJECT_GUIDE link, and current MCP stack.

## [2026-07-01] ingest | synthet-code-framework adoption (agent infra)

Cherry-picked generic agent-sdlc improvements from synthet-code-framework: `validate-implementation` skill, EARS `/spec`, `/plan`, `/decompose`, enhanced `/pr-ready`, `release-bump`, `threat-modeling-agentic-tools`, `mcp-server-design`, `eval` skills. Added [ai-workflow/README.md](ai-workflow/README.md), [raw/framework-adoption-port-manifest.md](raw/framework-adoption-port-manifest.md), `scripts/sync_assistant_trees.py` (Cursor→Claude), CI validators (`check_agent_frontmatter.py`, `check_secrets.py`), workflow [agent-infra.yml](../.github/workflows/agent-infra.yml).

## [2026-07-01] ingest | Codebase size audit July + Phase 1b electron router split

Published [reports/CODEBASE_SIZE_AUDIT_2026-07.md](reports/CODEBASE_SIZE_AUDIT_2026-07.md) with raw JSON [codebase-size-audit-2026-07-01-backend.json](raw/codebase-size-audit-2026-07-01-backend.json) and [codebase-size-audit-2026-07-01-gallery.json](raw/codebase-size-audit-2026-07-01-gallery.json). Split `modules/api/routers/electron.py` into domain sub-routers (Closes [#298](https://github.com/synthet/image-scoring-backend/issues/298)). Updated [planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md](planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) Phase 1b and [raw/README.md](raw/README.md).

## [2026-07-01] ingest | Branch docs salvage (gallery docs-only branches)

Ingested gallery branch-cleanup salvage cross-ref into [reports/BRANCH_DOCS_SALVAGE_2026-07.md](reports/BRANCH_DOCS_SALVAGE_2026-07.md): docs-only branches archived and deleted on gallery; UNMERGED code branches retained. Gallery detail: [09-branch-docs-salvage-2026-07.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/reports/09-branch-docs-salvage-2026-07.md). Updated [reports/INDEX.md](reports/INDEX.md).

## [2026-06-30] ingest | Codebase size audit and refactor plan

Ingested June 2026 codebase-size audit into [reports/CODEBASE_SIZE_AUDIT_2026-06.md](reports/CODEBASE_SIZE_AUDIT_2026-06.md). Archived machine output to [raw/codebase-size-audit-2026-06-30-backend.json](raw/codebase-size-audit-2026-06-30-backend.json) and [raw/codebase-size-audit-2026-06-30-gallery.json](raw/codebase-size-audit-2026-06-30-gallery.json). Added OKF frontmatter to [planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md](planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md). Cross-linked [planning/db-refactor-decomposition.md](planning/db-refactor-decomposition.md), [planning/refactoring/REFACTORING_PLAN.md](planning/refactoring/REFACTORING_PLAN.md). Updated [reports/INDEX.md](reports/INDEX.md), [docs/INDEX.md](INDEX.md), [raw/README.md](raw/README.md).

## [2026-06-30] created — Codebase size refactor plan

Added [planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md](planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md): phased checkbox backlog from `codebase_size_audit.py` (Phases 0–10; cross-link to gallery sibling plan). Updated [planning/INDEX.md](planning/INDEX.md).

## [2026-06-30] ingest | Run "Data gaps" badges fix

Ingested the misleading "Data gaps" badge fix (run 4555) into [reports/RUN_DATA_GAP_BADGES_FIX_2026-06-30.md](reports/RUN_DATA_GAP_BADGES_FIX_2026-06-30.md): hash-based `is_image_indexing_complete` + phase-scoped post-run audit badge (`executed_phases`/`pipeline_status`), chaining preserved via `maybe_schedule_post_audit_followup`. Cross-linked [reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](reports/AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md), [reports/AUTO_DRIVE_FIX_SUMMARY.md](reports/AUTO_DRIVE_FIX_SUMMARY.md). Updated [reports/INDEX.md](reports/INDEX.md).

## [2026-06-21] ingest — Culling scripts layout and re-cluster rollout runbook

Documented script reorganization (culling backfills → `scripts/maintenance/`; re-cluster launchers under `scripts/research/clip_culling/` and `scripts/batch/`). Added **Step 9** to [guides/CULLING_EMBEDDING_BACKFILL.md](guides/CULLING_EMBEDDING_BACKFILL.md) (library-wide CLIP re-cluster rollout, checkpoint/resume, Postgres prerequisite). Updated [architecture/project-structure.md](architecture/project-structure.md) (`research/`, `study/`, agent scratch dirs). Fixed stale `python -m scripts.backfill_*` paths in [features/planned/embeddings/two-level-culling.md](features/planned/embeddings/two-level-culling.md), [technical/CULLING_ANALYTICS.md](technical/CULLING_ANALYTICS.md), [reports/CULL_DISTRIBUTION_AUDIT_2026-06.md](reports/CULL_DISTRIBUTION_AUDIT_2026-06.md). Updated [INDEX.md](INDEX.md).

## [2026-06-21] ingest | Picked advisory gap research (195193)

Ingested agent cull picked-image advisory gap research into [reports/PICKED_ADVISORY_GAP_195193_2026-06-21.md](reports/PICKED_ADVISORY_GAP_195193_2026-06-21.md). Archived forensics JSON to [raw/picked-advisory-forensics-2026-06-21.json](raw/picked-advisory-forensics-2026-06-21.json). Cross-linked [study/agent-cull-cli-matrix.md](study/agent-cull-cli-matrix.md), [specs/agent-assisted-cull-review/summary.md](specs/agent-assisted-cull-review/summary.md), [guides/setup/agent-cull-review-gemini-cli.md](guides/setup/agent-cull-review-gemini-cli.md). Updated [reports/INDEX.md](reports/INDEX.md), [INDEX.md](INDEX.md).

## [2026-06-21] created — UX/UI constitution and design-token agent skills

Three-tier UX/UI governance: shared [image-scoring-ui UX_UI_CONSTITUTION.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/UX_UI_CONSTITUTION.md); backend binding [design/UX_UI_CONSTITUTION.md](design/UX_UI_CONSTITUTION.md), `backend-frontend-ui` skill, `frontend-ui.mdc` rule; updated [design/INDEX.md](design/INDEX.md), [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md), [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) §6 (package **1.2.x**). Gallery mirror: [UX_UI_CONSTITUTION.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/design/UX_UI_CONSTITUTION.md), `gallery-ui` skill.

## [2026-06-20] updated — Playwright via is-be-mcp; multi-agent MCP examples

Playwright **`browser.*`** actions integrated into **`is-be-mcp`** (`search`/`dispatch`); removed standalone Playwright MCP from Cursor examples. Added Claude Code (`.mcp.json.example`), Antigravity (`mcp_config.example.json`), and Codex (`.codex/config.example.toml`) templates in both repos; updated [guides/setup/mcp-compact-servers.md](guides/setup/mcp-compact-servers.md) § Other agents, [`.claude/settings.json.example`](../../.claude/settings.json.example), [technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md). Gallery mirror: [05-mcp-compact-servers.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md).

## [2026-06-20] ingest — Unified compact MCP servers (Node stdio)

Documented Node `mcp-server/dist/compactIndex.js` entry for **`is-be-mcp`** and **`is-ui-mcp`**, **`sse_status`** probe, SSE proxy/degradation, and multi-root Cursor `cwd` pattern. Added [guides/setup/mcp-compact-servers.md](guides/setup/mcp-compact-servers.md); updated [technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md), [features/implemented/08-mcp-and-agents.md](features/implemented/08-mcp-and-agents.md), [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md), [guides/setup/INDEX.md](guides/setup/INDEX.md), [INDEX.md](INDEX.md). Gallery mirror: [05-mcp-compact-servers.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md).

## [2026-06-19] updated — bump LLM judge example model ID

Updated `MODEL_RECOMMENDATIONS_PIPELINES.md` Claude LLM-judge example from `claude-opus-4-7` to `claude-opus-4-8` (current Opus-tier default as of June 2026).

## [2026-06-18] ingest — Agent cull review Gemini CLI (Docker)

Added [guides/setup/agent-cull-review-gemini-cli.md](guides/setup/agent-cull-review-gemini-cli.md) (Docker/WSL/Windows `agent.command` matrix, Compose `GEMINI_CONFIG_SOURCE`, verification). Updated [specs/agent-assisted-cull-review/summary.md](specs/agent-assisted-cull-review/summary.md), [features/planned/agent-assisted-cull-review.md](features/planned/agent-assisted-cull-review.md), [guides/setup/INDEX.md](guides/setup/INDEX.md), [guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md). Gallery mirror: [04-agent-cull-review.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/04-agent-cull-review.md).

## [2026-06-16] created — OKF lint in GitHub Actions

Wired OKF bundle lint into [`.github/workflows/docs-lint.yml`](../.github/workflows/docs-lint.yml): pytest `tests/test_okf_lint.py`, full gallery bundle lint, and `scripts/ci/okf_lint_changed.py` for PR/push diffs. Gallery `test-and-contract.yml` runs full OKF lint via cloned backend. Documented in [OKF_ADOPTION.md](OKF_ADOPTION.md) and [TESTING.md](TESTING.md).

## [2026-06-16] created — OKF automated lint tooling

Added `scripts/okf_bundle.py`, `scripts/okf_lint.py`, and `scripts/wiki_lint.py`; tests in `tests/test_okf_lint.py`. Expanded [OKF_ADOPTION.md](OKF_ADOPTION.md) with official SPEC links, Vexlum deviation table, and lint commands. Updated `/wiki-lint` commands and docs-wiki skill.

## [2026-06-16] reorganized — OKF-aligned documentation metadata

Added [OKF_ADOPTION.md](OKF_ADOPTION.md) and updated [README.md](README.md), [INDEX.md](INDEX.md), [WIKI_SCHEMA.md](WIKI_SCHEMA.md), and [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md) with an incremental Open Knowledge Format profile for agent-readable docs.

## [2026-06-12] created — Agent cull spec hub + GitHub backlog (#253 / #134)

Added [specs/agent-assisted-cull-review/](specs/agent-assisted-cull-review/INDEX.md) (summary, worklog, issue map).
Filed cross-repo epics: backend [#253](https://github.com/synthet/image-scoring-backend/issues/253),
gallery [#134](https://github.com/synthet/image-scoring-gallery/issues/134) and child issues on Project board #1.
Updated [features/planned/agent-assisted-cull-review.md](features/planned/agent-assisted-cull-review.md) status and links.

## [2026-06-12] feature — Agent cull safety hardening + stale fingerprint

Dry-run apply block, unusable-alternative gate, `recommendation_ids` on apply, config shutoff on write
endpoints, CLI `max_retries`, `modules/agent_cull/fingerprint.py` for `stale_group_state` (409).
51 unit tests in `tests/test_agent_cull_*.py`.

Added operator approve/reject/rollback and apply-candidates POST endpoints under
`/api/culling/agent-review/*`; gallery IPC actions and interactive
`AgentCullReviewPanel` (still metadata-only, no delete/trash).

## [2026-06-12] created — Agent-assisted cull review planned spec and backend MVP modules

Added [features/planned/agent-assisted-cull-review.md](features/planned/agent-assisted-cull-review.md),
[technical/AGENT_CULL_REVIEW_SCHEMA.json](technical/AGENT_CULL_REVIEW_SCHEMA.json),
Alembic `0031_agent_cull_recommendations`, `modules/agent_cull/*`, `scripts/agent_cull_review.py`,
and unit tests `tests/test_agent_cull_*.py`. Metadata-only removal candidates; no file deletion in MVP.

## [2026-06-11] created — Cull distribution audit report, diagnostic SQL, pick_status sync

Added [reports/CULL_DISTRIBUTION_AUDIT_2026-06.md](reports/CULL_DISTRIBUTION_AUDIT_2026-06.md),
[`05_cull_decision_distribution.sql`](../scripts/sql/culling_analytics_diagnostics/05_cull_decision_distribution.sql),
`scripts/maintenance/backfill_pick_status_from_cull_decision.py`. `batch_update_cull_decisions` now syncs
`pick_status`; analytics `flags.auto_cull*` expose `cull_decision` stack/sub-stack stats.
Updated [CULLING_ANALYTICS.md](technical/CULLING_ANALYTICS.md), [two-level-culling.md](features/planned/embeddings/two-level-culling.md), [STACK_CULLING_REFACTOR_PLAN.md](planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md).

## [2026-06-09] chore | Dead code registry and removal (#252)

Added [reports/DEAD_CODE_REGISTRY.md](reports/DEAD_CODE_REGISTRY.md) documenting orphan Gradio tabs/assets, `remote_scoring.py`, CullingPage wrapper, gallery orphans, and archive trees removed with GitHub history citations.

## [2026-06-08] docs | Consolidated AI-memory-tool reviews into one decision doc

Merged four per-agent reviews (Claude/Codex/Cursor/Antigravity, never committed) into [ai-memory-comparison.md](ai-memory-comparison.md). Decision: keep `.agent-memory/memory.md` + native Claude `MEMORY.md` canonical; external tools are opt-in capture/search sidecars (ai-memory preferred, Icarus/Origin close, Midas for recall). Rejected the Mem0-embedded-in-app-pgvector proposal (violates separation-from-app-DB, the human-promote gate, and markdown SOtT).

## [2026-06-07] chore | Finalize compact MCP config (is-be-mcp only)

Default project MCP config is **`is-be-mcp`** + optional **`is-be-webui`**. Added [`.cursor/mcp.example.json`](../.cursor/mcp.example.json); legacy profile servers removed from templates. Track `.cursor/` rules/skills in git (operator-local `.cursor/mcp.json` gitignored).

## [2026-06-06] feature | MCP support.export_debug_bundle dispatch

First side-effecting compact action: `support.export_debug_bundle` with code allowlist, path safety, `confirmation_required`, and metadata-only response ([technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md)).

## [2026-06-06] feature | MCP search + dispatch PR1

Shipped compact backend MCP **`is-be-mcp`** with **`search`** and **`dispatch`** over a curated action registry ([technical/MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md), [mcp/action_registry.json](../mcp/action_registry.json)). Planning: [planning/mcp-search-dispatch.md](planning/mcp-search-dispatch.md).

## [2026-06-05] lint | Wiki health check (housekeeping)

Housekeeping `/wiki-lint` pass: fixed archive hub depth in [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md) (`../../planning/` → `../../../planning/` for living Phase 4 targets); added [technical/AGENT_MEMORY.md](technical/AGENT_MEMORY.md) so root [INDEX.md](INDEX.md) index target resolves (ships with agent-memory PR slice). Scanner baseline on B6: orphans=35 (mostly archive/embeddings APP specs), broken_docs=62 (archive code-pointer history deferred), isolated_active=9. Full mass-edit from pre-split stash remains in `stash@{0}` for a follow-up docs PR if needed.

## [2026-06-03] lint | Wiki health check (deferred-bucket follow-up)

Second `/wiki-lint` pass clearing the prior pass's deferred items. Fixed 10 live-page broken links (wrong relative depth in [features/planned/import-discovery-alignment.md](features/planned/import-discovery-alignment.md), [features/planned/ux-ui-implementation-plan.md](features/planned/ux-ui-implementation-plan.md), [guides/setup/ENVIRONMENTS.md](guides/setup/ENVIRONMENTS.md), [guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md); moved `MODEL_FALLBACK_MECHANISM.md` target in [technical/MODEL_SOURCE_TESTING.md](technical/MODEL_SOURCE_TESTING.md), [technical/MULTI_MODEL_SCORING.md](technical/MULTI_MODEL_SCORING.md); embeddings README→INDEX in [features/implemented/05-embeddings-and-similarity.md](features/implemented/05-embeddings-and-similarity.md)). Repointed retired root-TODO links to the GitHub Project board in two embeddings docs; fixed missing `PIPELINE_ARCHITECTURE.md` target in [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md). Corrected stale `modules/db.py`→`modules/db_legacy.py` code pointers across 7 live docs and in [CLAUDE.md](../CLAUDE.md) (db.py is now the `modules/db/` package facade; refactor status updated from "not implemented" to "in progress"). Indexed 18 orphan pages across [INDEX.md](INDEX.md), [technical/INDEX.md](technical/INDEX.md), [planning/INDEX.md](planning/INDEX.md), [project/INDEX.md](project/INDEX.md), [reports/INDEX.md](reports/INDEX.md), [reports/project-reviews/INDEX.md](reports/project-reviews/INDEX.md), [reviews/INDEX.md](reviews/INDEX.md), [testing/INDEX.md](testing/INDEX.md), and [features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md](features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md). Result: broken page links 101→75 (remainder are archive/snapshot code-pointers kept as history), orphans 27→9 (the 9 are embeddings APP specs already indexed in their non-`INDEX.md`-named hub), zero-inbound 11→0.

## [2026-06-03] lint | Wiki health check

Full `/wiki-lint`: fixed broken relative links in [architecture/system-overview.md](architecture/system-overview.md), [architecture/technical-summary.md](architecture/technical-summary.md), and [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md); corrected CUDA guide links to [guides/setup/install_cuda.md](guides/setup/install_cuda.md); updated [architecture/DB_CONNECTOR.md](architecture/DB_CONNECTOR.md) engine table for Postgres-primary; indexed [technical/AGENT_MEMORY.md](technical/AGENT_MEMORY.md), deprecations, [EXPORT_PIPELINE.md](EXPORT_PIPELINE.md), and [guides/CULLING_EMBEDDING_BACKFILL.md](guides/CULLING_EMBEDDING_BACKFILL.md) in [INDEX.md](INDEX.md), [technical/INDEX.md](technical/INDEX.md), [planning/INDEX.md](planning/INDEX.md), [guides/INDEX.md](guides/INDEX.md). Added repeatable scanner [scripts/wiki_lint_scan.py](../scripts/wiki_lint_scan.py). Archive-internal link rot deferred.

## [2026-05-31] docs | OpenAPI contract across projects

Added [technical/OPENAPI_CROSS_PROJECT.md](technical/OPENAPI_CROSS_PROJECT.md) (backend/gallery/UI ownership, sync workflow). Updated [gallery/API_TYPES.md](gallery/API_TYPES.md) to match `generate:api-types` → `api.generated.ts`. Gallery re-synced `api-contract/openapi.json` and `electron/api.generated.ts`.

## [2026-05-31] database | Drop images.scores_json column (Phase 4)

Alembic 0030; greenfield DDL and upsert/read paths gate on `_postgres_images_has_scores_json_column()`. Removed React legacy inspector section and API type fields.

## [2026-05-31] database | scores_json Phase 2–3 parity audit

Gradio gallery reads IMS for model scores (blob only for legacy timing). Added `verify_scores_json_parity.py`, `get_scores_json_parity_report()`, IMS backfill from blob, MCP `scores_json_parity` in `get_database_stats`.

## [2026-05-31] database | Deprecate images.scores_json dual-write (Phase 1)

Config `database.write_legacy_scores_json_column` (default `true`); when `false`, upserts leave `scores_json` NULL and use `image_model_scores` + aggregate columns. Salvage SQL and recalc paths retargeted off the blob. See [SCORES_JSON_COLUMN_DEPRECATION.md](planning/database/SCORES_JSON_COLUMN_DEPRECATION.md).

## [2026-05-31] feature | Image Inspector sections replace Other columns

React `/images/:id` inspector: domain sections (Culling & picks, Provenance, Indexing, Embeddings, Technical flags, Legacy & debug) instead of catch-all Other columns; `GET /api/images/{id}` adds `embeddings_present`, `indexing_metadata`, `scores_json_parsed`. See [API_CONTRACT.md](technical/API_CONTRACT.md).

## [2026-05-31] infra | Cursor follow-ups complete

Enabled `imgscore-subagent-orchestrator` in `.cursor/mcp.json`; mirrored always-on rules to `.claude/rules/` (python-wsl-webapp-env, backlog-queue, pytest-e2e-vocabulary, sdlc-core). Archived docs-restructure plan to [planning/docs-review-restructure-reindex.md](planning/docs-review-restructure-reindex.md).

## [2026-05-31] planning | Docs review restructure spec archived

Promoted Cursor plan to [planning/docs-review-restructure-reindex.md](planning/docs-review-restructure-reindex.md); removed `.cursor/plans/docs_review_restructure_reindex_a6011e62.plan.md`.

## [2026-05-31] archive | Clustering stacks ephemeral plan removed

Shipped clustering data-path fixes (`get_images_by_folder` column coverage, safe `score_general` in `clustering.py`, zero-stack logging). Deleted `.cursor/plans/fix_clustering_stacks_no_stacks.plan.md`; note added to [features/implemented/04-clustering-culling-stacks.md](features/implemented/04-clustering-culling-stacks.md).

## [2026-05-31] extended | Pipeline-wide input-size study

Extended harness to scoring (SPAQ/AVA, TOPIQ/ARNIQA @1024), keywords (`input_size_tagging_eval.py`), BLIP captions (`--track caption`), multi-track eval, and tiered policy draft [UNIFIED_INPUT_POLICY_2026-05-31.md](reports/UNIFIED_INPUT_POLICY_2026-05-31.md). Updated runbook and preliminary memo.

## [2026-05-31] infra | Cursor agent setup review

Added `.cursor/README.md`, wiki slash commands (`wiki-ingest`, `wiki-lint`, `wiki-query`), `.cursor/skills/docs-wiki`, plans policy, `imgscore-subagent-orchestrator` in `mcp.json` (disabled until sibling build). Updated `.agent/AGENT_INFRA_*`, `COMMANDS.md`, `PROJECT_GUIDE.md`.

## [2026-05-30] created | Input-size study preliminary results

Documented Phase 0 native sizes, run blockers (MobileNet embed died at 64/2126, 0 NPZ), prod/E2E DB health, and phased future plan: [reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md); artifact copy [reports/clip-culling/input-size/PRELIMINARY_RESULTS.md](../reports/clip-culling/input-size/PRELIMINARY_RESULTS.md).

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

---

## [2026-06-09] create | Lens folder normalization

Added `modules/lens_folder_name.py` (Nikon EXIF quad → canonical `…mm` folders), gallery parity in `lensFolderName.ts`, and `scripts/maintenance/merge_numeric_lens_folders.py` for legacy backup trees + manifest relPath rewrite. Refactored maintenance scripts to import shared module. Tests: `tests/test_lens_folder_name.py`.
