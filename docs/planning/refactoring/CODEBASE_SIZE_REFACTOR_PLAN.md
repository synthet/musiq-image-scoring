---
type: Plan
title: Codebase size refactor plan (backend)
description: Phased checkbox backlog to reduce files ≥1000 LoC and functions ≥150 LoC; derived from the June 2026 codebase-size audit.
resource: docs/planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md
tags: [docs, planning, refactoring, codebase-size]
timestamp: 2026-06-30T00:00:00Z
okf_version: 0.1
---

# Codebase size refactor plan (backend)

Phased checklist to reduce files ≥1000 LoC and functions/methods ≥150 LoC in **image-scoring-backend**. Derived from the latest `codebase_size_audit.py` run.

**Source audit:** [CODEBASE_SIZE_AUDIT_2026-06.md](../../reports/CODEBASE_SIZE_AUDIT_2026-06.md) · Raw JSON in [docs/raw/](../../raw/)

**Last audit:** 2026-07-01 (post Phase 1 + Phase 4 resume)  
**Thresholds:** files ≥1000 LoC, functions/methods ≥150 LoC  
**Sibling plan:** [image-scoring-gallery CODEBASE_SIZE_REFACTOR_PLAN.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/planning/CODEBASE_SIZE_REFACTOR_PLAN.md)  
**Re-run audit:** [`.cursor/skills/codebase-size-audit/SKILL.md`](../../../.cursor/skills/codebase-size-audit/SKILL.md)

```bash
# From image-scoring-backend root
python scripts/audit/codebase_size_audit.py
python scripts/audit/codebase_size_audit.py --root ../image-scoring-gallery
python scripts/audit/codebase_size_audit.py --format json -o .agent/scratch/audit-backend.json
```

---

## Backlog contract

> **This document is informational.** Implementing any phase below requires filing and claiming a GitHub Project board issue first (see [docs/project/00-backlog-workflow.md](../../project/00-backlog-workflow.md) and `.cursor/skills/backlog-queue/SKILL.md`). Move the card to **In Progress** on the first commit; reference `Closes #<N>` in the PR.

---

## Ground rules (all phases)

- **Mechanical extraction only** — move code into sibling modules; do not change behavior in the same PR unless fixing a bug discovered during extraction.
- **Stable public surface** — keep import paths, REST routes, MCP tool names, and DB column contracts unchanged unless a coordinated cross-repo change is filed.
- **Re-export pattern** — prefer new modules plus barrel re-exports (`modules/api.py`, `modules/db/__init__.py`, `modules/mcp_server.py`) so call sites change minimally.
- **Test after every phase** — fast subset: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`; add targeted suites for touched areas (API, MCP, DB).
- **Re-audit after every phase** — re-run `codebase_size_audit.py`, update checkboxes, and record new line counts in the phase notes.
- **Risk labels:** **Safe** = low contract blast radius; **High** = OpenAPI/DB/schema coupling; **Optional** = scripts/CLI, defer unless touched for other reasons.

---

## Phase 0 — Batch 1 (done)

Safe mechanical extractions already merged. Post-extraction line counts from 2026-06-30 audit:

| Area | Action | Result (LoC) |
|------|--------|-------------:|
| `modules/api.py` | Extracted `api_helpers.py`, `api_models.py` | **7,357** (file); `create_api_router` still **6,846** |
| `modules/mcp_server.py` | Extracted `modules/mcp/tools/*` | **1,108** |
| Gallery `electron/main.ts` | Extracted `electron/ipc/register*.ts` (sync, backup, db, …) | **1,623** (see sibling plan) |
| Gallery `electron/db.ts` | Not touched in Batch 1 | **2,601** (unchanged) |

- [x] Extract API helpers and Pydantic models from `modules/api.py`
- [x] Split MCP tool implementations into `modules/mcp/tools/*`
- [x] Split gallery IPC registration into `electron/ipc/register*.ts`
- [x] Re-run audit and confirm post-Batch-1 counts above

---

## Phase 1 — `modules/api.py` domain routers

**Risk: High** — OpenAPI route order, FastAPI dependency injection, integration E2E matrix. **Gate:** file/claim issue; run Postgres API E2E (`pytest -m postgres`) before merge.

| Target | LoC | Range |
|--------|----:|-------|
| Package `modules/api/` | 311 (`__init__.py`) | — |
| `create_api_router` | **33** | composer only |
| Largest router | **1,837** (`routers/electron.py`) | follow-up splits |

Suggested domain routers (one PR per router or tightly related pair):

- [x] **Gate:** Issue [#173](https://github.com/synthet/image-scoring-backend/issues/173) claimed; mechanical OpenAPI preserved (100 API tests pass)
- [x] Extract **jobs / tasks** routes → `modules/api/routers/tasks.py`
- [x] Extract **images** routes → `modules/api/routers/data_query.py`, `utility.py`, `public.py`
- [x] Extract **folders** routes → `modules/api/routers/electron.py`, `data_query.py`
- [x] Extract **stacks / culling** routes → `modules/api/routers/data_query.py`, `agent_cull.py`
- [x] Extract **keywords** routes → `modules/api/routers/similar.py` (keyword cloud)
- [x] Extract **config / diagnostics** routes → `modules/api/routers/general.py`, `debug.py`, `shutdown_schema.py`
- [x] Extract **runners** (scoring/tagging/clustering) → `scoring.py`, `tagging.py`, `clustering.py`, `bird_species.py`
- [x] Extract **pipeline / runs** → `pipeline_submit.py`, `electron.py`, `import_register.py`
- [x] Extract **maintenance** → `modules/api/routers/maintenance.py`
- [x] Keep `create_api_router` as thin composer mounting sub-routers (preserve route order)
- [x] Update call sites / imports only as needed; keep `from modules.api import create_api_router` stable (`modules/api/state.py`, `deps.py`, `handler_registry.py`)
- [x] Run fast pytest on touched routes (100 passed)
- [x] Re-run audit; `create_api_router` **33 LoC**, `__init__.py` **311 LoC** — record actual counts: **33 / 311** (electron router **1,837** still exceeds threshold; optional follow-up)

---

## Phase 2 — `modules/db_legacy.py` domain decomposition

**Risk: High** — schema authority, 90+ import sites, connector routing. Follow [docs/planning/db-refactor-decomposition.md](../db-refactor-decomposition.md).

| Target | LoC | Range |
|--------|----:|-------|
| File `modules/db_legacy.py` | 15,457 | — |
| `_init_db_impl` | 1,547 | L2468–4014 |
| `upsert_image` | 426 | L8653–9078 |
| `update_job_status` | 265 | L5777–6041 |
| `_build_image_query_components` | 210 | L1938–2147 |
| `get_folder_phase_summary` | 192 | L14817–15008 |
| `set_image_phase_status` | 224 | L13738–13961 |
| `_heal_stale_phase_flags` | 161 | L14654–14814 |
| `delete_empty_folder_cache_subtree` | 153 | L5327–5479 |

Domain modules under `modules/db/` (facade in `__init__.py` re-exports everything):

- [ ] **Gate:** Issue + confirm facade pattern in `modules/db/__init__.py` is current
- [ ] Extract `modules/db/connection.py` — engine routing, pool, ping
- [ ] Extract `modules/db/images.py` — CRUD, queries; include `_build_image_query_components`, `upsert_image`
- [ ] Extract `modules/db/folders.py` — folder tree, `delete_empty_folder_cache_subtree`, `get_folder_phase_summary`
- [ ] Extract `modules/db/stacks.py` — stack membership, clustering helpers
- [ ] Extract `modules/db/jobs.py` — `update_job_status`, phase status (`set_image_phase_status`, `_heal_stale_phase_flags`)
- [ ] Extract `modules/db/keywords.py` — normalized keyword sync/read helpers
- [ ] Extract `modules/db/embeddings.py` — embedding read/write batch APIs
- [ ] Extract `modules/db/telemetry.py` — pipeline events, metrics
- [ ] Extract `modules/db/backup.py` — backup/restore helpers
- [ ] Split `_init_db_impl` into per-domain DDL helpers (coordinate with Phase 3 Postgres init)
- [ ] Keep `modules.db` import path stable via facade re-exports
- [ ] Run DB-marked tests + integration subset applicable to touched domains
- [ ] Re-run audit; target `db_legacy.py` **<3000 LoC** (interim) then retire monolith — record: ___

---

## Phase 3 — `modules/db_postgres.py` DDL split

**Risk: High** — Alembic + `_init_db_transaction` must stay idempotent.

| Target | LoC | Range |
|--------|----:|-------|
| File `modules/db_postgres.py` | 1,320 | — |
| `_init_db_transaction` | 891 | L430–1320 |

- [ ] **Gate:** Issue; read Alembic head vs inline DDL overlap
- [ ] Extract per-table or per-domain DDL functions (e.g. `images`, `jobs`, `keywords`, `embeddings`, `stacks`)
- [ ] Keep `_init_db_transaction` as orchestrator calling domain inits in dependency order
- [ ] Run postgres-marked tests / fresh DB bootstrap smoke test
- [ ] Re-run audit; target `_init_db_transaction` **<200 LoC** — record: ___

---

## Phase 4 — Runner `_run_batch_internal` pattern

**Risk: Medium** — pipeline correctness; prefer one runner per PR.

Shared smell: large batch loops mixing I/O, DB updates, and model calls. Pattern: extract **per-image step** into private helper; keep loop thin.

| File / symbol | LoC | Range |
|---------------|----:|-------|
| `TaggingRunner._run_batch_internal` | 511 | L532–1042 |
| `modules/tagging.py` (file) | 1,299 | — |
| `ClusteringEngine._cluster_images_impl` | 582 | L497–1078 |
| `modules/clustering.py` (file) | 1,214 | — |
| `IndexingRunner._run_batch_internal` | 436 | L456–891 |
| `MetadataRunner._run_batch_internal` | 358 | L68–425 |
| `BirdSpeciesRunner._run_batch_internal` | 274 | L307–580 |
| `ScoringRunner._run_batch_internal` | 160 | L162–321 |
| `ScoringRunner._fix_db_internal` | 152 | L468–619 |
| `SelectionService.run` | 329 | L200–528 |
| `SelectionRunner._run_internal` | 196 | L85–280 |
| `ResultWorker.process` | 166 | L621–786 |
| `PrepWorker.process` | 151 | L194–344 |
| `BatchImageProcessor.process_directory` | 208 | L78–285 |

- [x] Extract tagging per-image step from `_run_batch_internal` → `_process_tagging_image_row` (`_run_batch_internal` **208 LoC**)
- [x] Extract metadata batch step helper → `_process_metadata_image_row`
- [x] Extract indexing batch step helper → `_process_indexing_file`
- [x] Extract clustering per-image / per-group step from `_cluster_images_impl` → `_filter_runnable_cluster_rows` (`_cluster_images_impl` still **~530 LoC**; folder/time-batch body deferred)
- [x] Extract bird_species batch step helper → `_process_bird_species_image_row`
- [x] Extract scoring batch + `_fix_db_internal` helpers → `_build_fix_db_jobs_from_records` (`_run_batch_internal` **160 LoC**)
- [x] Extract selection service loop body + runner internal loop → `_resolve_culling_scope` on `SelectionRunner` (`SelectionService.run` **329 LoC** — folder body deferred)
- [x] Extract `PrepWorker.process` / `ResultWorker.process` step helpers → `_apply_scoring_prep`, `_handle_*_job`
- [x] Extract `process_directory` directory-walk vs per-file bodies → `_discover_scoring_input_files`
- [x] Run phase-appropriate pytest (unit + any `ml`-marked only when necessary)
- [x] Re-run audit; each symbol target **<150 LoC** — record counts: tagging loop **208**, `_process_tagging_image_row` **563** (further split optional); bird loop **~45**, `_process_bird_species_image_row` **~95**; `_filter_runnable_cluster_rows` **~55**; `_build_fix_db_jobs_from_records` **~45**; `_discover_scoring_input_files` **~95**; mega-helpers still above threshold (acceptable interim)

---

## Phase 5 — `modules/runs_autodrive.py`

**Risk: Medium–High** — autodrive job orchestration; large test file `tests/test_runs_autodrive.py` (1,948 LoC) may need fixture updates.

| Target | LoC | Range |
|--------|----:|-------|
| File `modules/runs_autodrive.py` | 2,449 | — |
| `auto_drive_runs` | 328 | L1572–1899 |

- [ ] **Gate:** Issue; identify planning vs enqueue vs loop boundaries
- [ ] Extract planning submodule (folder/run selection)
- [ ] Extract enqueue submodule (job submission)
- [ ] Extract main loop / polling submodule
- [ ] Keep public entrypoints stable (`auto_drive_runs` signature unchanged)
- [ ] Run `tests/test_runs_autodrive.py` subset or full file
- [ ] Re-run audit; target file **<1500 LoC**, `auto_drive_runs` **<150 LoC** — record: ___

---

## Phase 6 — Misc long functions (library code)

**Risk: Low–Medium** — one symbol or small module per PR where possible.

| Target | LoC | Range | Label |
|--------|----:|-------|-------|
| `JobDispatcher._dispatch_to_runner` | 246 | L493–738 | Medium |
| `heal_phase_data` | 259 | L259–517 | Medium |
| `apply_safety_gates` | 215 | L77–291 | Safe |
| `validate_agent_response` | 176 | L80–255 | Safe |
| `compute_embedding_map` | 194 | L188–381 | Medium |
| `compute_library_flags` | 183 | L11–193 | Safe |
| `compute_library_hierarchy` | 161 | L100–260 | Safe |
| `get_embedding_stats` (MCP) | 198 | L195–392 | Safe |
| `setup_server_endpoints` | 156 | L114–269 | Safe |
| `backfill_exif_camera_lens` | 150 | L346–495 | Safe |
| `webui.py::main` | 469 | L113–581 | Medium |
| `propagate_tags` | 189 | L19–207 | Medium |

- [ ] Split `_dispatch_to_runner` by job type / phase (**Medium**)
- [ ] Split `heal_phase_data` by healing pass (**Medium**)
- [ ] Refactor agent_cull safety + schema validators (**Safe**)
- [ ] Split culling_analytics `flags.py` / `hierarchy.py` compute functions (**Safe**)
- [ ] Slim MCP `get_embedding_stats` query blocks (**Safe**)
- [ ] Move Gradio/status endpoints out of `setup_server_endpoints` (**Safe**)
- [ ] Chunk `backfill_exif_camera_lens` by EXIF field group (**Safe**)
- [ ] Continue `webui.py` modularization per [REFACTORING_PLAN.md](REFACTORING_PLAN.md); shrink `main` (**Medium**)
- [ ] Re-run audit; record cleared symbols: ___

---

## Phase 7 — Scripts (optional / low priority)

**Risk: Low** — standalone CLIs; split only when actively editing or for agent ergonomics.

| Target | LoC | Notes |
|--------|----:|-------|
| `scripts/python/run_all_musiq_models.py` | 1,561 | Research/batch CLI |
| `generate_html_with_embedded_data` | 617 | Gallery generator |
| `scripts/analysis/analyze_phase_status.py` | 1,109 | `print_report` 348 LoC |
| `scripts/backup/fix_backup_structure.py` | — | `run_fix` 248, `run_fix_by_metadata` 198 |
| `scripts/backup/sync_backup.py` | — | `run_sync` 235 |
| `scripts/backup/cleanup_backup.py` | — | `run_cleanup` 222 |
| Maintenance / research scripts | various | See audit output |

- [ ] _(Optional)_ Split `run_all_musiq_models.py` by model family
- [ ] _(Optional)_ Split gallery generator HTML/data builders
- [ ] _(Optional)_ Split `analyze_phase_status.py` report sections
- [ ] _(Optional)_ Extract shared backup script helpers
- [ ] Re-run audit if any optional phase completed

---

## Phase 8 — Explicitly exempt (no action required)

| Target | LoC | Reason |
|--------|----:|--------|
| `migrations/versions/0001_initial_schema.py::upgrade` | 374 | Generated/historical Alembic baseline |
| `tests/test_runs_autodrive.py` | 1,948 | Test file; split only if stricter test hygiene requested |
| `.agent/scratch/*` | varies | Scratch / not shipped |

No checkboxes — do not count toward refactor completion unless policy changes.

---

## Phase 9 — Frontend `/ui/` SPA (lower priority)

**Risk: Medium** — coordinate with `.cursor/skills/backend-frontend-ui/SKILL.md` and design-token package.

| Component | LoC | Range |
|-----------|----:|-------|
| `RunsBucketsPanel.tsx` | 472 | L311–782 |
| `ImageInspectorPage.tsx` | 337 | L331–667 |
| `ScopeSelector.tsx` | 327 | L29–355 |
| `GeoMapPage.tsx` | 263 | L196–458 |
| `RunsPage.tsx` | 243 | L18–260 |
| `RunDetailPage.tsx` | 234 | L21–254 |
| `GalleryPage.tsx` | 219 | L17–235 |
| `DbPage.tsx` | 217 | L31–247 |
| `RunsToolsTab.tsx` | 193 | L94–286 |
| `CullingWorkspace.tsx` | 181 | L16–196 |
| `FolderPage.tsx` | 156 | L21–176 |

- [ ] Extract hooks from `RunsBucketsPanel` (filters, bucket state)
- [ ] Split `ImageInspectorPage` into inspector panels + data hooks
- [ ] Decompose `ScopeSelector` into subcomponents
- [ ] Extract map layer / geo hooks from `GeoMapPage`
- [ ] Page-level extractions for Runs/Gallery/Db/Folder pages (one page per PR)
- [ ] Run frontend unit tests + `npm run design:check` if tokens touched
- [ ] Re-run audit from backend root (includes `frontend/` paths)

---

## Phase 10 — Verification and guardrails

- [ ] All phases above either complete or explicitly deferred with issue links
- [ ] Full fast pytest: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`
- [ ] Optional: `ruff check` on touched modules
- [ ] Re-run combined audit (backend + gallery); confirm no regressions above thresholds except grandfather list
- [ ] _(Optional)_ Add CI step: `python scripts/audit/codebase_size_audit.py --file-min 1000 --fn-min 150 --format json` with non-zero exit on new violations (grandfather list for exempt files/functions)
- [ ] Update this document's **Last audit** date and line-count table

**Grandfather candidates (if CI guard added):** migration `0001`, `tests/test_runs_autodrive.py`, `.agent/scratch/*`, optional script paths from Phase 7.

---

## Related documents

- [CODEBASE_SIZE_AUDIT_2026-06.md](../../reports/CODEBASE_SIZE_AUDIT_2026-06.md) — June 2026 audit snapshot (source data)
- [db-refactor-decomposition.md](../db-refactor-decomposition.md) — DB god-object strategy (Phase 2 detail)
- [REFACTORING_PLAN.md](REFACTORING_PLAN.md) — Gradio / `webui.py` tab split
- [STACK_CULLING_REFACTOR_PLAN.md](STACK_CULLING_REFACTOR_PLAN.md) — Culling domain design
- [Gallery codebase size plan](https://github.com/synthet/image-scoring-gallery/blob/main/docs/planning/CODEBASE_SIZE_REFACTOR_PLAN.md)
