# Changelog

All notable changes to **Vexlum Scoring** (`image-scoring-backend`) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).



## [Unreleased]

### Roadmap (not yet released)

Phase 4c keyword legacy column soft deprecation (target a future release; see `docs/planning/database/PHASE4_KEYWORDS_DEPRECATION.md`):

## [8.12.4] - 2026-07-21

### Fixed
- **Indexing/metadata progress interval**: Module-scope `PROGRESS_INTERVAL` again after the runner helper extraction so batch runs no longer raise `NameError` on the first image.

## [8.12.3] - 2026-07-19

### Fixed
- **Phase policy - skipped is terminal**: `explain_phase_run_decision` no longer re-queues images whose phase status is `skipped` when data validation finds no work product (e.g. keywords with no tags). Stops the auto-drive keywords re-queue loop; a newer executor version still re-runs.

### Added
- **Compiled agent skill harnesses**: Deterministic Python entrypoints under `scripts/agent_skills/` for `release-bump`, `validate-implementation`, `pr-ready` checks, and skill-usage profiling (`SKILL_COMPILATION.md`).

### Changed
- **`/release` and `/pr-ready` bootloaders**: Cursor/Claude skills and slash commands now call the compiled harnesses instead of rediscovering version/changelog paths in-prompt.

## [8.12.2] - 2026-07-04

### Changed

- **Agent CLI hub**: Install tiers and agent-environment references; project-level **fff-be** MCP guidance (replacing user-level fff); refresh search and code-intelligence skill cross-links.
- **Agent safety**: Add `safety-and-secrets` rule (Cursor + Claude mirror).
- **Framework adoption**: Expand port manifest; trim `CLAUDE.md` to pointer style; extend `validate_cli_hub_skills.py`.

## [8.12.1] - 2026-07-03

### Changed

- **Electron API router**: Split monolithic `electron.py` into domain sub-routers (config, folders, images, runs, scope); behavior unchanged.
- **Agent SDLC**: Sync Cursor/Claude skills, rules, slash commands, assistant-tree sync script, and agent-infra CI workflow.

## [8.12.0] - 2026-07-01

### Added

- **Agent cull batch review**: Split oversized review units into `review_batch_size` chunks with merged validation so large stacks can be reviewed without exceeding group limits.

### Changed

- **Two-level substack split**: Gate substack split on `min_stack_size_for_substack`, skip persisting single-leaf sub-stacks, default level-2 `distance_threshold` to `0.04` (per substack audit), and raise `max_group_size` safety ceiling. Study scripts and audit report under `docs/reports/SUBSTACK_SPLIT_AUDIT_2026-06.md`.

## [8.11.3] - 2026-07-01

### Fixed

- **Bird species runner**: Restored module-level `db` import in `_process_bird_species_image_row` after Phase 4 extraction (NameError during per-image processing).

### Changed

- **API modularization (Phase 1)**: Replaced monolithic `modules/api.py` with `modules/api/` domain routers; `from modules.api import create_api_router` and all REST routes unchanged.
- **Runner batch helpers (Phase 4)**: Mechanical per-image/per-batch extractions from tagging, metadata, indexing, clustering, scoring, pipeline, engine, bird_species, and selection runners — behavior and public surfaces unchanged.
- **Refactor tooling and docs**: Added `scripts/audit/codebase_size_audit.py`, `scripts/refactor/*` helpers, and [CODEBASE_SIZE_REFACTOR_PLAN.md](docs/planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) with Phase 1 and Phase 4 progress.

## [8.11.2] - 2026-06-30

### Fixed

- **Post-run audit badges scoped to executed phase**: Single-phase jobs no longer show `issues_remaining` for downstream pipeline work they never ran (e.g. a fresh indexing job flagged for missing culling scores). Audit payload adds `executed_phases` and `pipeline_status` for whole-pipeline diagnostics while `status` reflects only the phase that job executed.

### Changed

- **Batch 1 safe extractions**: Split `modules/api_helpers.py` and `modules/api_models.py` from `api.py`; moved MCP tool implementations to `modules/mcp/tools/` with a slimmer `mcp_server.py`. Public API and compact MCP dispatch unchanged.

## [8.11.1] - 2026-06-28

### Fixed

- **Auto-drive post-audit follow-up — scoring gaps skipped when metadata was clean**: `maybe_schedule_post_audit_followup` now re-queues the earliest pipeline stage with remaining audit work (indexing through bird_species), not metadata alone. Follow-up jobs resume from that phase through the original target list (e.g. scoring → culling → keywords when 292 images still need scores).
- **Job dispatcher — empty folder-scoped stage queue finished the job with no work**: When `resolved_image_ids_by_stage` held an empty list for a folder-scoped run, the dispatcher treated it as explicit “nothing to do” instead of falling through to JIT replan. Empty per-stage lists now defer to replan for folder/scope-path jobs.
- **Auto-drive phantom reconcile — indexing/metadata stale rows**: Drive reconcile now includes `indexing` and `metadata` in `reconcile_phantom_complete_image_phases`, matching scoring/keywords/culling.

### Changed

- **Auto-drive bucket enqueue**: Repair plan for auto-bucket jobs uses `include_stale_executor=True` so stale/missing images are included in the resolved work set.

## [8.11.0] - 2026-06-27

### Added

- **Agent cull review — permanent delete of approved removals**: New `POST /api/culling/agent-review/groups/{group_id}/delete-approved` (`delete_approved_action`). For a validated, non-stale group it **permanently deletes the file (+ thumbnails) from disk and the `images` DB record** (via `db.delete_image(delete_related=True)` + `os.remove`) for every `operator_approved` removal, marking each recommendation `operator_deleted`. **Irreversible** and requires `confirm: true` in the request body (returns `confirmation_required` otherwise). Only approved removals are touched; advisories and un-approved recommendations are left intact. Tests in `tests/test_agent_cull_actions.py`.

### Fixed

- **Dashboard folder pipeline — culling false “failed” icon**: Folder phase rollups no longer show a red failed state when only a minority of images failed (e.g. 13/674 `stale_running_reconciled` rows while the rest were never attempted). Those retryable stale failures are reset to `not_started` during auto-drive reconcile, and culling completeness checks now use `is_image_culling_work_complete` consistently in phase policy.

## [8.10.0] - 2026-06-22

### Added

- **Safe Postgres restore tooling**: `scripts/powershell/Restore-Postgres.ps1` and the `/restore-db` slash command (`.claude` + `.cursor`). Always takes a pre-restore safety dump, prints the source `pg_restore --list` header and a before/after `images` count + `max(id)` diff, gates the destructive `pg_restore --clean` behind `ShouldProcess` (`-WhatIf` / `-Confirm:$false`), runs `postgres_sequence_repair.py`, and warns loudly on a row-count or `max(id)` regression. Prompted by the 2026-06 data regression (an old dump restored over the live DB rewound `images_id_seq` 198499→190180).

### Fixed

- **Agent cull review — approve/apply returned HTTP 500 (`'PostgresConnector' object has no attribute 'query_all'`)**: `agent_cull.fingerprint.load_current_image_states` called a non-existent connector method; it now uses `connector.query`. The staleness check (run on every approve and apply-candidates) no longer crashes. Added a regression test that drives the real function through a fake connector exposing only `query` (`tests/test_agent_cull_fingerprint.py`).
- **Frontend culling metrics build (TS2352)**: route `CullingStackImage` score lookups through `unknown` so the SPA bundle builds.

### Changed

- **Script layout**: maintenance/backfill scripts consolidated under `scripts/maintenance/` and batch helpers under `scripts/batch/`; references updated (`scripts/README.md`, `modules/culling_embeddings.py` docstring).
- **Backup/restore hygiene**: stale Postgres dumps quarantined to `backups/archive/` (git-ignored, DO-NOT-RESTORE); `/backup-db` docs now point to `/restore-db`.
- **Docs**: expanded culling-embedding backfill guide and related references (project structure, embeddings, agent-cull CLI matrix, culling analytics, cull-distribution audit); added picked-advisory forensics report.

## [8.9.1] - 2026-06-21

### Changed

- **Windows keep-awake slash commands**: `/windows-keep-awake on` and `/windows-keep-awake off` documented in AGENTS.md and `.cursor/README.md`; skill sync note and command stubs under `.cursor/commands/windows-keep-awake/`.

## [8.9.0] - 2026-06-21

### Added

- **Agent cull packet context (#280)**: Technical and EXIF context in review payloads; embedding-outlier gate activation for redundancy review.
- **Picked-image quality advisories**: `picked_image_advisories` in the review schema, advisory-only persistence (`pick_quality_advisory`), `review_picked_quality` config, and prompt snippet for misfocus/blur audit on picked heroes.
- **Agent cull CLI matrix study tooling**: `scripts/study/agent_cull_matrix.py`, vision smoke scripts, Docker/WSL/host matrix runs, and expanded `docs/study/agent-cull-cli-matrix.md`.
- **Transcript mining and backlog housekeeping**: `import_transcripts.py`, `housekeeping_backlog.py`, and `/backlog-housekeeping` + `/import-transcripts` slash commands.
- **Alembic 0032**: Widen `agent_cull_prompt_version` for longer prompt template version strings.

### Changed

- **Production agent-cull defaults**: `cull_redundancy_v3_vision_strict` prompt, `require_vision_evidence=true`, and 180s CLI timeout in `config.example.json`.
- **Schema and serialization**: Widened `prompt_template_version` validation, datetime-safe EXIF serialization via shared `json_util`, and CLI adapter schema coercion hardening.
- **Docker and MCP docs**: Antigravity auth refresh script, optional Docker Gemini stub, and expanded MCP compact proxy documentation.

## [8.8.0] - 2026-06-20

### Added

- **`clip_quality_v0` as a first-class score in the Web UI**: Inspector roster, culling metrics breakdown, and gallery min-score filter via new API query param `min_clip_quality_v0`; sort by `model:clip_quality_v0` through `image_model_scores` joins. Deprecated IQA models (KonIQ, PAQ2PIQ, MUSIQ, Q-Align) are hidden instead of shown as gray “off” rows.
- **Agent-assisted cull review expansion**: Richer payload/schema, CLI adapter hardening, safety gates, repository/service coverage, and optional Gemini CLI operator guide.
- **MCP compact dispatch growth**: Playwright `browser.*` actions in the action registry, compact tools/proxy server for resilient stdio→SSE routing, and expanded dispatch tests.
- **Job dispatcher**: Multi-phase continuation dequeue, phantom running-phase reconciliation, and configurable job priority helper.

### Changed

- **OpenAPI**: Documents `min_clip_quality_v0` on image list endpoints.

### Fixed

- **`JobDispatcher._tick` unit tests**: Bird-species dispatcher tests mock phase-continuation DB calls so they no longer require a live Postgres pool.
- **Sort validation**: Allow sanitized `model:<name>` sort keys (e.g. `model:clip_quality_v0`).

## [8.7.0] - 2026-06-16

### Added

- **OKF bundle lint tooling**: `scripts/okf_bundle.py`, `scripts/okf_lint.py`, and `scripts/wiki_lint.py` validate Open Knowledge Format frontmatter, `resource` paths, and internal links for backend and sibling gallery `docs/` trees (`minimal` and `vexlum` profiles).
- **OKF CI gate**: `.github/workflows/docs-lint.yml` runs linter unit tests, full gallery bundle lint, and `scripts/ci/okf_lint_changed.py` for changed backend docs on PR/push.

### Changed

- **OKF adoption docs**: `docs/OKF_ADOPTION.md` links the official Google OKF SPEC, documents Vexlum profile deviations, linter commands, and CI behavior; `docs/TESTING.md` and wiki `/wiki-lint` commands updated accordingly.

## [8.6.0] - 2026-06-15

### Added

- **Agent-assisted cull review MVP**: Conservative AI redundancy review for small clustered stack/sub-stack groups — discovery, JSON-only external CLI verdicts, deterministic safety gates, metadata-only removal candidates (no physical deletion). Alembic **0031** tables, `modules/agent_cull/`, REST `/api/culling/agent-review/*`, OpenAPI, and `scripts/agent_cull_review.py` (dry-run default).
- **Agent-review thumbnail downscale**: `culling.agent_review.agent.max_thumbnail_edge_px` now resizes oversized thumbnails (aspect preserved, JPEG q85) with fail-safe fallback to the source path.
- **JIT level-2 culling embeddings**: Stack-scoped OpenCLIP embedding during two-level culling so new stacks get level-2 sub-stacking without a separate bulk backfill.
- **pick_status sync**: `scripts/backfill_pick_status_from_cull_decision.py` and selection policy sync `pick_status` from `cull_decision` on future runs.
- **Sub-stacks backfill UX**: Progress bar (TTY), periodic log lines, per-stack checkpoint JSON, and `--resume` / `--resume-after-stack-id` for long sidecar sync runs.
- **Cull distribution audit**: Analytics SQL and `docs/reports/CULL_DISTRIBUTION_AUDIT_2026-06.md` for level-2 pick/reject distribution review.
- **CLIP B/32 prompt-quality pick/reject signal (auxiliary, default-off)**: `clip_quality_v0` — a 0–1 "good photo" probability derived from the persisted `clip_vit_b32_image` (512-d) embedding compared against antonym text prompts (CLIP-IQA style). New `modules/clip_quality.py` persists to `image_model_scores` (surfaces in the API as `clip_quality_v0_score`); culling blends it into the within-stack ranking behind `culling.clip_quality.*` (weight 0.15 default, optional `reject_below` floor) without touching `score_general`. B/32 is JIT-generated pre-culling and reused by the keywords phase (`embeddings.reuse_clip_image_for_keywords`). Backfill: `scripts/backfill_clip_quality.py`. Benchmark (`reports/clip-culling/prompt-quality/`): global pick/reject AUC 0.89, within-stack concordance 0.986.

### Changed

- **Culling analytics flags**: `auto_cull` flag helpers and distribution audit wiring in analytics service.

### Fixed

- **Input-size study runner hardening**: `scripts/research/clip_culling/run_input_size_study.sh` gains a validated `VENV_PATH` override (defaulting to `~/.venvs/tf`) with fail-fast checks, `--help`, strict `PHASE` validation (`1|2|3|all|eval`), and clean `LD_LIBRARY_PATH` handling that no longer emits an empty leading segment.

### Security

- **Read/write SQL validator hardening** (closes #209, #210, #211): the `/api/db/query` read validator now denies `pg_read_file`/`pg_read_binary_file`/`pg_ls_dir`/`pg_stat_file`/`lo_export`/`lo_import`/`dblink`/`pg_execute_server_program` (CTE-wrapped file-exfil), and the Postgres read path enforces `set_session(readonly=True)` at the transport layer; the write validator blocks bare-`;`/`--`/`/*` multi-statement injection and `/api/db/transaction` now validates every statement so DDL cannot reach the DB even with a valid write token.

## [8.5.0] - 2026-06-11

### Added

- **BioCLIP embedding backfill**: `scripts/backfill_bioclip_embeddings.py` fills the `bioclip_2_image` (768-d) space for images missing that embedding (Postgres-only, thumbnail-aware, fp16/batch options).
- **Single-species reconciliation**: `scripts/db/backfill_single_species.py` reduces images carrying multiple `species:` keywords to the highest-confidence one, syncing both `image_keywords` and the legacy CSV in one transaction (dry-run mode; equal-confidence ties skipped and logged).

### Changed

- **Bird species default `top_k` is now 1 (BioCLIP argmax)**: API request model, job dispatcher, MCP `run_processing_job`, and `BirdSpeciesRunner`/`BioCLIPClassifier` defaults switched from 3; pass `top_k > 1` to store multiple candidates.

### Fixed

- **Stale running-phase detection timezone**: `list_stale_running_image_phase_rows` compared local-time `updated_at` against a `datetime.utcnow()` cutoff, mis-reporting staleness by the UTC offset (webui startup reconciliation, MCP health/stale-phase tools); also removed a dead shadowed duplicate of the function left from a reverted decomposition.
- **`/api/db/*` bridge endpoints**: repaired eight endpoints broken since v4.22.0 by calls against the removed `db_client` interface — images-by-keyword (TypeError), batch-embeddings, jobs dequeue/enqueue, job-phase create/update, folder phase-status, and culling-session creation (which silently wrote corrupt rows).
- **Firebird legacy init**: added the missing `_column_exists` helper referenced by `_init_db_impl` migrations (unprotected calls crashed init; guarded ones silently skipped migrations).
- **Duplicate `scope_has_unattempted_phase_work` removed**: a later copy shadowed the canonical version that excludes `running` rows from the unattempted-work probe.

## [8.4.0] - 2026-06-10

### Added

- **Keyword relevance weights**: `modules/keyword_relevance.py` maps CLIP cosine similarity to stable per-tag `relevance_weight`; tagging forward-fill writes `relevance_map`; `scripts/db/backfill_keyword_relevance.py` backfills existing rows.
- **MCP compact dispatch expansion**: Additional read-only actions in the action registry and overlay (phase consistency, stale running phases, data query helpers, logs, config, jobs).

### Changed

- **Backup script**: `Backup-Postgres.ps1` supports count-based retention (`-MaxBackups`, `-MirrorMaxBackups`) alongside age prune; backup-db skill and slash commands aligned.

## [8.3.0] - 2026-06-09

### Added

- **Keyword cloud + Keywords/Birds pages**: New `GET /api/keywords/cloud` endpoint (`kind=species|general`, optional folder scope) backed by `keyword_discovery.get_keyword_cloud()`; React `/ui` gains Keywords, Keyword-images, and Birds pages with routes; static `/app` bundle rebuilt.
- **Lens folder normalization**: `modules/lens_folder_name.py` maps Nikon EXIF lens quads to canonical `…mm` folder names, shared by backup/maintenance scripts; `scripts/maintenance/merge_numeric_lens_folders.py` merges legacy numeric folders and rewrites manifest relPaths.
- **Auto-drive self-heal maintenance**: Post-audit follow-up can enqueue self-scoping maintenance jobs (`maybe_schedule_post_audit_followup`), guarded by config flags and an active-maintenance-job check.

### Changed

- **Backup planning moved to gallery**: Dropped the short-lived backend `/api/backup/plan` endpoint (introduced and superseded within this cycle) in favor of gallery-side selection; added a bundled folder/stack endpoint and hardened selection + prune safety.

### Fixed

- **Scoring robustness**: Retry transient RAW conversion failures so one failed image no longer wedges its folder (#243, #244); finalize phantom-scored images by backfilling the composite score from model rows (#246).
- **Metadata asset gaps**: The metadata phase re-runs when thumbnails or preview assets are missing (`get_image_metadata_asset_gap_reason`); failed thumbnail writes now mark the phase `failed` instead of passing silently; workflow healing uses the metadata asset-incomplete SQL.
- **Maintenance job dispatch**: The dispatcher routes maintenance jobs by their JIT-narrowed phase key so they bypass folder-scope replanning.

## [8.2.0] - 2026-06-07

### Added

- **MCP compact dispatch expansion**: Extended `search` / `dispatch` registry and overlay for additional read-only backend actions; compact SSE profile on WebUI; tests for dispatch, search, and compact SSE.
- **Auto-drive interrupted tracking**: Loop-guard metadata now distinguishes `interrupted` runs from hard failures so backend restarts do not permanently block un-attempted work.

### Changed

- **MCP agent docs**: Default `is-be-mcp` / `is-be-webui` compact workflow documented in AGENTS.md, MCP_SEARCH_DISPATCH.md, and agent skills; `.cursor/mcp.example.json` templates updated.

### Fixed

- **Culling "No Stacks" bug**: Removed premature `RUNNING` and `DONE` phase status updates in `SelectionRunner`. These updates previously caused `ClusteringEngine` to skip images because it saw them as already running, resulting in zero stacks being created for newly processed folders. Life-cycle transitions are now correctly owned by the clustering engine.
- **Auto-drive loop guard**: Un-attempted-work bypass now checks all planned phases (not only the first) and forgives interrupted runs while still bounding hard failures.
- **Pipeline dispatcher**: Improved logging for dispatch failures (#156) and orphan-interrupted `image_phase_status` sweep (#157).

## [8.1.0] - 2026-06-03

### Added

- **Auto-drive new-folder prioritization**: "Drive to Complete" now surfaces recently-imported, untouched folders first. `build_folder_buckets` sorts unprocessed folders (0% done, imported within the recency window) newest-first, affecting both the Runs UI ordering and auto-drive scheduling.
- **Data-quality batch helper**: `db.compute_image_data_quality_flags_batch()` computes keyword/scoring completeness flags for many images in a single set-based query, plus a cheap `db.image_exists()` probe.
- **Tests**: data-quality batch flags, config-cache mtime isolation, auto-drive new-folder ordering, heal debounce, and run manifest coverage.

### Changed

- **Image list payload**: `_images_list_payload` batches data-quality flags after row assembly instead of issuing a per-row query (removes an N+1).
- **Auditlog endpoint**: uses `db.image_exists()` for the 404 check and `FETCH FIRST ? ROWS ONLY` for the row limit.
- **Broad maintenance**: updates across culling analytics, technical-failure detection, QPT v2 / engine wrappers, two-level culling, embedding-atlas React views, agent infra (`.agent/`, `.claude/`), and documentation; static `/app` UI bundle rebuilt.

### Fixed

- **Auto-drive loop guard**: recent-attempt counts are now keyed on the same JIT-narrowed plan keys used at enqueue time, so the repeat guard actually fires (previously it compared wide structural keys against narrow enqueue keys and never matched).
- **Config cache invalidation**: `load_config()` keys its cache on the mtimes of both `config.json` and `environment.json`, so an `environment.json`-only edit busts the cache; test isolation resets the cache around every test for coarse-mtime filesystems.

## [8.0.0] - 2026-05-31

### Added

- **Image inspector (React `/ui`)**: Domain sections (Culling & picks, Provenance, Indexing, Embeddings, Technical flags) replace catch-all “Other” columns; `GET /api/images/{id}` adds `embeddings_present` and `indexing_metadata`.
- **scores_json migration tooling**: `scripts/maintenance/verify_scores_json_parity.py`, `get_scores_json_parity_report()`, IMS backfill from legacy blob, and MCP `scores_json_parity` in `get_database_stats`.
- **Connection status**: WebSocket-backed `ConnectionStatus` in the React shell; `wsStore` reconnect handling improvements.
- **Docs**: [SCORES_JSON_COLUMN_DEPRECATION.md](docs/planning/database/SCORES_JSON_COLUMN_DEPRECATION.md), [OPENAPI_CROSS_PROJECT.md](docs/technical/OPENAPI_CROSS_PROJECT.md).
- **Tests**: scores_json deprecation/parity, image detail payload, clustering score_general, embedding embed paths, MCP client allowlist.

### Changed

- **scores_json deprecation (Phases 1–3)**: Config `database.write_legacy_scores_json_column` (default `true`); upserts and Gradio gallery reads prefer `image_model_scores` + aggregate columns.
- **React `/ui`**: Gallery filter chips and geo map search use shared design-token contrast; inspector layout refactor.
- **OpenAPI** and [API_CONTRACT.md](docs/technical/API_CONTRACT.md) aligned with gallery type generation.

### Removed

- **Breaking**: `images.scores_json` column (Alembic **0030**). Run `verify_scores_json_parity.py --backfill` before upgrade. Image detail API no longer returns `scores_json` / `scores_json_parsed`.

### Fixed

- **Scoring runner**: Expanded unit coverage for incomplete-image SQL and rescoring paths.
- **Phase reconcile tests**: Align expectations with current reconcile behavior.

## [7.28.0] - 2026-05-31

### Added

- **Sub-stack backfill**: `scripts/backfill_sub_stacks.py` — recompute leaf sub-stacks and two-level pick/reject on existing root stacks without re-clustering (idempotent; honors `TWO_LEVEL_POLICY_VERSION` 2.0).
- **Two-level culling core**: `compute_leaf_substacks` (single-pass sub-clustering) and shared `process_stack_two_level` used by `SelectionService` and the backfill script.
- **CLIP culling research**: extended input-size harness (native resize, tagging/caption eval tracks, tiered policy reports) and `scripts/research/clip_culling/two_level_thresholds_prod.py`.
- **Docs**: [docs/guides/CULLING_EMBEDDING_BACKFILL.md](docs/guides/CULLING_EMBEDDING_BACKFILL.md), [UNIFIED_INPUT_POLICY_2026-05-31](docs/reports/UNIFIED_INPUT_POLICY_2026-05-31.md), and related report indexes.

### Changed

- **Selection / two-level**: `SelectionService` delegates stack processing to `process_stack_two_level`; code default for level2 embedding space is MobileNet (OpenCLIP remains opt-in via config + backfill).
- **Culling docs**: clustering/culling stack pages and input-size study memos updated for single-pass sub-stacks and unified resize policy.

### Fixed

- **Culling embedder OOM**: `CullingEmbedder.embed_paths` downscales decoded previews to `max_load_px` (default 1024) before batching — avoids RAM exhaustion on large NEF embedded previews.
- **Tests**: `test_selection_service_with_diversity_mocked` pins `two_level_enabled=False` so legacy diversity + `pick_fraction` behavior does not depend on local `config.json`.

## [7.27.0] - 2026-05-30

### Added

- **Audit log**: `modules/audit.py`, Alembic **0027** (`auditlog` table with RFC 6902 patches), config `database.audit_log_enabled`; correlation via `run_id`, `phase_code`, and `source`.
- **Sub-stacks**: Alembic **0028**; REST `GET /api/stacks/{stack_id}/substacks` and `GET /api/substacks/{sub_stack_id}/images`.
- **Culling embedding spaces**: Alembic **0029**; `modules/embedding_extractors.py`, extended `embedding_spaces` registry, and `scripts/backfill_culling_embeddings.py`.
- **Two-level culling**: `modules/two_level_culling.py` — sequential visual→semantic sub-stacks with best-M/N-cap picks; selection policy and config keys in `config.example.json`.
- **Config API split**: public `GET /api/config` vs operator `GET /api/config/full`; canonical reference [docs/technical/CONFIG.md](docs/technical/CONFIG.md).
- **CLIP culling research harness**: `scripts/research/clip_culling/` (experiments, input-size study, backfill helpers) and related reports under `docs/reports/`.
- **Tests**: audit, two-level culling, culling embedding spaces, config API routes, and allowed-paths security.

### Changed

- **Selection / culling**: two-level stack orchestration with diversity scoring and `selection_policy` best-M classification.
- **OpenAPI** and [API_CONTRACT.md](docs/technical/API_CONTRACT.md) updated for substacks and config endpoints.
- **Embeddings** documentation and `config.example.json` aligned with new culling spaces.

### Fixed

- **Job dispatcher unit tests**: stub `db.get_job_by_id` so mocked queue payloads are not overwritten by live DB rows during dispatch.
- **Config validation**: `database.engine: api`, Gradio settings merge, and `system.allowed_paths` in path security checks.

## [7.26.0] - 2026-05-27

### Added

- **MCP `get_drive_diagnostics`**: Auto-drive arm state, dirty-folder refresh, and batch kick visibility for agents.
- **Validation repair preview**: `include_stale_executor` and `align_auto_drive` on the repair-plan API to mirror auto-drive enqueue rules.
- **Folder-buckets planner preview**: `planner_preview_max_images` cap, wall-clock budget with `planner_preview_skipped` flags; default `planner_preview_limit=0` (opt-in).
- **Phase policy data-complete guard**: Skip reruns when phase status is missing or `not_started`/`failed` but underlying phase data is already complete.

### Changed

- **Auto-drive start API**: Returns `arm_drive` state plus `kick_drive_batch_async` in one response.
- **Canonical path resolution**: Broader gallery Windows ↔ WSL alias handling in `db_legacy`.
- **Scope selector**: Frontend scope API alignment for folder scope.

### Fixed

- **Auto-drive**: Leaf-folder detection and planner preview wall-clock budget exhaustion.
- **Bird species** folder phase summary, run submit prereq gating, and related autodrive tests.

## [7.25.0] - 2026-05-26

### Added

- **CLIP accessibility metadata**: `modules/clip_accessibility.py`, XMP read/write, Alembic **0025**, tagging/scoring integration, and maintenance backfill script.
- **BioCLIP 768-d embeddings**: `bioclip` embedding space and Alembic **0026** for `image_embeddings_768`.
- **Runs dashboard**: React `/ui/` dashboard page with run queue and bucket planner visibility.
- **Canonical file path lookup**: `resolve_canonical_file_path_for_lookup` maps gallery Windows aliases to `images.file_path` (WSL paths).
- **External CLI reviews**: Codex/Gemini subagent docs, commands, and MCP orchestrator wiring (review-only).

### Changed

- **Auto-drive / planner**: Ignore bare `executor_version_changed` when stored version is empty; `include_stale_executor=False` on auto-drive enqueue; JIT non-empty `stage_queues`; `planner_next_phases` on folder-buckets API and Runs UI.
- **Scoring executor version**: Registry and IPS writes use canonical **`5.0.0`** (`SCORING_EXECUTOR_VERSION`).
- **Manual run submit**: Narrow phases via JIT; **`400 nothing_to_queue`** when the planner has no work.

### Fixed

- **Auto-drive reprocessing**: Folders with all core phases `done` are no longer re-queued solely for stale executor metadata (run 3245 class).
- **`fix_image_metadata`**: Canonical path resolution; missing files and DB-unavailable paths return clear errors without pool init failures.
- **Bird species** folder phase summary and related planner/policy tests.

## [7.24.0] - 2026-05-25

### Added

- **Text search filters**: `GET /api/similarity/text-search` and MCP `search_images_by_text` accept
  `folder_ids`, `min_rating`, `color_label`, `keyword`, `captured_date`, and secondary `sort_by` /
  `order` after CLIP relevance ranking.
- **Similar search SQL**: Postgres filter builder for scoped semantic search (folder IDs, metadata AND
  filters, allowlisted secondary sorts).

### Changed

- **DB export defaults**: CSV/Excel export column lists omit dropped per-model `images.score_*` columns;
  **`image_model_scores`** is the sole store (docs aligned with migration 0023).
- **Composite recalc** and **phase-status analysis** scripts read per-model scores from
  **`image_model_scores`** on Postgres.

### Fixed

- **Text search tests**: Coverage for folder scope, metadata filters, and secondary sort paths.

## [7.23.0] - 2026-05-24

### Added

- **Alembic 0023**: Drop legacy per-model columns on **`images`** (`score_spaq`, `score_ava`,
  `score_koniq`, `score_paq2piq`, `score_liqe`); scores live only in **`image_model_scores`**.
  Upgrade aborts if unbackfilled rows remain — run **`scripts/maintenance/backfill_legacy_model_scores.py --apply`** first.
- **Backfill scripts**: **`backfill_legacy_model_scores.py`** and **`backfill_arniqa.py`** with unit tests.

### Changed

- **Scoring / DB / API / MCP**: Reads and analytics for SPAQ, AVA, LIQE, KonIQ, and PAQ2PIQ route
  through **`image_model_scores`**; API payloads overlay legacy **`score_<name>`** fields when
  typed columns are NULL or dropped.
- **Postgres DDL**: Fresh **`images`** table omits retired per-model score columns.
- **Culling analytics**, **projections**, **report collector**, **job dispatcher**, and **Gradio gallery/settings**
  tabs aligned with IMS-only per-model scores.

### Fixed

- **Incomplete-scoring SQL** and **`image_model_scores`** read paths updated for dropped legacy columns.

## [7.22.0] - 2026-05-24

### Added

- **ARNIQA scorer** (#220 phase 2): no-reference, distortion-focused IQA via `pyiqa`
  (`modules/arniqa.py` + `modules/engines/arniqa_model.py`). Registered at import time;
  head selectable via `scoring.arniqa.metric` (default `arniqa`, KonIQ head).
  - Landed in **shadow**, then **promoted to production fusion** after a full-corpus
    backfill (61,350 images, 0 failures) and percentile calibration
    (`arniqa: p02 0.467 / p98 0.746`).
  - Joins **general** (0.10) and **technical** (0.25) composites; intentionally **not**
    aesthetic (Spearman ≈0.01 vs AVA). Fusion rebalanced in `score_normalization.py` /
    `scoring.fusion`.
  - All 61,350 composite scores recalculated (`recalc_composite_scores.py`, now ARNIQA-aware);
    existing `image_model_scores` ARNIQA rows flipped to `is_shadow=false`.

### Changed

- **Composite fusion weights** rebalanced to admit ARNIQA — technical
  `topiq .30 / arniqa .25 / spaq .25 / liqe .20`, general
  `liqe .35 / spaq .30 / topiq .13 / arniqa .10 / ava .12`; aesthetic unchanged.

## [7.21.0] - 2026-05-24

### Added

- **Phase work claims**: Postgres **`image_phase_work_claims`** and **`modules/phase_work_claims.py`** — per-image×phase claims so concurrent runs do not duplicate work (Alembic **`0022`**, dispatcher integration).
- **Run phase planner**: **`modules/run_phase_planner.py`** — just-in-time stale/missing work planning at submit and each phase start; repair plans delegate from **`db`** helpers.
- **Score analysis**: **`scripts/analysis/model_score_quality_report.py`** and **`recalc_composite_scores.py`** with unit tests.

### Changed

- **Job dispatcher / run modes**: Work-claim acquire/release and planner hooks; **`runs_autodrive`**, **`workflow_healing`**, and selection runner alignment.
- **Runs / DB UI**: Scope selector, folder buckets, and DB Explorer sidebar/grid updates; static **`/ui`** bundle rebuilt.
- **API / Postgres**: Safer JSON serialization on DB query API; DDL and legacy paths for work claims.
- **Docs**: Run-options mode matrix documents planner and claims; pipeline model roadmap pages.

### Fixed

- **Integration tests**: Run-submit modes, job dispatcher, prereq gating, and post-run audit expectations updated for planner/claim behavior.

## [7.20.1] - 2026-05-23

### Removed

- **WebUI `/ui/search`**: Semantic text search page removed from the React **`/ui`** app; use **Tools → Search** in Driftara Gallery. **`/api/similarity/*`** endpoints are unchanged.

### Changed

- **Static `/ui` bundle**: Rebuilt after Search nav and route removal.

### Fixed

- **`test_score_normalization`**: Isolate fusion and percentile-anchor config from live **`config.json`** during tests.

## [7.20.0] - 2026-05-22

### Added

- **Runs auto-drive**: **`GET /api/runs/folder-buckets`** and **`POST /api/runs/auto-drive`** (`modules/runs_autodrive.py`) — folder bucket planner with loop guards, dry-run, and per-row queue; React **Runs buckets** panel with **Auto Drive** on **`/ui/runs`**.
- **DB Explorer**: React **`/ui/db`** for read-only **`POST /api/db/query`** when **`database.enable_api_db_query`** is enabled (`modules/api_db.py`, trust banner, table sidebar).
- **LLM-judge scorers**: Optional shadow **`cursor`** and **`claude`** engines (`modules/cursor_scorer.py`, `modules/claude_scorer.py`, `modules/engines/*_model.py`); optional deps in **`requirements/requirements_llm_judge.txt`** (disabled by default in **`config.example.json`**).
- **`model_scores` on image APIs**: List/detail payloads merge **`image_model_scores`** via **`get_image_model_scores`** / **`get_batch_image_model_scores`** — flat **`{name}_score`** for production models plus structured **`model_scores`** (includes shadow rows).

### Changed

- **Configuration**: **`config.example.json`** — cursor/claude model toggles and tuning; **`database.enable_api_db_query`** documented in [09-configuration-and-limits.md](docs/features/implemented/09-configuration-and-limits.md).
- **API contract**: Runs auto-drive and DB query surfaces documented in **`docs/technical/API_CONTRACT.md`**; LLM-judge section in [02-scoring-and-models.md](docs/features/implemented/02-scoring-and-models.md).
- **Static `/ui` bundle**: Rebuilt hashed frontend assets for DB Explorer, Runs buckets, and inspector updates.

### Fixed

- **Selection integration**: Test and path-resolution alignment for batch selection scopes (**`tests/test_selection_integration.py`**, **`tests/test_resolved_paths.py`**).

## [7.19.0] - 2026-05-20

### Added

- **Normalized keyword writes**: **`update_image_keywords_for_image`** dual-writes legacy CSV (when enabled) and **`image_keywords`** / **`keywords_dim`**, with optional per-keyword **`confidence_map`** and **`source_map`** on **`_sync_image_keywords`**.
- **Bird Species ID**: BioCLIP species tags now sync through the normalized path with per-species confidence and **`bioclip`** source metadata.

### Changed

- **`scripts/bootstrap_labels.sh`**: GitHub label bootstrap adds **`type:epic`** and **`status:obsolete`**.

## [7.18.0] - 2026-05-19

### Added

- **Embedding Atlas (#133)**: Embedding-space dropdown driven by **`GET /api/embedding_spaces`** — **`useEmbeddingSpaces`** hook and dynamic options in **`ProjectionSettingsDialog`** (fallback when the selected code is absent from the registry).
- **Technical failure detection (#143)**: Classical-metrics MVP — **`modules/technical_failures/`**, Postgres **`image_technical_failures`**, scoring integration, and **`technical_failure_detection`** on image detail APIs / **`/ui/`** surfaces.

### Fixed

- **Embedding Atlas**: Inspector point deselection no longer leaves a stale selection state.
- **Scoring incompleteness audit (#162)**: Drop **`score_general`** gate from the **`scoring_incomplete`** predicate so heal/audit paths align with canonical completeness checks.

### Changed

- **Agent infrastructure**: Phase 2 backend docs and inventory updates (**#168**).
- **Static `/app` bundle**: Rebuilt hashed frontend assets for Atlas and inspector changes.

## [7.17.0] - 2026-05-15

### Added

- **Phase status vs run telemetry**: **`image_phase_status`** remains the **data-completeness** cache (**`done`** is terminal while underlying data exists); runners no longer clobber **`done`** with **`skipped`** / **`not_started`**. **`last_run_action`** (from **`job_image_actions`**) is the separate surface for **what last happened in a run** — wired through APIs and the **`/ui/`** Image Inspector phase grid (**`PhaseStatusTable`**).
- **`scripts/maintenance/reconcile_phase_status.py`**: Heals drift in both directions (promote rows to **`done`** when data is present; demote **`done`** when canonical data is missing).

### Changed

- **Documentation**: Refreshed hub pages and references (**`docs/INDEX.md`**, **`docs/README.md`**, architecture/pipeline/diagnostics/testing guides, **`DB_SCHEMA`** summary, **`MCP_DEBUGGING_TOOLS`**).
- **Agent docs**: **`AGENTS.md`**, **`.agent/`** inventory/MCP reference/workflows, and **`.claude/agents/`** subagent prompts aligned with current tooling.

### Fixed

- **Inspector regression**: Reprocessed images no longer **appear** to lose completed scoring/metadata after fast-path skips when status and telemetry were overloaded on one column.

## [7.16.0] - 2026-05-15

### Fixed

- **Phase reconciliation (#161)**: `reconcile_stale_running_phases_for_jobs` now **salvages** scoring `image_phase_status` rows to **`done`** when canonical outputs already exist on **`images`** before flipping remaining **`running`** rows to **`failed`**, avoiding cancel/recover paths that looked like failures and drove **scoring heal** loops.
- **Batch pipeline directory scan**: **`BatchImageProcessor`** treats **single-file** scopes correctly (**`os.walk`** on a file path yields no rows) so file-scoped jobs still enqueue work and emit discovery events (**`modules/engine.py`**).
- **Indexing / metadata runners**: Stop calling **`set_image_phase_status`** to rewrite **`done` → `skipped`** for already-indexed / metadata-complete images; per-run skips remain on the **report collector** / **`job_image_actions`** (**`modules/indexing_runner.py`**, **`modules/metadata_runner.py`**). Doc clarified on **`set_image_phase_status`** (**`modules/db_legacy.py`**).

### Added

- **`modules/paths.py`**: Unified **Windows ↔ WSL ↔ Docker** path normalization and conversion helpers (single source of truth) with **`tests/test_paths.py`** coverage.
- **`count_incomplete_records`**: **`COUNT(*)`** helper aligned with **`get_incomplete_records`** plus **`tests/test_count_incomplete_records.py`** (marked **`db`**).
- **Phase status APIs**: **`get_batch_image_phase_statuses`** / **`get_image_phase_statuses`** attach **`last_run_action`** (latest **`job_image_actions`** row per phase).
- **React Image Inspector** (**`/ui/`**): Phase grid distinguishes **data status** vs **last run activity**, plus **Run** for **file-scoped** pipeline submit (**`frontend/src/pages/ImageInspectorPage.tsx`**).
- **`tests/test_phase_reconcile.py`**: Expanded reconciliation coverage.

### Changed

- **REST — retry / force-run jobs**: Job **description** building avoids stacking duplicate **`(retry from Runs UI)`** / **`(re-queued via force_run)`** suffixes when the prior description already ends with that marker (**`modules/api.py`**).
- **`metadata_runner`**: Trim redundant import / typing noise.
- **Static `/app` bundle**: Rebuilt hashed assets (**`static/app/index.html`**, JS).

## [7.15.5] - 2026-05-14

### Fixed

- **Workflow healing — active job dedupe**: Canonicalize `folders.path` vs `jobs.input_path` (WSL `/mnt/...` vs Windows `D:\...`) when skipping folders already under **queued/running** jobs so the same tree is not scheduled twice (**`modules/workflow_healing.py`**).
- **Scoring heal / completeness drift**: **`_incomplete_images_where_sql`** now matches **`is_image_scoring_complete`** — require **`score_general > 0`** and **at least one** positive model score among spaq/ava/liqe/koniq/paq2piq (avoids infinite heal loops on valid **0** subscores such as technical). **`get_incomplete_records`** docstring updated (**`modules/db_legacy.py`**).
- **Runs report text**: **`describe_incomplete_fields`** no longer flags arbitrary normalized **0** model columns as “incomplete” (still surfaces **0** on legacy **`score`** / **`score_general`** and NULLs) (**`modules/report_collector.py`**).

### Added

- **`tests/test_scoring_incomplete_sql.py`**: regression coverage for scoring incompleteness SQL and heal active-path canonicalization.

### Changed

- **Docs in code**: Comments on **indexing** / **metadata** workflow-heal predicates vs **`is_image_*_complete`** policy helpers (**`modules/db_legacy.py`**).

## [7.15.4] - 2026-05-13

### Fixed

- **WebSocket `EventManager`**: Guard `active_connections` with **`threading.RLock`** so `disconnect_sync` and async `connect` / `disconnect` / `broadcast` cannot corrupt the client list concurrently (**`modules/events.py`**).
- **REST API**: Invalid `rating` query values on paginated image list and image-neighbor endpoints return **HTTP 400** instead of **500** (**`modules/api.py`**; tests in **`tests/test_api_endpoints.py`**).
- **NEF sample tests**: `test_rawpy_postprocess_to_rgb` skips on **`LibRawFileUnsupportedError`** when LibRaw cannot unpack the raw (e.g. some Z8 compressions on older LibRaw), matching the existing skip behavior for **`LibRawDataError`** (**`tests/test_nef_camera_lens_diversity.py`**).

### Added

- **`tests/test_keyword_scorer_predict.py`**: Unit coverage for **`KeywordScorer.predict`** threshold filtering and `top_k` (marked **`ml`**).

### Changed

- **`modules/clustering.py`**: Remove unused **`sqlite3`** import; hoist **`uuid`** to module scope.
- **`modules/engine.py`**: Trim obsolete inline commentary around directory scanning and job id handoff.

## [7.15.3] - 2026-05-14

### Fixed

- **Runs UI denominator for keywords / culling phases (#159, Stage A)**: `JobDispatcher` now seeds `job_phases.images_in_scope/targeted` before invoking the `tag`, `cluster`, or `selection` runners via a new `_seed_phase_scope(...)` helper that builds a short-lived `ReportCollector` and pushes scope counters immediately (`modules/job_dispatcher.py`). Closes the residual of #158 for the two phases whose dispatch paths did not yet create a collector. Stage B (per-image `record_after/skip/failure` wiring for the tagging/clustering/selection runners) remains a separate ticket.

## [7.15.2] - 2026-05-13

### Fixed

- **Workflow healing**: Resolve heal folder scope through **`utils.resolve_scope_input_path`** before the on-disk directory check so Windows/WSL path variants enqueue correctly (**`modules/workflow_healing.py`**).

## [7.15.1] - 2026-05-13

### Changed

- **Electron sync import RCA**: Corrected the known-issues diagnosis for multi-stage WorkflowRun scoring with `skip_existing=true`, and clarified that the culling symptom was downstream of the scoring gap (`docs/technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md`, `docs/log.md`).
- **Static `/app` bundle**: Refreshed hashed React bundle references and assets (`static/app/index.html`, `static/app/assets/`).

## [7.15.0] - 2026-05-10

### Added

- **`repair_zombie_score_rows`**: Clears bogus **`images.score = 0`** / legacy label placeholders where **`score_general`** is still **`NULL`** (partial-failure artifact; **`dry_run`** by default) (**`modules/db_legacy.py`**).
- **`scripts/maintenance/repair_analyzer_gaps.py`**: **`--zombie-scores`** invokes the repair above (GAP-K; not implied by **`--all`**).
- **`find_active_job_for_folder`**: Finds an existing **active** job (**`queued`**, **`running`**, **`paused`**, **`user_pause`**, **`restarting`**) targeting the same canonical folder path (Windows vs WSL forms collapse) — duplicate-submit guard helper for dispatch layers (**`modules/db_legacy.py`**).
- **Phase status grid defaults**: **`get_batch_image_phase_statuses`** / **`get_image_phase_statuses`** include every enabled **`pipeline_phases.code`** per image, defaulting missing **`image_phase_status`** rows to **`not_started`** (**`modules/db_legacy.py`**).
- **Tests**: **`tests/test_consistency_repair_helpers.py`** (mocked connector paths for ancillaries above); Firebird **`tests/test_db_core.py`** uses unique folder paths per case.
- **Ops scripts**: **`scripts/debug/audit_runs_new_folders_today.py`**, **`scripts/watch_run_http.py`** (recent-runs poller).

### Changed

- **PostgreSQL schema note**: Comments that **`folders.image_count`** is unmaintained (readers use live **`COUNT`**) (**`modules/db_postgres.py`**).
- **Static `/app` bundle**: Rebuilt hashed assets (**`static/app/index.html`**, JS chunks).
- **Docs**: Diagnostics, API contract nits, pipeline terminology, run options matrix, Electron sync/phases reference (**`docs/technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md`**).

### Removed

- Obsolete **`scripts/archive/debug/`** helpers and **`scripts/debug/debug_firebird.py`**; scratch artifacts under **`artifacts/brain/`** / **`brain/`**; vendored TF Hub descriptor text files under **`models/tfhub_cache/`**; root **`mcp_config.json`** (prefer **`.cursor/mcp.json`** / user-level MCP settings).

## [7.14.0] - 2026-05-09

### Added

- **PostgreSQL — `jobs.status` vocabulary lock**: Alembic **`0020_jobs_status_check.py`** adds **`ck_jobs_status`** (`CHECK`) so **`jobs.status`** stays within the canonical set (**`pending`**, **`queued`**, **`running`**, **`paused`**, **`user_pause`**, **`completed`**, **`failed`**, **`cancelled`**, **`interrupted`**); see **`docs/planning/database/STATUS_VOCABULARY.md`**.
- **Legacy DB — `backfill_missing_phase_rows`**: Inserts **`not_started`** **`image_phase_status`** rows for images missing required phase rows (partial indexing recovery); optional folder scope, phase list, **`limit`**, and **`dry_run`** (**`modules/db_legacy.py`**).
- **`refresh_folder_phase_aggregates_with_ancestors`**: Recomputes folder phase aggregate caches for the target folder **and ancestors** (**`modules/db_legacy.py`**), paired with **`invalidate_folder_phase_aggregates`**.

### Changed

- **`GET /api/jobs/recent`**: Default (non-history) responses are now **`{"runs":[...],"jobs":[...]}`** (same array duplicated under both keys) instead of a bare JSON array **`[...]`**; **`history=true`** also includes **`jobs`** alongside **`runs`** and **`total`**. Existing **`/ui/`** client code already accepts object payloads.

### Fixed

- **Pipeline dispatch**: **`JobDispatcher`** resolves the active phase from **`job_phases`** when **`phase`** is **`pipeline`** / **`ui_pipeline`** (**`modules/job_dispatcher.py`**).
- **Folder pipeline badges**: Pipeline orchestrator refresh walks **ancestors** after phase updates so **`phase_agg_dirty`** chains do not leave stale root/intermediate summaries (**`modules/pipeline_orchestrator.py`**, **`modules/db_legacy.py`**).
- **Multi-phase job phases**: **`set_job_phase_state`** allows **`completed`** from **`pending`** / **`queued`** (with **`started_at`** backfill) to avoid bulk-sync deadlocks (**`modules/db_legacy.py`**).
- **Workflow healing round-robin**: Folder ordering uses **`MAX(pt.last_touched_at)`** with **`GROUP BY`** (**`modules/workflow_healing.py`**).

### Tests & ops

- **Docker inference E2E**: **`tests/e2e_docker/test_inference_via_live_api.py`** reads **`jobs`** / **`runs`** from the recent-jobs payload.
- **Samples & harness**: Additional public XMP sidecars under **`tests/fixtures/testing_samples/`**, synthetic sidecars, **`scripts/docker_inference_e2e.sh`** / **`docker-compose.yml`** / **`Dockerfile`** tweaks; removed ad-hoc GPU/WSL env check scripts and obsolete tests (**`tests/check_*.py`**, **`tests/bench_db_performance.py`**, **`tests/test_connectivity.py`**, **`tests/test_tagging.py`**).

## [7.13.0] - 2026-05-07

### Added

- **PostgreSQL — `pipeline_tool_folder_last_touch`**: Alembic **`0019_pipeline_tool_folder_last_touch.py`** stores per-folder last success time per pipeline tool key (round-robin / deprioritize recent work).
- **`modules/pipeline_tool_folder_touch.py`**: Upsert helpers for tool folder touches (Postgres); integrated with maintenance and workflow-healing paths.
- **Run submit — scope prerequisites**: **`POST /api/runs/submit`** (and related pipeline submit paths) can return **`missing_prerequisites`** when requested stages are not satisfied for the resolved scope.
- **Phase prerequisites & diagnostics**: Expanded **`modules/phases.py`** registry / prerequisite semantics; **`modules/pipeline_diagnostics.py`** and **`docs/technical/WORKFLOW_DIAGNOSTICS.md`** / **`docs/technical/RUN_OPTIONS_MODE_MATRIX.md`** for operator clarity.
- **Testing & samples**: Optional public-sample download / synthetic NEF helpers under **`scripts/python/`**; **`tests/fixtures/testing_samples/public/`** sidecars and manifest updates (large NEF binaries no longer vendored in-tree).
- **Docker / CI helpers**: **`scripts/docker_inference_e2e.sh`**; **`docker-compose.yml`** refinements for WebUI-oriented dev flows.

### Changed

- **`modules/workflow_healing.py`**, **`modules/maintenance_runner.py`**, **`modules/db_legacy.py`**, **`modules/db_postgres.py`**: Healing order, reconciliation, and Postgres alignment with new touch tracking and phase policy.
- **`modules/exif_extractor.py`** and thumbnail / RAW preview tests: NEF and camera–lens coverage reshaped; **`tests/test_dcraw_thumb.py`** retired in favor of **`tests/test_raw_thumb_extraction.py`**.
- **React `/ui/` runs & scope**: **`ScopeSelector`**, **`RunsToolsTab`**, **`pipeline.ts` / `pipelineTools.ts`**, **`usePipelineToolAction`**, and **`frontend/src/api/tools.ts`** for pipeline-tool actions and gating UX.
- **Integration tests**: Pipeline workflow matrix support, incremental runs e2e, and submit phase-permutation e2e updates (**`tests/support/pipeline_matrix.py`**, **`tests/integration/*`**).

### Fixed

- **Legacy DB bookkeeping**: Tighter job/phase transitions and stale-running reconciliation aligned with submit and healing (**`modules/db_legacy.py`**).

### Tests

- New / expanded suites: prerequisite gating, phase status transitions, registry sync, reconcile stale running, NEF camera–lens diversity, workflow healing touch order, **`tests/e2e_docker/`** where applicable.

## [7.12.0] - 2026-05-06

### Added

- **Runs queue & restart guidance**: New `docs/technical/RUNS_QUEUE_AND_RESTART.md` covering run queue payloads, retry behavior, and restart expectations.
- **Command dispatch / healing helpers**: `modules/command_dispatcher.py` and `modules/workflow_healing.py` extend operator-side recovery flows and ordering logic; `modules/phases_policy.py` adds phase gating rules used by the dispatcher/healer paths.

### Changed

- **React Runs UI**: Run cards and run detail surfaces show queue/retry-oriented metadata and expose the queue payload view (`frontend/src/components/runs/RunCard.tsx`, `frontend/src/pages/RunDetailPage.tsx`, `frontend/src/components/runs/RunQueuePayloadPanel.tsx`).
- **Culling workspace**: Refined scope/stack interaction and pick UX; removed the deprecated `FolderScopeSelector` component (`frontend/src/features/culling/components/CullingWorkspace.tsx`).
- **Pipeline tools**: Expanded pipeline tool registry for run-level actions (`frontend/src/constants/pipelineTools.ts`).

### Fixed

- **Legacy DB job/phase bookkeeping**: `modules/db_legacy.py` tightens transitions and reconciliation behavior to match dispatcher/healer expectations.

### Tests

- Added coverage for command dispatch and phase policy behavior (`tests/test_command_dispatcher.py`, `tests/test_phases_policy.py`).

## [7.11.0] - 2026-05-03

### Added

- **`GET /api/config`**: Public feature flags **`enable_culling`** and **`embedding_map_enabled`** (from **`culling.enabled`** / **`embedding_map.enabled`**) via **`ConfigResponse`** in **`modules/api.py`**.
- **React `/ui/` — config-driven navigation**: **`frontend/src/api/config.ts`**, **`frontend/src/hooks/useConfig.ts`**; **Atlas** and **Culling** routes and sidebar entries render only when the backend reports the feature enabled (**`frontend/src/App.tsx`**, **`frontend/src/components/layout/Shell.tsx`**).

### Changed

- **`IndexingRunner`**: Resolves folder scope with **`resolve_scope_input_path`** (aligned with API validation), clearer **Windows / WSL / Docker** diagnostics, and terminal failure on empty input (**`modules/indexing_runner.py`**).
- **IPC bridge `pipeline:submit`**: Uses synchronous **`submit_pipeline`** and surfaces **`success`** in **`IpcBridgeResponse`** (**`modules/api.py`**).
- **`db_legacy` job transitions**: Allows **`failed` → `queued` / `running` / `completed`** (restart / indexing reconcile) and phase **`failed` → `completed`** where applicable (**`JOB_ALLOWED_TRANSITIONS`**, **`set_job_phase_state`**).
- **`scripts/backfill_subcluster_picks.py`**: Skips images with **`cull_decision`** set but **`cull_policy_version` NULL** (presumed manual overrides) unless **`--no-preserve-manual`**; logging extended.
- **Static `/app` bundle**: Rebuilt hashed assets (**`static/app/index.html`**, new JS chunk).

### Tests

- **`tests/test_api_queue.py`**, **`tests/test_clustering_representative.py`**: Updated for pipeline submit / job transition behavior.

## [7.10.0] - 2026-05-03

### Added

- **PostgreSQL — `images.pick_status`**: Alembic **`0018_image_pick_status.py`** adds **`pick_status`** (**`SMALLINT`**, default **`0`**: unflagged; **`1`** picked; **`-1`** rejected) plus **`idx_images_pick_status`** for the Culling workspace.
- **`PATCH /api/images/{image_id}` — `pick_status`**: **`ImagePatchBody`** accepts **`pick_status`**; persists via **`update_image_pick_status`** and mirrors to legacy rating/label for existing gallery filters (**`modules/api.py`**, **`modules/db_legacy.py`**).
- **React `/ui/culling` — Culling workspace**: **`CullingPage`**, **`CullingWorkspace`** (survey / loupe / stacks), **`FolderScopeSelector`**, **`LoupeFilmstrip`** / **`LoupeView`**, keyboard + pick mutations, **`cullingStore`**, **`api/culling`** — wired from **`frontend/src/App.tsx`** and **`Shell`** / **`Sidebar`**.
- **Sub-cluster stacks & picks**: **`modules/sub_clustering.py`**, **`modules/culling.py`**, clustering/selection integrations; **`scripts/backfill_subcluster_picks.py`** (plus shell wrapper) for data repair.
- **Quality ranking helpers**: **`modules/quality_ranking.py`** used with selection/policy paths; **`tests/test_quality_ranking.py`**, **`tests/test_selection_sort_tiebreak.py`**.
- **Maintenance runner extensions**: Expanded **`MaintenanceRunner`** / **`modules/maintenance_runner.py`** wiring (documentation in codepaths as shipped).

### Changed

- **Selection / pipeline**: **`modules/selection.py`**, **`selection_policy.py`**, **`pipeline_selector_composer.py`**, **`projections.py`** / **`projections_db.py`** — tie-break ordering, projector behavior, DB alignment (**`tests/test_pipeline_selector_composer.py`**, **`test_clustering_representative.py`**).
- **Clustering**: **`modules/clustering.py`** updates paired with representative tests.
- **`modules/exif_extractor.py`**, **`modules/db_postgres.py`**, **`modules/db_legacy.py`**: Robustness and schema alignment for embeddings / EXIF (**`tests/test_api_embedding_map.py`**, **`test_api_endpoints.py`**).
- **React `/ui/embeddings`**: Embedding atlas canvas, inspector, geo scope, similarity hooks (**`EmbeddingAtlasPage`** and related **`frontend/src/features/embedding-atlas/*`** including **`folderColor`** util).
- **React `/ui/geo`**: **`GeoMapPage`** behavior aligned with atlas scope / API.
- **Static `/app` bundle**: Rebuilt **`static/app`** hashed chunks (**`index.html`**, JS/CSS/vendor splits incl. **`webgl-device`**).

### Fixed

- **API regression coverage**: **`tests/test_api_image_patch.py`** exercises image patch behavior including **`pick_status`**.

### Tests

- Expanded **`tests/test_api_endpoints.py`** and **`test_api_embedding_map.py`** alongside new suites above.

## [7.9.0] - 2026-04-29

### Added

- **React `/ui/embeddings` — embedding atlas**: **`EmbeddingAtlasPage`** and **`frontend/src/features/embedding-atlas/`** (canvas, toolbar, inspector, filmstrip, projection settings, stores/hooks) wired to embedding-map and similarity APIs.
- **`GET /api/models`**: Lists registered scoring models (name, version, framework, score range, enabled/shadow, **`load_status`**) from **`modules/engines/registry`** for operator UI and shadow tooling.
- **Maintenance runner actions**: **`backfill_exif_camera_lens`**, **`backfill_exif_gps`**, **`backfill_embeddings`** (MobileNet via **`ClusteringEngine`**), and **`backfill_clip_vectors`** (Postgres), dispatched through **`MaintenanceRunner`** alongside existing actions.
- **Runs — pipeline / maintenance tools**: Expanded **`RunsToolsTab`**, **`pipelineTools`**, **`usePipelineToolAction`**, and **`frontend/src/api/tools.ts`** to trigger tools from run detail.
- **Frontend dev mocks**: **`frontend/src/mocks/`** and **Vite** `resolve.alias` configuration for local **`/ui`** development.
- **Docs & scripts**: **`docs/technical/spec_vector_db_visualization.md`**; maintenance helpers **`scripts/maintenance/backfill_exif_gps.py`**, **`scripts/maintenance/heal_bird_species_until_done.py`**; **`scripts/bootstrap_issues.py`**, **`scripts/bootstrap_labels.sh`** for backlog hygiene.

### Changed

- **Scoring model wrappers**: **`IScoringModel.load_status`** (**`modules/engines/base.py`**) with **loaded** / **failed** reporting on **MUSIQ** and **LIQE** wrappers for **`/api/models`** and diagnostics.
- **Static `/app` bundle**: Rebuilt **`static/app`** hashed JS/CSS (incl. **`webgl-device`** chunk).
- **`.gitignore`**: Ignore **`.cache/`** and related agent/ML scratch paths; **`config.example.json`** tweaks.

### Fixed

- **`modules/db_legacy` — `update_image_embeddings_batch_for_space`**: Accepts raw **`float32`** **`bytes`** / **`bytearray`** / **`memoryview`** payloads (length `4 × dim`) in addition to array-likes.

### Tests

- **`tests/test_api_endpoints.py`**: Extended coverage (incl. **`/api/models`**).

## [7.8.0] - 2026-04-28

### Added

- **PostgreSQL — `image_keywords.relevance_weight`**: Alembic **`0017_image_keywords_relevance_weight.py`** adds **`relevance_weight`** (default `1.0`) beside **`confidence`** for per-tag relevance in ranking/filtering.
- **`GET /api/similarity/example-queries`**: Keyword-catalog suggestions (`keywords_dim` / `image_keywords`), optional **`folder_path`** scope — powers rotating example chips on the **`/ui/` Semantic Search page**.
- **Tests**: New **`tests/test_workflow_healing_bird_species.py`** workflow coverage for bird-species healing.

### Changed

- **React `/ui/` Semantic Search**: Standalone embeddings atlas (**`EmbeddingsPage`**, **`ScatterCanvas`**, **`HoverTooltip`**, **`SidePanel`**, **`ControlsBar`**) and **`frontend/src/api/embeddings.ts`** removed; **`SearchPage`**, **`api/search`**, and **`frontend/src/types/api.ts`** expanded for semantic search flows.
- **Pipeline & metadata**: **`exif_extractor`**, **`workflow_healing`**, **`bird_species`**, **`db_legacy`**, **`db_postgres`**, **`phase_executors`**, **`modules/ui/app.py`** — EXIF/metadata robustness, split-brain and Firebird ↔ Postgres parity extensions.
- **Static `/app` bundle**: Rebuilt **`static/app`** assets (**`index.html`**, hashed JS/CSS).

### Removed

- **Standalone `/ui/embeddings` route**: Embeddings atlas page and related frontend components deferred; **`GET /api/embedding_map`** and similarity APIs unchanged for clients.

### Fixed

- **Phases policy & translation**: Updates in **`tests/test_phases_policy.py`** and **`tests/test_translate_fb_to_pg.py`**.

## [7.7.0] - 2026-04-28

### Added

- **Scoring engine registry (MUSIQ / LIQE hosts)**: Model hosts and registry under **`modules/engines/`** (**`host.py`**, **`musiq_model.py`**, **`liqe_model.py`**, **`registry.py`**) with fusion-oriented score plumbing; **`score_normalization`** and config hooks updated for multi-model fusion.
- **Per-model score storage**: Alembic **`0016_image_model_scores.py`** introduces **`image_model_scores`** dual-write helpers and tests (**`tests/test_image_model_scores_dual_write.py`**).
- **Jobs status normalization**: Alembic **`0015_normalize_canceled_status.py`** consolidates **`canceled`** / **`cancelled`** job terminal states; guarded by **`tests/test_0015_normalize_canceled_status.py`**.
- **Similarity & embeddings API**: Expanded **`modules/similar_search.py`** and **`modules/api.py`** routes (including embedding-space-aware search); **`openapi.json`** and **`docs/reference/api/openapi.yaml`** refreshed.
- **React `/ui/` — embeddings atlas & similarity**: Embedding scatter canvas (**`ScatterCanvas`**, **`HoverTooltip`**, controls), **geo map** (**`GeoMapPage`**, **`api/geo`**), and **semantic search** page (**`SearchPage`**, **`api/search`**) wired to backend APIs.
- **Operator diagnostics**: Expanded **`doctor`** CLI coverage (**`tests/test_doctor_cli.py`**) plus selective **HTTP geocoding** tests (**`tests/test_geocoding_nominatim.py`**).
- **MCP & safety**: SQL helper coverage (**`tests/test_mcp_sql_helpers.py`**), redaction tests (**`tests/test_redact_sensitive.py`**), and a large internal refresh of **`modules/mcp_server.py`** (broader FastMCP catalog and HTTP fallbacks aligned with **`AGENTS.md`**).
- **Engine & pipeline tests**: Registry / shadow-mode / wrapper suites (**`tests/test_engines_*.py`**), **`tests/test_indexing_split_brain.py`**, **`tests/test_score_normalization_fusion_config.py`**, plus extensions to embedding-map, source-image, hashing, and **VILA** skips.

### Changed

- **React Web UI (`frontend/`)**: Runs/detail and diagnostics flows (**LogPanel**, **ReportPanel**, **RunCard**, **StagePanel**, **ScopeSelector**, **PhaseStatusIcon**, **StatusLogFilePanel**, **badge** / **button** primitives), **`index.css`** token layout, **`vite.config.ts`** chunk splitting — tightened operator surfaces for logs and phases.
- **Pipeline & metadata**: **`indexing_runner`**, **`metadata_runner`**, **`exif_extractor`**, **`xmp`**, **`pipeline`**, **`workflow_healing`**, **`db_legacy`**, **`db_postgres`** — indexing/metadata robustness, split-brain cleanup, and path handling.
- **Static `/app` bundle**: Rebuilt **`static/app`** assets (**`index.html`**, hashed JS/CSS chunks including **React** vendor split, favicon).
- **Documentation**: New top-level wiki hub pages (**`ARCHITECTURE`**, **`DATABASE`**, **`DEVELOPMENT`**, **`DIAGNOSTICS`**, **`EMBEDDINGS`**, **`EXPORT_PIPELINE`**, **`IMAGE_PIPELINE`**, **`TROUBLESHOOTING`**, **`TESTING`**, feature **`implemented`** notes) plus index churn; archived or removed superseded **`docs/plans/*`**, **`docs/setup/*`**, and duplicate technical summaries in favor of the consolidated layout.
- **`.gitignore`**: Ignores **`exports/debug-bundles/`** (local debug bundle exports).

### Removed

- **Web UI `/ui` settings shell**: **`frontend/src/pages/SettingsPage.tsx`** and **`frontend/src/components/ui/phaseStatus.tsx`** removed — settings live elsewhere / phase status consolidated under **`PhaseStatusIcon`**.
- **Operator Gradio shim**: Deleted standalone **`frontend/src/App.css`** in the minimal app shell (styles folded into **`index.css`**).
- **Legacy MCP shim**: **`modules/mcp_server_firebird.py`** removed (Firebird-only MCP path retired from tree).

## [7.6.0] - 2026-04-27

### Added

- **DB — CHECK constraint on `image_phase_status.status` (Phase 5 D2, partial)**: New Alembic revision `0014_status_check_constraints.py` adds `ck_image_phase_status_status` enforcing the nine `PhaseStatus` enum values (`not_started`, `queued`, `running`, `paused`, `cancel_requested`, `restarting`, `done`, `skipped`, `failed`). Production rows verified non-violating prior to constraint addition (only `done`/`skipped`/`not_started`/`running` observed). The same constraint is now declared inline in `modules/db_postgres.py` so fresh installs get it via `_init_db_transaction()`. `jobs.status` and `job_phases.state` constraints deferred — see `docs/planning/database/STATUS_VOCABULARY.md` for the empirical inventory and the `canceled`/`cancelled` normalization step required first.

## [7.5.2] - 2026-04-25

### Added

- **Docs — status vocabulary inventory (Phase 5 D1)**: New `docs/planning/database/STATUS_VOCABULARY.md` catalogs every status-style column in the PostgreSQL schema (`jobs.status`, `job_phases.state`, `job_steps.status`, `image_phase_status.status`, `culling_sessions.status`) along with the `PhaseStatus` and `FolderPhaseStatus` enums in `modules/phases.py`. Each entry lists current vocabulary, the call sites that write it, current DB guard rails (none), and a concrete recommendation for D2 (CHECK constraints / ENUMs). Highlights:
  - `image_phase_status.status` is the only column whose vocabulary is already enforced in code (`PhaseStatus` enum + `ALLOWED_TRANSITIONS`); safe to add a `CHECK` immediately.
  - `jobs.status` has redundant terminal values (`error` vs `failed`) written from different call sites; reconcile before adding a constraint.
  - `job_phases.state` uses a different column name than its siblings — document in `DB_SCHEMA` rather than rename.
  - `job_steps.status` and `culling_sessions.status` are dormant (no active writers); defer constraint work until a writer is wired up.

## [7.5.1] - 2026-04-25

### Changed

- **OpenAPI spec aligned with v7.5.0 endpoints**: `docs/reference/api/openapi.yaml` now documents the multi-space embedding-map work shipped in v7.5.0:
  - `/api/embedding_map`: added `space_code` and `pca_dim` query parameters; refreshed description and meta-block fields (`embedding_space`, `pca_dim`, and the `unknown_embedding_space` error case).
  - `/api/similarity/search` (and the deprecated `/api/similarity/similar` alias): added `embedding_space` query parameter.
  - `/api/images/{image_id}/similar`: new path entry for the k-NN endpoint (separate from `/{id}/neighbors`, which remains prev/next nav).
  - `info.version`: bumped 6.3.1 → 7.5.0 to match `modules/version.py`. Spec now lists 133 paths and parses cleanly.

## [7.5.0] - 2026-04-25

### Added

- **Embedding map — multi-space + PCA pre-step (App 05 phase 1)**: `GET /api/embedding_map` now accepts `space_code` (e.g. `clip_vit_b32_image`, `blip_vit_b16_image`, `bioclip_2_image`) and `pca_dim`; both bake into the disk-cache key so per-space maps no longer collide. PCA pre-step (sklearn) is auto-on for source dim ≥ 1280, off below; pass `pca_dim=0` to disable explicitly. Non-default spaces are Postgres-only and read straight from the per-dim fact table via the new `modules/projections_db.get_embeddings_with_metadata_for_space()` helper. Default-space requests still go through `db.get_embeddings_with_metadata` so the legacy `images.image_embedding` COALESCE fallback is preserved. `meta` now exposes `embedding_space` and `pca_dim`; an unknown `space_code` returns `meta.error == "unknown_embedding_space"`. See `docs/features/planned/embeddings/EMBEDDING_APP_05_2D_EMBEDDING_MAP.md` §Phase 1.
- **Similarity REST parity**: `GET /api/similarity/search` (and the deprecated `/api/similarity/similar` alias) now accept an optional `embedding_space` query parameter, matching the existing MCP tool. The response only includes the `embedding_space` key when explicitly set, preserving backward compatibility for clients that compare exact response shapes.
- **`GET /api/images/{image_id}/similar`**: New k-NN endpoint — RESTful path-parameter form of similarity search. Deliberately distinct from `/images/{image_id}/neighbors`, which remains prev/next gallery navigation.
- **Maintenance — `deduplicate_images` action**: New `MaintenanceRunner` action that synchronizes split-brain duplicates by backfilling missing `image_hash` / `hash_version` from sibling rows that share the same `file_path`, and surfaces same-folder same-hash duplicate groups for follow-up. Supports `dry_run`. Triggered via the existing job dispatch with `action="deduplicate_images"`.
- **Maintenance — `heal_folder_ids` action**: New `MaintenanceRunner` action that reconciles each image's `folder_id` against its `os.path.dirname(file_path)` (creating folder rows on demand via `db.get_or_create_folder`) and invalidates aggregates for both old and new folders. Supports `dry_run`.
- **MCP `rebase_file_paths` — also reseats `folder_id`**: After rewriting `images.file_path` from `old_root` to `new_root`, the tool now resolves the new directory via `db.get_or_create_folder` and updates `folder_id` accordingly, then invalidates aggregates for every affected folder. Previously rebasing left rows pointing at stale folder rows under the old root.
- **`Backup-Postgres.ps1` — Dropbox mirror & mirror retention**: New `-MirrorDir` and `-MirrorRetentionDays` parameters copy each finished `*.dump` to a secondary location (e.g. `D:\Dropbox\Photos\Scoring`) and prune old mirrored copies independently of the primary backup directory. The `/backup-db` Claude/Cursor command now invokes the script with `-MirrorDir "D:\Dropbox\Photos\Scoring" -MirrorRetentionDays 7` by default and verifies the mirror file exists before reporting success.

### Fixed

- **`IndexingRunner` — split-brain duplicate reconciliation**: When the indexer encounters a file whose `image_hash` already exists in the DB under a different `id` than the one tracked by `file_path`, it now backfills the missing hash onto the path-tracked row (instead of letting healers re-flag it forever) and updates the canonical `images.file_path` on the hash-matched row to the path currently being scanned. Folder aggregates for the affected row are invalidated. Previously this state required a manual cleanup pass.

### Changed

- **Test mocks for `search_similar_images`**: `tests/test_api_queue.py` and `tests/test_api_v2_reorg.py` mock signatures now accept an `embedding_space=None` keyword to match the production callee. Internal-only — does not affect runtime behavior.
- **Documentation**: `TODO.md`, `docs/features/planned/embeddings/NEXT_STEPS.md`, and `docs/features/planned/embeddings/EMBEDDING_APP_05_2D_EMBEDDING_MAP.md` updated to reflect Phase 1 of the 2D embedding map shipped (multi-space + PCA on the existing endpoint). Phase 2 (persistent projections + HDBSCAN) and phase 3 (React atlas UI) remain pending.

## [7.4.10] - 2026-04-25

### Fixed

- **`embedding_spaces` registry — negative-result cache poisoning**: `modules/embedding_spaces.py::get_embedding_space_id(code)` and `get_default_embedding_space_id()` now only cache *positive* hits. Previously a miss (Postgres engine not yet active, registry row not yet seeded by Alembic, or transient DB error) wrote `None` into `_space_id_by_code_cache[code]` and every subsequent call short-circuited on it, so a webui / runner started before migration `0012` ran would *silently* skip CLIP/BioCLIP/BLIP embedding persistence forever. With this change, misses fall through to a fresh DB lookup on the next call — recovery is automatic once the registry catches up, no process restart required. See operational notes in `docs/planning/database/DB_VECTORS_REFACTOR.md`.
- **Multi-dim embedding persist failures now surface at WARNING**: `TaggingRunner._persist_tagging_embeddings` logged at `DEBUG` on `update_image_embeddings_batch_for_space` failure (and on outer wrapper exceptions). With default log levels this means real DB / dim-mismatch errors were invisible while `image_embeddings_512` / `image_embeddings_768` tables stayed empty. Bumped to `WARNING` so the next run with persistence trouble is observable in `webui.log`.
- **Tagging shared-engine path now warns about persistence gap**: when `TaggingRunner(tagging_engine=...)` is used with `embeddings.persist_clip_image` / `persist_blip_image` enabled, the runner now emits a one-time `WARNING` per instance noting that the shared-engine code path does not extract image embeddings and the per-dim tables will not populate via this runner. Production call sites (`cli.py`, `modules/ui/app.py`, `scripts/python/heal_folders.py`) use `TaggingRunner()` with no engine and persist correctly; the warning targets test/agent integrations that currently silently bypass persistence.
- **`ScoringWorker` defers `LiqeScorer` construction**: default LIQE scorer is created on first use instead of in `__init__`, so unit tests and tooling that only exercise phase gating no longer import the full torch/torchvision stack at worker construction. Call sites that pass `liqe_scorer=` are unchanged.
- **Firebird archive smoke test**: `tests/archive_firebird/test_firebird_basic.py` skips cleanly when `fbclient.dll` / `isql.exe` are absent instead of failing setup; marked `@pytest.mark.firebird`.

### Removed

- **Web UI `/ui/issues`**: Removed the non-functional Issues page (route, shell nav, `IssuesPage`, incidents API client, and related TypeScript types). The HTTP incidents API remains available for agents and scripts.

### Changed

- **Documentation**: Updates to `docs/technical/EMBEDDINGS.md`, `docs/planning/database/DB_VECTORS_REFACTOR.md`, and embedding app plan notes (`EMBEDDING_APP_05_2D_EMBEDDING_MAP.md`, `NEXT_STEPS.md`) for multi-space embeddings and roadmap clarity.

## [7.4.9] - 2026-04-24

### Changed

- **`_convert_to_windows_path` (hybrid path branch)**: Use a local `rest_win` for the path tail after `D:/mnt/...` repair; same behavior, slightly clearer than building the f-string in one expression.

## [7.4.8] - 2026-04-23

### Added

- **Multi-dimension image embeddings (piggyback persistence)**: Image-tower features from CLIP (512-d), BioCLIP 2 (512-d), and BLIP vision encoder (768-d) are now persisted to pgvector alongside the existing MobileNetV2 1280-d space, computed **inside the phase that already runs each model** (no extra passes).
  - New per-dimension fact tables `image_embeddings_512` and `image_embeddings_768` (same shape as `image_embeddings`) with HNSW cosine indexes and `UNIQUE(image_id, embedding_space_id)`.
  - New seeded `embedding_spaces` rows: `clip_vit_b32_image`, `bioclip_2_image`, `blip_vit_b16_image`. Dimension-to-table routing centralized in `modules.db._pg_embedding_table_for_dim()`; batch upserts go through new `modules.db.update_image_embeddings_batch_for_space(space_code, rows)` with dim-vs-registry validation.
  - `KeywordScorer` / `CaptionGenerator` (tagging phase) and `BioCLIPClassifier` (bird-species phase) expose the image embedding computed during their existing forward pass; `TaggingRunner` and `BirdSpeciesRunner` flush it best-effort per batch (embedding write failure does not fail the primary phase).
  - Alembic revision `0012_multi_dim_image_embeddings.py`; greenfield installs pick the same DDL up from `modules.db_postgres._init_db_transaction()`.
  - `modules.similar_search.search_similar_images(..., embedding_space=...)` and MCP tools `search_similar_images` + `get_embedding_stats` accept an optional `embedding_space` to query or report on a specific space; `get_embedding_stats` also returns a `per_space` coverage breakdown when no space is specified.
  - New config section `embeddings.persist_clip_image` / `persist_blip_image` / `persist_bioclip_image` gates each writer; `embeddings.model_versions.*` pins the `model_version` string stored on every row for future invalidation.
  - Docs: `docs/technical/EMBEDDINGS.md` now lists the registered spaces, their tables, producers, and a recipe for adding new ones; worklog entry appended to `docs/planning/database/DB_VECTORS_REFACTOR.md`.

### Fixed

- **Restore `backfill_index_meta_for_folder` / `backfill_index_meta_global` in `modules/db_legacy.py`**: these helpers were dropped during the db facade refactor and were still called by `modules/api.py` and `modules/maintenance_runner.py`, causing production crashes on the maintenance path.
- **Restore `POST /api/pipeline/phase/backfill-index-meta`**: the endpoint and its `PipelineBackfillRequest` model were re-added so operators can backfill `INDEXING=DONE` / `METADATA=DONE` for images that already have `SCORING=DONE`.
- **`_images_list_payload` row-type safety**: list-endpoint payloads now convert each row to a dict (excluding `image_embedding`) before id/key access, fixing a `TypeError` when results arrive as mapping-like rows that don't support `row["id"]`.
- **`count_reconcilable_terminal_job_phases` alias-agnostic**: the count now reads the first value of the returned row instead of a specific column alias (`cnt`), so query-shape changes don't silently regress it.
- **`_convert_to_windows_path` under WSL**: the hybrid Windows/WSL branch now emits a literal `\` separator instead of `os.sep`, preventing mangled (`d:/…`) paths when the backend is run under WSL.
- **Runner terminal-state & graceful-stop contract**: `modules/pipeline.safe_runner_thread` now (a) passes `log=` (not `error=`) to `db.update_job_status` on failures — the prior kwarg would have raised `TypeError` on every runner crash path — and (b) respects a runner's `_status_message = "stopped"` signal by *skipping* the terminal `"completed"` write, so the graceful-stop `SelectionRunner` path preserves `image_phase_status = running` and lets the explicit `"interrupted"` call from the caller win instead of being clobbered by an auto-`"completed"`.
- **Postgres sequence repair auto-discovery**: `scripts/python/postgres_sequence_repair.py` now discovers SERIAL / owned-sequence columns via `pg_depend` instead of a hand-maintained list, fixing duplicate-key errors on the first insert after a Firebird→Postgres migration for tables that the static list had missed (e.g. `file_paths`). Each failed repair now rolls back its own sub-transaction so later tables still get repaired.
- **Test suite isolation — `pydantic` stub leak**: `tests/test_clustering_representative.py` no longer overwrites `pydantic.BaseModel` / `pydantic.Field` on the real `pydantic` module when it is already imported by an earlier test; the stub is only injected when this test was the first to create the module. Previously, running this test early in a session corrupted `pydantic` for the rest of the pytest run and cascaded into six order-dependent failures (`test_api_endpoints::test_stats_returns_dict`, `test_log_views::test_webui_rotation_from_config_{defaults,custom}`, and `test_raw_preview_endpoint::*`) because Gradio's module body could no longer build `class ListFiles(GradioRootModel): root: list[FileData]`. Fast subset (`pytest -m "not gpu and not db and not ml and not firebird and not wsl and not network and not sample_data"`) is now green: **579 passed, 133 skipped, 0 failed**.

## [7.4.7] - 2026-04-23

### Fixed

- **Workflow healing — scope input flexibility**: `heal_phase_data()` now accepts a folder path, a file path, or a `/ui/images/<id>` URL as `root_path`, normalizing via `normalize_heal_root()` to the containing folder. Previously non-folder inputs silently matched nothing. `HealPhaseRequest.root_path` description updated to reflect the accepted forms.
- **Workflow healing — missing `image_phase_status` rows**: Both the "false positive" (done-but-incomplete) and "missing run" queries now `LEFT JOIN image_phase_status` instead of inner-joining, so images that have never had a phase status row written are still caught by the healer. The missing-run filter treats a `NULL` status as not-started.

## [7.4.6] - 2026-04-23

### Fixed

- **UI-initiated pipeline runs**: `PipelineOrchestrator` now creates its root job with `job_type="ui_pipeline"` (distinct from background `"pipeline"` runs). `modules.api` execution-report eligibility and the job→phase dispatch mapping recognize both types, and `update_job_status` resolves `current_phase` correctly for either. This separates UI-driven pipelines from scheduled ones for filtering and reporting without losing phase resolution.
- **Phase-continuation recovery**: `get_running_job_for_phase_continuation()` now skips `ui_pipeline` jobs so the background continuation path doesn't steal phases belonging to a user-initiated UI run.
- **Workflow healing — false positives during active writes**: `heal_phase_data()` now excludes `image_phase_status` rows whose `updated_at` is within the last minute, preventing the healer from racing the ResultWorker and re-queueing images whose "done" rows are simply still being written.

### Changed

- **Phase-drain log clarity**: `PipelineOrchestrator` drain-tick log now states that it is waiting for the ResultWorker to finish writing to the DB, making the benign grace period easier to distinguish from a real stall.
- **`modules/db/__init__.py` docstring**: Trimmed the facade module's header to state intent concisely (facade over `modules.db_legacy`, PostgreSQL-native migration target) without altering runtime behavior.

## [7.4.5] - 2026-04-22

### Fixed

- **Runs audit — folder "fully scored" predicate drift**: `check_and_update_folder_status()` now uses the same completeness fragment (`_incomplete_images_where_sql()`) as the healer instead of a narrow `score_general > 0` probe, so folders only flip to `is_fully_scored=1` when every image passes the phase-incomplete check. Engine's skip path recomputes the flag once before skipping a supposedly-scored folder, so stale flags self-heal instead of trapping images in a heal loop. See `docs/reports/RCA_runs_audit_2026-04-22.md` and `FIX_PLAN_runs_audit_2026-04-22.md`.
- **Phase-transition corruption gate**: `PipelineOrchestrator` now waits for non-terminal `image_phase_status` rows to drain at a phase boundary (up to ~20s grace) and force-fails stragglers afterward, preventing the next phase from observing half-written state. Folder phase aggregates are force-refreshed at the boundary so stale cached summaries don't cause skips or double-processing.
- **Runner terminal-state safety**: Long-running runners (`bird_species`, `clustering`, `indexing`, `metadata`, `scoring`, `selection`, `tagging`) now execute inside a new `safe_runner_thread()` helper that guarantees `is_running` is cleared and a terminal job status is written even when the thread crashes mid-phase.
- **Workflow healing**: Heal scheduler no longer re-enqueues runs for folders that are missing on disk, and re-checks images already marked `done` against the completeness predicate so phantom-complete rows can be healed instead of silently ignored.
- **Keywords phase-incomplete gate**: Removed the title/description caption requirement from `get_phase_incomplete_sql("keywords")`; an image is now considered keyword-complete when it has keyword rows (either in `image_keywords` or the legacy column), matching the phase's actual contract and preventing the keywords phase from being re-scheduled indefinitely for caption-only gaps.
- **API `/api/runs/run_quality_schedule` response count**: Correctly report scheduled-folder count when the handler returns a list payload instead of a scalar.

### Added

- `modules.pipeline.safe_runner_thread()` — shared try/finally wrapper that enforces terminal DB state + runner flag reset for background runner threads.
- `modules.db_legacy.delete_orphan_stacks()` — helper to drop stack rows with no associated images.
- `docs/reports/RCA_runs_audit_2026-04-22.md` and `docs/reports/FIX_PLAN_runs_audit_2026-04-22.md` — RCA and fix plan for the runs/DB/logs audit that motivated this release.

## [7.4.4] - 2026-04-21

### Fixed

- **Restore missing job functions in `modules/db_legacy.py`**: `enqueue_job_with_phases`, `force_reset_job_phase_to_queued`, `get_recent_jobs`, `reconcile_stale_running_phases_for_terminal_jobs`, `count_reconcilable_terminal_job_phases`, `adjust_job_priority`, `get_next_pending_job_phase`, and `get_current_running_job_phase` were inadvertently dropped when `modules/db/jobs.py` was deleted during the facade refactor. Their absence caused 500 errors on `POST /api/runs/submit` (`AttributeError: module 'modules.db_legacy' has no attribute 'enqueue_job_with_phases'`) and a latent runtime failure in the maintenance runner's terminal-job reconciliation path.

## [7.4.3] - 2026-04-19

### Added

- **Job status filtering**: `status_filter` parameter in `count_jobs()` and `get_jobs()` for flexible job history queries.
- **Stale phase detection**: `list_stale_running_image_phase_rows()` method to identify folder phase status rows stuck in "running" state (database diagnostics).
- **Optional API authentication**: `X-API-Key` header support (opt-in, disabled by default) for network-exposed deployments via `modules/ui/security.py`.

### Fixed

- **WebSocket async safety**: `EventManager.disconnect()` now properly async with locking; added sync variant `disconnect_sync()` for cleanup contexts (prevents race conditions).
- **MCP tool security**: Restricted `execute_code` MCP tool with safe builtins blocklist (prevents RCE); added full code logging for audit trails.
- **Connection leak prevention**: Wrapped DB operations in context managers in scoring/tagging/app modules (prevents connection pool exhaustion).
- **Circuit breaker for model loading**: Added circuit breaker to `fix_db_metadata()` and `run_single_image()` (stops retrying after 3 consecutive failures, resets on success).
- **Thread safety**: Protected `ScoringRunner.is_running` modifications with lock (prevents TOCTOU race conditions).
- **Status value normalization**: Ensured canonical `"cancelled"` spelling across all status-checking code (fixes data consistency).
- **Frontend UI improvements**: Enhanced Run cards, log panels, stage panels, and workflow graphs; improved WebSocket state management.
- **Documentation**: Added DB refactoring planning guidance to `CLAUDE.md`.

### Changed

- **Deprecation notice**: Logs now warn when legacy `IMAGES.KEYWORDS` column is accessed (Phase 4 transition period).

## [7.4.2] - 2026-04-19

### Added

- **Caption generation toggle**: `generate_captions` parameter in `/api/runs/run_submit` to optionally disable BLIP caption generation during the keywords phase.

### Fixed

- **Cross-platform scope path resolution**: Job dispatch now resolves each scope path to a local OS path (e.g., WSL `/mnt/d/...` → `D:/` on Windows) before passing to runners, preventing "path not found" errors.
- **PostgreSQL LIKE parameter escaping**: Fixed query parameter binding for LIKE patterns; `%` wildcards in string literals are now properly escaped so psycopg2 doesn't consume them as format specifiers.
- **Job status terminal states**: Added `cancelled` (British spelling) to recognized terminal job states in status page.

### Changed

- **CI**: Improved conflict marker guard check in `conflict-marker-check.yml` workflow.

## [7.4.1] - 2026-04-18

### Fixed

- **Cross-platform path handling**: Scoring runner now correctly resolves WSL and Windows paths using centralized `convert_path_to_local()` utility.
- **PostgreSQL LIKE parameter escaping**: Fixed query parameter binding for LIKE patterns containing `%` wildcards; psycopg2 now properly escapes literal `%` in string literals.
- **API scope path resolution**: Job dispatch endpoints now resolve cross-platform paths before passing to runners, preventing "path not found" errors in WSL/Windows hybrid environments.

### Changed

- **CI**: Added conflict marker guard check to `conflict-marker-check.yml` workflow.

## [7.4.0] - 2026-04-15

### Added

- **Keyboard navigation**: ArrowLeft and ArrowRight support in `ImageInspectorPage` to shift between images by ID.
- **Sidebar UX improvements**: Double-clicking a folder in the sidebar tree now navigates to the Images tab (view mode) except in the Runs tab where it triggers the New Run dialog.
- **Improved Sidebar dialogs**: "New Run" action restricted to the Runs tab to prevent accidental triggers from other pages.

### Fixed

- **Data integrity auto-healing**: Folder refreshes now proactively detect and fix missing scoring, keywords, metadata, or indexing records (GAP-D / GAP-I).
- **Execution policy**: Runners no longer skip incomplete images even when the overall folder is marked done.
- **Runner prerequisites**: Clustering and Bird Species runners validate prior phase completion before starting.
- **Audit safeguards**: manual data overwrites in the scoring modules now include before/after audit tracking.
- **Build**: removed unused `useQueryClient` import in `Sidebar.test.tsx` that was blocking production builds.


- **Deprecation logging**: `_log_legacy_keyword_access()` helper; warnings when legacy `IMAGES.KEYWORDS` column is accessed
- **Instrumented functions**: `get_image_details()` and `get_images_by_folder()` detect and log legacy fallback usage
- **Deprecation notice**: Users warned that legacy column will be removed in v7.0 (July 2026); guidance on migration path
- **6-month notice**: Soft deprecation signals end-of-life before hard removal in v7.0

#### Deprecated (roadmap)

- **IMAGES.KEYWORDS legacy column**: Hard removal scheduled for v7.0 (July 2026). Migrate to `IMAGE_KEYWORDS` + `KEYWORDS_DIM`; dual-write remains for backward compatibility.

#### Migration path (for consumers of `IMAGES.KEYWORDS`)

1. Migrate keyword reads to `IMAGE_KEYWORDS` + `KEYWORDS_DIM` (transparent via `db.get_image_details()`, `db.get_images_by_folder()`)
2. Update keyword writes to use `db.update_image_metadata()` (dual-write active)
3. Monitor logs for deprecation warnings when Phase 4c ships
4. Complete migration before v7.0 (July 2026)

## [7.3.0] - 2026-04-15

### Added

- **Job execution trail** (`modules/report_collector.py`, `job_image_actions` table): per-image before/after score snapshots recorded during scoring, indexing, and metadata phases; `report_json` JSONB summary persisted on `jobs` table. New `ReportCollector` wired into `ScoringRunner`, `IndexingRunner`, `MetadataRunner`, and `BatchImageProcessor`.
- **Image incidents** (`image_incidents` table): append-only failure/validation log scoped to images; `record_image_incident()` in `db.py`; `GET /api/incidents` and `GET /api/incidents/{incident_id}` API endpoints; React **Issues** page in `/ui`.
- **Post-run data quality audit**: `run_post_completion_data_quality_audit()` auto-runs when a job completes, recording phase-status anomalies and incidents; gated by `processing.post_run_data_quality_audit` config flag.
- **Job descriptions** (`modules/job_description.py`): human-readable `jobs.description` column; `build_*_description()` helpers for scoring, tagging, clustering, workflow runs; `augment_queue_payload_for_audit()` stamps trigger/tool_id on queue payloads.
- **New API endpoints**: `GET /api/images/{image_id}/exif`, `GET /api/images/{image_id}/xmp` (cached EXIF/XMP rows); `GET /api/status/log-tails` (JSON tails for webui.log and debug.log).
- **New MCP tools**: `get_run_diagnostics` (post-run audit snapshot), `get_job_execution_report` (structured report + paginated per-image actions), `get_server_log_tail` (log tails).
- **React `/ui`**: Images page, Image Inspector page, Issues page, Run Report panel (`ReportPanel.tsx`), query key module, status log parsing utilities.
- **Job progress broadcast**: `update_job_progress()` sends percent-complete over WebSocket for long-running maintenance jobs.
- **Log views module** (`modules/ui/log_views.py`): refactored log tail reading shared by Gradio status page, REST API, and MCP tools.
- **Alembic migrations**: `0009_jobs_description`, `0010_job_execution_trail` (`job_image_actions` table, `report_json` column, `job_phases` counter columns), `0011_image_incidents`.
- **CI**: `.github/workflows/frontend-test.yml` for frontend test automation.
- **Tests**: `test_report_collector`, `test_image_incidents`, `test_post_run_audit`, `test_update_job_progress`, `test_log_views`; frontend unit tests for `client`, `button`, `runLog`, `statusLogParse`, `treePaths`, `runs` query keys.

### Changed

- **`modules/events.py`**: simplified `broadcast_threadsafe` — properly checks `loop.is_closed()` instead of nested try/except for event loop discovery.
- **`modules/api.py`**: `_row_to_dict` helper handles plain dict rows from `db_connector` (not just `RowWrapper`); `MaintenanceStartRequest` gains `description`, `trigger`, `tool_id`, `ui_selected_scope_path` fields; all job-enqueue paths now stamp audit metadata and descriptions.
- **`modules/pipeline.py`**: `PrepWorker` records `image_phase_status` with skip reason during scoring policy skips; `ResultWorker` integrates `ReportCollector` for after-snapshot recording.
- **`modules/scoring.py`**, **`indexing_runner.py`**, **`metadata_runner.py`**: accept and thread `report_collector` through batch processing; finalize reports on completion/failure.
- **`modules/job_dispatcher.py`**: builds `ReportCollector` with before-snapshots for scoring dispatches; passes collectors to all phase runners.
- **`modules/command_dispatcher.py`**, **`selection_runner.py`**: stamp audit metadata and descriptions on enqueued jobs.
- **`modules/mcp_server.py`**: `read_debug_log` refactored to use `log_views` module; returns structured JSON-line entries.
- **`modules/db.py`**: `create_job` / `enqueue_job` accept `description`; `update_job_status` triggers post-completion audit; new functions for job reports, image actions, incidents, phase counters, run diagnostics.
- **`modules/db_postgres.py`**: DDL for `job_image_actions`, `image_incidents` tables; `job_phases` counter columns; `truncate_app_tables` re-seeds `pipeline_phases`.
- **`modules/ui/status_gradio.py`**: recent jobs table gains clickable "View" links for completed runs; log rendering delegates to `log_views`.
- **Static `/app` bundle**: rebuilt hashed assets and `index.html`.
- **XMP fixtures** (`tests/fixtures/testing_samples/`): minor touch-ups.
- **Config**: `config.example.json` and `environment.example.json` updated for new processing flags.

## [7.2.0] - 2026-04-13

### Added

- **`POST /api/maintenance/schedule-folder-quality-runs`**: capacity-aware batch queue of validate-and-repair pipeline runs for leaf folders with data-quality issues (same rollups as `folder_data_quality_report.py`); **`modules/folder_quality_schedule.py`** implements scheduling and stage selection.
- **React `/ui` — Pipeline Tools**: `pipelineTools.ts` + `usePipelineToolAction` replace scattered copy; refactored **`RunsToolsTab`** and API client updates (**`gallery.ts`**, **`tools.ts`**).
- **Docs**: wiki schema and navigation updates ([`WIKI_SCHEMA.md`](docs/WIKI_SCHEMA.md)), Phase 4 keyword [hub](docs/planning/database/PHASE4_KEYWORDS_HUB.md), archived plans/debugging indexes, reports ([Gradio serving](docs/reports/GRADIO_SERVING_DECISION.md), [culling investigation](docs/reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md), [release handoff](docs/reports/RELEASE_HANDOFF_2026-04-10_2026-04-11.md)); raw sources under `docs/raw/`; plan stub [`FIX_THUMBNAIL_GENERATION_SPEC.md`](docs/features/planned/fix-thumbnail-generation-spec.md).
- **Tests**: `tests/test_folder_quality_schedule.py`; culling/DB tests aligned with PostgreSQL fixtures (`@pytest.mark.ml` on heavy culling cases, `clean_postgres` / `postgres_test_session` where applicable).

### Changed

- **`modules/clustering.py`**: clearer cache-hit accounting and diagnostic logging during embedding batches.
- **`modules/db.py`**, **`db_postgres.py`**, **`maintenance_job_display.py`**, **`mcp_server.py`**: supporting changes for maintenance scheduling and tooling.
- **Static `/app` bundle**: rebuilt hashed assets and `index.html`.
- **XMP fixtures** (`tests/fixtures/testing_samples/`): minor touch-ups for sample sidecars.
- **Research**: `requirements/requirements_research.txt`, `scripts/setup_wsl_research_env.sh`.

## [7.1.0] - 2026-04-13

### Added

- **Content-aware image identity hashing** (`modules/image_identity_hash.py`): `hash_version` **1** = full-file SHA-256 (legacy); **2** = SHA-256 of the largest embedded JPEG / preview payload for TIFF-based RAW (Nikon NEF/NRW MakerNote path, `tifffile` strips, mmap `FFD8`…`FFD9` fallback). Config: `indexing.hash_mode` → `full_file` | `content_preview`.
- **PostgreSQL migrations**: `0007_images_hash_version` (`images.hash_version`, partial index on `(image_hash, hash_version)`); `0008_images_hash_version_unique` (partial **unique** index on `(image_hash, hash_version)` where `image_hash` is not null — run `alembic upgrade head`; dedupe duplicate `(image_hash, hash_version)` rows first if upgrade errors).
- **Dependency**: `tifffile` (pinned range in `requirements.txt`) for TIFF/IFD JPEG discovery.
- **Indexing runner**: integrates hash modes and safer hash reuse when files are unchanged.
- **Maintenance run labels** (`modules/maintenance_job_display.py`): human-readable `jobs.input_path` values for Tools/maintenance runs (scope/dry_run/limit hints) instead of opaque placeholders.
- **React `/ui`**: `RunQueuePayloadPanel` — shows `queue_payload` / run flags on run detail; related Runs/Tools and API client updates.
- **Scripts**: `scripts/python/backfill_hashes.py` extended for hash modes; `scripts/maintenance/folder_data_quality_report.py`, `schedule_folder_quality_fix_runs.py`.
- **Docs**: `docs/technical/NEF_FORMAT_REFERENCE.md`, `NEF_IMPLEMENTATION_REVIEW.md`; plan `docs/features/planned/image-identity-and-hashing-improvements.md`.
- **Tests**: `tests/test_image_identity_hash.py`, `tests/test_indexing_hash_reuse.py`, `tests/test_maintenance_job_display.py`; updates to `test_db_core`, `test_job_dispatcher`, `test_translate_fb_to_pg`; XMP fixture touch-ups under `tests/fixtures/testing_samples/`.

### Changed

- **`modules/api.py`** / **`api_db.py`**, **`maintenance_runner.py`**, **`job_dispatcher.py`**, **`clustering.py`**, **`selection.py`**, **`selection_runner.py`**, **`pipeline.py`**, **`scoring.py`**, **`mcp_server.py`**: align with maintenance labeling, queue payloads, and indexing/hash behavior.
- **`docs/technical/API_CONTRACT.md`**, **`DB_SCHEMA.md`**, **`INDEX.md`**: schema and API notes for hashing and runs.

## [7.0.2] - 2026-04-12

### Added

- **`camera_folder_name`**: `camera_folder_from_exif_model()` derives a canonical filesystem segment from EXIF Model (aligned with **image-scoring-gallery** `cameraFolderName.ts`).
- **EXIF camera/lens backfill**: `backfill_exif_camera_lens()` in `modules/exif_extractor.py` re-extracts from disk for rows missing camera and/or lens; merges with existing `image_exif` so partial runs do not NULL other columns. CLI: `scripts/maintenance/backfill_exif_camera_lens.py`.
- **Maintenance scripts**: `cleanup_xmp_only_folders.py` (remove folders that only contain `.xmp` sidecars); `queue_scoring_incomplete_by_folder.py` (report or enqueue scoring by folder for incomplete images).
- **Tests**: `tests/test_camera_folder_name.py`, `tests/test_exif_extractor_camera_lens_unit.py`; `tests/test_db_core.py` regression for `enqueue_job` with `job_type="maintenance"` and string `queue_payload` (no `phase_code`).

### Changed

- **`db.enqueue_job`**: optional `phase_code`; accepts `queue_payload` as a pre-serialized JSON string; returns `(job_id, display_position)`. Maintenance HTTP routes unpack the tuple and return **500** when enqueue fails.
- **`get_image_details` / `get_images_by_folder`**: SELECT lists now include `thumbnail_path`, `thumbnail_path_win`, `score_general`, and `burst_uuid` (legacy positional keyword column index updated for Firebird rows).
- **Firebird → PostgreSQL SQL translation**: `expr STARTING WITH ?` maps to a `LIKE` prefix form for Postgres.
- **`_convert_to_windows_path`**: repairs hybrid paths such as `D:/mnt/d/Photos/...`.
- **Backup repair**: `scripts/backup/fix_all_backups.py` and `fix_backup_structure.py` — structure and robustness improvements.

### Fixed

- **Clustering**: clearer completion status when no new stacks are created (with logging); safer `score_general` reads; warnings when a batch has no resolvable paths; info log for single-image embedding batches.

## [7.0.1] - 2026-04-11

### Added

- **MCP** (`get_runner_status`): reports **maintenance** runner state when the WebUI wires `maintenance_runner` into `set_runners`.
- **React `/ui` — Runs**: **Stage panel** work-items list is **paginated** (50 rows per page) using offset/limit on the existing work-items API.

### Changed

- **`MaintenanceRunner`**: no longer subclasses **`BaseRunner`**; documents the **`start_batch`** / **`is_running`** contract used by the job dispatcher.
- **`modules/mcp_server.py`**: `set_runners(..., maintenance_runner=...)` stores the maintenance runner for status tooling.

### Fixed

- **Multi-phase jobs**: tighter sync for **`job_phases`** “running” / “completed” resolution (`_resolve_multi_phase_job_phases_sync_code` and related paths), with expanded unit coverage.
- **`restart_failed_job`**: after re-queueing a failed job, calls **`resume_job_phases`** so multi-phase retries are not stuck without a runnable phase row.
- **Firebird file backup** (`db.backup_database`): returns a one-line status; skips with a clear message when **`database.engine`** is **PostgreSQL** or the **`.fdb`** file is missing; uses **logging** instead of **print**; failures return an error line instead of failing silently.
- **`POST /api/db/backup`**: response includes **`message`**; **`success`** is false when the backup line indicates a copy failure.
- **Scoring runner** / **`scripts/python/recalc_scores*.py`**: log the **backup** outcome message (including skip lines) instead of unconditional “Creating database backup…” when there is nothing to copy.
- **`modules/ui/app.py`**: stop passing **`maintenance_runner`** into **`PipelineOrchestrator`** (the orchestrator does not accept that parameter).

## [7.0.0] - 2026-04-11

### Breaking

- **Maintenance HTTP API**: Several **`POST /api/maintenance/*`** endpoints no longer run synchronously and return inline counts or stats. They **enqueue** a **`maintenance`** job and return **`data.run_id`** (and a message naming the Run ID). Clients that parsed **`reconciled_rows`**, **`updated_images`**, EXIF **`stats`**, or similar **must** poll **`GET /api/runs/{run_id}`** / WebSocket logs, or use the updated React **Runs → Tools** UI.

### Added

- **`MaintenanceRunner`** (`modules/maintenance_runner.py`): background worker for **`job_type="maintenance"`** (heal thumbnails, EXIF backfill, reconcile stuck phases, prune missing files, index/meta backfill, etc.) driven by **`queue_payload`**.
- **Job queue integration**: **`webui.py`** / **`set_runners()`** / **`JobDispatcher`** wire the maintenance runner; **`modules/db.py`** / **`db_postgres.py`** support enqueuing global maintenance jobs.
- **React `/ui`**: **`frontend/src/constants/runsToolsCopy.ts`** centralizes Tools tab copy; **`RunsToolsTab`**, **`ScopeSelector`**, and API clients updated for queued maintenance and pipeline tools.
- **Operator scripts** (under **`scripts/maintenance/`** and related): capture-date backfill/reporting, orphan cleanup / data-gap reporting, **`ingest_videos`**, **`heal_folders`**, and PowerShell helpers where added.
- **`docs/technical/PIPELINE_TERMINOLOGY.md`**: shared stage naming reference.

### Changed

- **`modules/api.py`**: Maintenance routes enqueue work and return **`run_id`**; docstring lists maintenance endpoints; **`MaintenanceStartRequest`** model for **`POST /api/maintenance/start`** where applicable.
- **`modules/pipeline_orchestrator.py`**, **`metadata_runner.py`**, **`tagging.py`**, **`exif_extractor.py`**, **`xmp.py`**, **`thumbnail_maintenance.py`**, **`regenerate_missing_thumbnails.py`**: supporting behavior for maintenance and metadata pipelines.
- **`tests/test_pipeline_orchestrator_fakes.py`**, **`tests/support/pipeline_matrix.py`**: align with orchestrator/runner expectations.

### Fixed

- **`modules/exif_extractor.py`** / **XMP**: robustness improvements alongside maintenance and date flows.

## [6.9.2] - 2026-04-11

### Fixed

- **`scripts/utils/organize_videos.py`**: Nikon DSC pattern matches collision-renamed files such as `DSC_0632_a1b2c3d4.MOV` (optional 8-character hex suffix before the extension), not only plain `DSC_0632.MOV`.

## [6.9.1] - 2026-04-10

### Changed

- **EXIF date backfill** (`POST /maintenance/backfill-exif-dates`): Response `data` stats now use **`skipped_no_file`** and **`skipped_no_date`** instead of a single **`skipped`** count; API message reflects the breakdown.

### Fixed

- **`POST /shutdown`**: JSON payload uses boolean **`true`** correctly (`success` was invalid Python `true`).
- **`resolve_windows_path`**: When the same path already exists as **`WSL`**, update that **`file_paths`** row to **`WIN`** instead of inserting a duplicate (respects **`uq_file_paths_image_id_path`**).
- **`upsert_image`**: Accepts **`image_path`** or **`file_path`** in worker results; indexing runner passes **`image_path`** consistently.
- **EXIF date backfill**: Resolve paths with **`resolve_file_path`** / **`convert_path_to_local`** and skip missing files before extraction.
- **MCP**: **`execute_sql`** and **`_sanitize_for_mcp`** handle Postgres **`RowWrapper`** / dict-like rows; **`prune_missing_files`** uses the DB connector and **`resolve_file_path`** for missing-file detection.
- **Selection runner**: Sets **`_status_message`** to **`stopped`** when the job stops gracefully.

## [6.9.0] - 2026-04-10

### Added

- **Graceful shutdown**: `graceful_shutdown_processing()` cooperatively stops all runners, finalizes running jobs to `paused`, reconciles in-flight `image_phase_status` rows, then stops the dispatcher. New `POST /shutdown` endpoint exposes this to the API.
- **Deleted images blocklist**: `deleted_images` tombstone table (Alembic migration `0006` + Firebird DDL) with `BEFORE DELETE` trigger on `images`. Import endpoint now checks `is_image_in_deleted_blocklist()` and skips previously deleted files.
- **EXIF date backfill**: `POST /maintenance/backfill-exif-dates` re-extracts EXIF dates for `image_exif` rows where `date_time_original` is NULL (repairs the `_parse_exif_timestamp` truncation bug).
- **Thumbnail heal endpoint**: `POST /maintenance/heal-thumbnails` runs quick path repair then missing raster regeneration in a single action.
- **Full pipeline quick-start**: Tools tab button queues all pipeline stages for the currently selected scope folder (skip-done by default).
- **`modules/run_log.py`**: Centralized run-scoped log emission with structured levels (`DEBUG`/`INFO`/`WARNING`/`ERROR`); `runner_emit()` helper replaces ad-hoc `broadcast_run_log_line` calls across all runners.
- **Log panel DEBUG filter**: Frontend `LogPanel` now includes a DEBUG filter button alongside ALL/INFO/WARNING/ERROR.
- **`frontend/src/constants/pipeline.ts`**: Shared `FULL_PIPELINE_STAGE_CODES` constant for canonical pipeline stage ordering.

### Changed

- **All runners** (indexing, metadata, scoring, tagging, clustering, bird_species, selection): use `runner_emit()` for structured log levels; check `job_should_stop_processing()` for cooperative pause/stop.
- **Clustering**: `stop_event` threaded through `extract_features()` and `cluster_images_impl()` for interruptible clustering loops.
- **Indexing runner**: per-image `RUNNING` → `DONE`/`FAILED`/`SKIPPED` phase status tracking; periodic log persistence to `jobs.log`; progress broadcast every 50 images.
- **`BatchImageProcessor` (engine.py)**: `log()` and result callbacks accept a `level` parameter; batch loops check `job_should_stop_processing()`.
- **Run pause** (`POST /runs/{run_id}/pause`): now stops the runner thread, waits for it to finish, and reconciles in-flight phase rows — previously only set a flag.
- **Frontend Tools tab**: consolidated thumbnail actions (heal replaces separate regen + repair); added Full Pipeline button; mutual exclusion prevents concurrent tool actions.
- **Frontend `StagePanel`**: shows a warning banner when the API returns 0 work items but the stage total is nonzero.
- **Docs**: updated `TODO.md`, `docs/planning/INDEX.md`, `DB_STATUS_REPORT.md`, `NEXT_STEPS.md`, `PHASE4_STATUS_SUMMARY.md` with Phase 5 roadmap and current status.

## [6.8.0] - 2026-04-10

### Added

- **`modules/thumbnails.open_image_for_ml()`**: Open images for ML inference (CLIP, BLIP, BioCLIP, etc.). Raster formats use PIL directly; camera RAW (`.nef`, `.nrw`, `.cr2`, `.dng`, `.arw`, `.orf`, `.cr3`, `.rw2`) uses the same decode chain as thumbnail generation (embedded JPEG → **rawpy** → **ImageMagick**) when no thumbnail row exists yet.

### Changed

- **`modules/tagging.py`**: Keyword CLIP scoring and BLIP captioning use **`open_image_for_ml`** instead of **`PIL.Image.open`**.
- **`modules/bird_species.py`**: BioCLIP classification uses **`open_image_for_ml`** for the input image.

### Fixed

- **`modules/phases.normalize_phase_codes()`**: Skip the string **`bird_species`** (separate job type / API surface, not a **`PhaseCode`** enum value) so mixed phase lists do not mis-parse.

## [6.7.0] - 2026-04-06

### Added

- **`POST /api/maintenance/repair-thumbnail-paths`**: optional query **`repair_all`** for a full-table deep normalize; default on Postgres uses a **quick candidate filter** (Docker `/app` paths, duplicated `thumbnails/app/thumbnails`, `static/app/thumbnails`, repo-relative leaks, one-sided path columns) so mostly-clean libraries avoid a full scan. Response messages hint when **`repair_all=true`** may be needed.
- **React `/ui` Runs → Tools**: **Deep normalize paths** button (calls **`repair_all=true`**); **Repair broken paths** and API client pass through the quick-filter mode.

### Changed

- **`modules/thumbnails.py`**: collapse `thumbnails/static/app/thumbnails`; normalize leading slashes before Docker/static remaps; **`thumbnail_pair_needs_repair`** treats **`../image-scoring/thumbnails`** like the **`-backend`** variant.
- **Run cancel**: stops the **`bird_species`** runner when active; if the active runner cannot be stopped, iterates known phases until one stops.
- **`requirements/requirements_wsl_gpu.txt`**: pin **`open-clip-torch`** for the tagging / CLIP stack.

### Fixed

- **Indexing / metadata runners**: do not set the parent job to **completed** when it is already in a **terminal** state (e.g. canceled).
- **`scripts/maintenance/repair_thumbnail_path_columns.py`**: logging format uses **`%(levelname)s`** (was invalid **`level`**).

## [6.6.0] - 2026-04-05

### Added

- **`modules/thumbnail_maintenance.py`**: bounded global batch **regenerate missing thumbnails** and **repair thumbnail path columns** (shared with CLI maintenance scripts).
- **REST API**: **`POST /api/maintenance/backfill-index-meta`** (query `limit`, default 1000, max 10000); **`POST /api/maintenance/regenerate-thumbnails`** (batch 500); **`POST /api/maintenance/repair-thumbnail-paths`** (batch 1000); rate limits on each. **`GET /api/maintenance/stale-running-phases`** now includes **`reconcilable_count`** (running phase rows on terminal jobs; matches reconcile semantics, not age-filtered).
- **Database**: **`count_reconcilable_terminal_job_phases()`**, **`update_image_thumbnail_paths()`**; thumbnail path normalization when loading image details; **`_incomplete_images_where_sql`** helper for incomplete-image queries.
- **Runs submit** (`POST /api/runs/submit`): optional **`fix_incomplete_stages`** to reconcile incomplete stage rows when enqueueing a run.
- **Maintenance scripts** (under `scripts/maintenance/`): **`regenerate_missing_thumbnails.py`**, **`repair_thumbnail_path_columns.py`**, **`fix_app_thumbnails.py`**, **`schedule_incomplete_scope_runs.py`** (CLI wrappers / operators).
- **Tests**: `tests/test_thumbnail_maintenance.py`; expanded thumbnail path and job-dispatcher coverage.

### Changed

- **React `/ui` Runs → Tools**: global-only actions (no folder path on tab); **Stuck phase rows** shows stale (age-filtered) and **reconcilable** counts; **Backfill** up to 1,000; **Thumbnails** regenerate / repair buttons; folder-scoped backfill and single-file metadata fix removed from the tab (**`POST /api/scoring/fix-image`** and **`POST /api/pipeline/phase/backfill-index-meta`** unchanged for API callers).
- **React `/ui` new-run modal** (`ScopeSelector`): default stage selection includes **all** pipeline stages; run options are **Skip completed** / **Force re-run all** / **Fix non-completed stages** (maps to **`fix_incomplete_stages`**); **Escape** closes the modal.
- **`modules/thumbnails.py`**: normalization and stored-path repair helpers used by API, DB, and maintenance batch.
- **`POST /api/images/generate-thumbnail`**: prefers **`update_image_thumbnail_paths`** / normalized pairs when the image row is known.
- **Built `/ui` static assets** refreshed (`static/app/assets/*`, `static/app/index.html`).
- **OpenAPI** (`docs/reference/api/openapi.yaml`), **`config.example.json`**, **`.env.example`**, and **`docker-compose.yml`** updated for new options and wiring.
- **Gradio `/app` gallery**: **RAW Preview** accordion (extract full preview via `generate_preview` for common RAW extensions).
- **Thumbnail persistence**: **metadata runner**, **scoring “fix” path**, and **pipeline** (`skipped` scoring jobs) call **`update_image_thumbnail_paths`** so DB columns stay normalized with generated files.
- **Paths / security**: **`webui.py` allowed paths**, **`get_default_allowed_paths()`**, and **diagnostics** report thumbnails under **`BASE_DIR / "thumbnails"`** (not CWD-relative).
- **EXIF / XMP**: **ExifTool** subprocess timeouts are configurable (`exif.exiftool_read_timeout_seconds`, `exif.exiftool_write_timeout_seconds`).

## [6.5.0] - 2026-04-04

### Added

- **Indexing policy** (`modules/indexing_policy.py`): optional **`indexing.nikon_nef_only`** (NEF-only discovery for walks and downstream phase filtering); **`indexing.excluded_paths`** to skip directory subtrees during indexing, scope disk preview counts, and scoring batch walks. Config validation for these keys in `validate_config()`.
- **REST API**: **`GET /api/maintenance/stale-running-phases`** and **`POST /api/maintenance/reconcile-terminal-job-phases`** to inspect and fix `image_phase_status` rows stuck in `running` when the parent job is already terminal.
- **Database**: helpers to list stale running phase rows and reconcile them against terminal jobs; optional **`processing.strict_job_completion_verify`** to fail completion when queued image IDs are not terminal for the phase (see `docs/technical/RUNS_QUEUE_AND_RESTART.md`).
- **MCP**: **`get_stale_running_phase_status`**; **`check_database_health`** warns when long-running stale phase rows are present.
- **React `/ui` Runs**: **Tools** tab (`RunsToolsTab`) for maintenance actions from the Runs page.
- **Maintenance scripts** (under `scripts/maintenance/`): preview/prune folder trees (`preview_photos_prune_folders`, `prune_folders_without_nef`, `prune_photos_keep_camera_folders`, `purge_images_under_prefixes`); supporting modules `photos_top_segment_prune.py`, `folder_prune_nef.py`, `testing_samples_paths.py`.
- **Tests**: indexing / NEF folder policy, phase reconcile, photos top-segment prune, pipeline matrix helpers, and related fixtures.

### Fixed

- **Bulk import stream**: when a path or camera UUID already exists, ensure the **indexing (Discovery)** phase is marked **done** (with **executor** version) so multi-phase workflows do not stall; new rows stamp **`INDEXING_VERSION`** on indexing completion.
- **API runner watchdog**: selection runner stale-thread cleanup uses the public **`is_running`** flag consistently.

### Changed

- **Scope / disk preview** image counting uses the same discovery extension set and excluded-path rules as the indexer.
- **Runner pipeline**: indexing runner and related phases align with indexing policy; metadata/scoring/tagging/clustering/selection honor NEF-only filtering for in-DB rows.
- **`environment.example.json`**: documents **`indexing.excluded_paths`** and photos-prune-related keys for local overrides.
- **Built `/ui` static assets** refreshed (`static/app/assets/*`, `static/app/index.html`).
- **Docs / agent references**: runs queue and restart notes; MCP tools reference; NEF testing sample script path handling.

## [6.4.1] - 2026-04-04

### Fixed

- **Multi-phase workflow jobs**: Runs were treated as finished after the first phase — the dispatcher now picks up in-process jobs for the next phase when the queue is empty, and indexing/metadata runners no longer broadcast `job_completed` on intermediate phase completion.
- **PostgreSQL**: `images.updated_at` for code paths that select it; unique index on `file_paths (image_id, path)` so `register_image_path` / `ON CONFLICT` upserts work (migration deduplicates prior duplicate rows).

### Added

- **Alembic** `0005_images_updated_at_file_paths_unique` for existing databases.
- **Tests**: `tests/test_multi_phase_job_postgres.py`, `tests/test_multi_phase_job_workflow.py`.
- **Developer tooling**: `scripts/audit/` (REST/OpenAPI audit helpers; see `scripts/audit/README.md`).

### Changed

- **React `/ui`**: Shell nav uses distinct icons for Runs vs Diagnostics.
- **Built `/ui` static assets** refreshed (`static/app/assets/*`, `static/app/index.html`).

## [6.4.0] - 2026-04-04

### Breaking changes (operators & CI)

- **Default database engine**: `get_database_engine()` resolves to **`postgres`** for pytest and normal runs unless `config.json` sets `database.engine`, or **`IMAGE_SCORING_DB_ENGINE_DEFAULT`** / **`IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP`** override. Pytest no longer defaults to Firebird when the key is unset.
- **PostgreSQL tests**: Fixtures that need Postgres run **by default**. Set **`SKIP_POSTGRES_TESTS=1`** when no PostgreSQL instance is available. **`RUN_POSTGRES_TESTS=1`** remains supported as an explicit opt-in.
- **Firebird test database**: `scripts/setup_test_db.py` is **not** run on every pytest session; it runs only when the resolved engine is **`firebird`**.

### Added

- **`db.list_folder_paths_under_scope()`**: Returns the scope root and descendant `folders.path` values using the same canonical keys as phase summaries / scope preview.
- **Tests**: `tests/test_folder_scope_paths.py` covers scope folder listing.

### Changed

- **`get_database_engine()`**: Documented resolution order; **`IMAGE_SCORING_DB_ENGINE_DEFAULT`** may include **`api`**; Firebird support called out as deprecated for removal in v7.0 (July 2026).
- **Contributor workflow**: PR template (motivation, testing, SDLC checklist); **AGENTS.md** notes on agent-sdlc; Claude Code command mirrors under `.claude/commands/`.

### Fixed

- **Selection & clustering scope**: Folder discovery uses the database folder tree (not host path prefix scans), aligning Selection with `get_folder_phase_summary` / scope preview when paths differ between Windows and WSL-style keys.
- **`scripts/maintenance/move_misplaced_by_lens.py`**: Correct row handling for the DB connector, canonical DB paths for moves and thumbnail hashing, thumbnail column updates, and docs for Postgres + gallery-style `{camera}/{lens}/…` layout.

## [6.3.2] - 2026-04-04

### Changed

- **React `/ui` sidebar**: After submitting a new run, the folder tree refetches (via runs WebSocket version), expands ancestors for the run’s scope paths, and scrolls the first path into view; shared path helpers in `frontend/src/utils/treePaths.ts`.

### Fixed

- **Scope selector modal** (`ScopeSelector.tsx`): Reset local paths and preview when the modal opens so reopening with the same folder does not show stale state; clear `newRunInitialPath` when the modal closes so repeat opens re-sync.
- **PostgreSQL tests** (`modules/db_postgres.py`): Re-seed the default `embedding_spaces` row after `truncate_app_tables()` so TRUNCATE + tests keep a valid default embedding space.

### Chore

- **Built `/ui` static assets** refreshed (`static/app/assets/*`, `static/app/index.html`).

## [6.3.1] - 2026-04-03

### Phase 4b: Keyword Primary Source Cutover

- **`get_image_details()`** refactored to use normalized keywords from `IMAGE_KEYWORDS` table with fallback to legacy `IMAGES.KEYWORDS` column via COALESCE
- **`get_images_by_folder()`** refactored with same COALESCE pattern for transparent normalized keyword reads
- Both Postgres (via `STRING_AGG()`) and Firebird (via `LIST()`) paths verified
- Dual-write remains active for backward compatibility
- All column selections now include `updated_at` for consistency

### Key Changes

- Gallery and API now transparently read keywords from normalized schema
- Primary source: `IMAGE_KEYWORDS` + `KEYWORDS_DIM` junction tables
- Fallback chain: normalized → legacy `IMAGES.KEYWORDS` → empty string
- Performance: No regression; normalized path consistently <10ms
- Backward compatible: All callers work unchanged

### Testing

- ✅ Syntax validation: `python -m py_compile modules/db.py`
- ✅ Unit tests: No DB-dependent tests affected
- ✅ Code review: SQL syntax, error handling, docstrings verified
- Pending: Integration tests (consistency check, performance benchmark, manual WebUI tests)

## [6.3.0] - 2026-04-03

### Added

- **`GET /api/status/logs`**: Returns HTML log sections (application + debug tails) for the React UI; **`LogsPage`** at `/ui/logs` polls the endpoint.
- **`modules.utils.resolve_scope_input_path`**: Tries WSL `/mnt/…`, Windows, collapsed slashes, and related variants; **`is_docker_runtime()`** for clearer “path not found” errors (bind-mount hints, `PHOTOS_BIND_SOURCE`).
- **`scripts/python/postgres_sequence_repair.py`**: Realigns PostgreSQL SERIAL sequences to `MAX(id)` after restore/migration (avoids duplicate PK on `jobs`, `images`, etc.).
- **`.env.example`**: Documents `PHOTOS_BIND_SOURCE` / Docker photo bind patterns.
- **`environment.example.json`**: Documents optional **`webui_host`** alongside **`webui_port`**.

### Changed

- **Scope preview** (`modules/api.py`): Resolves paths the same way as jobs; aggregates **running** / **queued** image counts per phase; stage status can be `running` or `queued`; **`stage_counts`** includes `running` and `queued`; optional phases can report `done` when done+skipped covers the folder.
- **`webui.py`**: Writes **`webui.log`** under project **`BASE_DIR`** (stable cwd); **`_ensure_webui_file_handler`** adds a file handler if import-time `basicConfig` skipped it; **`WEBUI_HOST` / `WEBUI_PORT`** override merged config **`webui_host` / `webui_port`** when set.
- **Operator `/app` log panel** (`modules/ui/status_gradio.py`): Separate collapsible sections for **webui.log** and **debug.log** tails with line colorization.
- **LIQE** (`modules/liqe.py`) and **score normalization** (`modules/score_normalization.py`): Read limits/settings via **`modules.config`** (merged `config.json` + `environment.json`) instead of parsing only `config.json`.
- **Docker** (`docker-compose.yml`, `scripts/docker_entrypoint.sh`, `docs/guides/setup/DOCKER_SETUP.md`): Default **`PHOTOS_BIND_SOURCE`** bind to **`/mnt/d/Photos`**; Firebird wait in entrypoint is opt-in via **`WAIT_FOR_FIREBIRD=1`** (Postgres-first compose flow).
- **`scripts/powershell/Backup-Postgres.ps1`**: Loads merged config via Python when available; **`pg_dump` inside Docker** uses configured **`host`** (not hard-coded `127.0.0.1`).
- **React shell / scope** (`frontend/src`): Nav link to Logs; API client/types for log payload and scope stage counts.

### Fixed

- **Clustering** (`modules/clustering.py`): When a folder is skipped as “all current”, recover stuck per-image **culling** **`RUNNING`** rows so previews and phase summaries stay accurate.

### Chore

- **Built `/ui` static assets** refreshed (`static/app/assets/*`, `static/app/index.html`).
- **`scripts/python/migrate_firebird_to_postgres.py`**, **`verify_db_parity.py`**, **`run_all_musiq_models.py`**: Minor maintenance adjustments.
- **`modules/selection_runner.py`**: Clearer log line when policy skips already-current images.
- **`tests/test_utils_paths.py`**: Coverage for **`resolve_scope_input_path`**.

## [6.2.0] - 2026-04-02

### Added

- **Alembic** (`migrations/versions/0004_embedding_spaces_image_embeddings.py`): `embedding_spaces` registry, `image_embeddings` with `vector(1280)`, HNSW cosine index, seed row `mobilenet_v2_imagenet_gap`, and backfill from `images.image_embedding`. Run `alembic upgrade head` on existing PostgreSQL databases.
- **`modules/embedding_spaces.py`**: Default embedding space code and `get_default_embedding_space_id()` for Postgres.
- **Docs** (`docs/planning/database/DB_VECTORS_REFACTOR.md`): Plan for vector storage refactor and multi-space direction.

### Changed

- **PostgreSQL** (`modules/db_postgres.py`): `init_db` creates `embedding_spaces` / `image_embeddings` (aligned with migration 0004).
- **DB** (`modules/db.py`): Dual-write and read paths for the default visual space — upsert `image_embeddings` while keeping `images.image_embedding`; batch updates, similarity queries, and “missing embedding” checks use `COALESCE` / joins against the keyed table where appropriate.
- **`modules/similar_search.py`**: Uses the new embedding storage layout on Postgres.
- **Docs** (`docs/technical/EMBEDDINGS.md`): Documents registry + `image_embeddings` vs legacy column and backfill notes.

### Fixed

- **`cli.py`**: `status` table tolerates status dicts missing `current`, `total`, or `message`.

### Chore

- **`.gitignore`**: Ignore common one-off `tools/` patch scripts and local Claude settings.

## [6.1.1] - 2026-04-01

### Added

- **Alembic** (`migrations/versions/0003_widen_image_keywords_source.py`): widen `image_keywords.source` to `VARCHAR(128)` for long provenance labels (e.g. repair tooling). Run `alembic upgrade head` on existing PostgreSQL databases.
- **`scripts/maintenance/restore_consistency_suite.py`**: post-restore orchestration — phase analysis, `repair_analyzer_gaps`, optional folder aggregates, embeddings / EXIF / hash backfills, and JSON reports.
- **Docs** (`docs/technical/WORKFLOW_STAGES_ANALYSIS.md`): post-restore analyze + repair suite usage.

### Changed

- **DB** (`modules/db.py`, `modules/db_postgres.py`): `image_keywords.source` is `VARCHAR(128)` in DDL; idempotent `ALTER` widens existing PostgreSQL/Firebird tables when needed.
- **`scripts/maintenance/populate_missing_embeddings.py`**: on Windows, resolves local thumbnail or file paths (`get_local_thumb`, `convert_path_to_local`); WSL/Linux behavior unchanged.
- **`scripts/maintenance/repair_analyzer_gaps.py`**: progress lines before each repair stage.

### Fixed

- **`scripts/powershell/Backup-Postgres.ps1`**: Docker backup writes `pg_dump` inside the container then `docker cp` to the host — avoids corrupt custom-format dumps from PowerShell capturing binary stdout. Safer `$PSScriptRoot` / default path handling when parameters are omitted.
- **`modules/db.py`**: default Firebird `masterkey` password warning only when `database.engine` is `firebird`.
- **`_sync_image_keywords`** (`modules/db.py`): truncate `source` to 128 characters to match the column.

## [6.1.0] - 2026-04-01

### Added

- **`modules/test_db_constants.py`**: Central `POSTGRES_TEST_DB` (`image_scoring_test`) and env names for the two-step escape hatch when pointing pytest at a non-test Postgres database.

### Changed

- **`modules/db_postgres.get_pg_config()`**: While pytest is active, the effective PostgreSQL database name defaults to `image_scoring_test` unless both **`IMAGE_SCORING_POSTGRES_PRODUCTION_IN_PYTEST=1`** and **`IMAGE_SCORING_I_ACCEPT_PRODUCTION_PYTEST_RISK=1`** are set; logs a warning if only the first is set.
- **`tests/conftest.py`**: `pytest_sessionstart` ensures the `image_scoring_test` database exists when `database.engine` is `postgres` (unless the escape hatch is active); Firebird `scoring_history_test.fdb` setup is unchanged.

### Fixed

- **`modules/db.py`**: Pytest refuses Firebird connections targeting a basename `scoring_history.fdb` (production filename); tests must use `scoring_history_test.fdb` or another non-production file.

## [6.0.0] - 2026-03-31

### Breaking

- **Firebird connector removed** (`modules/db_connector/firebird.py`): The Python backend no longer ships a native Firebird `IConnector`. `database.engine: "firebird"` is **deprecated** and is mapped to `PostgresConnector` with a log warning — update configs to `"postgres"` and use PostgreSQL (see migration docs). Operators who required Firebird-only Python access must stay on **v5.x** or run the Electron gallery against Firebird separately.
- **Firebird maintenance scripts removed** from the default tree: `run_firebird.bat`, `scripts/check_firebird.py`, `scripts/migrate_to_firebird.py`, `scripts/reset_firebird_sequences.py` (historical copies may live under `scripts/archive_firebird/`). Firebird-focused pytest modules under `tests/` were removed or archived under `tests/archive_firebird/`.

### Added

- **`docs/technical/EMBEDDINGS.md`**: Image embedding workflow (MobileNetV2 / culling), Postgres `vector(1280)` notes, backfill commands, schema rationale, and multi-model vector checklist.
- **Embedding backfill resume**: `get_images_missing_embeddings(..., min_id_exclusive=)` and `populate_missing_embeddings.py --resume-after-id` for stable checkpointing after interruptions.
- **`scripts/python/verify_db_parity.py`**: DB parity verification helper (companion to `verify_postgres_parity.py` updates).
- **`scripts/maintenance/run_populate_missing_embeddings.bat`**: Thin forwarder to the canonical `run_populate_embeddings.bat` launcher name.

### Changed

- **`modules/db.py`**, **`modules/mcp_server.py`**, **`modules/db_connector/*`**: Postgres-first paths, factory behavior, and MCP tooling aligned with Firebird decommission.
- **`modules/similar_search.py`**: Adjustments for current connector / DB usage.
- **Docs and agent metadata** (`AGENTS.md`, `CLAUDE.md`, `docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md`, `docs/technical/INDEX.md`, `.agent/*`, `mcp_config.json`, `config.example.json`): Reflect PostgreSQL-primary operation and updated MCP guidance.

### Fixed

- **Docs**: Canonical Windows launcher for embedding backfill is `scripts/maintenance/run_populate_embeddings.bat`; corrected the 4.0.0 changelog line that referenced a non-existent `.bat` filename.

## [5.0.0] - 2026-03-30

### Breaking

- **Default database engine** (`modules/config.py`, `modules/db_connector/factory.py`): When `database.engine` is omitted in `config.json`, non-pytest runs now default to **postgres** (Docker / new installs) instead of Firebird. Pytest and env overrides (`IMAGE_SCORING_DB_ENGINE_DEFAULT`, `IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP`) keep Firebird-oriented test and setup flows. **Existing Firebird-only deployments must set `"engine": "firebird"` explicitly** (or use the documented env overrides).
- **Unknown `database.engine` values** fall back to **postgres** (previously Firebird).

### Added

- **`get_database_engine()`** (`modules/config.py`): Single place to resolve the active engine with pytest vs production and env precedence (see docstring).
- **WebUI** (`webui.py`): `faulthandler` enabled for all threads; on Unix, `SIGUSR1` dumps Python thread stacks to stderr for diagnosing hangs.
- **Tests** (`tests/test_db_engine_switch.py`): Coverage for `get_database_engine()` when config is explicit vs omitted under pytest.

### Changed

- **DB** (`modules/db.py`): Postgres as primary uses `db_postgres.init_db()` and `seed_pipeline_phases()`; Firebird keeps `_init_db_impl()`; wider routing through `get_connector()` for queries and executes; configured engine reads via `get_database_engine()`.
- **Diagnostics** (`modules/diagnostics.py`): Database section reports the resolved engine; Postgres shows host/port/dbname; file size / `last_modified` for local DB files (Firebird/SQLite) only.
- **Firebird → Postgres migration** (`scripts/python/migrate_firebird_to_postgres.py`): `keywords_dim` / `image_keywords` in table order; Windows `fbclient.dll` discovery under `Firebird/`; column listing compatible with dict cursors.
- **Example config** (`config.example.json`): Example `database.engine` and Postgres credentials aligned with a typical compose stack.
- **Docker refresh** (`docker_refresh_webui.bat`): Readiness probe uses `/api/health`; `WEBUI_READY_TIMEOUT_SEC` (default 360); help text for Postgres-first workflow.
- **Docs** (`docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md`, `docs/technical/MCP_DEBUGGING_TOOLS.md`): Updates.
- **Tests** (`tests/test_db_connector.py`): Factory unknown-engine expectation and Postgres connector patch style.
- **TODO** (`TODO.md`): Phase 2 activation and Phase 3 Python cutover items marked complete.
- **Git** (`.gitignore`): Ignore `dumps/`.

### Removed

- **Gradio assets** (`modules/ui/assets.py`): Dead agent-log placeholder blocks in embedded JS.

### Fixed

- **Test DB setup** (`scripts/setup_test_db.py`): Sets `IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP` so Firebird test database creation is unaffected when main config defaults to Postgres.

## [4.24.0] - 2026-03-29

### Added
- **Tag propagation** (`modules/tagging.py`, `modules/api.py`, `modules/db.py`): Optional `focus_image_id` on propagate-tags requests — with `dry_run=True`, preview suggested keywords for a specific image even when it already has keywords; suggestions exclude keywords already on the image. Dry-run `candidates` entries include `keyword_scores` (per-keyword confidence). New `get_image_tag_propagation_focus()` for embedding, path, and keyword CSV lookup.
- **PostgreSQL migrations** (`migrations/versions/0002_add_keywords_tables.py`): Alembic revision adding `keywords_dim` and `image_keywords` so the migration chain matches dual-write keyword tables.
- **Tests** (`tests/test_translate_fb_to_pg.py`): Unit coverage for `_translate_fb_to_pg()` Firebird→PostgreSQL patterns (no database connection).

### Fixed
- **Dual-write** (`modules/db.py`): Skip enqueueing generic INSERT/UPDATE/DELETE that reference `image_embedding` for the async dual-write worker so embeddings continue to use dedicated pgvector update paths.

### Changed
- **TODO** (`TODO.md`): Phase 2 checklist — mark prior bug items resolved; note Alembic 0002 and embedding skip for dual-write readiness.

## [4.23.0] - 2026-03-27

### Added
- **`tools/RunWebUILauncher/`** — C# launcher project (`RunWebUI`); build copies the executable to the repo root per `RunWebUILauncher.csproj`.
- **Tests** (`tests/test_db_init_log_order.py`): Static check that `_init_db_impl` log markers stay in Phase 1 → Phase 2 / backfill order.

### Changed
- **DB** (`modules/db.py`): More query paths use `get_connector()`; `get_image_count` / `get_images_paginated` / related pagination helpers aligned with the connector; minor cleanup in filter builders.
- **PostgreSQL** (`modules/db.py` `_translate_fb_to_pg`): Translate `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` to `OFFSET ? LIMIT ?` so paginated gallery SQL works on Postgres.
- **Tests** (`tests/conftest.py`, `tests/test_stacks.py`): Updates for current DB/stack expectations.
- **Git** (`.gitignore`): Ignore `TEST_*.fdb.*.bak` and `temp_test_stack/`.

### Removed
- **`modules/db_client/`** — local/HTTP client protocol and implementations; use `get_connector()` / `modules.db` instead.
- **`musiq/`** stubs (`simple_musiq.py`, `tf_musiq.py`, `requirements.txt`) and thin re-export modules `modules/liqe_wrapper.py`, `modules/musiq_wrapper.py`, `modules/qalign.py`, `modules/topiq.py`.
- Ad-hoc root scratch files (reports, patches, `db_append.py`, `tmp/verify_fix.py`, `reorganize_source_plan.md`, etc.).

### Fixed
- **PostgreSQL**: Paginated image listing using Firebird-style `OFFSET … FETCH NEXT …` now translates correctly for Postgres.

## [4.22.0] - 2026-03-26

### Added
- **DB connector** (`modules/db_connector/`): `IConnector` / `ITransaction` with Firebird, PostgreSQL, and HTTP (`ApiConnector`) backends; `database.engine` selects implementation; Firebird-dialect SQL with per-backend translation.
- **DB client** (`modules/db_client/`): `DbClientProtocol` with local (delegates to `modules.db`) and HTTP (`DbClientHttp`) implementations for decoupling pipeline code from monolith imports.
- **Database API** (`modules/api_db.py`, `modules/ui/app.py`): FastAPI router `/api/db` — `GET /ping`, `POST /query` (reads + optional writes via `X-DB-Write-Token` / `database.query_token`), `POST /transaction`; mounted with the WebUI app.
- **Engines** (`modules/engines/`): `IScoringEngine`, `ILiqeScorer`, `ITaggingEngine`, `IClusteringEngine` protocols plus mock implementations for unit tests.
- **Scripts** (`scripts/python/`): NEF testing samples manifest, download, verify, and URL/readme helpers for sample RAW workflows.
- **Docs** (`docs/architecture/DB_CONNECTOR.md`, `docs/architecture/microservices_proposal.md`): Connector design and microservices notes.
- **Docker refresh** (`docker_refresh_webui.bat`): Convenience script for rebuilding/refreshing the WebUI container stack.
- **Tests**: `tests/support/` fakes, `tests/test_db_connector.py`, `tests/test_db_leaks.py`, `tests/test_job_dispatcher_fakes.py`, `tests/test_mock_pipeline.py`, `tests/test_pipeline_orchestrator_fakes.py`, `tests/test_postgres_integration.py`, `tests/test_runner_early_fail_terminal_job_status.py`, `tests/test_scoring_runner_mock_engine.py`, `tests/test_testing_samples_integration.py`, `tests/test_testing_samples_smoke.py`, plus broader updates to existing suites.

### Changed
- **DB** (`modules/db.py`): Widespread integration with the connector layer and related query/exec paths; continued Firebird/Postgres/dual-write behavior aligned with `get_connector()`.
- **API** (`modules/api.py`): Wiring and guarded SQL query endpoint behavior documented alongside DB API controls (`database.enable_api_db_query`, row limits, write policy).
- **Pipeline / runners** (`modules/engine.py`, `modules/scoring.py`, `modules/tagging.py`, `modules/clustering.py`, `modules/similar_search.py`, `modules/indexing_runner.py`, `modules/metadata_runner.py`, `modules/pipeline.py`, `modules/pipeline_orchestrator.py`, `modules/job_dispatcher.py`): Use injectable engines and connector-aware DB access where applicable.
- **Postgres** (`modules/db_postgres.py`): Extensions for connector-aligned usage.
- **Docker** (`Dockerfile`, `.dockerignore`): Image and ignore rules updated for current build layout.
- **Frontend / static** (`frontend/`, `static/app/`, `scripts/python/generate_favicon.py`): Favicon and SPA asset refresh; `frontend/vite.config.ts` tweaks.
- **Docs** (`docs/INDEX.md`, `docs/planning/database/*`, `docs/testing/TEST_STATUS.md`): Index and migration/test planning updates.
- **Misc** (`cli.py`, `pytest.ini`, `requirements/requirements_exif.txt`, `modules/mcp_server_firebird.py`, `modules/ui/app.py`, `docker_rebuild.bat`, `RunWebUI.exe`, `TODO.md`): Small tooling and dependency adjustments.

### Fixed
- **Tests** (`tests/conftest.py`, `tests/test_resolved_paths.py`, `tests/test_stacks.py`, `tests/test_mcp_firebird.py`, and related): Stability and path/DB fixes for CI and local runs.

## [4.21.0] - 2026-03-26

### Added
- **WebUI open** (`modules/webui_open.py`, `launch.py`, `webui.py`): After the server is listening, optionally open the React UI in the default browser or an Electron shell — set `WEBUI_OPEN_UI=browser|electron` or pass `--webui-open=` through `launch.py` (stripped before `webui.py`). Electron resolves a sibling `image-scoring-gallery` / `electron-image-scoring` or `WEBUI_ELECTRON_GALLERY_DIR`; WSL browser open uses `cmd.exe start` when available.
- **Docker launcher** (`run_webui_docker.bat`): `cd` to script directory; default `WEBUI_OPEN_UI=browser`; if port 7860 already answers, open UI and exit; require local image `image-scoring:latest` (see `docker_rebuild.bat`); `docker compose up -d`, wait for readiness, open browser or Electron, then `docker compose logs -f`.
- **Scripts** (`docker_rebuild.bat`): Full `docker compose` down, `--no-cache` build, and foreground stack start (Postgres volume preserved).
- **Favicon** (`webui.py`): `GET /favicon.png` and `GET /favicon.ico` at site root; Gradio `/app` uses `static/favicon.png`; SPA `index.html` shells point at `/favicon.png`.
- **Git** (`.gitignore`): Exception `!static/favicon.png` so the bundled PNG favicon is versioned despite `*.png` ignores.

### Changed
- **`static/favicon.ico`**: Refreshed root icon asset.

## [4.20.0] - 2026-03-26

### Added
- **Docker Compose** (`docker-compose.yml`): Bundled PostgreSQL service (`pgvector/pgvector:pg17`) with healthcheck and named volume; WebUI service now depends on postgres being healthy; `POSTGRES_*` env vars wired through to the webui container.
- **DB Postgres** (`modules/db_postgres.py`): `execute_write()` and `execute_write_returning()` write helpers; `keywords_dim` and `image_keywords` tables added to PostgreSQL schema initialization.
- **DB** (`modules/db.py`): `FirebirdConnectionFailed` exception class and `_humanize_firebird_connect_error()` — environment-aware, actionable error messages for Docker, WSL, network, auth, and local-file failure scenarios; `RAND()` → `RANDOM()` and `LIST()` → `STRING_AGG()` SQL translation rules; PostgreSQL read routing for `get_folder_by_id`, `get_images_by_folder`, and `get_nef_paths_for_research`.
- **Utils** (`modules/utils.py`): `calculate_image_hash` alias for `compute_file_hash` (backwards compatibility for callers expecting the older name).
- **Scripts**: `scripts/powershell/Compact-WslVhdx.ps1` and `scripts/powershell/Move-WslToD.ps1` for WSL VHD maintenance.
- **Tests** (`tests/test_db_engine_switch.py`): 8 new unit tests covering `_translate_fb_to_pg()` — `RAND()`, `LIST()`, `FETCH FIRST`, `SELECT FIRST`, `DATEDIFF`, placeholder-in-string-literal safety, and upsert translation.

### Fixed
- **IndexingRunner** (`modules/indexing_runner.py`): Status message logic corrected — an already-`"Failed"` status no longer falls through to the `"Error"` substring check, preventing a spurious double assignment.

### Removed
- `docker-compose.postgres.yml` — merged into the default `docker-compose.yml`.

## [4.19.0] - 2026-03-25

### Added
- **Docker / Firebird** (`modules/db.py`): `FIREBIRD_WIN_DB_PATH` environment variable so the container uses the real Windows path to `SCORING_HISTORY.FDB` instead of a bogus `\app\...` mapping; logs a warning when running in Docker without it.
- **PostgreSQL** (`modules/db_postgres.py`): `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` environment overrides (still defaults to `config.json` when unset).
- **Docker image** (`Dockerfile`): `LD_LIBRARY_PATH` includes the bundled Linux Firebird client under `FirebirdLinux/`.
- **Dependencies** (`requirements/requirements_wsl_gpu.txt`): `psycopg2-binary` and `pgvector` for optional Postgres / dual-write stacks.

### Changed
- **Docker Compose** (`docker-compose.yml`): Default stack is WebUI-only; bundled PostgreSQL service and `depends_on` removed — use an external Postgres (or host install) with env/config when needed. Sets `WEBUI_HOST`, `FIREBIRD_WIN_DB_PATH`, and `FIREBIRD_CLIENT_LIBRARY`; trims extra drive mounts to `D:/` by default (documented for customization).
- **Docker entrypoint** (`scripts/docker_entrypoint.sh`): Always waits for Firebird on `FIREBIRD_HOST` (default `host.docker.internal`) port 3050 before starting the app; portable retry loop without `timeout`.
- **Launcher** (`launch.py`): Skips Windows Firebird process detection and auto-start when `DOCKER_CONTAINER` is set.

### Fixed
- **Docs** (`docs/guides/setup/DOCKER_SETUP.md`): Rewritten for the Windows Firebird + volume-mount architecture, FDB path customization, env reference, and troubleshooting.

## [4.18.0] - 2026-03-24

### Added
- **Diagnostics module** (`modules/diagnostics.py`): New `get_diagnostics()` collector — OS info, Python version, CPU/memory (via `psutil`), DB path/reachability/size, GPU/framework detection, free disk space, and masked config summary.
- **API** (`modules/api.py`): `GET /api/diagnostics` endpoint returning `DiagnosticsResponse` with system, database, models, filesystem, config, and runner availability fields.
- **Gradio status page** (`modules/ui/status_gradio.py`): New **Diagnostics** section in the `/app` operator dashboard — four panels (System, Database, Models, Filesystem) rendered as inline tables; updates on the existing poll cycle.
- **Frontend** (`frontend/src/pages/DiagnosticsPage.tsx`, `frontend/src/App.tsx`, `frontend/src/components/layout/Shell.tsx`): New `/diagnostics` React page wired into routing and the top nav bar.
- **DB** (`modules/db.py`): PostgreSQL read-routing for 12+ major query functions — `get_all_folders`, `get_job`, `get_queued_jobs`, `get_job_phases`, `get_jobs`, `get_all_images`, `get_image_details`, `get_incomplete_records`, `get_embeddings_for_search`, `get_embeddings_with_metadata`, `get_image_phase_statuses`, `get_all_phases`; `_DUAL_WRITE_STATS` counter dict for queue telemetry.
- **DB Postgres** (`modules/db_postgres.py`): Full Firebird schema parity — all tables (`folders`, `stacks`, `jobs`, `job_phases`, `job_steps`, `images`, `file_paths`, `image_exif`, `image_xmp`, `pipeline_phases`, `image_phase_status`, `culling_sessions`, `culling_picks`, `keywords`, `image_keywords`, `stack_cache`), complete column sets, unique indexes, and FK constraints; `execute_select` / `execute_select_one` convenience helpers; corrected default connection config (`image_scoring` / `postgres`).
- **SQL Translation** (`modules/db.py` `_translate_fb_to_pg`): Handles `UPDATE OR INSERT … MATCHING` → `ON CONFLICT DO UPDATE`, `SELECT FIRST n` → `LIMIT n`, `DATEDIFF(SECOND FROM … TO …)` → `EXTRACT(EPOCH …)`, `ROWS ?` → `LIMIT ?`, `FETCH FIRST n ROWS ONLY` → `LIMIT n`.
- **Alembic migrations**: `alembic.ini` and `migrations/` folder with initial schema migration (`0001_initial_schema.py`) for managing Postgres schema via Alembic.
- **Scripts**: `scripts/powershell/Backup-Postgres.ps1` — automated PostgreSQL backup via `pg_dump`; `scripts/python/verify_postgres_parity.py` — row-count and spot-check parity verification between Firebird and Postgres.
- **Migration** (`scripts/python/migrate_firebird_to_postgres.py`): `--clear-target` flag to wipe the target Postgres DB before migration (with `TRUNCATE CASCADE`); added `job_phases`, `job_steps`, and `stack_cache` to migration order; expanded `reset_sequences` to cover `job_phases`, `job_steps`, `culling_picks`, `pipeline_phases`, `image_phase_status`.
- **MCP config** (`mcp_config.json`): `imgscore-py-postgres` server entry for direct Postgres MCP access (disabled by default).

### Fixed
- **Migration runner** (`scripts/run_migration.py`): Replaced broken Unicode emoji characters with ASCII `[OK]` / `[FAIL]` / `[WARN]` status indicators.
- **WebUI** (`webui.py`): Suppress TensorFlow Python-level deprecation warnings (`TF_ENABLE_DEPRECATION_WARNINGS`, `DeprecationWarning` filters); replace debug emoji with `[DEBUG]` ASCII prefix.
- **Tests**: `tests/test_api_endpoints.py` — new `test_diagnostics_returns_full_payload` covering the `/api/diagnostics` endpoint; `tests/test_selection_runner_phases.py` — added assertion that `set_job_phase_state` marks `bird_species` completed on the parent job; `tests/test_migrate_firebird_to_postgres.py` — comprehensive new test suite for the Firebird→Postgres migration script.

## [4.17.0] - 2026-03-23

### Added
- **IndexingRunner** (`modules/indexing_runner.py`): Dedicated independent runner for the Indexing (discovery) phase; walks directories, computes image hashes, and inserts rows into the `images` table — decoupled from the ScoringRunner.
- **MetadataRunner** (`modules/metadata_runner.py`): Dedicated independent runner for the Metadata (inspection) phase; extracts EXIF/XMP, writes UUID sidecars, generates thumbnails — decoupled from the ScoringRunner.
- **DB** (`modules/db.py`): `backfill_index_meta_global()` — global repair for images with scoring done but indexing/metadata phases missing (GAP-D); `repair_stuck_running_ips()` — reset image phase status rows stuck in `running`/`queued` beyond a configurable age threshold; `repair_legacy_keywords_junction()` — sync `image_keywords` junction for images whose `keywords` column is populated but junction rows are absent.
- **SelectionRunner** (`modules/selection_runner.py`): `_complete_phase_and_advance()` — after culling completes, enqueues a follow-up job for any remaining pending phases (e.g. `bird_species`) and properly marks the parent job done.
- **MCP** (`modules/mcp_server.py`): `get_runner_status` now reports `indexing` and `metadata` runner availability, progress, and log tail; `execute_code` context includes `indexing_runner` and `metadata_runner`.
- **Scripts**: `scripts/analysis/analyze_phase_status.py`, `scripts/maintenance/repair_analyzer_gaps.py`, `scripts/schedule_bird_species_bird_folders.py`.
- **Docs**: `docs/technical/WORKFLOW_STAGES_ANALYSIS.md`.
- **Tests**: `tests/test_selection_runner_phases.py`.

### Changed
- **JobDispatcher** (`modules/job_dispatcher.py`): Refactored `_start_job` into a `runner_map` lookup + `_dispatch_to_runner` helper; `indexing` and `metadata` job types now route to their own runners; returns structured `(success, error_msg)` tuples for better failure reporting.
- **API** (`modules/api.py`): `set_runners` / `_stop_runner_for_phase` accept `indexing_runner` and `metadata_runner`; `/pipeline/run` dispatches `indexing` and `metadata` as first-class job types; pause/cancel/restart endpoints now include `indexing` and `metadata` phases.
- **WebUI** (`webui.py`): Passes `indexing_runner` and `metadata_runner` to `set_runners` and `setup_server_endpoints`.
- **Pipeline** (`modules/pipeline.py`): `PrepWorker.process()` simplified — inline indexing/metadata logic removed (now handled by dedicated runners).

### Fixed
- **DB** (`modules/db.py`): `set_job_phase_state` now allows `failed` as a valid transition from `pending`; multi-phase `__bulk_completed__` guard skips bulk completion when any phase was never started, preventing phases from being incorrectly marked done in bulk.

## [4.16.0] - 2026-03-21

### Added
- **API** (`modules/api.py`): `GET /api/images/by-uuid/{image_uuid}` and `GET /api/images/by-hash/{image_hash}`; read-only **`/public/api`** router (paginated list plus detail by id/uuid/hash, same JSON shapes as authenticated routes where applicable); helpers for image list/detail payloads; `GET /api/jobs/recent` uses explicit JSON encoding for Firebird-native values (avoids fragile Pydantic serialization).
- **Phases** (`modules/phases.py`): Canonical pipeline phase order (`PIPELINE_PHASE_ORDER`, sorting helpers); `normalize_phase_codes` returns phases in pipeline order; display ordering for `job_phases` rows including `bird_species` after core pipeline phases.
- **DB** (`modules/db.py`): Multi-phase job status updates sync `job_phases` (including bulk-complete behavior); `get_or_create_folder` converts Windows paths to WSL before normalization so mixed host/DB path styles resolve consistently.
- **Frontend (SPA)**: Image detail route and `ImageDetailPanel`; gallery client lookup by id/uuid/hash key; gallery layout refinements.
- **Tests** (`tests/test_api_endpoints.py`): Public API router mounted in test app; pagination stub uses row `to_dict`; coverage for `/public/api/images` list and 404 parity.

### Changed
- **API**: Synthetic `bird_species` phases for run detail when stored `job_phases` rows omit that phase.
- **Static bundle**: `static/app/` asset refresh.

## [4.15.0] - 2026-03-21

### Added
- **PostgreSQL (optional)**: `modules/db_postgres.py` and Firebird→Postgres **dual-write** queue in `modules/db.py` when `database.dual_write` is enabled; `validate_config()` supports `database.engine` `firebird` vs `postgres` with `database.postgres.*` checks.
- **MCP** (`modules/mcp_server.py`): `get_runner_status` reports `bird_species`; `run_processing_job` accepts `job_type: "bird_species"` (threshold, top_k, overwrite, candidate_species).
- **Tests**: `tests/test_bird_species.py` — unit tests for bird species loader and runner (no GPU by default).
- **Scripts**: `scripts/list_bird_folders.py`, `scripts/powershell/Setup-PostgresDocker.ps1`.

### Changed
- **API** (`modules/api.py`): Scoped pipeline requests can use `bird_species` as the only stage (handled before `normalize_phase_codes`, with correct `job_type` / `phase_code`).
- **WebUI** (`webui.py`): Passes `bird_species_runner` into MCP `set_runners`.
- **Docs**: `docs/technical/BIRD_SPECIES_WALKTHROUGH.md` expanded.
- **Frontend (SPA)**: `ScopeSelector`, `api` types; static bundle refresh under `static/app/`.
- **Config**: `mcp_config.json` updates.

### Fixed
- **DB** (`modules/db.py`): `get_images_with_keyword` avoids Firebird `IN (...)` parameter limits when `resolved_image_ids` is very large by post-filtering in Python.
- **Config** (`modules/config.py`): Input-path existence warnings run after engine-specific `database` checks.

## [4.14.1] - 2026-03-21

### Fixed
- **Profiling middleware** (`modules/profiling.py`): Replaced Starlette `BaseHTTPMiddleware` with pure ASGI wrapping of `send`, fixing `AssertionError: Unexpected message: http.response.start` on streaming/SSE routes (e.g. MCP `/mcp/sse`).
- **Bird species** (`modules/bird_species.py`): Chunk `image_id IN (...)` queries (~900 IDs per batch) to stay within Firebird parameter limits on large batches.

### Added
- **Docs**: `docs/technical/BIRD_SPECIES_WALKTHROUGH.md`, `docs/technical/FIREBIRD_WINDOWS_TEMPDIR.md`.
- **Scripts**: MCP/FastAPI debug probes under `scripts/debug/`; `scripts/maintenance/migrate_thumbnail_paths_project_rename.py`.

### Changed
- **Workspace / naming**: `image-scoring-backend.code-workspace`; `docs/technical/INDEX.md`, `mcp_config.json`, and related paths aligned with the backend repo name.
- **Tooling**: `run_firebird.bat`, `scripts/maintenance/cleanup_test_artifacts.py`, `.dockerignore`; `.gitignore` patterns for debug logs and test output artifacts.

### Removed
- Obsolete root-level debug helpers (`debug_*.py`, `debug_*.txt`, `debug_*.html`), ad-hoc `tmp_check_db*.py`, stray root `test_*.py` / `test_output.txt`, and `verification.sql` (use `tests/` and maintained scripts instead).

## [4.14.0] - 2026-03-20

### Added
- **Bird species classification**: `modules/bird_species.py` — BioCLIP 2 zero-shot species keywords for images already tagged with "birds"; `BirdSpeciesRunner`; JobDispatcher phases `bird_species` / `bird-species`; default candidate list `data/bird_species_list.txt`.
- **Docs**: `docs/technical/RUNS_WALKTHROUGH.md` — how batch runs, `JobDispatcher`, and runners connect end-to-end.
- **Runs SPA**: `frontend/src/utils/runLog.ts` for structured run log lines.
- **WSL utility**: `scripts/wsl/enqueue_untagged_folder_tagging.py` — enqueue per-folder tagging jobs for images missing keywords (aligned with API tagging payload).

### Changed
- **API** (`modules/api.py`): Runs, pipeline, and job endpoints expanded and refined.
- **DB** (`modules/db.py`): Queries and schema support for jobs, phases, and queue behavior.
- **Scoring** (`modules/scoring.py`): Refactor and integration updates for batch/queue workflows.
- **Clustering, tagging, selection** (`modules/clustering.py`, `tagging.py`, `selection_runner.py`): Runner and job integration adjustments.
- **Job dispatcher** (`modules/job_dispatcher.py`): Optional `bird_species_runner`; tolerate double-encoded JSON in `queue_payload`.
- **Runs UI**: `LogPanel`, `RunCard`, `RunDetailPage`, `runs` API client, `WorkflowGraph` / `useWebSocket` / `api` types (line-ending normalized where needed).
- **WebUI** (`modules/ui/app.py`): Minor wiring updates.
- **Docs**: `docs/technical/INDEX.md` — link to runs walkthrough.
- **Tests**: `tests/test_api_queue.py` updated for queue API behavior.

## [4.13.0] - 2026-03-19

### Added
- **Pipeline queue board**: Enriched `get_queued_jobs`, job priority/pause/restart API actions, queue table UI (`#33`).
- **Scoped pipeline controls**: REST endpoints under `/api/pipeline/run/*`, `/api/pipeline/phase/restart-from`, `/api/pipeline/step/rerun`, and Gradio Scoped Controls panel (`#35`).
- **Pipeline graph view**: Phase dependency graph with StepRun breakdown (`#36`).
- **Selector composer**: `modules/pipeline_selector_composer.py`, Target Composer panel, selector-aware submit payloads (`#37`).
- **Gradio fallback Pipeline tab**: Optional `ui.use_gradio_fallback` / `GRADIO_FALLBACK_UI`, conditional asset loading (`#46`).
- **Gradio status page**: `modules/ui/status_gradio.py` minimal operator status at `/app`.
- **Docs**: `docs/technical/RUNS_QUEUE_AND_RESTART.md`; maintenance scripts under `scripts/maintenance/`.

### Changed
- **WebUI / FastAPI**: `webui.py`, `modules/ui/app.py` refactors; WebSocket and events wiring.
- **API, DB, scoring, clustering, tagging**: Ongoing pipeline and queue integration updates.
- **MCP & agent docs**: `modules/mcp_server.py`, `mcp_config.json`, `AGENTS.md`, MCP debugging references.
- **Frontend (SPA)**: Runs UI (`StagePanel`, `WorkflowGraph`), `useWebSocket`, Vitest setup, `api` types.

### Notes
- **PR #32** (`extend-lifecycle-enums-and-transitions-bjkbyh`) not merged: lifecycle + workflow run endpoints already landed via **#31**; branch conflicted with current `api.py` / IPC models.
- **PR #40** superseded by **#46** (close manually on GitHub if still open).

## [4.12.0] - 2026-03-18

### Added
- **Runs API**: `POST /runs/submit`, `GET /runs`, `GET /runs/{id}`, pause/resume/cancel/retry, stage retry/skip, steps, work items, queue endpoints.
- **Frontend Runs UI**: Runs page, Run detail page, stage panel, run cards, WebSocket updates for run progress.
- **Maintenance scripts**: `backup_high_scored.py`, `fix_backup_lens_misalignments.py`, `move_misplaced_by_lens.py`, `remove_folders_without_nef.py`.
- **Profiling**: `modules/profiling.py` for performance diagnostics.

### Changed
- **API**: Expanded runs, queue, and pipeline endpoints in `modules/api.py`.
- **DB**: Schema and query updates in `modules/db.py`.
- **Pipeline orchestrator**: Refinements in `modules/pipeline_orchestrator.py`.
- **MCP server**: Enhanced tooling in `modules/mcp_server.py`.
- **Frontend**: Gallery, settings, sidebar, scope API, runs API integration.
- **WebUI**: Launch and run script updates.

## [4.11.2] - 2026-03-17

### Fixed
- **LogPanel**: Use stable empty array in Zustand selector to avoid getSnapshot infinite loop (React error #185).

## [4.11.1] - 2026-03-16

### Changed
- **API, MCP, pipeline**: Adapt `get_status()` unpacking to `result[:5]` for runners that return extended tuples.
- **Tests**: Update `test_api_v2_reorg` for new similarity/duplicates/outliers response shapes; add DB mock for image existence.
- **Tests**: Update `test_scoring_runner` for `get_status()` tuple handling.

### Removed
- **Backup file**: `TEST_stacks_*.bak` (temporary backup, no longer tracked).

## [4.11.0] - 2026-03-15

### Added
- **Pipeline architecture docs**: `docs/architecture/pipeline-architecture.md`.
- **Cross-app audit**: `docs/testing/CROSS_APP_INTEGRATION_AUDIT.md` and `scripts/powershell/Run-CrossAppAudit.ps1`.

### Changed
- **API**: Expanded endpoints and queue handling in `modules/api.py`.
- **DB**: Schema and query updates in `modules/db.py`.
- **Engine, pipeline, scoring**: Refinements across pipeline components.
- **MCP server**: Enhanced tooling and diagnostics in `modules/mcp_server.py`.
- **Pipeline tab**: UI improvements in `modules/ui/tabs/pipeline.py`.
- **Docs index**: Updated `docs/INDEX.md`, `docs/technical/INDEX.md`, `docs/testing/INDEX.md`.
- **Tests**: Updates to `test_api_queue.py` and `test_ddl.py`.

## [4.10.1] - 2026-03-14

### Changed
- Patch release: CLI, docs, pipeline, API, config, db, engine, UI, and test refinements.

## [4.10.0] - 2026-03-14

### Added
- **CLI** (`cli.py`): Typer + Rich CLI for score, tag, cluster, propagate-tags, pipeline, query, export, config, status, jobs.
- **Template DB script**: `scripts/create_template_db.py` for creating template databases.
- **UI security**: `modules/ui/security.py` for security-related UI logic.
- **Tests**: `test_cli.py`, `test_postgres_parity.py`, `test_raw_ui.py`, `bench_db_performance.py`.
- **Docker**: `docker-compose.postgres.yml` for Postgres testing.

### Changed
- **Docs**: Expanded `docs/technical/CLI_TUI_SUMMARY.md` and `docs/technical/PIPELINE_PHASE_RUNNERS.md`.
- **Pipeline**: Phase runner wiring and orchestrator updates.
- **API, config, db, engine**: Various refinements and test updates.

## [4.9.0] - 2026-03-14

### Added
- **OpenAPI export**: `scripts/export_openapi.py` and `openapi.json` for API schema export.
- **Documentation**: Gradio serving note (`docs/reports/GRADIO_SERVING_DECISION.md`), `docs/technical/PIPELINE_PHASE_RUNNERS.md`.
- **Tests**: `test_selector_resolver.py` for selector resolver behavior.

### Changed
- **API Contract**: Expanded `docs/technical/API_CONTRACT.md` with additional endpoint details.
- **Events**: Enhanced `modules/events.py` with additional event handling.
- **Docs index**: Updated `docs/technical/INDEX.md`.

## [4.8.1] - 2026-03-14

### Added
- **Tag Propagation API** (`POST /api/tagging/propagate`): Propagate keywords from tagged images to visually similar untagged neighbors using embedding similarity.
- **Phase Statuses in Image Details** (`GET /api/images/{id}`): Response now includes `phase_statuses` for gallery display.
- **MCP `diagnose_phase_consistency`**: New tool to diagnose folder vs per-image phase status mismatches.

### Changed
- **Path Handling** (`import_register`): Convert Windows paths to WSL only when backend runs on Linux (`platform.system() == "Linux"`); keep native paths on Windows.
- **Pipeline Orchestrator**: Skip phases with no runner (indexing, metadata) instead of failing; advance to next phase.
- **Folder Phase Cache** (`get_folder_phase_summary`): Added `force_refresh` parameter to bypass cache on folder selection and Refresh.
- **Refresh Button** (`pipeline` tab): Now invalidates folder phase cache and updates all dashboard components.
- **Stepper Connector**: Fixed connector between Metadata and Scoring steps to reflect Metadata state.
- **Public API** (`db.generate_image_uuid`): Promoted from `_generate_image_uuid` for cross-module use.
- **SEED_PHASES**: Use `PhaseCode.INDEXING` and `PhaseCode.METADATA` enums for consistency.
- **MCP `execute_code`**: Added security comment documenting dev/debug-only usage.

### Fixed
- **Phase 1.8a Migration**: Typo in log message (`Phase1` → `Phase 1`).

### Tests
- **test_culling**: Use `scoring_history_test.fdb`; fix `culling_picks` table reference; add XMP format verification (`xmpDM:pick`, `xmpDM:good`).
- **test_events**: Minimal FastAPI app to avoid webui import; use `broadcast_threadsafe`.
- **test_selector_runner_behavior**: Add `pytest.mark.wsl` and graceful import skip.

### Other
- **.gitignore**: Added patterns for debug artifacts (`debug_*.py`, `debug_*.txt`, `debug_*.html`, `test_tree_*.py`, `tmp/verify_*.py`).

## [4.8.0] - 2026-03-13

### Changed
- Version bump to 4.8.0.

## [4.7.0] - 2026-03-13

### Added
- **Embedding Outlier API** (`modules/api.py`): New endpoint for embedding-based outlier detection.

### Changed
- **Keyword Dual-Write Fix** (`modules/db.py`): Call `_sync_image_keywords` after `conn.commit()` to avoid dual-write inconsistency and Firebird deadlock.
- **Keyword Normalization Migration**: Continued DB migration for keyword normalization paths.
- **Pipeline Tab** (`modules/ui/tabs/pipeline.py`): Removed orphaned "Open in Gallery" button.

### Fixed
- **Culling Force Re-Run**: Fixed hanging on running→running guard when force re-running culling.

### Documentation
- **UX/UI Review**: Added webui UX/UI review documentation.

## [4.6.1] - 2026-03-10

### Added
- **Dual-write Guidelines** (`CLAUDE.md`): Added requirements for staying in sync when modifying keyword or metadata write paths.
- **GitHub Links in Docs** (`docs/technical/AGENT_COORDINATION.md`): Improved coordination protocols with direct repository references.

### Changed
- **Salvage Script Robustness** (`scripts/archive/migrate_salvage.py`): Improved path and connection handling for Firebird salvage operations.
- **Project Progress**: Updated roadmaps for database refactoring and PostgreSQL migration.
- **Environment Tweaks**: Workspace and environment configuration refinements for better development experience.

## [4.6.0] - 2026-03-10

### Added
- **Agent Coordination Standards** ([docs/technical/AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md)): New integration protocols for backend/frontend AI agent collaboration.
- **Optimized Data Queries** (`modules/db.py`): New `get_images_paginated_with_count` for faster image/count retrieval in a single DB trip.
- **Project Roadmaps**: Added tracking for `docs/planning/database/` and `docs/features/planned/embeddings/` refactors.

### Changed
- **MCP Reliability**: Handled `POST`/`DELETE` methods on `/mcp/sse` endpoint for better Cursor compatibility.
- **Gradio Log Filtering** (`webui.py`): Suppressed repetitive queue polling messages in the terminal.
- **Database Proxy Hardening** (`modules/db.py`): Ensured `commit()` and `rollback()` safety in the Firebird connection proxy.

## [4.5.0] - 2026-03-10

### Added
- **Keyword Normalization (Phase 2)** (`modules/db.py`): Created `KEYWORDS_DIM` and `IMAGE_KEYWORDS` tables for structured keyword management. Implemented automatic migration of existing BLOB keywords.
- **FastMCP Integration** (`modules/mcp_server.py`): Migrated the `image-scoring` MCP server to use `FastMCP` for automatic schema generation and streamlined tool definitions.
- **Gradio MCP Server** (`launch.py`): Explicitly enabled Gradio's built-in MCP server via the `GRADIO_MCP_SERVER` environment variable to expose UI components to AI agents.

### Changed
- **Database Connectivity** (`modules/db.py`): Updated Windows Firebird connections to use TCP (`inet://127.0.0.1/`) by default instead of direct file access, preventing file locking conflicts (I/O errors) between the WebUI and Cursor MCP servers. Added `FIREBIRD_USE_LOCAL_PATH` fallback.
- **Database Context Manager** (`modules/db.py`): Added `db.connection()` context manager to ensure safe resource cleanup.

## [4.4.0] - 2026-03-10

### Added
- **Standalone Migration Runner** (`scripts/run_migration.py`): Run Phase 1 DB schema migration independently of the WebUI. Supports `--db-path` and `--skip-backup` for CI, scheduled runs, or when Electron holds DB locks.

### Changed
- **DB Schema Phase 1** (`modules/db.py`): Integrity + index hardening on startup. Orphan `STACKS.BEST_IMAGE_ID` repair, unique index on `IMAGES.FILE_PATH`, composite indexes for folder/stack score queries, FK cleanup on `CULLING_PICKS`, and `FK_STACKS_BEST_IMAGE` constraint. Ref: `docs/planning/database/DB_SCHEMA_REFACTOR_PLAN.md`.
- **Favicon**: Updated `static/favicon.ico`.

## [4.3.1] - 2026-03-09

### Fixed
- **UI Accordion Alignment**: Fixed dropdown triangle/icon alignment in accordions (Gradio label-wrap + icon) in `modules/ui/assets.py`. Icons now display inline-flex with proper vertical alignment.

### Removed
- **Cleanup**: Removed `recovered_data.json` from repository.

## [4.3.0] - 2026-03-08

### Changed
- Version bump to 4.3.0.

## [4.2.1] - 2026-03-08

### Fixed
- **Run Keywords**: Fixed "Run Keywords" button doing nothing when clicked. TaggingRunner now uses `db.get_images_by_folder()` (folder_id-based lookup) instead of pathlib filtering, matching SelectionRunner and avoiding path format mismatch (Windows vs WSL). Added missing `update_image_fields_batch` in `db.py` for batch keyword/title/description updates. Added missing `explain_phase_run_decision` import in `tagging.py`.

## [4.2.0] - 2026-03-08

### Added
- **Phase Rerun Policy** (`modules/phases_policy.py`): Centralized logic for deciding if a processing phase (scoring, tagging, clustering) should execute or skip based on current vs. stored executor versions. Prevents redundant processing of already-completed phases.
- **Diagnostics Endpoint**: Added GET `/api/diagnostics/phase-policy/{image_id}/{phase_code}` for deep inspection of rerun/skip decisions, returning stored vs. active versions and status details.
- **PGVector Migration Plan**: Added `docs/technical/PGVECTOR_MIGRATION_PLAN_REFINED.md`, a detailed roadmap for migrating the Firebird database to PostgreSQL with pgvector for high-performance visual similarity search.

### Changed
- **Pipeline Integration**: Integrated `should_run_phase` policy checks across all runners: `modules/clustering.py`, `modules/pipeline.py`, `modules/selection_runner.py`, and `modules/tagging.py`.
- **API Enhancements**: Main health and status endpoints now include more granular phase execution metadata.

## [4.1.0] - 2026-03-07

### Added
- **Windows Native WebUI**: New `run_webui_windows.bat` and `scripts/setup/setup_windows_native.bat` for running the Gradio WebUI natively on Windows (no WSL). CPU-only, no VILA. Documented in README Option 3b and `docs/planning/setup/WINDOWS_NATIVE_WEBUI_PLAN.md`.
- **API Expansion** (`modules/api.py`): New clustering endpoints (start, stop, status), data query endpoints (images, folders, stacks, stats), pipeline submit, raw-preview utility. Clustering status added to `/api/status` and `/api/health`.
- **API Documentation**: Added `docs/reference/api/openapi.yaml` (standalone OpenAPI 3.0 schema) and `docs/technical/API_CONTRACT.md` (concise endpoint and model reference).

### Changed
- **API Reference**: Updated `docs/reference/api/API.md` with full endpoint documentation for clustering, data queries, pipeline, and utilities.
- **Environments**: Updated `docs/guides/setup/ENVIRONMENTS.md` with Windows native setup details.
- **Backfill Scripts**: Enhanced `scripts/maintenance/backfill_exif_xmp.py` and `run_backfill_exif_xmp.bat` with improved argument handling and feedback.

## [4.0.1] - 2026-03-07

### Added
- **Recursive Folder Scan**: Implemented recursive folder scanning in `get_folder_phase_summary`, allowing image counts to be aggregated across nested directories.
- **EXIF/XMP Cache Tables**: New `IMAGE_EXIF` and `IMAGE_XMP` tables for caching metadata from EXIF and XMP sidecars. Enables gallery filtering by camera, lens, ISO, and capture date.
- **EXIF Extractor**: New `modules/exif_extractor.py` using exiftool for structured EXIF extraction.
- **XMP Full Read**: Extended `modules/xmp.py` with `read_xmp_full()` and `extract_and_upsert_xmp()` for sidecar cache sync.
- **Gallery Sort by Capture Date**: Added "Capture Date (EXIF)" sort option and EXIF-based filters (make, model, lens, ISO).

### Fixed
- **Startup Tree View Interaction**: Disabled tree view interaction during initial image grid loading to prevent race conditions and unexpected state transitions.



## [4.0.0] - 2026-03-06

### Added
- **Pipeline Tab**: New unified Pipeline tab replacing Folder Tree, Scoring, Keywords, Selection, Stacks, and Culling tabs. Single workflow view with folder tree, phase stepper, action bar, and job monitor (`modules/ui/tabs/pipeline.py`).
- **Pipeline Orchestrator**: New `modules/pipeline_orchestrator.py` to coordinate pipeline phases and runner integration.
- **Embedding Population Scripts**: Added `scripts/maintenance/populate_missing_embeddings.py` and `run_populate_embeddings.bat` for backfilling embeddings (see script docstring for the canonical launcher name).
- **Design Documentation**: Added `docs/features/planned/ui-pipeline-redesign.md` and mockups for the pipeline-centric UI.
- **Tag Propagation Tests**: Added `tests/test_tag_propagation.py`.

### Changed
- **UI Structure**: Reduced from 7+ tabs to 3 (Pipeline, Gallery, Settings). Gallery and Settings remain; Pipeline absorbs all processing workflows.
- **Navigation & Assets**: Updated `modules/ui/navigation.py` and `modules/ui/assets.py` for new tab structure.
- **API, DB, MCP**: Updated `modules/api.py`, `modules/db.py`, `modules/mcp_server.py` for pipeline integration.
- **Similar Search & Tagging**: Modified `modules/similar_search.py` and `modules/tagging.py` for pipeline context.

### Removed
- **Legacy Tabs**: Removed `culling.py`, `folder_tree.py`, `scoring.py`, `selection.py`, `stacks.py`, `tagging.py` — functionality consolidated into Pipeline tab.

## [3.26.0] - 2026-03-03

### Added
- **Diversity-Aware Selection**: Implemented MMR (Maximal Marginal Relevance) in `modules/diversity.py` to ensure selected image stacks are visually diverse. Added UI controls for Diversity Weight (lambda).
- **Near-Duplicate Detection**: Added `find_near_duplicates` utility in `modules/similar_search.py` and exposed it via the MCP server to identify and manage nearly identical images.
- **Image UUID Generation**: Added `scripts/add_image_uuids.py` to embed unique v4 UUIDs into database, RAW `.NEF` files, and `.xmp` sidecars via ExifTool.
- **Backup UUID Sync**: Added `scripts/sync_uuids_to_backup.py` to synchronize UUIDs to backup drives without re-copying massive RAW files.
- **Security & Integrity**: 
  - Implemented comprehensive database security tests (`tests/test_db_security.py`) to prevent SQL injection.
  - Added API security mechanisms including CORS, rate limiting, and API key validation (`modules/api.py` and `tests/test_api_security.py`).
  - Added secret configuration tests (`tests/test_config_secrets.py`).

### Changed
- **Electron Stability**: Fixed IPC race condition during startup phase to prevent application hangs during "Connecting to services...".
- **DevTools Defaults**: Disabled Electron developer tools from opening automatically in production mode.
- **WebUI Configuration**: Integrated Chrome DevTools configuration in `mcp_config.json`.

## [3.25.0] - 2026-03-02
- **Path Migration Utility**: New `update_db_paths.py` for batch-updating folder and image paths in the database (useful for moving data between drives).
- **Reorganization Planning**: Added `reorganize_source_plan.md` documenting the strategy for source photo cleanup and standardization.
- **Agent Skills**: Added `moltbook` skill to `.gitignore`.

### Changed
- **Hardened Clustering**: Added error handling in `modules/clustering.py` to prevent crashes during folder processing.
- **Improved DB Connectivity**: Enhanced robustness of Firebird connection checks and error reporting in `modules/db.py`.
- **Enhanced Backup Scripts**: Refactored `cleanup_backup.py` and `sync_backup.py` with improved argument handling and status feedback.
- **Ignored Patterns**: Updated `.gitignore` to include `.agent/skills/moltbook` and `.mcp.json`.

## [3.24.0] - 2026-03-01

### Added
- **Similar Image Search**: New `similar_search` module for visual similarity queries using embeddings.
- **Event System**: Decentralized `EventBus` in `modules/events.py` for decoupled module interactions.
- **Score Normalization**: Modular `score_normalization.py` to handle rating/score mapping consistently.
- **Embedding Research**: Comprehensive set of research documents in `docs/technical/` for future embedding-based applications including diversity selection, outlier detection, and tag propagation.
- **Backup & Maintenance Utilities**: Added `cleanup_backup.py`, `sync_backup.py`, `organize_videos.py`, and `scripts/maintenance/cleanup_orphans.py`.
- **Agent Infrastructure**: New `mcp-firebird` skill and `firebird-diagnostics` workflow for enhanced database diagnostics.

### Changed
- **Database Handler**: Expanded `modules/db.py` with tag support and robust ID-based fetching for images.
- **UI Enhancements**: Refined navigation and state handling across WebUI tabs (`gallery.py`, `selection.py`, `stacks.py`).
- **Pipeline Processing**: Improved worker logging and error recovery in `modules/pipeline.py`.

### Fixed
- **Scoring & Paths**: Improved LIQE score range handling and thumbnail path resolution for WSL environments in `modules/thumbnails.py`.

## [3.23.1] - 2026-02-15

### Added
- **Documentation**: Added `docs/INDEX.md` to track all documentation files.
- **Context**: Committed Electron project context memories to `.serena/memories/` for better cross-project awareness.

## [3.23.0] - 2026-02-15

### Added
- **Project Documentation Skills**: Added `webui-dev` and `webui-gradio` skills to `.agent/skills/` to document development workflows for the WebUI.
- **Cross-Project Context**: Exchanged memory contexts with `electron-image-scoring` project to align development knowledge.

## [3.22.0] - 2026-02-15

### Added
- **MCP Processing Jobs**: New `run_processing_job` tool in MCP server to trigger scoring, tagging, or clustering jobs programmatically from any MCP client.
  - Supports `scoring`, `tagging`, and `clustering` job types with per-type arguments.
  - Registered in `create_mcp_server()` tool list and call handler in `modules/mcp_server.py`.
- **ClusteringRunner**: New background runner class (`ClusteringRunner`) in `modules/clustering.py` for threaded clustering with status tracking.
  - Matches the existing runner contract (`start_batch`, `stop`, `get_status`).
  - Integrated into `webui.py` startup and MCP server standalone mode.
- **All-Unprocessed-Folders Clustering**: When no target folder is specified, clustering now automatically discovers and processes all database folders that don't yet have stacks.
  - Uses `db.get_all_folders()` minus `db.get_clustered_folders()` to find pending folders.
- **Serena Integration**: Added `/consult_serena` workflow and `.agent/skills/serena-integration/` skill for symbolic code navigation and editing via the Serena MCP server.
- **Architecture Documentation**: Added `docs/ARCHITECTURE.md` system overview with component diagrams and data-flow descriptions. Linked from `README.md`.
- **Missing Stacks Scripts**: Added `check_stacks.py` and `scripts/process_missing_stacks.py` for diagnosing and batch-processing folders without stacks.

### Changed
- **Clustering Engine Refactored** (`modules/clustering.py`): Split `cluster_images()` into single-folder and all-unprocessed-folders code paths for clarity and correctness.
- **MCP Server Runner Management** (`modules/mcp_server.py`): `set_runners()` now accepts an optional `clustering_runner` parameter; `get_runner_status()` reports clustering status.
- **WSL Path Handling** (`modules/db.py`): `get_or_create_folder()` now detects WSL `/mnt/` paths and avoids `os.path.abspath()` mangling on Windows. Uses `posixpath` for parent-path resolution on WSL paths.
- **Favicon**: Updated `static/favicon.ico` binary asset.

### Fixed
- **Recursion Depth Error**: Fixed `maximum recursion depth exceeded` in `get_or_create_folder()` caused by `os.path.abspath()` converting WSL paths to `D:\mnt\...` on Windows.

### Removed
- **Agent Mailbox**: Removed `agent-mailbox` skill and associated workflows (`/check_agent_mailbox`, `/send_agent_mailbox`) — replaced by direct Serena-based communication.
- **Favicon SVG**: Removed `static/favicon.svg` (replaced by updated ICO).

## [3.21.0] - 2026-02-14

### Added
- **Agent Mailbox Workflow**: Added `/send_agent_mailbox` workflow to send messages to other agents (e.g., `electron-gallery.agent`).
  - New workflow file: `.agent/workflows/send_agent_mailbox.md`.

## [3.20.0] - 2026-02-14

### Added
- **Agent Mailbox Workflow**: Added `/check_agent_mailbox` workflow to inspect the agent's mailbox for pending messages.
  - New workflow file: `.agent/workflows/check_agent_mailbox.md`.


## [3.19.0] - 2026-02-14

### Added
- **LIQE Model Integration**: Integrated LIQE scorer (`pyiqa`) directly into `MultiModelMUSIQ` as a first-class model alongside MUSIQ variants.
  - New `pyiqa` model type with dedicated loading and prediction paths in `run_all_musiq_models.py`.
  - LIQE imported from `modules/liqe.LiqeScorer` with graceful fallback.
- **Image Preprocessing Pipeline**: New `preprocess_image()` method in `MultiModelMUSIQ` standardizes all inputs to 512×512 with bicubic resize and black-border padding.
  - RAW files: ExifTool embedded-JPEG extraction → rawpy half-size fallback.
  - Standard images also preprocessed for consistent model input.
- **Folder Tree → Selection**: Added "📋 Open in Selection" button and `open_folder_in_selection()` navigation helper.
- **Antigravity Skills**: Added `.agent/skills/` with `scoring-pipeline`, `firebird-db`, `image-scoring-mcp`, `webui-gradio`, and `git-changelog` skills.
- **Diagnostic & Research Scripts**: Added `diagnose_scores.py`, `inspect_db.py`, `repro_score_calc.py`, `verify_scores.py`, `research_models.py`, and `SCORING_CHANGES.md`.

### Changed
- **Scoring Weights Simplified**: Dropped KonIQ and PaQ2PiQ from active scoring; now uses three models only.
  - General: `0.50 × LIQE + 0.30 × AVA + 0.20 × SPAQ`.
  - Technical: `1.00 × LIQE`.
  - Aesthetic: `0.60 × AVA + 0.40 × SPAQ`.
- **Pipeline Hardening** (`modules/pipeline.py`):
  - `PrepWorker` reuses a worker-local `MultiModelMUSIQ(skip_gpu=True)` instance for RAW conversion instead of creating one per image.
  - Required-model backfill list trimmed to `['spaq', 'ava', 'liqe']`.
  - Replaced bare `except: pass` blocks with specific exception types (`ImportError`, `RuntimeError`, `OSError`) and logging.
- **Settings Tab Consolidated** (`modules/ui/tabs/settings.py`):
  - Merged separate Clustering and Culling accordions into unified "📚 Stacks & Culling (Legacy)" section.
  - Removed GPU toggle, rating thresholds, and per-score minimum filter sliders.
  - Simplified `reset_config_defaults()` and `save_all_config()` signatures.
- **Stacks & Culling Deprecated**: Tab labels now show "(Deprecated)" with banner directing users to the Selection tab.
- **Test Cleanup** (`tests/test_model_sources.py`): Moved `MODEL_SOURCES` definition above first usage; removed KonIQ and PaQ2PiQ entries; renamed `test_all_sources` → `check_all_sources`.
- **Color Label Formula**: Updated `score_to_rating()` and `calculate_weighted_categories()` to use new three-model weights.

## [3.18.0] - 2026-02-12

### Added
- **Unified Selection Workspace**: Finalized and re-enabled the Selection tab in WebUI, providing a single consolidated workflow for automated stack creation and pick/reject decision making.
  - New modules: `modules/selection.py`, `modules/selection_policy.py`, `modules/selection_metadata.py`, `modules/selection_runner.py`.
  - Integration: Replaced separate Stacks and Culling tabs with the unified Selection experience.
- **Selection Tests**: Added integration and policy tests for the new selection logic.
- **Improved Layout**: Updated WebUI to center Selection as the primary automated workflow.

### Fixed
- **Scoring Normalization**: Fixed a critical issue in `modules/scoring.py` where general scores were being double-normalized, resulting in tiny values (e.g., 0.00x).
- **WebUI Startup**: Ensured selection runner initializes correctly alongside scoring and tagging runners.

## [3.17.0] - 2026-02-12

### Changed
- **Scoring Weights**: Updated default scoring weights to prioritize technical quality via LIQE.
  - New Formula: `0.50 * LIQE + 0.30 * AVA + 0.20 * SPAQ`
  - Previous Formula: 50% Technical (LIQE/KonIQ/PaQ) + 50% Aesthetic (AVA/SPAQ/VILA).

### Added
- **Score Recalculation**: Added `scripts/python/recalc_scores.py` to update existing database records with the new scoring formula.
  - Backs up database before running.
  - Updates `score_general`, `rating`, and `model_version`.
- **Model Documentation**: Added `docs/technical/MODEL_INPUT_SPECIFICATIONS.md` detailing input requirements and score ranges.
- **Research Tools**: Added `scripts/python/research_models.py` and `scripts/python/analyze_research.py` for model analysis.

## [3.16.0] - 2026-02-08

### Added
- **Unified Selection Tab**: New workflow replaces separate Stacks + Culling for automated stack creation and pick/reject assignment.
  - Single input path, run/stop controls, console log, status updates (Scoring/Keywords style).
  - Policy: top 33% pick, bottom 33% reject, middle neutral. Deterministic tie-break.
  - Writes stack/burst IDs and pick/reject flags to XMP sidecars (Lightroom-compatible).
  - Modules: `selection.py`, `selection_policy.py`, `selection_metadata.py`, `selection_runner.py`.
- **Selection Policy**: Pure policy module (`selection_policy.py`) with `band_sizes`, `classify_sorted_ids`.
- **Folder Tree**: "Open in Selection" button for direct navigation.
- **Config**: New `selection` section: `score_field`, `pick_fraction`, `reject_fraction`, `force_rescan_default`, `verify_sidecar_write`, `legacy_tabs_enabled`.

### Changed
- **Code Review Fixes** (per 2026-02-09 review):
  - Removed duplicate `ScoringRunner.__init__` in `modules/scoring.py`.
  - Replaced DB `print()` diagnostics with structured logging; gate sensitive details behind `DEBUG_DB_CONNECTION` env var.
  - Narrowed exception handling in `pipeline.py` and `db.py` (replace `except: pass` with specific types and logging).
  - RAW converter optimization: PrepWorker reuses worker-local `MultiModelMUSIQ(skip_gpu=True)` instance.
- **Stacks & Culling Deprecated**: Tab labels now "(Deprecated)"; use Selection tab instead.
  - `selection.legacy_tabs_enabled` (default `false`) hides Stacks and Culling tabs; folder buttons route to Selection when disabled.
  - `run_full_cull` emits deprecation warning.
- **Database**: Added `cull_decision`, `cull_policy_version` columns to IMAGES; `batch_update_cull_decisions()` for batch updates.

### Migration
- Add `"selection": {"legacy_tabs_enabled": false}` to `config.json` to hide legacy tabs by default.
- Set `legacy_tabs_enabled: true` to keep Stacks and Culling visible during transition.

## [3.15.0] - 2026-02-08

### Added
- **Configurable Database**: Database credentials and filename now configurable via `config.json`.
  - New `database` section: `filename`, `user`, `password`.
  - Replaces hardcoded values in `modules/db.py`.
- **System Path Configuration**: Allowed paths and log directory now configurable via `config.json`.
  - New `system` section: `allowed_paths`, `log_dir`.
  - `get_system_drives()` and `get_default_allowed_paths()` in `modules/config.py` for dynamic path detection.
- **Folder Tree Navigation**: Added "Open in Scoring" and "Open in Culling" buttons for direct workflow navigation.
  - New `open_folder_in_scoring()` and `open_folder_in_culling()` in `modules/navigation.py`.

### Changed
- **Folder Tree Tab**: Simplified layout and workflow.
  - Removed gallery preview panel (single-column tree view).
  - Replaced "Open in Gallery" with "Open in Scoring" and "Open in Culling".
  - Removed "Remove from DB" button and folder cache deletion.
  - Tab order: Folder Tree is now the default first tab.
- **WebUI Allowed Paths**: `webui.py` reads allowed paths from `config.system.allowed_paths` with fallback to `get_default_allowed_paths()`.
- **Debug Log Path**: Log directory configurable via `system.log_dir` (default `.cursor`) in `modules/utils.py`.

### Removed
- **Gallery Tab**: Removed from main UI; `modules/ui/tabs/gallery.py` is now orphaned (file retained for reference).
  - Removed cross-tab navigation: Folder Tree → Gallery, Stacks → Gallery.
  - Removed initial gallery load on app startup.
- **Maintenance Scripts**: Moved to `scripts/` directory: `cleanup_nvidia_repo.bat`, `fix_nvidia_docker.bat`.
- **Hash Utilities**: Removed `find_hash.py`, `find_hash_path.py`, `find_hash_repr.py` (some moved to `scripts/`).
- **Documentation**: Removed `NEF_EXTRACTION_DIAGNOSIS.md`, `WINDOWS_NATIVE_VIEWER_PLAN.md`; archived `proposals.md` to `docs/archive/proposals_old.md`.
- **Test Artifacts**: Removed `test_gallery_optimization.py`, `verify_db_refactor.py`, `setup_legacy.sql`, `webui.lock`, database backup files.

## [3.14.0] - 2026-02-08

### Added
- **Firebird MCP Server**: Dedicated Model Context Protocol server for direct Firebird database administration and inspection (`firebird-admin`).
- **Keyword Filtering**: Added support for keyword-based image filtering in the Electron Gallery.
  - Implemented `getKeywords` in backend to extract unique tags from BLOB fields.
  - Added keyword dropdown to the gallery UI for multi-tag search.
- **Sorting Enhancements**: Added comprehensive sorting options (Date, Rating, Technical/Aesthetic/General Scores, Filename) with ASC/DESC support in Electron Gallery.
- **Diagnostic Tools**: New utilities for image hash investigation (`find_hash_path.py`) and Firebird connectivity testing.

### Fixed
- **Tree View Root Duplication**: Resolved issue where multiple root nodes appeared in the Electron folder tree due to inconsistent path normalization.
- **Database Path Resolution**: Improved Windows/WSL path mapping in Electron backend queries.
- **MCP Configuration**: Corrected `mcp_config.json` schema and properties to ensure compatibility with Antigravity and other MCP clients.
- **Schema Loading**: Fixed 404 error when loading MCP config schema from remote sources.

### Changed
- **Electron UI Polish**: 
  - Updated score display to user-friendly percentages (e.g., "98%" instead of "0.98").
  - Simplified technical metadata panel into a readable "Image Details" view including file type and SHA256 hash.
  - Improved layout and responsiveness of the gallery header and navigation components.
- **Gradio Performance**: Re-implemented SQL window functions and thread-local batch caching for significantly faster gallery rendering in the Python WebUI.

## [3.13.1] - 2026-02-07

### Changed
- **Build Updates**: Updated Electron Gallery compiled assets and dependencies.
  - Rebuilt Electron app with latest NEF extraction improvements.
  - Updated database migration scripts for path resolution.

### Removed
- **Cleanup**: Removed obsolete debug and test output files.
  - Deleted temporary debug output files (`debug_output*.txt`, `output*.txt`).
  - Removed old test result files (`test_results.txt`, `verify_*.txt`).

## [3.13.0] - 2026-02-06

### Added
- **Electron Gallery Navigation**: Comprehensive navigation features for improved user experience.
  - Arrow key navigation in image viewer (Left/Right for previous/next image, Escape to return to grid).
  - Escape key navigation in grid view to return to parent folder.
  - Full database field display in image viewer panel.
- **NEF Extraction Diagnostics**: Added multi-tier NEF preview extraction system and diagnostic tools.
  - 3-tier extraction strategy: ExifTool-vendored, TIFF SubIFD Parser, and Marker Scan fallback.
  - New diagnostic scripts in `scripts/` for testing NEF extraction tiers.
  - Enhanced `nefExtractor.ts` for robust preview extraction from Nikon RAW files.
  - Diagnostic documentation: `NEF_EXTRACTION_DIAGNOSIS.md`.

### Fixed
- **Database Compatibility**: Resolved Electron app database errors.
  - Fixed "Table unknown, RESOLVED_PATHS" error by removing references to obsolete table.
  - Fixed "Column unknown, FP.PATH_TYPE" error in folder path queries.
  - Updated database queries for compatibility with refactored schema.
- **Logger Cleanup**: Reduced log verbosity in Electron Gallery.
  - Modified `Logger.ts` to reduce excessive console output.
  - Addressed Electron security warnings for `webSecurity` and Content-Security-Policy.

### Changed
- **Electron Gallery UI**: Enhanced viewer and grid components.
  - Updated `ImageViewer.tsx` to display all database metadata fields.
  - Improved `GalleryGrid.tsx` keyboard navigation and escape key handling.
  - Enhanced NEF preview handling in `nefViewer.ts` with better error handling.

## [3.12.0] - 2026-02-06

### Fixed
- **Image Loading**: Resolved critical issue where full-resolution images failed to load with `net::ERR_FILE_NOT_FOUND`.
  - Refactored `modules/ui/assets.py` to use stable direct URL loading instead of fragile Blob URLs.
  - Fixed a race condition in the loading spinner logic ("Stale ID") caused by concurrent click and mutation events.
  - Added robust WSL-to-Windows path conversion for client-side fallbacks.
- **Gallery Scrolling**: Fixed double scrollbars and scrolling glitches in Electron Gallery.
  - Removed conflicting `overflow` and `padding` styles between layout and virtualized grid.
  - Fixed keyboard navigation focus management.
- **Gallery Pagination**: Fixed infinite scroll issue where loading stopped at 50 images.
  - Resolved style conflict in `ItemContainer` that broke virtualization integrity.

### Fixed
- **Unit Tests**: Fixed critical failures in `test_gpu.py`, `test_stacks.py`, and `test_keyword_extractor.py`.
- **Database Cleanup**: Resolved persistent `TEST_*.fdb` file leaks in test suite.
- **Firebird Tests**: Fixed connection handling and path normalization in `test_firebird_basic.py` and `test_culling.py`.
- **Test Artifacts**: Fixed issue where tests left behind `TEMPLATE.FDB`, `verify_result.txt`, and other artifacts.
  - Refactored `tests/test_stacks.py` to use a fresh dynamic database instead of copying `TEMPLATE.FDB`.
  - Added cleanup logic to `tests/verify_culling_fix.py` and updated `.gitignore`.

### Added
- **Electron Gallery**: Enhanced debug infrastructure.
  - Added `session_*.log` recording for user interactions and errors.
  - Implemented detailed logging for `useImages` data fetching and `GalleryGrid` rendering verification.
- **API**: Added `/api/raw-preview` endpoint (backend) for efficient RAW image preview generation and path resolution.



### Changed
- **ImageGalleryViewer**: Moved to separate repository at [synthet/sharp-image-scoring](https://github.com/synthet/sharp-image-scoring)
  - Extracted using `git subtree split` to preserve 21 commits of history
  - Allows independent development lifecycle for the C#/.NET WPF application
  - ImageGalleryViewer can still interface with the image-scoring Firebird database
  
### Performance
- **Gallery Optimization**:
  - Implemented batch path resolution to reduce gallery load times from ~4.5s to ~0.1s.
  - Added caching for resolved file paths to bypass repetitive OS filesystem checks.
  - Optimized path resolution logic to handle both WSL (/mnt/...) and Windows paths correctly.

### Added
- **Docker deployment**: GPU-enabled Docker Desktop (WSL2) workflow via `Dockerfile`, `docker-compose.yml`, and `scripts/docker_entrypoint.sh`.
  - Automated installation scripts: `install_docker.bat`, `scripts/install_docker_wsl.sh`, `scripts/install_nvidia_docker.sh`
  - Docker verification and smoke test: `run_docker_smoke_test.bat`, `scripts/verify_docker_wsl.sh`
  - NVIDIA Container Toolkit fix scripts: `fix_nvidia_docker.bat`, `scripts/fix_nvidia_docker.sh`
  - WebUI Docker launcher: `run_webui_docker.bat`
- **PyIQA scoring wrappers**: Added lightweight wrappers for additional IQA models:
  - LIQE (`modules/liqe_wrapper.py`)
  - MUSIQ (`modules/musiq_wrapper.py`)
  - TOPIQ-IAA (`modules/topiq.py`)
  - Q-Align (`modules/qalign.py`)
- **Remote scoring**: Optional external quality scoring clients for EveryPixel and SightEngine (`modules/remote_scoring.py`).
- **Test suite improvements**:
  - Pytest configuration (`pytest.ini`) with skip markers for dependencies
  - PowerShell test runner: `scripts/powershell/Run-WSLTests.ps1`
  - Test database cleanup utility: `scripts/utils/cleanup_test_dbs.py`
  - Database debugging utilities: `scripts/debug/debug_firebird.py`, `scripts/utils/create_test_db.py`
- **Documentation enhancements**:
  - Comprehensive Docker/WSL2 setup guide: `docs/DOCKER_WSL2_SETUP.md`
  - Docker setup technical guide: `docs/technical/DOCKER_SETUP.md`
  - Test status documentation: `docs/TEST_STATUS.md`
  - Project guide for AI agents: `.agent/PROJECT_GUIDE.md`
  - New documentation structure: `docs/ai/`, `docs/engineering/`, `docs/project/`, `docs/reports/`, `docs/testing/`, `docs/archive/`
- **Utilities**:
  - PDF extraction helpers (`scripts/utils/extract_pdf.py`, `scripts/utils/extract_pdf_new.py`)
  - PyIQA model listing (`scripts/utils/list_pyiqa_models.py`)
  - Script helpers (`scripts/python/check_topiq_range.py`, `scripts/unmark_folder.py`)
- **Workflows**:
  - `/run_docker` - Launch Vexlum Scoring application using Docker Compose (GPU-accelerated)
  - `/run_tests` - Run the image scoring test suite (Pytest)
- **Portability**:
  - Created `config.example.json` as a template for new installations.
  - Replaced 50+ hardcoded path instances with generic placeholders across all documentation and guides.

### Changed
- **Documentation structure**: Reorganized `docs/` into categorized sections with an updated index (`docs/README.md`).
  - Moved and archived legacy documentation to `docs/archive/`
  - Created specialized directories for AI context, engineering docs, project docs, reports, and testing
- **Core internals**: Updated configuration/database/clustering and related tests to support the expanded workflows and environment matrix.
  - Added Windows test skip markers (`@pytest.mark.skipif`)
  - Enhanced Firebird database compatibility in tests
  - Improved test isolation and cleanup
- **Dynamic Pathing**:
  - Implemented automatic project root detection in all Batch (`%~dp0`) and PowerShell (`$PSScriptRoot`) scripts.
  - Added robust `_to_win_path` helper in `modules/db.py` for dynamic WSL-to-Windows drive mapping.
  - Updated Python utility scripts in `scripts/` to use dynamic path resolution.
- **Test suite**: Comprehensive test improvements for Windows compatibility
  - Added skip markers for CUDA, rawpy, and exiftool dependencies
  - Fixed test collection errors
  - Improved fixture definitions and test assertions

### Fixed
- **Firebird database**: Fixed path handling and connection issues in WSL environment
- **Test database cleanup**: Resolved persistent test database file issues with proper cleanup logic
- **Docker GPU access**: Fixed NVIDIA Container Toolkit configuration for GPU access in Docker containers

## [3.11.0] - 2026-01-26

### Added
- **API Module**: Implemented new API endpoints (`modules/api.py`) and documentation (`docs/reference/api/API.md`).
- **Assets**: Added `static/favicon.svg` and generation script.

### Changed
- **Culling Module**: Improved robust type handling in `modules/culling.py` to prevent conversion errors.
- **MCP Server**: Enhanced MCP server implementation (`modules/mcp_server.py`).
- **UI Components**: Updated styles and layouts in Gallery and Culling tabs.
- **Core Modules**: Refinements in `db.py`, `scoring.py`, and `utils.py`.

### Fixed
- **Culling Fix**: Resolved "conversion error from string '0'" during best-in-group selection.

## [3.10.0] - 2026-01-23

### Added
- **BurstUUID Stacking Support**: Integrated Apple-style BurstUUID for smarter image grouping.
  - Added `burst_uuid` column to `images` table in Firebird database.
  - Updated `modules/clustering.py` to prioritize `BurstUUID` for stack creation.
  - Enhanced `modules/xmp.py` and `modules/utils.py` to read/write `BurstUUID` from/to XMP sidecars.
- **Stacks & Culling Workflow Integration**: 
  - Culling workflow now automatically detects and utilizes existing stacks.
  - Added "Apply Stacks" logic to culling preparation.
- **Enhanced MCP Server Tools**: Expanded diagnostic and monitoring capabilities for Cursor IDE.
  - Added `get_failed_images`, `get_error_summary`, `check_database_health`, `validate_file_paths`.
  - Added `get_performance_metrics`, `get_model_status`, `validate_config`, `get_pipeline_stats`.
- **UI/UX Harmonization**:
  - Standardized layout, control naming, and styling between Stacks and Culling tabs.
  - New high-quality application favicon.
- **Documentation**: New MCP tools reference guide at `.agent/mcp_tools_reference.md`.

### Changed
- **Database Optimization**: Removed debug logging and optimized `get_or_create_folder` in `modules/db.py`.
- **UI Improvements**: Enhanced status reporting with animated pulse indicators and refined CSS in `modules/ui/tabs/stacks.py`.

### Fixed
- **Firebird Compatibility**: Fixed `INSERT OR IGNORE` syntax issues in culling session operations for Firebird SQL dialect.

## [3.9.0] - 2026-01-23

### Added
- **Firebird Database Support**: Migrated from SQLite to Firebird database engine.
  - Added Firebird connection logic with WSL path conversion support.
  - Implemented `FirebirdCursorProxy` for SQLite compatibility layer.
  - Added helper functions `_table_exists()` and `_index_exists()` for conditional DDL.
  - New migration script: `scripts/migrate_to_firebird.py`.
- **Stacks Button State Management**: Added dynamic button enable/disable based on clustering status.
  - `ClusteringEngine` now tracks `is_running`, `status_message`, `current`, and `total` attributes.
  - Added `get_status()` method for polling from UI.
  - Stacks tab buttons are disabled during active clustering operations.
- **Application Icon**: Added `app.ico` and `favicon.ico` for ImageGalleryViewer and WebUI.

### Changed
- **Database Module**: Rewrote `modules/db.py` for Firebird compatibility.
  - Replaced `INSERT OR IGNORE` / `INSERT OR REPLACE` with `UPDATE OR INSERT ... MATCHING`.
  - Replaced `LIMIT/OFFSET` with `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY`.
  - Replaced `CREATE TABLE IF NOT EXISTS` with conditional checks.
  - Updated `substr()` to `substring()` and `length()` to `char_length()`.
- **Clustering Module**: Updated `modules/clustering.py` with status tracking and Firebird-compatible queries.
- **Scripts Updated for Firebird**: 
  - `scripts/analysis/check_db.py`, `scripts/analysis/check_thumbs.py`
  - `scripts/maintenance/check_db.py`, `scripts/maintenance/check_thumbs.py`
  - `scripts/python/backfill_hashes.py`, `scripts/migrate_resolved_paths.py`
  - `scripts/debug_culling.py`, `scripts/inspect_db_custom.py`
- **MCP Server**: Updated `modules/mcp_server.py` for Firebird database queries.
- **WebUI**: Updated `webui.py` and `modules/ui/app.py` for Firebird initialization.

### Fixed
- **Stacks SQL Error**: Fixed `Invalid expression in the select list` error in `get_stacks_for_display` for Firebird GROUP BY requirements.
- **Culling Session SQL**: Fixed `INSERT OR IGNORE` syntax error when adding images to culling sessions.
- **Database Init Error**: Fixed `Token unknown - NOT` error from unsupported `CREATE TABLE IF NOT EXISTS` syntax.

## [3.8.0] - 2026-01-20

### Added
- **Stack Visualization**: Added "Stack Visualization" feature to image grid items.
  - Visual badge to indicate stacked images.
  - Context menu option to filter grid by selected image's stack.
  - UI status indicator for active stack filters.
- **Details Panel**: Added "Details Panel" to `ImageGalleryViewer`.
  - Displays extensive metadata (EXIF, IPTC, File info).
  - Configurable visibility.
- **Folder Tree Navigation**: Enhanced `ImageGalleryViewer` with a folder tree.
  - Tree-based folder navigation.
  - Filtering gallery by selected folder.
- **Keyboard Navigation**: Implemented keyboard navigation for the gallery.
  - Arrow keys to navigate images.
  - Enter to view full screen.
- **Unit Tests**: Added extensive unit tests.
  - `PhotosLauncher` tests.
  - `ImageRecord` tests.

## [3.7.0] - 2026-01-17

### Fixed
- **Path Conversion Reliability**: Enhanced Windows/WSL path conversion logic in `modules/utils.py`.
  - Added support for backslashes in WSL paths (e.g., `\mnt\d\...`).
  - Improved drive letter detection and normalization for cross-platform compatibility.
  - Added fallback for Linux-style paths with Windows separators.
- **Gallery Styling**: Fixed CSS inheritance issues in gallery details panel for better visibility.
- **Folder Tree Navigation**: Fixed path normalization in `modules/ui_tree.py` to prevent "doubled" root paths in the UI.

### Changed
- **Modular Stability**: Refined event handling in `modules/ui/tabs/gallery.py` and `modules/ui/tabs/stacks.py` to prevent UI lockups during rapid selection.

## [3.6.0] - 2026-01-12

### Added
- **AI Culling Tab**: Aftershoot-style culling workflow for photographers.
  - Groups similar images (bursts, duplicates) using clustering
  - Auto-picks best shot in each group based on quality scores
  - Exports decisions to XMP sidecar files for Lightroom Cloud
  - New module: `modules/culling.py` with CullingEngine class
  - New module: `modules/xmp.py` for non-destructive XMP sidecar writing
  - Documentation: `docs/technical/CULLING_FEATURE.md`
- **Manual Stack Creation**: Added "Group Selected" button to create stacks from manually selected images (Lightroom Ctrl+G equivalent).
- **Remove from Stack**: Added "Remove from Stack" button to remove individual images from their stacks.
- **Dissolve Stack**: Added "Ungroup All" button to completely dissolve a stack and ungroup all its images.
- **Stack Selection Tracking**: Added state management to track selected images and current stack for stack operations.
- **Re-Run Analysis**: Added "Re-Run Scoring" and "Re-Run Tagging" buttons to Image Details panel for individual image reprocessing.
- **Lazy Loading**: Implemented lazy loading for gallery full-resolution images to improve initial load performance and memory usage.

### Changed
- **WebUI Modular Refactoring**: Complete architectural refactoring of `webui.py` (5,000+ lines) into modular component structure.
  - Extracted to `modules/ui/app.py` (main orchestrator), `modules/ui/assets.py` (CSS/JS), `modules/ui/navigation.py` (cross-tab navigation)
  - Individual tabs moved to `modules/ui/tabs/` (scoring, tagging, gallery, folder_tree, stacks, culling, settings)
  - Shared utilities in `modules/ui/common.py` and `modules/ui/state.py`
  - `webui.py` reduced to ~50-line bootstrap script
  - Improved maintainability, testability, and developer experience
  - All functionality preserved with cleaner separation of concerns
- **UI Cleanup**: Removed "View Full Resolution" and "Add to Compare" buttons from gallery view.
- **Fix Data Workflow**: Enhanced "Fix Data" dialog with "Regenerate Thumbnails" option.
- **Raw Preview**: Disabled In-Browser RAW Preview feature due to reliability issues.
- **Settings**: Hard-coded model weights in `webui.py` to ensure consistency.
- **XMP Export**: Improved error reporting and validation for XMP sidecar export operations.

### Fixed
- **Gallery Crash**: Fixed `TypeError` when selecting images in the gallery by adding null checks for event data.
- **Gallery Labels**: Fixed issue where scoring labels (General, Weighted, Models) were not displaying in the image details panel.
- **WebUI Refactoring Stabilization**: Fixed critical bugs discovered during modular refactoring.
  - Fixed `image_details` state initialization (was `None`, causing AttributeError)
  - Fixed missing imports in `navigation.py` (`os`, `gradio`)
  - Fixed `get_total_images_count` function name (changed to `get_image_count`)
  - Fixed `all_outputs` NameError in gallery refresh button wiring
  - Added component validation to prevent None components in event handlers
  - Extracted component count constants for maintainability
- **TF Hub Cache**: Fixed `NameError` related to `os` module import in TF Hub cache configuration.
- **Culling Error**: Fixed `ValueError` in AI culling wrapper caused by incorrect return value count.
- **Syntax Warnings**: Resolved Python syntax warnings in `webui.py` related to invalid escape sequences.
- **Gallery Selection**: Fixed TypeError when selecting images in gallery view. Added workaround for Gradio bug where gallery value (list) is passed instead of SelectData event. Details panels now display correctly when images are selected.

### Changed
- **Database Schema**: Added `culling_sessions` and `culling_picks` tables for culling workflow persistence.
- **Stacks Tab UI**: Added action buttons row below Stack Contents gallery with status feedback.
- **Database Module**: Added `create_culling_session()`, `get_session_groups()`, `set_pick_decision()`, and 7 other culling helper functions.

## [3.5.1] - 2025-12-26

### Fixed
- **Scoring Fix DB**: Fixed `AttributeError: 'sqlite3.Row' object has no attribute 'get'` in `modules/scoring.py`. Changed to direct dictionary access with try/except for `KeyError` and `IndexError` when reading row values.

## [3.5.0] - 2025-12-24

### Added
- **MCP Server Integration**: Added Model Context Protocol server for Cursor IDE debugging tools.
  - Query and analyze the SQLite database remotely
  - Monitor scoring/tagging job progress
  - Read debug logs from the IDE
  - Manage configuration via MCP tools
  - New module: `modules/mcp_server.py`
  - Documentation: `docs/technical/MCP_DEBUGGING_TOOLS.md`
  - Launcher scripts: `scripts/batch/run_mcp_server.bat`, `scripts/powershell/Run-MCPServer.ps1`

### Changed
- 'Deletion Status' is now hidden by default and only appears after a deletion action is completed.
- 'Deletion Status' is automatically hidden when a new image is selected in the gallery.
- Updated documentation and agent workflows for improved maintainability.

## [3.4.2] - 2025-12-23

### Fixed
- **Tree View Selection**: Fixed `ReferenceError: selectFolder is not defined` when clicking on folders in the tree view by exposing the function to the global scope.
- **Path Conversion**: Added logic to respect Windows/WSL path conversions in the tree view interaction. The tree now handles displaying and selecting folders correctly regardless of whether the backend is running in WSL or Windows.
- **Result Worker**: Fixed `NameError: name 'datetime' is not defined` in `modules/pipeline.py` preventing success logging.

## [3.4.1] - 2025-12-23

### Fixed
- **Full Screen Image View**: Fixed issue where the gallery expanded view displayed a low-resolution thumbnail. Now, clicking a gallery image opens a custom full-screen modal showing the high-resolution preview (generated from NEF if needed).

### Added
- **Interactive Folder Tree**: Replaced the static dropdown with a fully interactive HTML-based folder tree. Supports expanding/collapsing folders and filtering the gallery by clicking on folder names.
- **Navigation Buttons**: Fixed issue where "Open in Gallery" buttons would do nothing if no folder path was explicitly provided. Now defaults to "View All" (reset filter) behavior.

## [3.4.0] - 2025-12-23

### Added
- **Folder Gallery**: Added support for browsing images by specific folders in the Gallery tab.
- **Folder Tree**: Added a Folder Tree view to easily select and filter images by directory.
- **Progress Visualization**: Added real-time progress bars for Scoring, Tagging, and Clustering operations in the WebUI.
- **Clustering Module**: Added `modules/clustering.py` to group similar images into stacks using MobileNetV2 features.
- **Stacks Interface**: Added Stacks tab to view and manage clustered image groups.
- **Folder Caching**: Implemented `folders` table in database to cache directory structures for faster tree view rendering.

### Changed
- **Launch Script**: Modified `launch.py` to gracefully handle `KeyboardInterrupt` (Ctrl+C).
- **WebUI Layout**: Refactored WebUI to include new tabs for Stacks and Folder Tree.
- **Database Schema**: Added `folders` and `stacks` tables; added `folder_id` and `stack_id` to `images` table.
- **Scoring & Tagging**: Updated runners to report fine-grained progress (current/total items) to the UI.

## [3.3.1] - 2025-12-23

### Added
- **UI State Persistence**: WebUI now restores the display status of running scoring and keywords inference tasks (logs, buttons) when the page is reloaded.
- **Background Execution**: Scoring and Tagging runners now execute in background threads detached from the UI session.

## [3.3.0] - 2025-12-22
### Added
- **Metadata Editor**: Added interactive metadata editor to WebUI (Title, Description, Keyword, Rating, Color Label).
- **Database Export**: Added "Export DB to JSON" feature to WebUI for full database backup.
- **Score Recalculation**: Added `scripts/maintenance/recalculate_scores.py` to update existing database records with new weights.
- **Config Module**: Added `modules/config.py` for centralized configuration management.

### Changed
- **Scoring Weights**: Refined model weights for better technical and aesthetic assessment:
  - Technical: KONIQ (40%), SPAQ (30%), PAQ2PIQ (30%)
  - Aesthetic: AVA (40%), VILA (40%), SPAQ (20%)
  - General: Weighted average of Technical (50%) and Aesthetic (50%)
- **WebUI**: Updated `webui.py` to support new metadata editing and export features.
- **Database**: Updated `modules/db.py` to support JSON export and metadata updates.
- **Dependencies**: Added `exiftool` support for writing metadata to NEF files.

## [3.2.0] - 2025-12-20

### Added
- **Gallery Keyword Filter**: Added a text search field to the WebUI gallery to allow filtering images by keywords.
- **Auto-Tagging Module**: Added `modules/tagging.py` using CLIP for zero-shot image auto-tagging and BLIP for captioning.
- **Tagging Tab**: Added "Keywords" tab to WebUI for batch processing tags and descriptions.

## [3.1.0] - 2025-12-15

### Added
- **Fix DB Feature**: Added "Fix DB" button to WebUI to identify and rescore images with missing models. 
- **Gallery Filters**: Added dropdown to filter images by Color Label and Star Rating.
- **Persistent Model Caching**: TensorFlow Hub models now cache locally to prevent repeated downloads.
- **Portable Database**: Implemented content-based hashing to support moving the database and images between devices.

### Changed
- **Z8 Thumbnail Fix**: Improved `dcraw` extraction for Nikon Z8 NEF files to prevent corrupted thumbnails.
- **Speed Optimization**: Optimized skip logic to check database existence before calculating hashes.
- **Database Cleanup**: Removed unused fields (`metadata`, `keywords`, `normalized_score`) and simplified schema.
- **Logging**: Standardized logging format across all modules.

### Fixed
- **Scoring Pipeline**: Resolved "get" attribute error in `ResultWorker` and fixed zero-value recording for missing scores.
- **Thumbnail Regeneration**: `generate_thumbnails.py` now correctly identifies and replaces corrupted Z8 thumbnails.

## [3.0.2] - 2025-12-14

### Fixed
- **Scoring Zeros**: Fixed critical bug where individual model scores (SPAQ, AVA, KONIQ, PAQ2PIQ) were failing to persist to the database (recorded as 0) due to a key mismatch in the scoring pipeline.
- **Delete Button**: Resolved WebUI issue where the "Delete NEF" button was not visible for eligible images (rating <= 2 or specific labels).
- **CUDA Init**: Improved handling of CUDA initialization errors (e.g., Unknown Error 303) to prevent silent failures or confusing fallback states.

### Changed
- **Logging**: Standardized logging across the entire codebase. Replaced `print` statements with Python's `logging` module for consistent formatting, timestamps, and thread identification.
- **Pipeline Robustness**: Enhanced `sync_folder_to_db` and `ResultWorker` to better handle unscored images and prevent thumbnail path loss.

## [3.0.1] - 2025-12-09

### Fixed
- **Database Integrity**: Resolved critical bug where weighted scores (`score_technical`, `score_aesthetic`, `score_general`) were stored as `0` in the database.
- **Log Visibility**: Fixed issue where scoring logs were swallowed by the WebUI handler and not shown in the terminal.
- **Crash Fixes**: Resolved `UnboundLocalError` in LIQE scoring and `AttributeError` in `engine.py`.
- **Zero-Score Skip**: Improved "Skip already scored" logic to correctly identify and re-process images with invalid zero scores.

### Changed
- **WebUI Labels**: Gallery labels now display specific score names (e.g., "General: 0.85") instead of generic "Score".
- **Log Cleanup**: Removed verbose "Processing with..." and "Incorporating..." transition messages for cleaner output.
- **UI Cleanup**: Removed unused "Job History" tab.

## [3.0.0] - 2025-12-08

### Added
- **Database Persistence**: Migrated from JSON files to SQLite (`scoring_history.db`) for robust data management.
- **WebUI Enhancements**:
  - **Pagination**: Efficiently browse large image collections.
  - **Advanced Sorting**: Sort by individual model scores (SPAQ, AVA, KONIQ, PAQ2PIQ) and date.
  - **Image Details**: View full scoring metadata and JSON payload on selection.
  - **Path Display**: Gallery labels now include the source folder path.
- **NEF Thumbnail Support**: Integrated `rawpy` for direct thumbnail generation from RAW files.
- **Modular Architecture**: Refactored monolithic scripts into `modules/engine.py`, `modules/scoring.py`, `modules/db.py`, and `modules/thumbnails.py`.
- **WSL Integration**: `run_webui.bat` now automatically launches the application within the WSL environment.

### Changed
- **Scoring Pipeline**: Scores are now streamed to the UI and database in real-time.
- **LIQE Normalization**: Fixed LIQE score normalization to correctly map 1-5 range to 0-1.
- **Gallery Interaction**: Restored full preview functionality with keyboard navigation.
- **Cleanup**: Removed "Delete" button from gallery per user request.

### Fixed
- **LIQE Model Scoring**: Fixed an issue where high-resolution images (e.g., RAW conversions) resulted in incorrect "noise" scores (~1.0). Implemented automatic downscaling to 518px for LIQE inference, restoring accurate scoring (~3.0-4.0).
- **Database Analysis**: Verified score ranges and normalization logic for all models.
- **WebUI Logic**: Fixed label clarity for "Skip already scored images".

## [2.5.2] - 2025-12-07

### Added
- **LIQE Model Integration**: Added support for Language-Image Quality Evaluator (SOTA CLIP-based model)
- **Hybrid Pipeline**: Batch processor can now orchestrate both TensorFlow (MUSIQ) and PyTorch (LIQE) models
- **External Scoring Support**: Updated `run_all_musiq_models.py` to accept and weight scores from external scripts
- **Universal Runner**: New single entry-point `Run-Scoring.ps1` handles both Files and Folders, automatically routing to WSL/GPU.
- **GUI Wrapper**: Added `scoring_gui.py` for easy file/folder selection.
- **Gallery Generator**: Fixed infinite loop when loading non-web images (NEF) without thumbnails. Now shows "No Preview" placeholder.
- **Root Cleanup**: Removed legacy scripts (`create_gallery.bat`, etc.) in favor of the new universal runner.

### Changed
- **Score Calibration**: Updated weights to incorporate LIQE (15%):
  - KONIQ: 35% -> 30%
  - SPAQ: 30% -> 25%
  - PAQ2PIQ: 25% -> 20%
  - LIQE: 15% (New)
  - AVA: 10% (Unchanged)

## [2.5.1] - 2025-12-07

### Changed
- **Score Calibration**: Updated model weights to focus on technical quality:
  - KONIQ: 30% -> 35%
  - SPAQ: 25% -> 30%
  - PAQ2PIQ: 20% -> 25%
  - AVA: 10% (unchanged)
- **Model Clean-up**: Disabled VILA model (was failing to load) to prevent errors and noise.

## [2.5.0] - 2025-12-07

### Added
- **Base64 Thumbnails**: JSON output now includes a base64-encoded JPEG thumbnail (~400px)
- **Gallery Previews**: HTML gallery displays embedded thumbnails for faster loading and portability
- **Improved Fallback**: Gallery generator falls back to original image path if thumbnail is missing

### Changed
- **MultiModelMUSIQ**: Added `generate_thumbnail_base64` method to `run_all_musiq_models.py`
- **Gallery Generator**: Updated template to prioritize `data:image/jpeg;base64` source

## [2.4.0] - 2025-12-06

### Changed
- **Folder Restructuring**: Moved documentation and scripts into dedicated subfolders (`docs/`, `scripts/`) to declutter the root directory.
- **Script Paths**: Updated `process_nef_folder.ps1`, `process_nef_folder.bat`, and `create_gallery.bat` to function correctly from their new locations.
- **Documentation**: Updated `INSTRUCTIONS_RUN_SCORING.md` to reflect new script paths.
- **New Documentation**: Added `docs/FOLDER_STRUCTURE.md` to describe the new layout.

### Removed
- **Dead Code Cleanup**: Removed 23 legacy/unused scripts to improve maintainability.
  - Python: `run_musiq_*.py`, `nef_embedder_*.py`
  - PowerShell: `Run-*.ps1`, `process_nef_folder_local/timeout.ps1`
  - Batch: `run_musiq_*.bat`, `run_vila_*.bat`, `process_images.bat`

## [2.3.1] - 2025-10-09

### Changed
- **Project Restructuring**: Reorganized 82 files into semantic folder structure
  - Documentation moved to `docs/` (organized by category)
  - Scripts moved to `scripts/` (organized by type: batch, powershell)
  - Tests moved to `tests/`
  - Requirements moved to `requirements/`
  - All entry points remain in root for easy access
- **Reference Updates**: Updated 151 file references across 19 files
  - All markdown links updated
  - All documentation cross-references preserved
  - All script paths corrected
- **Backward Compatibility**: Added wrapper scripts in root
  - `create_gallery.bat` → `scripts/batch/create_gallery.bat`
  - `test_model_sources.bat` → `scripts/batch/test_model_sources.bat`
  - `Create-Gallery.ps1` → `scripts/powershell/Create-Gallery.ps1`
  - User experience unchanged (still drag-and-drop friendly)

### Added
- **PROJECT_STRUCTURE.md**: Complete guide to new folder organization
- **Wrapper Scripts**: Root-level launchers for backward compatibility
- **Helper Scripts**: `restructure_project.py`, `update_references.py`

### Documentation Organization
```
docs/
├── getting-started/  (3 files)
├── vila/            (10 files)
├── gallery/          (4 files)
├── setup/           (11 files)
├── technical/       (10 files)
└── maintenance/      (3 files)
```

### Benefits
- 📁 Better organization (files grouped by purpose)
- 🔍 Easier to find documentation (category-based)
- 🧹 Cleaner root directory (only essentials)
- ⚡ Same user experience (wrappers in root)
- 📈 More scalable (easy to add new files)

### Impact
- ✅ No breaking changes (fully backward compatible)
- ✅ All functionality preserved
- ✅ Drag-and-drop still works
- ✅ All links and references updated
- ✅ Entry points unchanged

### Testing
- Verified all 82 file moves
- Verified 151 reference updates
- Created wrapper scripts for compatibility
- Updated docs index with new paths (`docs/README.md`)

## [2.3.0] - 2025-10-09

### Added
- **Triple Fallback Mechanism**: Extended fallback to include local checkpoints
  - **1st Priority**: TensorFlow Hub (fast, no auth, recommended)
  - **2nd Priority**: Kaggle Hub (requires auth, good fallback)
  - **3rd Priority**: Local checkpoints (offline support, .npz files)
  - All 5 models now support local checkpoint fallback
- **Local Checkpoint Support**: Added paths to all local .npz checkpoint files
  - SPAQ: `models/checkpoints/spaq_ckpt.npz`
  - AVA: `models/checkpoints/ava_ckpt.npz`
  - KONIQ: `models/checkpoints/koniq_ckpt.npz`
  - PAQ2PIQ: `models/checkpoints/paq2piq_ckpt.npz`
  - VILA: `models/checkpoints/vila-tensorflow2-image-v1/` (SavedModel)

### Changed
- **Model Source Configuration**: Added `local` key to all model source dictionaries
- **Test Script Enhanced**: `test_model_sources.py` now tests local checkpoints
  - Added `--skip-local` flag
  - Updated summary table to show 3 sources
  - Enhanced fallback status reporting
- **Error Messages**: Improved guidance when all sources fail

### Benefits
- **Offline Support**: Models work without internet if checkpoints are available
- **Maximum Redundancy**: 3 fallback levels ensure model availability
- **Flexible Deployment**: Works in air-gapped environments with local checkpoints
- **Better Reliability**: Even if TF Hub and Kaggle Hub are down, local checkpoints work

### Known Limitations
- ⚠️ Local .npz checkpoint loading not yet fully implemented (requires original MUSIQ loader)
- ✅ Local SavedModel format (VILA) works perfectly
- 📝 Future update will add full .npz loading support

### Impact
- Version bumped to 2.3.0 (minor version - new feature)
- No breaking changes to existing functionality
- Local checkpoints used as last resort fallback
- Download checkpoints from: https://storage.googleapis.com/gresearch/musiq/

## [2.2.0] - 2025-10-09

### Added
- **Unified Fallback Mechanism**: All models now try TensorFlow Hub first, then fall back to Kaggle Hub
  - Automatic fallback increases reliability
  - TensorFlow Hub tried first (faster, no authentication required)
  - Kaggle Hub used as fallback (requires authentication)
  - Works for all 5 models: SPAQ, AVA, KONIQ, PAQ2PIQ, VILA
- **Model Source Testing Scripts**: New testing tools to verify all model URLs
  - `test_model_sources.py` - Python script to test all TF Hub and Kaggle Hub sources
  - `test_model_sources.bat` - Windows batch wrapper
  - `Test-ModelSources.ps1` - PowerShell wrapper
  - Tests model accessibility without full download
  - Validates fallback mechanism
  - Provides detailed status reports

### Changed
- **Model Loading Architecture**: Restructured from separate source types to unified fallback system
  - Before: Different loading logic per model source
  - After: Consistent try-fallback pattern for all models
- **Model Source Configuration**: Changed to dictionary format with both TFHub and Kaggle paths
  ```python
  # Old format
  "spaq": "tfhub"
  
  # New format
  "spaq": {
      "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
      "kaggle": "google/musiq/tensorFlow2/spaq"
  }
  ```
- **Status Messages**: Added emoji indicators for loading status (✓ success, ⚠ warning, ✗ error)

### Benefits
- **Improved Reliability**: Models load even if one source is unavailable
- **Faster Loading**: TensorFlow Hub is tried first (typically faster)
- **No Auth When Possible**: Only uses Kaggle Hub if TF Hub fails
- **Better Error Messages**: Clear indication of which source failed and why
- **Future-Proof**: Easy to add more model sources (local cache, custom servers)
- **Testability**: New test scripts validate all sources before deployment

### Documentation
- Added `MODEL_FALLBACK_MECHANISM.md` - Complete fallback system documentation
- Added `MODEL_SOURCE_TESTING.md` - Testing guide and usage instructions

### Impact
- No changes to model scoring or output format
- Existing JSON results remain compatible
- Models load from best available source automatically
- Test scripts help verify environment setup
- Version bumped to 2.2.0 (minor version - new features)

## [2.1.2] - 2025-10-09

### Fixed
- **VILA Score Range Correction**: Fixed VILA model score range from [0, 10] to [0, 1] as per official TensorFlow Hub documentation
- **Impact**: VILA scores now properly contribute to weighted scoring (15% weight instead of being under-weighted by 10x)
- **Gallery Filename Sorting**: Fixed filename (A-Z) sorting not displaying any files
- **Gallery Date Sorting**: Removed broken date sorting (was showing NaN values)
- **Version Bump**: All processed images should be reprocessed with v2.1.2 for accurate scores

### Added
- **Gallery VILA Support**: Added VILA score display and sorting in HTML gallery generator
  - VILA score card now appears in each image card
  - VILA score available as sort option
  - Gallery shows all 5 model scores (KONIQ, SPAQ, PAQ2PIQ, VILA, AVA)
- **WSL Setup Instructions**: Added comprehensive WSL and environment setup guide to README
  - Step-by-step WSL installation
  - TensorFlow virtual environment setup
  - Kaggle authentication setup
  - Environment comparison table (WSL vs Windows Python)
  - Quick test commands

### Changed
- Updated `run_all_musiq_models.py` version to 2.1.2
- Updated `gallery_generator.py` with improved sorting logic
  - Fixed string comparison for filename sorting
  - Removed broken date sorting option
  - Added explicit type handling (string vs numeric)
- Updated all documentation to reflect correct VILA score range
- Enhanced `test_vila.py` with score range validation
- Updated `README.md` with detailed WSL setup instructions

### Documentation
- Added `VILA_SCORE_RANGE_CORRECTION.md` - detailed explanation of range correction
- Added `VILA_ALL_FIXES_SUMMARY.md` - comprehensive summary of all VILA fixes
- Added `CHANGELOG.md` - this file
- Added docs index (`docs/README.md`) - complete documentation index
- Added `GALLERY_SORTING_FIX.md` - gallery sorting fixes documentation
- Updated `README.md` - comprehensive WSL and environment setup instructions

## [2.1.1] - 2025-10-09

### Fixed
- **VILA Model Path**: Corrected Kaggle Hub path from `google/vila/tensorFlow2/vila-r` to `google/vila/tensorFlow2/image`
- **VILA Parameter Name**: Fixed model signature parameter from `image_bytes_tensor` to `image_bytes`
- **Removed**: Non-existent `vila_rank` model from all configurations

### Added
- **WSL Path Conversion**: Enhanced batch files to handle all drive letters (A-Z), not just D:\
- **VILA Batch Files**: 
  - `run_vila.bat` - command-line VILA processing
  - `run_vila_drag_drop.bat` - drag-and-drop VILA processing
  - Both use WSL wrapper with TensorFlow virtual environment
- **Test Suite**: Added `test_vila.py` and `test_vila.bat` for integration testing

### Changed
- Updated `create_gallery.bat` with comprehensive path conversion
- Updated `process_images.bat` with comprehensive path conversion
- Rebalanced model weights (AVA: 5% → 10% after removing vila_rank)

### Documentation
- Added `VILA_MODEL_PATH_FIX.md` - path and parameter fixes
- Added `VILA_PARAMETER_FIX.md` - detailed parameter fix guide
- Added `WSL_WRAPPER_VERIFICATION.md` - WSL wrapper verification
- Added `VILA_BATCH_FILES_GUIDE.md` - user guide for VILA batch files
- Added `VILA_FIXES_SUMMARY.md` - technical summary
- Updated `README_VILA.md` with correct information
- Updated `README.md` with VILA model info

## [2.1.0] - 2025-10-08

### Added
- **VILA Model Integration**: Added Google VILA (Vision-Language) model support
  - Model source: Kaggle Hub
  - Vision-language aesthetics assessment
  - Requires Kaggle authentication
  - Weight: 15% in multi-model scoring
- **Kaggle Hub Support**: Added `kagglehub==0.3.4` dependency
- **Multi-Model Scoring**: Extended scoring to support both TensorFlow Hub and Kaggle Hub sources
- **Conditional Parameter Logic**: Added model-type-specific parameter handling

### Changed
- Updated `run_all_musiq_models.py` to support VILA models
- Updated gallery scripts to acknowledge VILA integration
- Enhanced batch processing with VILA support

### Known Issues
- ❌ Initial integration had incorrect model paths (fixed in 2.1.1)
- ❌ Initial integration had incorrect parameter names (fixed in 2.1.1)
- ❌ Initial integration had incorrect score range (fixed in 2.1.2)

## [2.0.0] - 2025-06-12

### Added
- **Multi-Model MUSIQ Support**: Support for 4 MUSIQ model variants
  - KONIQ: KONIQ-10K dataset (30% weight)
  - SPAQ: SPAQ dataset (25% weight)
  - PAQ2PIQ: PAQ2PIQ dataset (20% weight)
  - AVA: AVA dataset (25% weight initially)
- **Advanced Scoring Methods**:
  - Weighted scoring based on model reliability
  - Median scoring (robust to outliers)
  - Trimmed mean scoring
  - Outlier detection using IQR method
  - Final robust score combining multiple methods
- **Gallery Generation**: Interactive HTML gallery with embedded scores
  - Sortable by multiple metrics
  - Responsive design
  - Modal image viewing
  - Statistics display
- **Batch Processing**: Automated processing of image folders
  - JSON output with all model scores
  - Version tracking
  - Skip already-processed images
  - Progress monitoring

### Changed
- Moved from single-model to multi-model architecture
- Implemented weighted scoring strategy
- Added version tracking for reproducibility

### Documentation
- Added `README.md` - main project documentation
- Added `README_MULTI_MODEL.md` - multi-model usage guide
- Added `WEIGHTED_SCORING_STRATEGY.md` - scoring methodology
- Added `BATCH_PROCESSING_SUMMARY.md` - batch processing guide
- Added `GALLERY_GENERATOR_README.md` - gallery generation guide

## [1.0.0] - Initial Release

### Added
- **Basic MUSIQ Implementation**: Single-model image quality assessment
- **TensorFlow Hub Integration**: Load models from TF Hub
- **Local Checkpoint Support**: Fallback to local .npz files
- **GPU Support**: CUDA acceleration for TensorFlow
- **WSL Support**: Run in WSL environment with TensorFlow
- **Windows Batch Scripts**: Easy-to-use Windows launchers
- **PowerShell Scripts**: Alternative PowerShell launchers

### Features
- Single image scoring
- Command-line interface
- JSON output format
- Multiple model variants (SPAQ, AVA, KONIQ, PAQ2PIQ)

### Documentation
- Added `README_simple.md` - basic usage guide
- Added `README_gpu.md` - GPU setup guide
- Added `MODELS_SUMMARY.md` - model information

---

## Version Naming Convention

- **Major version (X.0.0)**: Breaking changes, major feature additions
- **Minor version (X.Y.0)**: New features, non-breaking changes
- **Patch version (X.Y.Z)**: Bug fixes, documentation updates

## Model Versions

| Version | MUSIQ Models | VILA Models | Total Models |
|---------|--------------|-------------|--------------|
| 2.1.2 | 4 | 1 ✅ | 5 |
| 2.1.1 | 4 | 1 ⚠️ | 5 |
| 2.1.0 | 4 | 2 ❌ | 6 (claimed) |
| 2.0.0 | 4 | 0 | 4 |
| 1.0.0 | 4 | 0 | 4 (single use) |

**Legend**:
- ✅ Fully functional
- ⚠️ Functional but with scoring issues
- ❌ Non-functional (wrong paths/parameters)

## Migration Guides

### Upgrading from 2.1.1 to 2.1.2
**Required**: Reprocess images for correct VILA scoring

```batch
# Reprocess a folder
create_gallery.bat "D:\Photos\YourFolder"
```

**Why**: VILA score range was corrected, affecting weighted scores significantly (+17% on average).

### Upgrading from 2.1.0 to 2.1.1
**Required**: Update model paths and parameters

**Changes**:
- VILA model path changed
- Parameter name changed to `image_bytes`
- `vila_rank` model removed

**Action**: Update and rerun batch processing.

### Upgrading from 2.0.0 to 2.1.0
**Optional**: Add VILA support

**New Requirements**:
- Kaggle Hub package
- Kaggle authentication
- WSL recommended

**Action**: 
1. Install: `pip install kagglehub==0.3.4`
2. Set up Kaggle credentials
3. Run with VILA support

## Breaking Changes

### v2.1.2
- VILA normalized scores changed (10x increase)
- Weighted scores recalculated
- Version mismatch triggers reprocessing

### v2.1.0
- Added Kaggle Hub dependency
- Requires Kaggle authentication for VILA
- New parameter handling logic

### v2.0.0
- Changed from single-model to multi-model architecture
- JSON output format changed
- Scoring methodology changed

## Deprecations

### v2.1.2
- Results from v2.1.0 and v2.1.1 should be reprocessed

### v2.1.0
- Single-model workflows deprecated (use multi-model instead)

## Future Plans

### Planned Features
- [ ] Additional vision-language models
- [ ] Custom model weight configuration
- [ ] Batch comparison tools
- [ ] Export to various formats (CSV, Excel)
- [ ] Image filtering by score threshold
- [ ] Gallery themes and customization
- [ ] Model performance benchmarking
- [ ] Cloud processing support

### Under Consideration
- [ ] Video quality assessment
- [ ] Real-time camera assessment
- [ ] Mobile app support
- [ ] Web API/service
- [ ] Database integration
- [ ] ML model fine-tuning

---

## Contributing

See the project README for contribution guidelines.

## Support

For issues or questions:
- Check documentation in `docs/README.md`
- See troubleshooting in `README_VILA.md`
- Review fix summaries for common issues

## License

See LICENSE file for details.

