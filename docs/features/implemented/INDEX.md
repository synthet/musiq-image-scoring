# Features — implemented (catalog)

Routing catalog for **shipped** product behavior: what exists, which modules own it, and where to read deep reference. Do not duplicate long technical write-ups — follow links under [`../../technical/INDEX.md`](../../technical/INDEX.md) and [`../../CANONICAL_SOURCES.md`](../../CANONICAL_SOURCES.md).

**Planned / not shipped:** [`../planned/INDEX.md`](../planned/INDEX.md)

| Feature area | Page | Primary modules | Key HTTP prefixes | See also |
|----------------|------|-----------------|-------------------|----------|
| Pipeline, jobs, runs, queue | [01-pipeline-and-runs.md](01-pipeline-and-runs.md) | `phases.py`, `pipeline_orchestrator.py`, `job_dispatcher.py`, `api.py` | `/api/runs/*`, `/api/queue*`, `/api/scope/*`, `/api/pipeline/*`, `/api/jobs/*`, `/api/tasks/active` | [API_CONTRACT](../../technical/API_CONTRACT.md), [PIPELINE_TERMINOLOGY](../../technical/PIPELINE_TERMINOLOGY.md), [RUNS_QUEUE_AND_RESTART](../../technical/RUNS_QUEUE_AND_RESTART.md) |
| Scoring & IQA models | [02-scoring-and-models.md](02-scoring-and-models.md) | `scoring.py`, `musiq_wrapper.py`, `liqe*.py`, `topiq.py`, `qalign.py`, runners in `engine.py` / UI | `/api/scoring/*` | [MODELS_SUMMARY](../../technical/MODELS_SUMMARY.md), [SCORING_CHANGES](../../technical/SCORING_CHANGES.md), [WEIGHTED_SCORING_STRATEGY](../../technical/WEIGHTED_SCORING_STRATEGY.md) |
| Tagging & keywords | [03-tagging-and-keywords.md](03-tagging-and-keywords.md) | `tagging.py`, XMP sync | `/api/tagging/*` | [KEYWORD_EXTRACTION_GUIDE](../../technical/KEYWORD_EXTRACTION_GUIDE.md), [PHASE4_KEYWORDS_HUB](../../planning/database/PHASE4_KEYWORDS_HUB.md) |
| Clustering, culling, stacks | [04-clustering-culling-stacks.md](04-clustering-culling-stacks.md) | `clustering.py`, `db_*` stacks | `/api/clustering/*`, `/api/stacks*` | [CULLING_FEATURE](../../technical/CULLING_FEATURE.md), [STACKS_MANUAL_MANAGEMENT](../../technical/STACKS_MANUAL_MANAGEMENT.md) |
| Embeddings & similarity | [05-embeddings-and-similarity.md](05-embeddings-and-similarity.md) | `similar_search.py`, `embedding_spaces.py`, pgvector layer | `/api/similarity/*`, `/api/embedding_map` | [EMBEDDINGS](../../technical/EMBEDDINGS.md), [EMBEDDINGS.md](../../EMBEDDINGS.md) |
| Import, metadata, thumbnails, RAW | [06-import-metadata-thumbnails-raw.md](06-import-metadata-thumbnails-raw.md) | `exif_extractor.py`, `xmp.py`, `thumbnails.py` | `/api/raw-preview`, `/api/images/generate-thumbnail`, image EXIF/XMP/geocode | [RAW_PROCESSING_GUIDE](../../technical/RAW_PROCESSING_GUIDE.md), [INBROWSER_RAW_PREVIEW](../../technical/INBROWSER_RAW_PREVIEW.md) |
| WebUI & operator surfaces | [07-webui-and-operator-surfaces.md](07-webui-and-operator-surfaces.md) | `webui.py`, `modules/ui/*`, `frontend/` | `/ui/`, `/app`, `/api/status`, `/api/health` | [GRADIO_SERVING_DECISION](../../reports/GRADIO_SERVING_DECISION.md) |
| MCP & agents | [08-mcp-and-agents.md](08-mcp-and-agents.md) | `mcp_server.py` | (stdio/SSE tools; optional `execute_code`) | [AGENT_COORDINATION](../../technical/AGENT_COORDINATION.md), repo root [AGENTS.md](../../../AGENTS.md) |
| Configuration & limits | [09-configuration-and-limits.md](09-configuration-and-limits.md) | `config.py` | (cross-cutting; DB bridge `/api/db/query`) | [DIAGNOSTICS](../../DIAGNOSTICS.md), `config.example.json` |

**Sibling app:** [image-scoring-gallery feature catalog](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/INDEX.md) (Electron + Vite).
