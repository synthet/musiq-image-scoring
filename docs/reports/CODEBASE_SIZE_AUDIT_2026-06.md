---
type: Report
title: Codebase size audit — June 2026
description: Point-in-time LoC audit (files ≥1000, functions ≥150) for backend and gallery; feeds the phased refactor checklist.
resource: docs/reports/CODEBASE_SIZE_AUDIT_2026-06.md
tags: [docs, reports, refactoring, audit, codebase-size]
timestamp: 2026-06-30T00:00:00Z
okf_version: 0.1
---

# Codebase size audit — June 2026

Point-in-time scan of **image-scoring-backend** and sibling **image-scoring-gallery** using `scripts/audit/codebase_size_audit.py`. Thresholds: **files ≥1000 LoC**, **functions/methods ≥150 LoC**.

**Action plan:** [CODEBASE_SIZE_REFACTOR_PLAN.md](../planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) (backend Phases 0–10) · [Gallery plan](https://github.com/synthet/image-scoring-gallery/blob/main/docs/planning/CODEBASE_SIZE_REFACTOR_PLAN.md) (Phases 1–8) · Re-run skill [codebase-size-audit](../../../.cursor/skills/codebase-size-audit/SKILL.md)

**Raw JSON (immutable):** [codebase-size-audit-2026-06-30-backend.json](../raw/codebase-size-audit-2026-06-30-backend.json), [codebase-size-audit-2026-06-30-gallery.json](../raw/codebase-size-audit-2026-06-30-gallery.json)

---

## Key takeaways

1. **`modules/db_legacy.py` (15,457 LoC)** is the largest hotspot — Phase 2 of the refactor plan aligns with [db-refactor-decomposition.md](../planning/db-refactor-decomposition.md).
2. **`create_api_router` (6,846 LoC)** inside `modules/api.py` (7,357 LoC total) dominates backend function size — domain router split is Phase 1 (high OpenAPI risk).
3. **Batch 1 extractions are merged** — `mcp_server.py` down to 1,108 LoC; gallery `main.ts` 1,623 LoC after IPC register splits; `electron/db.ts` (2,601 LoC) and `create_api_router` remain for later phases.
4. **Gallery top files:** `electron/db.ts` (2,601), `ImageViewer.tsx` (1,746), `main.ts` (1,623); `AppContent` function still 919 LoC.
5. **Runner smell:** multiple `_run_batch_internal` / `process` methods ≥150 LoC across tagging, clustering, indexing, metadata, scoring, selection, pipeline, engine — Phase 4 groups mechanical per-image extractions.

---

## Backend — files ≥1000 LoC

| Lines | Path |
|------:|------|
| 15,457 | `modules/db_legacy.py` |
| 7,357 | `modules/api.py` |
| 2,449 | `modules/runs_autodrive.py` |
| 1,948 | `tests/test_runs_autodrive.py` *(exempt in plan)* |
| 1,561 | `scripts/python/run_all_musiq_models.py` *(optional)* |
| 1,320 | `modules/db_postgres.py` |
| 1,299 | `modules/tagging.py` |
| 1,214 | `modules/clustering.py` |
| 1,109 | `scripts/analysis/analyze_phase_status.py` *(optional)* |
| 1,108 | `modules/mcp_server.py` |

## Backend — top functions ≥150 LoC

| Lines | Symbol | Path |
|------:|--------|------|
| 6,846 | `create_api_router` | `modules/api.py` |
| 1,547 | `_init_db_impl` | `modules/db_legacy.py` |
| 891 | `_init_db_transaction` | `modules/db_postgres.py` |
| 582 | `ClusteringEngine._cluster_images_impl` | `modules/clustering.py` |
| 511 | `TaggingRunner._run_batch_internal` | `modules/tagging.py` |
| 469 | `main` | `webui.py` |
| 436 | `IndexingRunner._run_batch_internal` | `modules/indexing_runner.py` |
| 426 | `upsert_image` | `modules/db_legacy.py` |
| 328 | `auto_drive_runs` | `modules/runs_autodrive.py` |

Full symbol list: backend raw JSON above.

## Gallery — files ≥1000 LoC

| Lines | Path |
|------:|------|
| 2,601 | `electron/db.ts` |
| 1,746 | `src/components/Viewer/ImageViewer.tsx` |
| 1,623 | `electron/main.ts` |

## Gallery — top functions ≥150 LoC

| Lines | Symbol | Path |
|------:|--------|------|
| 919 | `AppContent` | `src/AppContent.tsx` |
| 711 | `startFullApplication` | `electron/main.ts` |
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

- [CODEBASE_SIZE_REFACTOR_PLAN.md](../planning/refactoring/CODEBASE_SIZE_REFACTOR_PLAN.md) — phased checkbox backlog (implementation)
- [db-refactor-decomposition.md](../planning/db-refactor-decomposition.md) — DB god-object strategy
- [REFACTORING_PLAN.md](../planning/refactoring/REFACTORING_PLAN.md) — Gradio / `webui.py` tab split
- [RUN_ORCHESTRATION_AUDIT_2026-04-17.md](RUN_ORCHESTRATION_AUDIT_2026-04-17.md) — prior orchestration size/complexity review
