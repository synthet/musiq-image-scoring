# Configuration and limits

**Purpose:** Centralize runtime **toggles and limits** (models, database engine, API safety, logging, pipeline) in `config.json` / `environment.json` as documented in repo examples.

**User-visible behavior:** Changing config affects which engines, runners, and API gates are active — for example SQL-over-HTTP for Electron, rate limits, log rotation, embedding spaces, and maintenance job behavior.

**Primary code paths:** `modules/config.py`, `config.example.json`, `.env.example` for environment variables consumed at process start.

**Representative API-gated features (see OpenAPI / docstrings for exact keys):**

- `POST /api/db/query` ([`modules/api_db.py`](../../../modules/api_db.py)) — `database.enable_api_db_query`, `database.api_db_query_max_rows`, write gating via `database.query_token` + `X-DB-Write-Token`; React DB Explorer (`/ui/db`) always sends `write: false`
- `database.db_explorer_enabled` — show/hide **DB Explorer** nav and route (default `true`)
- Rate limits on hot `start` endpoints (`modules/ui/security.py`)
- Maintenance endpoints under `/api/maintenance/*` (heal, backfill EXIF dates, regenerate thumbnails, repair paths, queued `start`, etc.)

**Related docs:** [DIAGNOSTICS](../../DIAGNOSTICS.md) · [DATABASE.md](../../DATABASE.md) · [AGENT_COORDINATION](../../technical/AGENT_COORDINATION.md) (Electron `database.engine` modes) · `config.example.json` at repo root
