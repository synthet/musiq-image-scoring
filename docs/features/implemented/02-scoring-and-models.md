# Scoring and models

**Purpose:** Batch and single-image **quality analysis** using multiple IQA / aesthetic models, persisting scores and derived rating/label metadata.

**User-visible behavior:** Folder or selector-based scoring jobs; optional skip of complete rows; force rescore; DB “fix” pass for incomplete rows; single-image score and metadata-only **fix-image** without re-inference.

**Primary code paths:** `modules/scoring.py`, model wrappers (`musiq_wrapper`, `liqe`, `topiq`, `qalign`, …), scoring runner wired from `modules/api.py` and `modules/engine.py`.

**Main HTTP API (prefix `/api`):**

- `POST /api/scoring/start` — enqueue scoring (`job_type` scoring; phases typically indexing → metadata → scoring)
- `POST /api/scoring/stop`, `GET /api/scoring/status`
- `POST /api/scoring/fix-db` — repair incomplete scores (uses runner directly; see OpenAPI description)
- `POST /api/scoring/single` — synchronous single file
- `POST /api/scoring/fix-image` — recompute weighted aggregates from DB model scores + XMP/thumbnail side effects

**Related docs:** [MODELS_SUMMARY](../../technical/MODELS_SUMMARY.md) · [MODEL_INPUT_SPECIFICATIONS](../../technical/MODEL_INPUT_SPECIFICATIONS.md) · [WEIGHTED_SCORING_STRATEGY](../../technical/WEIGHTED_SCORING_STRATEGY.md) · [SCORING_CHANGES](../../technical/SCORING_CHANGES.md) · [MODEL_WEIGHTS](../../reference/models/MODEL_WEIGHTS.md)
