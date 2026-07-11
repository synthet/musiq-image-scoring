---
type: Report
title: Codebase size audit — July 2026
description: Point-in-time LoC audit (files ≥1000, functions ≥150) for backend and gallery after Phase 1 API split and gallery main.ts extraction.
resource: docs/reports/CODEBASE_SIZE_AUDIT_2026-07.md
tags: [docs, reports, refactoring, audit, codebase-size]
timestamp: 2026-07-01T00:00:00Z
okf_version: 0.1
---

# Codebase size audit — July 2026

Point-in-time scan of **image-scoring-backend** and sibling **image-scoring-gallery** using `scripts/audit/codebase_size_audit.py`. Thresholds: **files ≥1000 LoC**, **functions/methods ≥150 LoC**.

**Action plan:** [CODEBASE_SIZE_REFACTOR_PLAN.md](../planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) (backend Phases 0–10) · [Gallery plan](https://github.com/synthet/image-scoring-gallery/blob/main/docs/planning/CODEBASE_SIZE_REFACTOR_PLAN.md) (Phases 1–8) · Re-run skill [codebase-size-audit](../../../.cursor/skills/codebase-size-audit/SKILL.md)

**Raw JSON (immutable):** [codebase-size-audit-2026-07-01-backend.json](../raw/codebase-size-audit-2026-07-01-backend.json), [codebase-size-audit-2026-07-01-gallery.json](../raw/codebase-size-audit-2026-07-01-gallery.json)

**Prior snapshot:** [CODEBASE_SIZE_AUDIT_2026-06.md](CODEBASE_SIZE_AUDIT_2026-06.md)

---

## Key takeaways

1. **Phase 1 API domain-router split is done** — `create_api_router` is **33 LoC**; `modules/api.py` no longer appears on the large-files list.
2. **New hotspot (pre–Phase 1b):** `modules/api/routers/electron.py` at **1,855 LoC** with `create_electron_router` at **1,588 LoC** — addressed in Phase 1b (issue [#298](https://github.com/synthet/image-scoring-backend/issues/298)).
3. **Gallery `electron/main.ts` dropped off the large-files list** (~382 LoC after IPC register extraction; closes [#151](https://github.com/synthet/image-scoring-gallery/issues/151)).
4. **`modules/db_legacy.py` (15,457 LoC)** remains the largest file — Phase 2 decomposition unchanged.
5. **Runner per-image helpers** (Phase 4) reduced loop sizes; mega-helpers like `_process_tagging_image_row` (~563 LoC) remain optional follow-ups.

---

## Backend — files ≥1000 LoC

| Lines | Path | Notes |
|------:|------|-------|
| 15,457 | `modules/db_legacy.py` | Phase 2 |
| 2,449 | `modules/runs_autodrive.py` | Phase 5 |
| 1,948 | `tests/test_runs_autodrive.py` | *(exempt)* |
| 1,561 | `modules/tagging.py` | Phase 4 follow-up |
| 1,561 | `scripts/python/run_all_musiq_models.py` | *(optional)* |
| 1,320 | `modules/db_postgres.py` | Phase 3 |
| 1,221 | `modules/clustering.py` | |
| 1,174 | `modules/indexing_runner.py` | |
| 1,109 | `scripts/analysis/analyze_phase_status.py` | *(optional)* |
| 1,108 | `modules/mcp_server.py` | Stable post Batch 1 |

**Dropped since June:** `modules/api.py` (7,357 LoC).

---

## Backend — top functions ≥150 LoC (pre–Phase 1b)

| Lines | Symbol | Path |
|------:|--------|------|
| 1,588 | `create_electron_router` | `modules/api/routers/electron.py` |
| 1,547 | `_init_db_impl` | `modules/db_legacy.py` |
| 919 | `AppContent` | gallery `src/AppContent.tsx` |
| 891 | `_init_db_transaction` | `modules/db_postgres.py` |
| 721 | `create_maintenance_router` | `modules/api/routers/maintenance.py` |
| 651 | `create_pipeline_submit_router` | `modules/api/routers/pipeline_submit.py` |
| 563 | `TaggingRunner._process_tagging_image_row` | `modules/tagging.py` |
| 533 | `ClusteringEngine._cluster_images_impl` | `modules/clustering.py` |
| 501 | `IndexingRunner._process_indexing_file` | `modules/indexing_runner.py` |
| 33 | `create_api_router` | `modules/api/__init__.py` |

Full symbol list: backend raw JSON above.

---

## Gallery — files ≥1000 LoC

| Lines | Path |
|------:|------|
| 2,601 | `electron/db.ts` |
| 1,746 | `src/components/Viewer/ImageViewer.tsx` |

**Dropped since June:** `electron/main.ts` (was 1,623 LoC).

---

## Gallery — top functions ≥150 LoC

| Lines | Symbol | Path |
|------:|--------|------|
| 919 | `AppContent` | `src/AppContent.tsx` |
| 587 | `registerSyncHandlers` | `electron/ipc/registerSyncHandlers.ts` |
| 450 | `registerBackupHandlers` | `electron/ipc/registerBackupHandlers.ts` |
| 412 | `createServerApp` | `server/index.ts` |
| 271 | `createHttpBridge` | `src/bridge.ts` |

Full symbol list: gallery raw JSON above.

---

## Re-run commands

```bash
python scripts/audit/codebase_size_audit.py
python scripts/audit/codebase_size_audit.py --root ../image-scoring-gallery
python scripts/audit/codebase_size_audit.py --format json -o docs/raw/codebase-size-audit-$(date +%Y-%m-%d)-backend.json
```

---

## Related

- [CODEBASE_SIZE_REFACTOR_PLAN.md](../planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) — phased checkbox backlog
- [CODEBASE_SIZE_AUDIT_2026-06.md](CODEBASE_SIZE_AUDIT_2026-06.md) — June baseline
- [db-refactor-decomposition.md](../planning/db-refactor-decomposition.md) — DB god-object strategy
