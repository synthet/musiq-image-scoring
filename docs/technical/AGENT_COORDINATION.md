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

**Legacy:** Historical Firebird usage and migration decisions are documented in [FIREBIRD_POSTGRES_MIGRATION.md](../plans/database/FIREBIRD_POSTGRES_MIGRATION.md). Current production paths are PostgreSQL (backend schema + Alembic; gallery `pg` / `api` connectors).

## 🤝 Coordination Protocols

### 1. Schema Changes
* **Protocol**: Database schema changes MUST be implemented in **image-scoring-backend** first (Alembic migrations).
* **Agent Action**: The backend agent should notify the gallery agent (or the user) of any column additions, removals, or type changes.
* **Sync Point**: The gallery agent must update `electron/db.ts` to reflect the new schema in query logic. Impact notes for the gallery live in [DATABASE_REFACTOR_ANALYSIS.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/DATABASE_REFACTOR_ANALYSIS.md) (**image-scoring-gallery**).

### 2. API Contract
* **Protocol**: The backend defines the REST API surface in `modules/api.py`.
* **Agent Action**: Any modification to request/response structures or endpoint paths requires a corresponding update in the gallery.
* **Sync Point**: The gallery agent must update `electron/apiService.ts` and relevant frontend hooks.

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

**Docs:** [`PHASE4_KEYWORDS_HUB.md`](../plans/database/PHASE4_KEYWORDS_HUB.md) (index), [`PHASE4_KEYWORDS_DEPRECATION.md`](../plans/database/PHASE4_KEYWORDS_DEPRECATION.md), archived completion summary [`PHASE4_COMPLETION_SUMMARY.md`](../archive/plans/database/PHASE4_COMPLETION_SUMMARY.md)

## 🔍 Troubleshooting with MCP

Agents use **stdio** MCP against the Python backend: **`imgscore-py-stdio`** in the **image-scoring-backend** workspace; **`imgscore-el-stdio`** in **image-scoring-gallery** (same server, different `cwd`). For WebUI / **`execute_code`**, enable **`imgscore-py-sse`** or **`imgscore-el-sse`** (unique keys, same URL). Use these to diagnose cross-project issues:

| Tool | Usage in Coordination |
|------|------------------------|
| `get_recent_jobs` | Verify if a job triggered by the gallery actually started in the backend. |
| `check_database_health` | Diagnose if data inconsistencies are due to backend pipeline failures. |
| `query_images` | Compare CLI/DB output with UI results to locate bugs in the query layer. |
| `get_runner_status` | Check if background workers (scoring/tagging) are alive. |

## 📚 Maintenance

Keep this document and `AGENTS.md` in both repositories aligned after any major integration refactor. **Canonical copy:** this file in **image-scoring-backend** ([`docs/technical/AGENT_COORDINATION.md` on GitHub](https://github.com/synthet/image-scoring-backend/blob/main/docs/technical/AGENT_COORDINATION.md)).
