# Plans & Proposals — Index

Plans, proposals, and specs for features not yet implemented.

---

## Priority overview (backlog order, 2026-04-10)

Aligned with root [`TODO.md`](../../TODO.md) **Highest-Impact Next Steps**. Tiers are relative; within a tier, cross-repo coordination and schema safety come first.

| Tier | Tracks | Notes |
|------|--------|--------|
| **P0** | Coordination + contracts | Notify gallery on API/schema changes; keep OpenAPI / `API_CONTRACT.md` aligned with `modules/api.py`. |
| **P0** | Database Phase 4–5 | Keyword path coordination with gallery; Phase **5** PG work ([POSTGRES_SCHEMA_OPTIMIZATIONS.md](database/POSTGRES_SCHEMA_OPTIMIZATIONS.md), [DB_STATUS_REPORT.md](database/DB_STATUS_REPORT.md)) — vectors + integrity **high** in that doc. |
| **P1** | Verification + embedding UX | RAW preview manual QA ([TODO.md](../../TODO.md)); embedding API → UI wiring, bidirectional control ([embedding/NEXT_STEPS.md](embedding/NEXT_STEPS.md), App 08). |
| **P1** | Operator UI | [UX_UI_IMPLEMENTATION_PLAN.md](UX_UI_IMPLEMENTATION_PLAN.md) P0/P1 (Quick Start, confirmations, gallery presets). |
| **P2** | Large UI / refactor proposals | [UI_PIPELINE_REDESIGN.md](UI_PIPELINE_REDESIGN.md) (tab merge); [IMPORT_DISCOVERY_ALIGNMENT.md](IMPORT_DISCOVERY_ALIGNMENT.md) (Import vs Discovery); [STACK_CULLING_REFACTOR_PLAN.md](refactoring/STACK_CULLING_REFACTOR_PLAN.md); [REFACTORING_PLAN.md](refactoring/REFACTORING_PLAN.md) (`webui.py` split). |
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

## Models & Scoring

| Document | Description |
|----------|-------------|
| [IQA_MODEL_STACK_UPDATE_PROPOSAL.md](models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md) | Proposal: Modernize model stack (QPT V2, TOPIQ-NR) |
| [SUGGESTED_SCORING_ADJUSTMENTS.md](models/SUGGESTED_SCORING_ADJUSTMENTS.md) | Proposed scoring weight changes |

## Embedding Applications (planned)

| Document | Description |
|----------|-------------|
| [NEXT_STEPS.md](embedding/NEXT_STEPS.md) | Implementation status and remaining gaps (UX, orchestration) |
| [EMBEDDING_APPLICATIONS.md](embedding/EMBEDDING_APPLICATIONS.md) | Overview of proposed embedding use cases |
| [EMBEDDING_APPLICATIONS_INDEX.md](embedding/EMBEDDING_APPLICATIONS_INDEX.md) | Index of detailed specs |
| [EMBEDDING_APP_01_DIVERSITY_SELECTION.md](embedding/EMBEDDING_APP_01_DIVERSITY_SELECTION.md) | Diversity-aware selection |
| [EMBEDDING_APP_02_NEAR_DUPLICATE_DETECTION.md](embedding/EMBEDDING_APP_02_NEAR_DUPLICATE_DETECTION.md) | Near-duplicate detection |
| [EMBEDDING_APP_03_TAG_PROPAGATION.md](embedding/EMBEDDING_APP_03_TAG_PROPAGATION.md) | Tag propagation |
| [EMBEDDING_APP_04_OUTLIER_DETECTION.md](embedding/EMBEDDING_APP_04_OUTLIER_DETECTION.md) | Outlier detection |
| [EMBEDDING_APP_05_2D_EMBEDDING_MAP.md](embedding/EMBEDDING_APP_05_2D_EMBEDDING_MAP.md) | 2D embedding map |
| [EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md](embedding/EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md) | Smart stack representative |
| [EMBEDDING_APP_07_MORE_LIKE_THIS_UI.md](embedding/EMBEDDING_APP_07_MORE_LIKE_THIS_UI.md) | More Like This UI |
| [EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md](embedding/EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md) | Gradio integration plan |

## Setup

| Document | Description |
|----------|-------------|
| [WINDOWS_NATIVE_WEBUI_PLAN.md](setup/WINDOWS_NATIVE_WEBUI_PLAN.md) | Plan: Run Gradio WebUI natively on Windows (no WSL) |

## Design

| Document | Description |
|----------|-------------|
| [UI_PIPELINE_REDESIGN.md](UI_PIPELINE_REDESIGN.md) | Pipeline-centric UI redesign proposal |
| [IMPORT_DISCOVERY_ALIGNMENT.md](IMPORT_DISCOVERY_ALIGNMENT.md) | Align gallery **Import** with pipeline **Discovery** (indexing): recursive scope, shared rules, optional job-backed import |

**See also:** [design/](../design/) — Mockups (HTML, Python) for pipeline UI · [Main docs index](../INDEX.md)
