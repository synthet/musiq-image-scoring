# Canonical Sources

Use these files as authority before adding or changing APIs, database fields, phase names, config keys, scripts, or integration behavior. If a fact is not confirmed here or in the linked source code, write: "Not confirmed in current docs/code; check `<canonical file>`."

| Topic | Authoritative file(s) |
|---|---|
| REST API contract | [technical/API_CONTRACT.md](technical/API_CONTRACT.md), [reference/api/openapi.yaml](reference/api/openapi.yaml), [reference/api/API.md](reference/api/API.md), [modules/api.py](../modules/api.py) |
| Application config (`config.json`, `environment.json`) | [technical/CONFIG.md](technical/CONFIG.md), [modules/config.py](../modules/config.py), [config.example.json](../config.example.json) |
| OpenAPI generation / schema artifact | [reference/api/openapi.yaml](reference/api/openapi.yaml), [openapi.json](../openapi.json), [reference/api/API_SCHEMA_IMPLEMENTATION.md](reference/api/API_SCHEMA_IMPLEMENTATION.md) |
| OpenAPI across backend / gallery / UI | [technical/OPENAPI_CROSS_PROJECT.md](technical/OPENAPI_CROSS_PROJECT.md) |
| Database schema and columns | [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md), [modules/db_postgres.py](../modules/db_postgres.py), [migrations/versions/](../migrations/versions/) |
| PostgreSQL + pgvector migration history | [planning/database/FIREBIRD_POSTGRES_MIGRATION.md](planning/database/FIREBIRD_POSTGRES_MIGRATION.md), [planning/database/DB_VECTORS_REFACTOR.md](planning/database/DB_VECTORS_REFACTOR.md) |
| Pipeline terminology, phase codes, user labels | [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md), [modules/phases.py](../modules/phases.py), [frontend/src/types/api.ts](../frontend/src/types/api.ts) |
| Runs submit options and dispatcher modes | [technical/RUN_OPTIONS_MODE_MATRIX.md](technical/RUN_OPTIONS_MODE_MATRIX.md), [technical/RUNS_QUEUE_AND_RESTART.md](technical/RUNS_QUEUE_AND_RESTART.md) |
| Image pipeline behavior | [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md), [architecture/pipeline-architecture.md](architecture/pipeline-architecture.md), [technical/PIPELINE_PHASE_RUNNERS.md](technical/PIPELINE_PHASE_RUNNERS.md) |
| RAW/NEF preview and EXIF behavior | [technical/RAW_PROCESSING_GUIDE.md](technical/RAW_PROCESSING_GUIDE.md), [technical/INBROWSER_RAW_PREVIEW.md](technical/INBROWSER_RAW_PREVIEW.md), [technical/NEF_IMPLEMENTATION_REVIEW.md](technical/NEF_IMPLEMENTATION_REVIEW.md), [technical/NEF_FORMAT_REFERENCE.md](technical/NEF_FORMAT_REFERENCE.md) |
| Embeddings and vector storage | [EMBEDDINGS.md](EMBEDDINGS.md), [technical/EMBEDDINGS.md](technical/EMBEDDINGS.md), [modules/embedding_spaces.py](../modules/embedding_spaces.py), [planning/database/DB_VECTORS_REFACTOR.md](planning/database/DB_VECTORS_REFACTOR.md) |
| Diagnostics, doctor CLI, debug bundles | [DIAGNOSTICS.md](DIAGNOSTICS.md), [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md), [scripts/doctor.py](../scripts/doctor.py), [scripts/export_debug_bundle.py](../scripts/export_debug_bundle.py) |
| MCP tools and agent workflows | [AGENTS.md](../AGENTS.md), [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md), [docs/technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md), [modules/mcp_server.py](../modules/mcp_server.py) |
| Testing commands and markers | [TESTING.md](TESTING.md), [testing/INDEX.md](testing/INDEX.md), [testing/TEST_STATUS.md](testing/TEST_STATUS.md), [../pytest.ini](../pytest.ini), [AGENTS.md](../AGENTS.md) |
| Troubleshooting | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [reports/DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md), [DIAGNOSTICS.md](DIAGNOSTICS.md) |
| Cross-repo coordination | [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md), [technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md) |
| Gallery docs and implementation follow-up | [image-scoring-gallery docs/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md), [image-scoring-gallery docs/CANONICAL_SOURCES.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/CANONICAL_SOURCES.md) |
| Backlog and planned work | [../TODO.md](../TODO.md), [project/00-backlog-workflow.md](project/00-backlog-workflow.md), [planning/INDEX.md](planning/INDEX.md), [features/planned/INDEX.md](features/planned/INDEX.md) |
| Design system (palette, icons, token package) | [image-scoring-ui docs/DESIGN_SYSTEM.md](https://github.com/synthet/image-scoring-ui/blob/main/docs/DESIGN_SYSTEM.md), npm package `@synthet/image-scoring-design` **1.0.0** ([image-scoring-ui](https://github.com/synthet/image-scoring-ui)); local pointer [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md); consumers: backend `frontend/` (Tailwind), gallery `src/styles/tokens.css` (CSS Modules), Gradio `gradio-snippet.css` |
| Wiki structure and maintenance | [WIKI_SCHEMA.md](WIKI_SCHEMA.md), [log.md](log.md), [INDEX.md](INDEX.md) |

## Cross-Repo Change Order

For API, schema, phase, or terminology changes:

1. Update backend code and backend canonical docs first.
2. Update [reference/api/openapi.yaml](reference/api/openapi.yaml) and [technical/API_CONTRACT.md](technical/API_CONTRACT.md) when REST behavior changes.
3. Update gallery integration code and docs second.
4. Append entries to both repositories' `docs/log.md`.
5. List backend and gallery checks in the PR or handoff.
