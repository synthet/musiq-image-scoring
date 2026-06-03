# Image pipeline

Hub page for ingestion, metadata, scoring, culling, keywords, embeddings, and RAW/NEF behavior. Keep phase names aligned with **[technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md)**.

## Ingestion And Indexing

- **[architecture/pipeline-architecture.md](architecture/pipeline-architecture.md)** - end-to-end flow.
- **[technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md)** - canonical stage titles, `phase_code` values, and submit operation tokens.
- **[technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md](technical/ELECTRON_SYNC_IMPORT_AND_PHASES.md)** - how gallery **Sync from device** records imported files and schedules backend phases.

## Metadata And Thumbnails

- **[features/implemented/06-import-metadata-thumbnails-raw.md](features/implemented/06-import-metadata-thumbnails-raw.md)** - shipped import, metadata, thumbnail, and RAW behavior.
- **[technical/RAW_PROCESSING_GUIDE.md](technical/RAW_PROCESSING_GUIDE.md)** - RAW processing reference.

## Scoring

- **[features/implemented/02-scoring-and-models.md](features/implemented/02-scoring-and-models.md)** - shipped scoring/model behavior.
- **[planning/models/TECHNICAL_FAILURE_DETECTION_PLAN.md](planning/models/TECHNICAL_FAILURE_DETECTION_PLAN.md)** - technical failure detection integration during scoring.
- **[technical/SCORING_CHANGES.md](technical/SCORING_CHANGES.md)** - scoring-related behavior notes.
- **[technical/MODEL_INPUT_SPECIFICATIONS.md](technical/MODEL_INPUT_SPECIFICATIONS.md)** and **[reference/models/MODEL_WEIGHTS.md](reference/models/MODEL_WEIGHTS.md)** - model inputs and weights.

## Culling And Stacks

- **[features/implemented/04-clustering-culling-stacks.md](features/implemented/04-clustering-culling-stacks.md)** - shipped clustering, culling, and stack behavior.
- **[technical/CULLING_FEATURE.md](technical/CULLING_FEATURE.md)** and **[technical/STACKS_MANUAL_MANAGEMENT.md](technical/STACKS_MANUAL_MANAGEMENT.md)** - deep references.

## Keywords

- **[features/implemented/03-tagging-and-keywords.md](features/implemented/03-tagging-and-keywords.md)** - shipped tagging and keyword behavior.
- **[technical/KEYWORD_EXTRACTION_GUIDE.md](technical/KEYWORD_EXTRACTION_GUIDE.md)** - BLIP/CLIP keyword extraction reference.
- **[planning/database/PHASE4_KEYWORDS_HUB.md](planning/database/PHASE4_KEYWORDS_HUB.md)** - keyword schema migration history and follow-up pointers.

## Embeddings

- **[EMBEDDINGS.md](EMBEDDINGS.md)** - vector storage and backfill hub.
- **[features/implemented/05-embeddings-and-similarity.md](features/implemented/05-embeddings-and-similarity.md)** - shipped similarity/embedding behavior.

## RAW / NEF / EXIF

- **[technical/NEF_IMPLEMENTATION_REVIEW.md](technical/NEF_IMPLEMENTATION_REVIEW.md)** - Nikon NEF / preview / metadata pitfalls.
- **[technical/NEF_FORMAT_REFERENCE.md](technical/NEF_FORMAT_REFERENCE.md)** - format notes.
- **[technical/INBROWSER_RAW_PREVIEW.md](technical/INBROWSER_RAW_PREVIEW.md)** - in-browser preview behavior.

**Regression warning:** do not change EXIF orientation, NEF preview extraction, RAW preview serving, or export orientation behavior without targeted regression tests and review of the RAW/NEF docs above.
