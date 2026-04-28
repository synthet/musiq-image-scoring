# Planning & migrations — index

Database migrations, schema phases, refactors, and model roadmaps. **Product / UI specs** that are not yet shipped live under [`../features/planned/INDEX.md`](../features/planned/INDEX.md) (embedding apps, pipeline UI plans, import alignment).

---

## Priority overview (backlog order, 2026-04-10)

Aligned with root [`TODO.md`](../../TODO.md) **Highest-Impact Next Steps**. Tiers are relative; within a tier, cross-repo coordination and schema safety come first.

| Tier | Tracks | Notes |
|------|--------|--------|
| **P0** | Coordination + contracts | Notify gallery on API/schema changes; keep OpenAPI / `API_CONTRACT.md` aligned with `modules/api.py`. |
| **P0** | Database Phase 4–5 | Keyword path coordination with gallery; Phase **5** PG work ([POSTGRES_SCHEMA_OPTIMIZATIONS.md](database/POSTGRES_SCHEMA_OPTIMIZATIONS.md), [DB_STATUS_REPORT.md](database/DB_STATUS_REPORT.md)) — vectors + integrity **high** in that doc. |
| **P1** | Verification + embedding UX | RAW preview manual QA ([TODO.md](../../TODO.md)); embedding API → UI wiring, bidirectional control ([`../features/planned/embeddings/NEXT_STEPS.md`](../features/planned/embeddings/NEXT_STEPS.md), App 08). |
| **P1** | Operator UI | [`../features/planned/ux-ui-implementation-plan.md`](../features/planned/ux-ui-implementation-plan.md) P0/P1 (Quick Start, confirmations, gallery presets). |
| **P2** | Large UI / refactor proposals | [`../features/planned/ui-pipeline-redesign.md`](../features/planned/ui-pipeline-redesign.md) (tab merge); [`../features/planned/import-discovery-alignment.md`](../features/planned/import-discovery-alignment.md) (Import vs Discovery); [STACK_CULLING_REFACTOR_PLAN.md](refactoring/STACK_CULLING_REFACTOR_PLAN.md); [REFACTORING_PLAN.md](refactoring/REFACTORING_PLAN.md) (`webui.py` split). |
| **P3** | Setup / research | [WINDOWS_NATIVE_WEBUI_PLAN.md](setup/WINDOWS_NATIVE_WEBUI_PLAN.md); [IQA_MODEL_STACK_UPDATE_PROPOSAL.md](models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md). |

---

## Database

| Document | Description |
|----------|-------------|
| [PHASE4_KEYWORDS_HUB.md](database/PHASE4_KEYWORDS_HUB.md) | **Start here** — index of Phase 4 keyword docs (living vs [archived](../archive/plans/database/INDEX.md)) |
| [PHASE4_KEYWORDS_DEPRECATION.md](database/PHASE4_KEYWORDS_DEPRECATION.md) | Deprecation timeline (`IMAGES.KEYWORDS` → normalized) |
| [PHASE4_STATUS_SUMMARY.md](database/PHASE4_STATUS_SUMMARY.md) | Phase 4 status narrative and timeline |
| [DB_SCHEMA_REFACTOR_PLAN.md](database/DB_SCHEMA_REFACTOR_PLAN.md) | Strategic phase definitions for schema refactor |
| [DB_SCHEMA_REFACTOR_IMPLEMENTATION.md](database/DB_SCHEMA_REFACTOR_IMPLEMENTATION.md) | Implementation guide for schema refactor |
| [FIREBIRD_POSTGRES_MIGRATION.md](database/FIREBIRD_POSTGRES_MIGRATION.md) | Migration plan from Firebird to PostgreSQL + pgvector |
| [NEXT_STEPS.md](database/NEXT_STEPS.md) | Keyword/metadata refactor — remaining steps and verification |
| [DB_VECTORS_REFACTOR.md](database/DB_VECTORS_REFACTOR.md) | Multi-type vectors (pgvector) and optional normalization appendix |
| [DB_STATUS_REPORT.md](database/DB_STATUS_REPORT.md) | PostgreSQL status narrative |
| [POSTGRES_SCHEMA_OPTIMIZATIONS.md](database/POSTGRES_SCHEMA_OPTIMIZATIONS.md) | Phase 5 PostgreSQL optimizations |

## Refactoring

| Document | Description |
|----------|-------------|
| [STACK_CULLING_REFACTOR_PLAN.md](refactoring/STACK_CULLING_REFACTOR_PLAN.md) | Unified Stack + Culling refactor plan |
| [REFACTORING_PLAN.md](refactoring/REFACTORING_PLAN.md) | webui.py modular refactoring plan |
| [db-refactor-decomposition.md](db-refactor-decomposition.md) | Long-range `modules/db.py` decomposition plan |
| [import-phase-enrichment.md](import-phase-enrichment.md) | Spec: enrich indexing/import with cheap file-local fields |

## Models & Scoring

| Document | Description |
|----------|-------------|
| [IQA_MODEL_STACK_UPDATE_PROPOSAL.md](models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md) | Proposal: Modernize model stack (QPT V2, TOPIQ-NR) |
| [SUGGESTED_SCORING_ADJUSTMENTS.md](models/SUGGESTED_SCORING_ADJUSTMENTS.md) | Proposed scoring weight changes |

## Setup (platform)

| Document | Description |
|----------|-------------|
| [WINDOWS_NATIVE_WEBUI_PLAN.md](setup/WINDOWS_NATIVE_WEBUI_PLAN.md) | Plan: Run Gradio WebUI natively on Windows (no WSL) |

**See also:** [Feature specs (planned)](../features/planned/INDEX.md) · [design/](../design/) mockups · [Main docs index](../INDEX.md)
