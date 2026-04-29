# Tagging and keywords

**Purpose:** Zero-shot and caption-based **keywords** (and optional titles/descriptions) written to the database and XMP sidecars, with optional propagation to visually similar neighbors.

**User-visible behavior:** Batch tagging jobs; per-image tagging; optional BLIP captions; tag propagation using embeddings.

**Primary code paths:** `modules/tagging.py`, tagging runner, keyword sync via `modules/db.py` / Postgres normalized tables (see Phase 4 docs).

**Main HTTP API (prefix `/api`):**

- `POST /api/tagging/start`, `POST /api/tagging/stop`, `GET /api/tagging/status`, `POST /api/tagging/single`
- `POST /api/tagging/propagate` — embedding-neighbor keyword propagation (supports dry run via body)

**Bird species (related optional job):** `POST /api/bird-species/start`, `POST /api/bird-species/stop`, `GET /api/bird-species/status` — BioCLIP-style species labels when `birds` keyword present.

**Related docs:** [KEYWORD_EXTRACTION_GUIDE](../../technical/KEYWORD_EXTRACTION_GUIDE.md) · [PHASE4_KEYWORDS_HUB](../../planning/database/PHASE4_KEYWORDS_HUB.md) · [PIPELINE_TERMINOLOGY](../../technical/PIPELINE_TERMINOLOGY.md) (stage name “Tagging” vs `phase_code` `keywords`)
