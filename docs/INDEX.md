# Documentation Index

Full categorized index for **image-scoring-backend**. Prefer small linked pages over large duplicated dumps; when a topic has a canonical source, link to it rather than restating it.

## Getting Started

| Page | Purpose |
|---|---|
| [README.md](README.md) | Documentation hub and recommended reading path. |
| [../README.md](../README.md) | Project overview and user-facing quick start. |
| [guides/getting-started/INDEX.md](guides/getting-started/INDEX.md) | Getting-started guide index. |
| [guides/getting-started/SCORING_GUIDE.md](guides/getting-started/SCORING_GUIDE.md) | Scoring workflow guide. |
| [guides/getting-started/SIMPLE_CLI_GUIDE.md](guides/getting-started/SIMPLE_CLI_GUIDE.md) | Simplified CLI-oriented guide. |

## Architecture

| Page | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architecture hub. |
| [architecture/system-overview.md](architecture/system-overview.md) | Component and data-flow overview. |
| [architecture/pipeline-architecture.md](architecture/pipeline-architecture.md) | Pipeline sequence and run model. |
| [architecture/project-structure.md](architecture/project-structure.md) | Repository layout. |
| [architecture/DB_CONNECTOR.md](architecture/DB_CONNECTOR.md) | Connector/transport architecture and compatibility notes. |
| [architecture/technical-summary.md](architecture/technical-summary.md) | Compact technical summary. |

## Database

| Page | Purpose |
|---|---|
| [DATABASE.md](DATABASE.md) | PostgreSQL + pgvector hub. |
| [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md) | Schema authority map and table catalog. |
| [planning/database/FIREBIRD_POSTGRES_MIGRATION.md](planning/database/FIREBIRD_POSTGRES_MIGRATION.md) | Historical Firebird to PostgreSQL migration. |
| [planning/database/DB_VECTORS_REFACTOR.md](planning/database/DB_VECTORS_REFACTOR.md) | Vector schema and embedding storage planning/worklog. |
| [planning/database/POSTGRES_SCHEMA_OPTIMIZATIONS.md](planning/database/POSTGRES_SCHEMA_OPTIMIZATIONS.md) | PostgreSQL schema optimization notes. |
| [technical/DB_RECOVERY_FROM_CORRUPTION.md](technical/DB_RECOVERY_FROM_CORRUPTION.md) | Recovery procedures. |

## Image Pipeline

| Page | Purpose |
|---|---|
| [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md) | Pipeline hub: ingestion, metadata, scoring, culling, keywords, embeddings, RAW/NEF. |
| [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md) | Canonical phase codes, operation tokens, and UI labels. |
| [technical/PIPELINE_PHASE_RUNNERS.md](technical/PIPELINE_PHASE_RUNNERS.md) | Runner behavior by phase. |
| [technical/RUN_OPTIONS_MODE_MATRIX.md](technical/RUN_OPTIONS_MODE_MATRIX.md) | Runs submit modes and dispatcher options. |
| [technical/RUNS_QUEUE_AND_RESTART.md](technical/RUNS_QUEUE_AND_RESTART.md) | Queue and restart behavior. |
| [technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md) | Gallery sync import and backend phase semantics. |

## API And MCP

| Page | Purpose |
|---|---|
| [technical/API_CONTRACT.md](technical/API_CONTRACT.md) | REST API contract summary. |
| [reference/api/openapi.yaml](reference/api/openapi.yaml) | OpenAPI specification. |
| [reference/api/API.md](reference/api/API.md) | REST API documentation. |
| [reference/api/API_SCHEMA_IMPLEMENTATION.md](reference/api/API_SCHEMA_IMPLEMENTATION.md) | API schema implementation notes. |
| [reference/api/API_SCHEMA_LLM.md](reference/api/API_SCHEMA_LLM.md) | LLM-oriented API schema summary. |
| [technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md) | MCP debugging tools reference. |
| [../AGENTS.md](../AGENTS.md) | Agent/MCP configuration and tool inventory. |
| [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) | Cross-repo integration protocol. |

## Models And Scoring

| Page | Purpose |
|---|---|
| [features/implemented/02-scoring-and-models.md](features/implemented/02-scoring-and-models.md) | Shipped scoring behavior. |
| [NEW_MODELS_SUMMARY.md](NEW_MODELS_SUMMARY.md) | Consolidated overview of new and roadmap models (ARNIQA, DINOv2, SigLIP2, QPT-V2 status). |
| [technical/MODELS_SUMMARY.md](technical/MODELS_SUMMARY.md) | Model overview. |
| [technical/MODEL_INPUT_SPECIFICATIONS.md](technical/MODEL_INPUT_SPECIFICATIONS.md) | Model input requirements. |
| [technical/MULTI_MODEL_SCORING.md](technical/MULTI_MODEL_SCORING.md) | Multi-model scoring notes. |
| [technical/WEIGHTED_SCORING_STRATEGY.md](technical/WEIGHTED_SCORING_STRATEGY.md) | Weighted scoring strategy. |
| [reference/models/MODEL_WEIGHTS.md](reference/models/MODEL_WEIGHTS.md) | Current model weights and scoring logic. |
| [MODEL_RECOMMENDATIONS_PIPELINES.md](MODEL_RECOMMENDATIONS_PIPELINES.md) | Canonical pipeline model roadmap (ARNIQA, DINOv2, SigLIP2, RAM++; CLIP/OpenCLIP alternate) for scoring, culling, keywords. |
| [planning/models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md](planning/models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md) | Planned model stack changes. |

## Embeddings

| Page | Purpose |
|---|---|
| [EMBEDDINGS.md](EMBEDDINGS.md) | Embeddings hub. |
| [technical/EMBEDDINGS.md](technical/EMBEDDINGS.md) | Registered vector spaces, dimensions, producers, and gotchas. |
| [features/implemented/05-embeddings-and-similarity.md](features/implemented/05-embeddings-and-similarity.md) | Shipped similarity behavior. |
| [features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md](features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md) | Planned embedding app specs. |
| [planning/database/DB_VECTORS_REFACTOR.md](planning/database/DB_VECTORS_REFACTOR.md) | Vector storage planning/worklog. |

## Features Implemented

| Page | Purpose |
|---|---|
| [features/implemented/INDEX.md](features/implemented/INDEX.md) | Shipped feature catalog. |
| [features/implemented/01-pipeline-and-runs.md](features/implemented/01-pipeline-and-runs.md) | Pipeline, jobs, runs, queue. |
| [features/implemented/03-tagging-and-keywords.md](features/implemented/03-tagging-and-keywords.md) | Tagging and keywords. |
| [features/implemented/04-clustering-culling-stacks.md](features/implemented/04-clustering-culling-stacks.md) | Culling, clustering, stacks. |
| [features/implemented/06-import-metadata-thumbnails-raw.md](features/implemented/06-import-metadata-thumbnails-raw.md) | Import, metadata, thumbnails, RAW. |
| [features/implemented/07-webui-and-operator-surfaces.md](features/implemented/07-webui-and-operator-surfaces.md) | Web UI/operator surfaces. |
| [features/implemented/08-mcp-and-agents.md](features/implemented/08-mcp-and-agents.md) | MCP and agents. |
| [features/implemented/09-configuration-and-limits.md](features/implemented/09-configuration-and-limits.md) | Config and limits. |
| [features/implemented/10-phase-status-decoupling.md](features/implemented/10-phase-status-decoupling.md) | Phase status telemetry. |

## Features Planned

| Page | Purpose |
|---|---|
| [features/planned/INDEX.md](features/planned/INDEX.md) | Planned feature index. |
| [features/planned/ui-pipeline-redesign.md](features/planned/ui-pipeline-redesign.md) | Pipeline UI redesign plan. |
| [features/planned/import-discovery-alignment.md](features/planned/import-discovery-alignment.md) | Import/discovery alignment plan. |
| [features/planned/image-identity-and-hashing-improvements.md](features/planned/image-identity-and-hashing-improvements.md) | Image identity and hashing improvements. |
| [features/planned/fix-thumbnail-generation-spec.md](features/planned/fix-thumbnail-generation-spec.md) | Thumbnail generation plan. |
| [features/planned/embeddings/EMBEDDING_APPLICATIONS.md](features/planned/embeddings/EMBEDDING_APPLICATIONS.md) | Embedding application plan. |

## Setup And Deployment

| Page | Purpose |
|---|---|
| [DEVELOPMENT.md](DEVELOPMENT.md) | Local development environment. |
| [guides/setup/INDEX.md](guides/setup/INDEX.md) | Setup guide index. |
| [guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md) | Docker setup. |
| [guides/setup/GPU_SETUP.md](guides/setup/GPU_SETUP.md) | GPU setup. |
| [guides/setup/ENVIRONMENTS.md](guides/setup/ENVIRONMENTS.md) | Environment and venv notes. |
| [guides/setup/PYTHON_VERSION_CAVEATS.md](guides/setup/PYTHON_VERSION_CAVEATS.md) | Python dependency caveats. |
| [guides/setup/WINDOWS_WSL_DEPLOYMENT.md](guides/setup/WINDOWS_WSL_DEPLOYMENT.md) | Windows + WSL deployment. |
| [guides/setup/WINDOWS_SCRIPTS_README.md](guides/setup/WINDOWS_SCRIPTS_README.md) | Windows scripts. |

## Testing

| Page | Purpose |
|---|---|
| [TESTING.md](TESTING.md) | Testing hub and fast command. |
| [testing/INDEX.md](testing/INDEX.md) | Testing subfolder index. |
| [testing/TEST_STATUS.md](testing/TEST_STATUS.md) | Current testing status. |
| [testing/WSL_TESTS.md](testing/WSL_TESTS.md) | WSL test notes. |
| [testing/AUTOMATED_VS_MANUAL_CHECKS.md](testing/AUTOMATED_VS_MANUAL_CHECKS.md) | Manual vs automated checks. |
| [testing/CROSS_APP_INTEGRATION_AUDIT.md](testing/CROSS_APP_INTEGRATION_AUDIT.md) | Backend/gallery integration test audit. |

## Troubleshooting

| Page | Purpose |
|---|---|
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Troubleshooting hub. |
| [DIAGNOSTICS.md](DIAGNOSTICS.md) | Doctor, debug bundle, logs, MCP diagnostics. |
| [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md) | Agent-safe infra quick reference. |
| [reports/DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md) | Indexed debugging write-ups. |

## Reports

| Page | Purpose |
|---|---|
| [reports/INDEX.md](reports/INDEX.md) | Reports index. |
| [reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md](reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md) | Run orchestration audit. |
| [reports/CODE_REVIEW_2026-04-15.md](reports/CODE_REVIEW_2026-04-15.md) | Code review report. |
| [reports/CODE_DESIGN_REVIEW_2026-04-18.md](reports/CODE_DESIGN_REVIEW_2026-04-18.md) | Code/design review. |
| [reports/GRADIO_SERVING_DECISION.md](reports/GRADIO_SERVING_DECISION.md) | Gradio/FastAPI product rationale. |
| [reports/project-reviews/INDEX.md](reports/project-reviews/INDEX.md) | Project review index. |

## Planning

| Page | Purpose |
|---|---|
| [planning/INDEX.md](planning/INDEX.md) | Planning index. |
| [project/INDEX.md](project/INDEX.md) | Project/backlog docs index. |
| [project/00-backlog-workflow.md](project/00-backlog-workflow.md) | Backlog workflow. |
| [../TODO.md](../TODO.md) | Canonical root backlog. |
| [planning/database/](planning/database/) | Database planning. |
| [planning/refactoring/](planning/refactoring/) | Refactoring plans. |
| [planning/models/](planning/models/) | Model plans. |
| [planning/setup/](planning/setup/) | Setup/deployment plans. |

## Archive

| Page | Purpose |
|---|---|
| [archive/INDEX.md](archive/INDEX.md) | Archive index. |
| [archive/vila/INDEX.md](archive/vila/INDEX.md) | VILA archive. |
| [archive/plans/database/INDEX.md](archive/plans/database/INDEX.md) | Archived database plans. |
| [archive/reports/debugging-sessions/INDEX.md](archive/reports/debugging-sessions/INDEX.md) | Archived debugging sessions. |

## Wiki Maintenance

| Page | Purpose |
|---|---|
| [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md) | Source-of-truth map. |
| [WIKI_SCHEMA.md](WIKI_SCHEMA.md) | Wiki conventions. |
| [log.md](log.md) | Append-only wiki activity log. |

## Sibling Repository

| Topic | Gallery link |
|---|---|
| Docs hub | [image-scoring-gallery docs/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md) |
| Canonical source map | [image-scoring-gallery docs/CANONICAL_SOURCES.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/CANONICAL_SOURCES.md) |
| Architecture | [image-scoring-gallery docs/architecture/01-system-overview.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/architecture/01-system-overview.md) |
| Integration TODO | [image-scoring-gallery docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) |
| Implemented features | [image-scoring-gallery docs/features/implemented/INDEX.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/INDEX.md) |
