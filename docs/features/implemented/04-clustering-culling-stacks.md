# Clustering, culling, and stacks

**Purpose:** Group similar images into **stacks** (similarity clustering / “culling” stage) so operators can compare picks and rejects.

**User-visible behavior:** Clustering jobs over a folder (or full library) with tunable threshold/time-gap; stack listing and per-stack image membership in API and UIs.

**Primary code paths:** `modules/clustering.py`, clustering runner, stack tables via `modules/db*.py`.

**Main HTTP API (prefix `/api`):**

- `POST /api/clustering/start`, `POST /api/clustering/stop`, `GET /api/clustering/status`
- `GET /api/stacks`, `GET /api/stacks/{stack_id}/images` (and related image query filters by `stack_id` on `GET /api/images`)

**Related docs:** [CULLING_FEATURE](../../technical/CULLING_FEATURE.md) · [STACKS_MANUAL_MANAGEMENT](../../technical/STACKS_MANUAL_MANAGEMENT.md) · [planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md](../../planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md)
