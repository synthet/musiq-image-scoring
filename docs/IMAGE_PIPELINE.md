# Image pipeline

Hub page — ingestion, metadata, scoring, and RAW/NEF behavior.

## Pipeline stages

- **[architecture/pipeline-architecture.md](architecture/pipeline-architecture.md)** — end-to-end flow.
- **[technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md)** — naming map.

## RAW / NEF / EXIF

- **[technical/NEF_IMPLEMENTATION_REVIEW.md](technical/NEF_IMPLEMENTATION_REVIEW.md)** — Nikon NEF / preview / metadata pitfalls.
- **[technical/NEF_FORMAT_REFERENCE.md](technical/NEF_FORMAT_REFERENCE.md)** — format notes.

**Agent warning:** do not change EXIF orientation or NEF preview handling without regression tests and review of the above docs.

## Scoring and models

- **[technical/SCORING_CHANGES.md](technical/SCORING_CHANGES.md)** — scoring-related behavior notes.

## Embeddings (similarity / clustering)

- **[EMBEDDINGS.md](EMBEDDINGS.md)** — link to vector storage and backfill.
