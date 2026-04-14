# Documentation Index

Complete index of all documentation files in the Image Scoring project.

---

## Getting Started

Essential documentation for new users. → [getting-started/INDEX.md](getting-started/INDEX.md)

| Document | Description |
|----------|-------------|
| [README.md](../README.md) | Main project overview and quick start guide |
| [SIMPLE_CLI_GUIDE.md](getting-started/SIMPLE_CLI_GUIDE.md) | Simplified guide / educational CLI tool |
| [SCORING_GUIDE.md](getting-started/SCORING_GUIDE.md) | Detailed NEF scoring instructions |
| [CHANGELOG.md](../CHANGELOG.md) | Version history and release notes |

---

## Architecture & Structure

High-level system design and project layout. → [technical/INDEX.md](technical/INDEX.md)

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](technical/ARCHITECTURE.md) | System architecture (components, data flow, deployment) |
| [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md) | Gradio vs dedicated inference servers for this product shape |
| [TECHNICAL_SUMMARY.md](technical/TECHNICAL_SUMMARY.md) | Technical summary with mermaid diagrams |
| [PROJECT_STRUCTURE.md](technical/PROJECT_STRUCTURE.md) | Repository structure (merged, updated 2026-03-08) |
| [architecture/DB_CONNECTOR.md](architecture/DB_CONNECTOR.md) | DB Connector transport layer — IConnector, FirebirdConnector, PostgresConnector, ApiConnector |
| [architecture/microservices_proposal.md](architecture/microservices_proposal.md) | Abstraction layers roadmap (DbConnector ✅, DbClient ✅, API split, runner refactor) |

---

## Database

| Document | Description |
|----------|-------------|
| [DB_SCHEMA.md](technical/DB_SCHEMA.md) | Firebird database schema (tables, columns, relationships) |
| [DB_RECOVERY_FROM_CORRUPTION.md](technical/DB_RECOVERY_FROM_CORRUPTION.md) | Recovery procedures for database corruption |

*Plans:* [Phase 4 keywords hub](plans/database/PHASE4_KEYWORDS_HUB.md) · [DB refactor](plans/database/DB_SCHEMA_REFACTOR_PLAN.md) · [Firebird→Postgres migration](plans/database/FIREBIRD_POSTGRES_MIGRATION.md) · [archived Phase 4 execution docs](archive/plans/database/INDEX.md)

---

## Models & Scoring

Model specifications, scoring strategy, and fallback systems.

| Document | Description |
|----------|-------------|
| [MODELS_SUMMARY.md](technical/MODELS_SUMMARY.md) | Overview of all models (MUSIQ, LIQE) |
| [MODEL_INPUT_SPECIFICATIONS.md](technical/MODEL_INPUT_SPECIFICATIONS.md) | Input formats, score ranges, constraints |
| [WEIGHTED_SCORING_STRATEGY.md](technical/WEIGHTED_SCORING_STRATEGY.md) | Hybrid pipeline scoring weights (v2.5.2) |
| [MODEL_WEIGHTS.md](reference/models/MODEL_WEIGHTS.md) | Current model weights and scoring logic |
| [MULTI_MODEL_SCORING.md](technical/MULTI_MODEL_SCORING.md) | Multi-model MUSIQ assessment runner |
| [MODEL_SOURCE_TESTING.md](technical/MODEL_SOURCE_TESTING.md) | Model source URL verification guide |

*Research:* [IAA paper analysis](reports/IAA_PAPER_ANALYSIS.md) · [IAA models](reports/IAA_MODELS_LOCAL_DEPLOYMENT.md) · [IAA survey 2024–25](reports/IAA_MODELS_SURVEY_2024_2025.md) · *Proposals:* [IQA model stack](plans/models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md) · [Suggested scoring](plans/models/SUGGESTED_SCORING_ADJUSTMENTS.md)

---

## Features

### Stacking & Culling

| Document | Description |
|----------|-------------|
| [CULLING_FEATURE.md](technical/CULLING_FEATURE.md) | AI Culling feature (v3.6.0) |
| [CULLING_REWORK_DESIGN_REVIEW.md](technical/CULLING_REWORK_DESIGN_REVIEW.md) | Pick/Reject flag rework review |
| [STACKS_MANUAL_MANAGEMENT.md](technical/STACKS_MANUAL_MANAGEMENT.md) | Manual stack management design |
| [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md) | Investigation: culling done but no stacks (runner phase-order bug) |

*Plan:* [Stack/Culling refactor](plans/refactoring/STACK_CULLING_REFACTOR_PLAN.md) · *Planned:* [Embedding applications](plans/embedding/EMBEDDING_APPLICATIONS.md)

### Keyword Extraction

| Document | Description |
|----------|-------------|
| [KEYWORD_EXTRACTION_GUIDE.md](technical/KEYWORD_EXTRACTION_GUIDE.md) | BLIP + CLIP keyword extraction tool |

### RAW Processing

| Document | Description |
|----------|-------------|
| [RAW_PROCESSING_GUIDE.md](technical/RAW_PROCESSING_GUIDE.md) | RAW file processing pipeline |
| [INBROWSER_RAW_PREVIEW.md](technical/INBROWSER_RAW_PREVIEW.md) | In-browser NEF preview (LibRaw/JS) |

### Gallery

→ [gallery/INDEX.md](gallery/INDEX.md)

| Document | Description |
|----------|-------------|
| [GALLERY_GUIDE.md](gallery/GALLERY_GUIDE.md) | Interactive HTML gallery features and scripts |
| [GALLERY_CREATION.md](gallery/GALLERY_CREATION.md) | Step-by-step gallery creation |
| [QUICK_REFERENCE.md](gallery/QUICK_REFERENCE.md) | Gallery creation quick reference |

### Lazy Loading

| Document | Description |
|----------|-------------|
| [LAZY_LOAD_DESIGN.md](technical/LAZY_LOAD_DESIGN.md) | Full-resolution lazy loading design |
| [LAZY_LOAD_DESIGN_REVIEW.md](technical/LAZY_LOAD_DESIGN_REVIEW.md) | Design review with issues found |

### Analysis Script

| Document | Description |
|----------|-------------|
| [ANALYSIS_SCRIPT_DOCUMENTATION.md](technical/ANALYSIS_SCRIPT_DOCUMENTATION.md) | JSON results analysis script docs |

---

## API & MCP

| Document | Description |
|----------|-------------|
| [API.md](reference/api/API.md) | REST API documentation |
| [API_CONTRACT.md](technical/API_CONTRACT.md) | API contract summary (endpoints, response models) |
| [RUNS_QUEUE_AND_RESTART.md](technical/RUNS_QUEUE_AND_RESTART.md) | Runs queue (`jobs`), dispatcher, WebUI restart recovery |
| [API_SCHEMA_IMPLEMENTATION.md](reference/api/API_SCHEMA_IMPLEMENTATION.md) | API schema implementation summary |
| [API_SCHEMA_LLM.md](reference/api/API_SCHEMA_LLM.md) | LLM-optimized API schema |
| [openapi.yaml](reference/api/openapi.yaml) | OpenAPI specification |
| [MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md) | MCP server tools for Cursor |

---

## Setup & Deployment

→ [setup/INDEX.md](setup/INDEX.md)

### Docker

| Document | Description |
|----------|-------------|
| [DOCKER_SETUP.md](setup/DOCKER_SETUP.md) | Docker installation (WSL2) + running the app |

### GPU & CUDA

| Document | Description |
|----------|-------------|
| [GPU_SETUP.md](setup/GPU_SETUP.md) | GPU setup guide (merged) |
| [INSTALL_CUDA.md](setup/INSTALL_CUDA.md) | CUDA installation (RTX 4060) |
| [WSL2_TENSORFLOW_GPU_SETUP.md](setup/WSL2_TENSORFLOW_GPU_SETUP.md) | TensorFlow GPU in WSL2 |

### WSL Environment

| Document | Description |
|----------|-------------|
| [ENVIRONMENTS.md](setup/ENVIRONMENTS.md) | Virtual environments (.venv, ~/.venvs/tf, tests) |
| [WINDOWS_WSL_DEPLOYMENT.md](setup/WINDOWS_WSL_DEPLOYMENT.md) | Windows + WSL2 deployment guide |
| [WSL_PYTHON_PACKAGES.md](setup/WSL_PYTHON_PACKAGES.md) | Python packages in WSL2 venv |
| [WSL_UBUNTU_PACKAGES.md](setup/WSL_UBUNTU_PACKAGES.md) | Ubuntu packages in WSL2 |
| [WSL_WRAPPER_VERIFICATION.md](setup/WSL_WRAPPER_VERIFICATION.md) | WSL wrapper script verification |

### Windows Scripts

| Document | Description |
|----------|-------------|
| [WINDOWS_SCRIPTS_README.md](setup/WINDOWS_SCRIPTS_README.md) | Windows batch/PS scripts for GPU runner |

*Plan:* [Windows native WebUI](plans/setup/WINDOWS_NATIVE_WEBUI_PLAN.md)

---

## Design

| Document | Description |
|----------|-------------|
| [UI_PIPELINE_REDESIGN.md](plans/UI_PIPELINE_REDESIGN.md) | Pipeline-centric UI redesign proposal |
| [design/](design/) | Mockups (HTML, Python) for pipeline UI |

---

## Testing

→ [testing/INDEX.md](testing/INDEX.md)

| Document | Description |
|----------|-------------|
| [CROSS_APP_INTEGRATION_AUDIT.md](testing/CROSS_APP_INTEGRATION_AUDIT.md) | Audit of shared **image-scoring-backend** ↔ **image-scoring-gallery** integration coverage and gaps; gallery tasks: [`docs/integration/TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) |
| [TEST_STATUS.md](testing/TEST_STATUS.md) | Unit test status overview |
| [WSL_TESTS.md](testing/WSL_TESTS.md) | WSL-only pytest markers |
| [archive/testing/DOCUMENTATION_ISSUES.md](archive/testing/DOCUMENTATION_ISSUES.md) | Archived pointer (issues folded into WSL_TESTS / TEST_STATUS) |

---

## Reports — Debugging sessions (historical)

Hub and archive (not a dump of every note in the master index). → [reports/DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md) · [archive/reports/debugging-sessions/INDEX.md](archive/reports/debugging-sessions/INDEX.md)

---

## AI & Agent Helpers

→ [ai/INDEX.md](ai/INDEX.md)

| Document | Description |
|----------|-------------|
| [AGENTS.md](../AGENTS.md) | MCP server and AI agent configuration |
| [LLM_CONTEXT.md](ai/LLM_CONTEXT.md) | High-density project context for AI agents |
| [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md) | Quick reference for MCP debugging tools |
| [.agent/ai_edit_spec.md](../.agent/ai_edit_spec.md) | Guidelines for AI agents editing code |
| [.agent/workflows/](../.agent/workflows/) | Workflows: run_scoring, verify_system, run_webui, run_tests, etc. |

---

## Sibling repository: image-scoring-gallery

Electron app (**[image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)**) — shared API and DB design.

| Topic | Link (GitHub) |
|--------|----------------|
| Docs index | [docs/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md) |
| Integration backlog | [docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) |
| DB refactor impact | [DATABASE_REFACTOR_ANALYSIS.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/DATABASE_REFACTOR_ANALYSIS.md) |
| Planned embedding UI | [features/planned/embeddings/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/planned/embeddings/README.md) |

Protocol: [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md).

---

## Reports & Reviews

→ [reports/INDEX.md](reports/INDEX.md)

| Document | Description |
|----------|-------------|
| [WORK_SUMMARY_2026-03-08.md](reports/WORK_SUMMARY_2026-03-08.md) | Work summary |
| [DEEP_RESEARCH_REPORT.md](reports/DEEP_RESEARCH_REPORT.md) | Deep research report |
| [PARTNER_UPDATES.md](reports/PARTNER_UPDATES.md) | Updates from partner agents |
| [IAA_PAPER_ANALYSIS.md](reports/IAA_PAPER_ANALYSIS.md) | Analysis of modern IAA models paper |
| [IAA_MODELS_LOCAL_DEPLOYMENT.md](reports/IAA_MODELS_LOCAL_DEPLOYMENT.md) | IAA models overview (from PDF) |
| [IAA_MODELS_SURVEY_2024_2025.md](reports/IAA_MODELS_SURVEY_2024_2025.md) | 2024–2025 IAA models survey |
| [GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md) | Gradio + FastAPI product rationale |
| [DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md) | Historical Gradio/fullscreen debugging (links to archive) |
| [RELEASE_HANDOFF_2026-04-10_2026-04-11.md](reports/RELEASE_HANDOFF_2026-04-10_2026-04-11.md) | Dated cross-repo release handoff snapshot |
| [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md) | Culling done / no stacks investigation |
| [PROJECT_REVIEW_2026-01-31.md](reports/project-reviews/PROJECT_REVIEW_2026-01-31.md) | Project review summary |
| [PROJECT_REVIEW_DETAILED_2026-01-31.md](reports/project-reviews/PROJECT_REVIEW_DETAILED_2026-01-31.md) | Detailed project review |
| [CODE_DESIGN_REVIEW.md](reports/CODE_DESIGN_REVIEW.md) | Code and design review |
| [2026_02_09_CODE_AND_DESIGN_REVIEW.md](reports/2026_02_09_CODE_AND_DESIGN_REVIEW.md) | Code & design review |

---

## Project Planning

| Document | Description |
|----------|-------------|
| [TODO.md](../TODO.md) | Canonical project backlog (repository root) |
| [00-backlog-workflow.md](project/00-backlog-workflow.md) | Task workflow, sync order, counts — aligned with [image-scoring-gallery `docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) |
| [BACKLOG_GOVERNANCE.md](project/BACKLOG_GOVERNANCE.md) | Alias → `00-backlog-workflow.md` |
| [project/TODO.md](project/TODO.md) | Pointer to root backlog (historical index archived) |

---

## Plans & Proposals

Plans, proposals, and specs for features not yet implemented. → [plans/INDEX.md](plans/INDEX.md)

| Category | Description |
|----------|-------------|
| [plans/database/](plans/database/) | DB refactor, Phase 4 keywords ([hub](plans/database/PHASE4_KEYWORDS_HUB.md)), Firebird→Postgres migration |
| [plans/refactoring/](plans/refactoring/) | Stack/Culling refactor, webui refactor |
| [plans/models/](plans/models/) | IQA model stack proposal, suggested scoring |
| [plans/embedding/](plans/embedding/) | Embedding application specs (planned) |
| [plans/setup/](plans/setup/) | Windows native WebUI plan |
| [plans/UI_PIPELINE_REDESIGN.md](plans/UI_PIPELINE_REDESIGN.md) | Pipeline-centric UI redesign |

---

## Archive (Legacy / Deprecated)

These files are preserved for historical reference but describe features that have been disabled or superseded. → [archive/INDEX.md](archive/INDEX.md)

| Document | Description | Status |
|----------|-------------|--------|
| [archive/vila/README_VILA.md](archive/vila/README_VILA.md) | VILA model integration | Disabled v2.5.1+, replaced by LIQE |
| [archive/vila/VILA_BATCH_FILES_GUIDE.md](archive/vila/VILA_BATCH_FILES_GUIDE.md) | VILA batch file usage | Disabled v2.5.1+ |
| [archive/vila/VILA_QUICK_START.md](archive/vila/VILA_QUICK_START.md) | VILA quick start | Disabled v2.5.1+ |
| [archive/MODEL_FALLBACK_MECHANISM.md](archive/MODEL_FALLBACK_MECHANISM.md) | TFHub → Kaggle fallback (VILA) | Deprecated |
| [archive/TRIPLE_FALLBACK_SYSTEM.md](archive/TRIPLE_FALLBACK_SYSTEM.md) | Triple fallback (VILA) | Deprecated |
| [archive/UNCOMMITTED_CHANGES_ANALYSIS.md](archive/UNCOMMITTED_CHANGES_ANALYSIS.md) | Uncommitted changes analysis (2025-01-29) | Archived |
| [archive/IMPLEMENTATION_SUMMARY_2025-01.md](archive/IMPLEMENTATION_SUMMARY_2025-01.md) | January 2025 implementation summary | Archived |
| [archive/PROPOSALS_OLD.md](archive/PROPOSALS_OLD.md) | Old feature proposals | Archived |

---

## Wiki Maintenance

This documentation is an LLM-maintained wiki. See [WIKI_SCHEMA.md](WIKI_SCHEMA.md) for conventions, page types, and workflows.

| Document | Description |
|----------|-------------|
| [WIKI_SCHEMA.md](WIKI_SCHEMA.md) | Wiki conventions, page types, linking rules, operations |
| [log.md](log.md) | Chronological record of wiki operations (ingest, query, lint) |
| [raw/](raw/) | Immutable source documents (articles, papers, PDFs) |

**Slash commands:** `/wiki-ingest` (process a source), `/wiki-query` (search and cite), `/wiki-lint` (health-check)

---

## Getting Help

- **Where do I start?** [README.md](../README.md) for overview, then [SCORING_GUIDE.md](getting-started/SCORING_GUIDE.md) or [SIMPLE_CLI_GUIDE.md](getting-started/SIMPLE_CLI_GUIDE.md).
- **How do I create a gallery?** [GALLERY_CREATION.md](gallery/GALLERY_CREATION.md) or [QUICK_REFERENCE.md](gallery/QUICK_REFERENCE.md).
- **What's new?** [CHANGELOG.md](../CHANGELOG.md) has all version changes.
