# Agent Coordination: Integration Guide

This document defines the coordination protocols for AI agents working across **[image-scoring-backend](https://github.com/synthet/image-scoring-backend)** (Python backend) and **[image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)** (Electron gallery).

## 🏗️ Architectural Overview

The integration relies on two primary shared components:

1. **Shared database: PostgreSQL + pgvector** (primary path; e.g. local Docker).
   * **Owner**: **image-scoring-backend** defines the schema in `modules/db_postgres.py` and versioned migrations via Alembic.
   * **Consumer**: **image-scoring-gallery** queries via `pg` (node-postgres) or `ApiConnector` (HTTP SQL to the backend), depending on configuration.
2. **Service interface: FastAPI** (default port `7860`).
   * **Provider**: **image-scoring-backend** exposes endpoints for scoring, tagging, and clustering.
   * **Consumer**: **image-scoring-gallery** triggers jobs via this API.

**Legacy:** Historical Firebird usage and migration decisions are documented in [FIREBIRD_POSTGRES_MIGRATION.md](../planning/database/FIREBIRD_POSTGRES_MIGRATION.md). Current production paths are PostgreSQL (backend schema + Alembic; gallery `pg` / `api` connectors).

## 🤝 Coordination Protocols

### 1. Schema Changes
* **Protocol**: Database schema changes MUST be implemented in **image-scoring-backend** first (Alembic migrations).
* **Agent Action**: The backend agent should notify the gallery agent (or the user) of any column additions, removals, or type changes.
* **Sync Point**: The gallery agent must update `electron/db.ts` to reflect the new schema in query logic. Impact notes for the gallery live in [DATABASE_REFACTOR_ANALYSIS.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/DATABASE_REFACTOR_ANALYSIS.md) (**image-scoring-gallery**).

### 2. API Contract
* **Protocol**: The backend defines the REST API surface in `modules/api.py`.
* **Agent Action**: Any modification to request/response structures or endpoint paths requires a corresponding update in the gallery.
* **Sync Point**: The gallery agent must update `electron/apiService.ts` and relevant frontend hooks.
* **OpenAPI**: Canonical machine schema is backend-owned; see [OPENAPI_CROSS_PROJECT.md](OPENAPI_CROSS_PROJECT.md). Gallery syncs `api-contract/openapi.json` and runs `npm run generate:api-types` after backend `openapi.json` changes.

**Culling / stack analytics (2026-05):** Backend exposes `GET /api/analytics/culling`, `GET /api/analytics/culling/sessions/{id}`, `GET /api/analytics/stacks/{id}` (see [CULLING_ANALYTICS.md](CULLING_ANALYTICS.md)). Gallery consumes via IPC `api:get-culling-analytics` and `api:get-stack-analytics`; UI in `src/components/CullingAnalytics/`. No new DB columns — read-only aggregates over existing tables.

### 3. Shared Resource Configuration
* **Protocol**: **image-scoring-gallery** `config.json` references API URL, database connection, or paths that pair with **image-scoring-backend** deployment.
* **Agent Action**: Moving the database container, changing credentials, or changing API base URL requires updates in both projects as applicable.

### 4. Keyword Schema Migration (Phase 4)

**Status (v6.3.1+):** The normalized keyword schema is now the **primary read source** on the Python backend. The gallery must be aware of this when querying keywords.

| Phase | Version | Backend Status | Gallery Impact |
|-------|---------|----------------|----------------|
| 4a | v6.2 | ✅ Validation & benchmarks | None |
| 4b | v6.3.1 | ✅ Primary source cutover | Gallery keyword queries should prefer `IMAGE_KEYWORDS` + `KEYWORDS_DIM` |
| 4c | v6.4 | ✅ Soft deprecation logging | Deprecation warnings in backend logs when legacy `IMAGES.KEYWORDS` accessed |
| 4d | v7.0 (Jul 2026) | 🔲 Hard removal | **Breaking:** `IMAGES.KEYWORDS` column removed; gallery MUST use normalized tables |

**Keyword read path (backend v6.3.1+):**
```sql
-- COALESCE: normalized → legacy → empty
COALESCE(
    (SELECT STRING_AGG(kd.keyword_display, ', ')
     FROM image_keywords ik
     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
     WHERE ik.image_id = i.id),
    i.keywords, ''
) AS keywords
```

**Gallery action items:**
- **Before v7.0:** Migrate keyword reads from `IMAGES.KEYWORDS` to `IMAGE_KEYWORDS` + `KEYWORDS_DIM` join
- **Writes:** Use backend API (`PATCH /api/images/{id}`) which dual-writes to both schemas
- **Filtering:** Use `IMAGE_KEYWORDS` join (not `LIKE` on `IMAGES.KEYWORDS`)

**Docs:** [`PHASE4_KEYWORDS_HUB.md`](../planning/database/PHASE4_KEYWORDS_HUB.md) (index), [`PHASE4_KEYWORDS_DEPRECATION.md`](../planning/database/PHASE4_KEYWORDS_DEPRECATION.md), archived completion summary [`PHASE4_COMPLETION_SUMMARY.md`](../archive/plans/database/PHASE4_COMPLETION_SUMMARY.md)

### 5. Cross-repo Sync Automation

To keep the discipline above from being silently skipped, this repo runs the [`Cross-repo sync notice`](../../.github/workflows/cross-repo-sync-notice.yml) workflow on every PR that touches:

* `openapi.json` (REST contract)
* `migrations/versions/**` (Alembic schema)
* `modules/api.py` (FastAPI surface)
* `modules/db_postgres.py` (PostgreSQL schema authority)
* `frontend/package.json` / `frontend/package-lock.json` (`@synthet/image-scoring-design` dependency)

The workflow posts (and idempotently updates) a comment listing the gallery files that typically need follow-up — `api-contract/openapi.json`, `electron/apiTypes.ts`, `electron/apiService.ts`, `electron/db.ts` — and links back to the discipline-tracking issue [`image-scoring-gallery#71`](https://github.com/synthet/image-scoring-gallery/issues/71). The comment is a nudge, not a hard gate; reviewers are still responsible for confirming the gallery side is updated or a counterpart issue is filed.

The same workflow also runs when `frontend/package.json` changes the `@synthet/image-scoring-design` dependency and posts a **design token sync** checklist (gallery `package.json`, UI package rebuild, consumer CSS).

### 6. Design tokens

**Ownership split** (do not conflate UI colors with pipeline schema):

| Concern | Owner | Canonical source |
|---------|-------|------------------|
| UX/UI principles (constitution) | **image-scoring-ui** | [`docs/UX_UI_CONSTITUTION.md`](https://github.com/synthet/image-scoring-ui/blob/main/docs/UX_UI_CONSTITUTION.md); app bindings: [backend `docs/design/UX_UI_CONSTITUTION.md`](../design/UX_UI_CONSTITUTION.md), [gallery `docs/design/UX_UI_CONSTITUTION.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/design/UX_UI_CONSTITUTION.md) |
| Palette, status colors, Lucide icon contract, npm token package | **image-scoring-ui** | [`docs/DESIGN_SYSTEM.md`](https://github.com/synthet/image-scoring-ui/blob/main/docs/DESIGN_SYSTEM.md), package `@synthet/image-scoring-design` (currently **1.2.x**) |
| User-facing stage labels (`STAGE_DISPLAY`, Discovery → Tagging) | **image-scoring-ui** + mirrored in consumers | UI package / backend [`frontend/src/types/api.ts`](../../frontend/src/types/api.ts); gallery [`pipelineLabels.ts`](https://github.com/synthet/image-scoring-gallery/blob/main/src/constants/pipelineLabels.ts) |
| `phase_code`, REST `job_type`, DB phase rows | **image-scoring-backend** | [PIPELINE_TERMINOLOGY.md](PIPELINE_TERMINOLOGY.md), [`modules/phases.py`](../../modules/phases.py) |

**Consumers** (install the design package; do not fork hex tables locally):

- **image-scoring-backend** — React SPA at `/ui/` (Tailwind v4 + `tailwind-theme.css` from the package); minimal Gradio operator UI at `/app` (append `gradio-snippet.css`).
- **image-scoring-gallery** — Electron renderer (CSS Modules + `tokens.css` from the package).

**Agent protocol when the design package changes** (version bump, `src/tokens.json`, or breaking renames):

1. Change **image-scoring-ui** first; run `npm run build` there and bump `@synthet/image-scoring-design` version if publishing.
2. Update `frontend/package.json` (backend) and gallery `package.json` to the new version or refresh `file:` sibling installs.
3. Rebuild/sync generated CSS in both apps; run visual smoke on `/ui/` and gallery shell.
4. Append both repos' `docs/log.md` and mention the version in the PR.

**Agent skills:** `design-tokens` (image-scoring-ui), `backend-frontend-ui` (backend `frontend/`), `gallery-ui` (gallery `src/`).

Local pointers (not authoritative): [design/DESIGN_SYSTEM.md](../design/DESIGN_SYSTEM.md), [design/UX_UI_CONSTITUTION.md](../design/UX_UI_CONSTITUTION.md) in backend and gallery.

## 🔍 Troubleshooting with MCP

Agents use the same **`search` → `dispatch`** workflow on both repos (plus **`sse_status`** to probe live SSE):

| Repo | Default MCP | Optional SSE | Notes |
|------|-------------|--------------|-------|
| **image-scoring-backend** | **`is-be-mcp`** (Node stdio) | **`is-be-live`** | Registry: `mcp/action_registry.json`; setup: [guides/setup/mcp-compact-servers.md](../guides/setup/mcp-compact-servers.md) |
| **image-scoring-gallery** | **`is-ui-mcp`** (Node stdio) | **`is-ui-live`** | Registry: `mcp-server/action_registry.json`; [gallery guide](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md) |

For legacy raw tools not yet in the registry, set **`MCP_SSE_PROFILE=full`** on the backend WebUI process. For **`execute_code`**, use full SSE profile with **`ENABLE_MCP_EXECUTE_CODE=1`** on **`is-be-live`**.

Example backend dispatch for cross-project checks:

| action_id | Usage in coordination |
|-----------|----------------------|
| `jobs.get_recent_jobs` | Verify if a job triggered by the gallery actually started in the backend. |
| `diagnostics.check_database_health` | Diagnose if data inconsistencies are due to backend pipeline failures. |
| `data.query_images` | Compare CLI/DB output with UI results to locate bugs in the query layer. |
| `jobs.get_runner_status` | Check if background workers (scoring/tagging) are alive. |

Gallery examples: `search("gallery status")` → `dispatch("local.gallery_status", {})`; `search("backend health")` → `dispatch("api.api_health", {})`.

## 📚 Maintenance

Keep this document and `AGENTS.md` in both repositories aligned after any major integration refactor. **Canonical copy:** this file in **image-scoring-backend** ([`docs/technical/AGENT_COORDINATION.md` on GitHub](https://github.com/synthet/image-scoring-backend/blob/main/docs/technical/AGENT_COORDINATION.md)).
