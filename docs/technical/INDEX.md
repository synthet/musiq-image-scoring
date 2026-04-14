# Technical — Index

Existing features and implementation docs only. Plans and proposals → [plans/INDEX.md](../plans/INDEX.md)

## Architecture & Structure

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture (components, data flow, deployment) |
| [PIPELINE_ARCHITECTURE.md](PIPELINE_ARCHITECTURE.md) | Pipeline sequence, flowchart, and Electron integration diagrams |
| [PIPELINE_PHASE_RUNNERS.md](PIPELINE_PHASE_RUNNERS.md) | Phase-by-phase runner ownership and step-by-step execution flow |
| [TECHNICAL_SUMMARY.md](TECHNICAL_SUMMARY.md) | Technical summary with mermaid diagrams |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Repository structure (merged, updated 2026-03-08) |

## Database

| Document | Description |
|----------|-------------|
| [DB_SCHEMA.md](DB_SCHEMA.md) | Firebird database schema (tables, columns, relationships) |
| [EMBEDDINGS.md](EMBEDDINGS.md) | MobileNetV2 `image_embedding`, pgvector, backfill scripts, multi-model notes |
| [DB_RECOVERY_FROM_CORRUPTION.md](DB_RECOVERY_FROM_CORRUPTION.md) | Recovery procedures for database corruption |
| [FIREBIRD_WINDOWS_TEMPDIR.md](FIREBIRD_WINDOWS_TEMPDIR.md) | Windows `TempDirectories` / `fb_sort_*` sort errors (335544675) |
| [migrate_thumbnail_paths_project_rename.py](../../scripts/maintenance/migrate_thumbnail_paths_project_rename.py) | After renaming the repo folder: fix `THUMBNAIL_PATH`, `THUMBNAIL_PATH_WIN`, `SCORES_JSON` in `IMAGES` |

*Plans:* [DB refactor](../plans/database/) · [Firebird→Postgres](../plans/database/FIREBIRD_POSTGRES_MIGRATION.md)

## Models & Scoring

| Document | Description |
|----------|-------------|
| [MODELS_SUMMARY.md](MODELS_SUMMARY.md) | Overview of all models (MUSIQ, LIQE) |
| [MODEL_INPUT_SPECIFICATIONS.md](MODEL_INPUT_SPECIFICATIONS.md) | Input formats, score ranges, constraints |
| [WEIGHTED_SCORING_STRATEGY.md](WEIGHTED_SCORING_STRATEGY.md) | Hybrid pipeline scoring weights (v2.5.2) |
| [MULTI_MODEL_SCORING.md](MULTI_MODEL_SCORING.md) | Multi-model MUSIQ assessment runner |
| [MODEL_SOURCE_TESTING.md](MODEL_SOURCE_TESTING.md) | Model source URL verification guide |

## Stacking & Culling

| Document | Description |
|----------|-------------|
| [CULLING_FEATURE.md](CULLING_FEATURE.md) | AI Culling feature (v3.6.0) |
| [CULLING_REWORK_DESIGN_REVIEW.md](CULLING_REWORK_DESIGN_REVIEW.md) | Pick/Reject flag rework review |
| [STACKS_MANUAL_MANAGEMENT.md](STACKS_MANUAL_MANAGEMENT.md) | Manual stack management design |

*Plan:* [Stack/Culling refactor](../plans/refactoring/STACK_CULLING_REFACTOR_PLAN.md) · *Investigation:* [Culling done / no stacks](../reports/CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md)

## Other Features

| Document | Description |
|----------|-------------|
| [BIRD_SPECIES_WALKTHROUGH.md](BIRD_SPECIES_WALKTHROUGH.md) | Bird species classification via BioCLIP 2 — end-to-end walkthrough |
| [KEYWORD_EXTRACTION_GUIDE.md](KEYWORD_EXTRACTION_GUIDE.md) | BLIP + CLIP keyword extraction tool |
| [RAW_PROCESSING_GUIDE.md](RAW_PROCESSING_GUIDE.md) | RAW file processing pipeline |
| [NEF_FORMAT_REFERENCE.md](NEF_FORMAT_REFERENCE.md) | Nikon NEF container, MakerNote, previews (reference notes) |
| [NEF_IMPLEMENTATION_REVIEW.md](NEF_IMPLEMENTATION_REVIEW.md) | NEF handling code review: backend + image-scoring-gallery |
| [INBROWSER_RAW_PREVIEW.md](INBROWSER_RAW_PREVIEW.md) | In-browser NEF preview (LibRaw/JS) |
| [LAZY_LOAD_DESIGN.md](LAZY_LOAD_DESIGN.md) | Full-resolution lazy loading design |
| [LAZY_LOAD_DESIGN_REVIEW.md](LAZY_LOAD_DESIGN_REVIEW.md) | Design review with issues found |
| [ANALYSIS_SCRIPT_DOCUMENTATION.md](ANALYSIS_SCRIPT_DOCUMENTATION.md) | JSON results analysis script docs |

## API & MCP

| Document | Description |
|----------|-------------|
| [API_CONTRACT.md](API_CONTRACT.md) | API contract summary (endpoints, response models) |
| [RUNS_QUEUE_AND_RESTART.md](RUNS_QUEUE_AND_RESTART.md) | `jobs` queue persistence, `JobDispatcher`, and behavior on WebUI restart |
| [RUNS_WALKTHROUGH.md](RUNS_WALKTHROUGH.md) | End-to-end walkthrough: submit → dispatcher → runners, pause/resume/retry/force, UI tabs |
| [MCP_DEBUGGING_TOOLS.md](MCP_DEBUGGING_TOOLS.md) | MCP server tools for Cursor |

## Cross-project (image-scoring-gallery)

| Document / topic | Description |
|------------------|-------------|
| [AGENT_COORDINATION.md](AGENT_COORDINATION.md) | Integration protocols with **image-scoring-gallery** ([canonical on GitHub](https://github.com/synthet/image-scoring-backend/blob/main/docs/technical/AGENT_COORDINATION.md)) |
| [CROSS_APP_INTEGRATION_AUDIT.md](../testing/CROSS_APP_INTEGRATION_AUDIT.md) | Automated integration coverage between backend and gallery |

**See also:** [Main docs index](../INDEX.md) · [reference/models/](../reference/models/INDEX.md) · [reference/api/](../reference/api/INDEX.md) · [plans/](../plans/INDEX.md) · [image-scoring-gallery docs](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md)
