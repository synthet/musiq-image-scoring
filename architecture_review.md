# Architecture Review: Vexlum Scoring / Driftara Gallery

## Executive Summary
The Vexlum Scoring (backend) and Driftara Gallery (Electron) ecosystem relies on a robust architecture separated by process boundaries. The backend effectively orchestrates complex ML pipelines and abstracts database access via the new `db_connector` layer. The gallery correctly segregates UI concerns to the renderer and system access to the Electron main process.

However, a major architectural vulnerability exists: **database coupling**. By allowing the gallery to connect directly to the PostgreSQL database (`postgres` provider mode), the desktop client is tightly bound to internal backend implementation details. Upcoming backend schema refactorings (Keyword Normalization Phase 4 and Scores Fact Table migration) pose critical breaking risks to the gallery. The top priority refactoring theme is to establish the backend REST API as the single canonical integration boundary, deprecating direct database access from the gallery to ensure independent evolution and stability.

## Confirmed Architecture

### Backend
- **Core Stack:** Python, FastAPI, Gradio WebUI, PostgreSQL + pgvector (`docs/architecture/system-overview.md`).
- **Data Access:** Abstracted via `modules/db_connector/` transport layer supporting Firebird (legacy), Postgres (primary), and API modes (`docs/architecture/DB_CONNECTOR.md`).
- **Pipeline Orchestration:** Asynchronous job/phase tracking via `jobs`, `job_phases`, and `image_phase_status` tables. Executed by background runners (`docs/architecture/pipeline-architecture.md`).
- **Identifiers:** Clear separation between `image_hash` (byte/payload identity for deduplication) and `image_uuid` (logical EXIF identity) (`docs/technical/API_CONTRACT.md`).

### Gallery
- **Core Stack:** Electron main process, Preload/contextBridge, React/Vite renderer (`docs/architecture/01-system-overview.md`).
- **Main Process Boundaries:** Handles `db:*` IPC, `api:*` HTTP requests, native dialogs, and `media://` protocol. Renderer process contains no direct filesystem/DB access.
- **Data Access Provider:** `electron/db/provider.ts` supports both `postgres` (direct DB access) and `api` (HTTP proxy to backend) modes (`docs/architecture/02-database-design.md`).
- **RAW Handling:** Uses local IPC extraction, main-process ExifTool helpers, and backend preview endpoints.

### Cross-Repo Contracts
- **Contract Ownership:** Backend owns REST API contracts (`API_CONTRACT.md`, `openapi.yaml`), DB schema (`DB_SCHEMA.md`), and pipeline terminology (`AGENT_COORDINATION.md`).
- **Shared States:** Pipeline phase codes (`indexing`, `metadata`, `scoring`, `culling`, `keywords`) map to user-facing labels in `src/constants/pipelineLabels.ts` (Gallery) and `frontend/src/types/api.ts` (Backend WebUI).
- **Sync Protocol:** Schema/API changes must be made in backend first, followed by manual updates to gallery IPC/types.

## Top Blockers

### 1. Scores Fact Table Migration Breakage
- **Problem:** The gallery directly queries `score_general`, `score_technical`, etc., on the `images` table when running in `postgres` mode. Backend Phase A1 refactoring moves these to a separate Fact Table.
- **Evidence:** `docs/technical/DATABASE_REFACTOR_ANALYSIS.md` (Gallery) flags this as 🔴 High Risk.
- **Impact:** Complete UI breakage and query failures in the gallery when the backend schema is updated.
- **Recommended fix:** Migrate the gallery exclusively to the `api` DB provider mode, forcing it to consume data via backend DTOs instead of raw SQL. Alternatively, provide an `images_legacy` view in the backend database.
- **Files likely affected:** Gallery `electron/db.ts`, Backend `modules/db_postgres.py`.
- **Tests/checks:** Ensure `GET /api/images` responses map the new fact table structure back into the flat DTO format expected by the gallery.

### 2. Keyword Schema Deprecation (v7.0)
- **Problem:** The backend is soft-deprecating the `images.keywords` column in favor of a normalized `image_keywords` + `keywords_dim` structure (Phase 4). Hard removal is scheduled for v7.0.
- **Evidence:** `docs/technical/AGENT_COORDINATION.md` (Backend).
- **Impact:** Gallery keyword filtering and display will fail.
- **Recommended fix:** Immediately update gallery `electron/db.ts` to use the `EXISTS` join pattern for keyword filtering, or rely entirely on the backend `/api/images` endpoint.
- **Files likely affected:** Gallery `electron/db.ts`.

## Architectural Risks
- **Contract Drift:** Gallery API clients (`apiService.ts`, `apiTypes.ts`) are manually synchronized with backend `openapi.yaml`. Mismatches can cause runtime serialization errors.
- **Duplicated Terminology:** Pipeline labels (`pipelineLabels.ts` in gallery vs `frontend/src/types/api.ts` in backend) require manual double-entry.
- **API/DB Provider Duality:** Maintaining both `postgres` and `api` query modes in the gallery doubles the testing burden and splits the source of truth for query logic.
- **Legacy Compatibility Code:** Supporting legacy Firebird pathways or un-migrated `_get_db_engine()` branches in the backend creates maintenance overhead.

## Refactoring Recommendations

### Backend Refactors

**1. Complete DB Connector Migration**
- **Current issue:** ~60 functions in `modules/db.py` still use legacy `if _get_db_engine() == "postgres"` branches.
- **Proposed change:** Migrate remaining functions to use `get_connector().query()` / `execute()`.
- **Why it helps:** Unifies all DB transport logic, making the code engine-agnostic and easier to test without a live DB.
- **Affected files/modules:** `modules/db.py`.
- **Migration risk:** Low. The `db_connector` implementation is proven in production for key paths.
- **Test plan:** Run unit tests `pytest tests/test_db_connector.py` and Postgres API E2E tests.

### Gallery Refactors

**1. Standardize on API-First Data Access**
- **Current issue:** Gallery connects directly to Postgres, causing tight schema coupling.
- **Proposed change:** Deprecate the `postgres` mode in `electron/db/provider.ts`. Make `api` mode the sole mechanism for fetching data.
- **Why it helps:** Shields the gallery from Backend Keyword and Score Fact Table refactoring. The backend API handles the SQL joins and returns stable JSON contracts.
- **Affected files/modules:** `electron/db/provider.ts`, `electron/db.ts`.
- **Migration risk:** Medium. Requires ensuring all required gallery queries are fully supported by the backend `/api/` endpoints (e.g., specific stack/image filtering).
- **Test plan:** Switch gallery config to `api` mode locally and run full manual regression suite on image browsing and keyword filtering.

**2. Automated API Client Generation**
- **Current issue:** Manual synchronization of `apiTypes.ts`.
- **Proposed change:** Introduce an OpenAPI generator script (e.g., `openapi-typescript`) to generate frontend models directly from the backend's `openapi.json`.
- **Why it helps:** Eliminates contract drift and catches breaking API changes at compile time in the gallery.
- **Affected files/modules:** `package.json`, `electron/apiTypes.ts`.
- **Migration risk:** Low.
- **Test plan:** Validate generated types against existing UI usage via `tsc`.

### Cross-Repo Refactors

**1. Shared Pipeline Constants**
- **Backend change:** Expose pipeline constants (`phase_codes`, user labels) dynamically via a `GET /api/config/pipeline` endpoint.
- **Gallery change:** Fetch these constants on startup or generate them statically during a build step.
- **Shared contract affected:** Pipeline terminology definitions.
- **Docs to update:** `PIPELINE_TERMINOLOGY.md`.
- **Tests/checks in each repo:** Verify gallery UI renders correct stepper labels based on API response.

## Proposed Target Architecture
The desired end-state is an **API-first integration boundary**. 
- The **Backend API** acts as the canonical data interface. It completely hides internal database normalizations (like keyword tables and score fact tables) behind stable JSON response DTOs.
- The **Gallery** operates exclusively as a presentation client. The Electron main process communicates with the backend solely via REST API calls, eliminating the `pg` database driver.
- Type safety across the boundary is guaranteed by automated TypeScript client generation driven by the backend's OpenAPI specification.
- Local diagnostics remain robust via the shared MCP tooling and Doctor scripts.

## Phased Implementation Plan

### Phase 0 — Safety and Inventory
- Run backend doctor: `python scripts/doctor.py`
- Run backend fast tests: `python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py`
- Run gallery checks to establish baseline typecheck/lint status.

### Phase 1 — Contract Stabilization
- Backend: Finalize `openapi.yaml` schemas for the `GET /api/images` responses to ensure they explicitly define the flattened score and keyword structures the gallery expects.

### Phase 2 — Boundary Cleanup (The Core Fix)
- Gallery: Refactor `electron/db.ts` to route all queries through the `api` provider. 
- Gallery: Remove or hard-deprecate the `postgres` DB provider mode.
- Backend: Complete the migration of legacy `db.py` functions to the `db_connector` transport layer.

### Phase 3 — Reliability Improvements
- Gallery: Implement `openapi-typescript` generation to replace manual `apiTypes.ts` definitions.
- Backend/Gallery: Implement a single source of truth for pipeline phase terminology (e.g., build-time schema sync).

### Phase 4 — Developer Experience and Tests
- Update `DATABASE_REFACTOR_ANALYSIS.md` to reflect that the gallery is now shielded from backend DB refactoring via the API.
- Add contract integration tests ensuring the backend API fulfills all gallery query shapes.

## Recommended Commands

**Backend:**
```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```
