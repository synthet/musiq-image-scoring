# Vexlum Scoring — Python backend

AI-powered image scoring, tagging, and clustering engine using MUSIQ, LIQE, BLIP, and CLIP models. Serves a FastAPI REST API and Gradio web UI.

## Related Projects

| Project | Repository | Role |
|---------|------------|------|
| **image-scoring-backend** (this) | `https://github.com/synthet/image-scoring-backend` | AI scoring engine, FastAPI server, PostgreSQL DB schema owner |
| **image-scoring-gallery** | `https://github.com/synthet/image-scoring-gallery` | Desktop UI, IPC query layer, React/Vite |

This project is the **schema authority** — DDL is managed via `modules/db_postgres.py` (PostgreSQL) and Alembic migrations.

## Backlog & queue (read this before picking work)

The canonical queue is the **GitHub Project board**, not `TODO.md`:

**→ https://github.com/users/synthet/projects/1**

It spans both repos. The `TODO.md` files are pointers only.

**Mandatory contract for every agent (human or AI). Do all five steps:**

1. **Pick from `Stage = Ready`** on the board, sorted by `priority:p0..p3`. If `Ready` is empty, ask the maintainer — do not invent work.
2. **Claim** the issue: `/task-claim <N>` (preferred) or the manual `gh` flow in [`docs/project/00-backlog-workflow.md`](docs/project/00-backlog-workflow.md). Claiming assigns you and moves the card to `Stage = Claimed`.
3. **Flip to `Stage = In Progress`** on your first commit.
4. **If blocked**, move the card to `Stage = Blocked` *and* comment on the issue with the blocker + what would unblock it. Do not silently abandon a claimed card.
5. **Reference the issue in the PR** with `Closes #<N>` (the PR template requires it). Move the card to `Stage = Review` while the PR is open; merging closes the issue and flips `Status = Done`.

**Project ID quick-reference** (for scripts): project node `PVT_kwHOAFXgIs4BWC3c`, Stage field `PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0`. Full Stage option IDs and command examples in [`docs/project/00-backlog-workflow.md`](docs/project/00-backlog-workflow.md) §5.

**Do not** add tasks to `TODO.md`, do not work without an issue, and do not skip the Stage transitions — agents that don't update Stage make the queue lie about what's actually being worked on.

## Architecture

### Pipeline Phases

Processing is organized into sequential phases defined in `modules/phases.py`:

| Phase | Code | Description |
|-------|------|-------------|
| Indexing | `indexing` | Discover and register image files |
| Metadata | `metadata` | Extract EXIF, XMP, file metadata |
| Scoring | `scoring` | Run ML models (MUSIQ, LIQE, TOPIQ, Q-Align) |
| Culling | `culling` | Cluster similar images |
| Keywords | `keywords` | Generate tags via BLIP/CLIP captioning |

Phase status values: `not_started | running | done | skipped | failed`

### Key Modules

| Module | Role |
|--------|------|
| `modules/db.py` | Database abstraction layer; engine routing (`_get_db_engine()`) and PostgreSQL connection factory |
| `modules/api.py` | FastAPI REST endpoints for scoring, tagging, clustering jobs |
| `modules/engine.py` | Batch processor; producer-consumer pipeline orchestrator |
| `modules/pipeline.py` | Low-level pipeline primitives |
| `modules/pipeline_orchestrator.py` | High-level orchestration across phases |
| `modules/phases.py` | Phase definitions (`PhaseCode`, `PhaseStatus` enums) |
| `modules/phases_policy.py` | Rules for when phases can/should run |
| `modules/phase_executors.py` | Per-phase execution logic |
| `modules/job_dispatcher.py` | Routes API job requests to phase executors |
| `modules/config.py` | Config management via `config.json` |
| `modules/scoring.py` | Score computation and normalization |
| `modules/tagging.py` | Keyword/tag generation |
| `modules/clustering.py` | Image clustering (culling) |
| `modules/mcp_server.py` | MCP server for AI agent integration (stdio) |
| `modules/selection.py` | Image selection and filtering |
| `modules/ui/status_gradio.py` | Minimal operator status page served at `/app` |

### ML Models

| Model | Module | Task |
|-------|--------|------|
| MUSIQ | `modules/musiq_wrapper.py` | Multi-scale image quality |
| LIQE | `modules/liqe.py` / `liqe_wrapper.py` | Learned image quality evaluator |
| TOPIQ | `modules/topiq.py` | Top-down image quality |
| Q-Align | `modules/qalign.py` | Quality alignment scoring |
| BLIP/CLIP | `modules/tagging.py` | Captioning and tagging |

### Environment

- **Hybrid:** Windows host + WSL 2 for GPU/ML workloads
- **DB (primary):** PostgreSQL + pgvector (local Docker, port 5432) — set `database.engine: "postgres"` in `config.json`
- **WebUI:** FastAPI on port 7860; `/ui/` serves the React SPA (primary product UI), `/app` is a minimal Gradio operator status page (threads, profiling, runners, log tail)

## Key Files

- `modules/db.py` — DB abstraction layer and engine routing
- `modules/db_postgres.py` — PostgreSQL schema, connection pool, DDL init
- `modules/api.py` — FastAPI REST endpoints (scoring, tagging, clustering jobs)
- `modules/engine.py` — Scoring pipeline orchestrator
- `modules/config.py` — Configuration management
- `modules/mcp_server.py` — MCP server for AI agent integration
- `config.json` — Runtime configuration (model paths, thresholds, DB path)
- `webui.py` — Application entry point

## Commands

```bash
# Start WebUI (FastAPI + Gradio, port 7860)
python webui.py
# or on Windows:
run_webui.bat

# Start MCP server (standalone)
python -m modules.mcp_server

# Start MCP server alongside WebUI
ENABLE_MCP_SERVER=1 python webui.py   # Linux/WSL
$env:ENABLE_MCP_SERVER="1"; python webui.py  # PowerShell

# Run tests
python -m pytest
python -m pytest -m "not gpu and not db and not ml"  # fast subset, no hardware deps
python -m pytest tests/test_phases.py -v  # specific file
```

## Testing

Tests live in `tests/`. Markers defined in `pytest.ini`:

### E2E naming (tell an agent which suite you mean)

| You say | Canonical name | Where | Notes |
|---------|----------------|-------|--------|
| Integration E2E, API E2E, “e2e unit” (ambiguous—prefer below) | **Postgres API E2E** | `tests/integration/*_e2e.py` | `pytest -m postgres` or `RUN_POSTGRES_TESTS=1`; FastAPI `TestClient`, fake runners; **not** Docker-only |
| Docker E2E, inference E2E, GPU E2E in container | **Docker inference E2E** | `tests/e2e_docker/` | `IMAGE_SCORING_DOCKER_INFERENCE_E2E=1`; run via Compose profile `e2e-inference` (see `docker-compose.yml`) |
| Unit tests (not E2E) | **Fast / unit subset** | most of `tests/` outside the above | e.g. `pytest -m "not gpu and not db and not ml"` |

Avoid saying **“e2e unit tests”** alone; use **Postgres API E2E** or **unit tests** explicitly. Full commands: **`AGENTS.md`** (section **Pytest E2E vocabulary**).

| Marker | Meaning |
|--------|---------|
| `gpu` | Requires CUDA GPU |
| `db` | Requires database connection (PostgreSQL) |
| `ml` | Requires ML dependencies (TF, PyTorch, pyiqa) |
| `wsl` | Must run in WSL/Linux |
| `network` | Requires outbound network |
| `sample_data` | Requires local sample image files |
| `postgres` | Postgres-backed API/integration E2E (`tests/integration/*_e2e.py`) |
| `inference_e2e` | Docker-backed live inference E2E (`tests/e2e_docker/`) |

Skip hardware-dependent tests with: `python -m pytest -m "not gpu and not db and not ml"`

## Electron Frontend Integration Points

- **Shared DB:** Electron reads PostgreSQL via `electron/db/provider.ts` (or the backend HTTP API; see `electron/apiService.ts`). Firebird is decommissioned.
- **REST API:** Electron calls `http://localhost:7860` for scoring/tagging/clustering jobs (WebUI port). Backend URL is discovered via `webui.lock` with fallback to port 7860.
- **IPC contract:** Electron expects specific column names and result shapes from DB queries — do not rename columns without coordinated changes to `electron/db.ts` and the sibling repo. Cross-repo procedure: [`.agent/workflows/cross_repo_contract_change.md`](.agent/workflows/cross_repo_contract_change.md).
- **API types:** Gallery generates TypeScript types from `docs/reference/api/openapi.yaml` via the gallery's `npm run generate:api-types`. Keep OpenAPI in sync when changing endpoints.

## Schema Migration Pattern

**PostgreSQL (primary):** Use Alembic migrations in `migrations/versions/`. Run `alembic upgrade head` to apply.

**Firebird (legacy):** All migrations in `_init_db_impl()` follow this pattern:
```python
try:
    cur.execute("ALTER TABLE ...")
    conn.commit()
except Exception:
    conn.rollback()  # idempotent — already applied
```

Helpers: `_table_exists()`, `_column_exists()`, `_index_exists()`, `_constraint_exists()`

## Development Guidelines

- **No hardcoded paths** — use `modules/config.py` and `BASE_DIR`
- **Use `logging` module** — no `print()` in library code
- **Keep public API stable** — REST endpoints, config keys, DB column names
- **Minimal diffs** — prefer targeted edits over rewrites
- **DB column renames** require updating `electron/db.ts` too
- **New score columns** require updating `_init_db_impl()` in `modules/db.py`
- **Secrets** (API keys) go in `secrets.json` (git-ignored), never in `config.json`
- **Never modify `.git/config`** — do not set `extensions.worktreeConfig`, change `core.repositoryformatversion`, or add any git extensions. Third-party tools (Gemini Code Assist / Antigravity) use embedded git libraries that choke on non-standard extensions, breaking workspace resolution. If a worktree is needed, use a temporary one and clean it up immediately — do not leave worktree config persisted in the repo.

### DB.py Refactoring (Future: Post-MVP)

**Status:** Planning phase (not yet implemented)

The `modules/db.py` file has grown to 414 KB / 10,565 lines (a "god object" with 60+ public methods). This creates high defect risk, merge conflicts, and testing difficulty. A phased decomposition is planned into domain-specific modules:

**Proposed structure:**
```
modules/db/
├── connection.py  (engine routing, connection management)
├── images.py      (image CRUD, queries, filtering)
├── folders.py     (folder operations, hierarchy)
├── stacks.py      (stack membership, clustering)
├── jobs.py        (job lifecycle, phases, recovery)
├── keywords.py    (keyword sync, filtering, discovery)
├── embeddings.py  (embedding storage, similarity search)
├── telemetry.py   (pipeline events, metrics, logging)
└── backup.py      (backup/restore, disaster recovery)
```

Backward compatibility is maintained via a facade layer in `modules/db.py`. See `docs/planning/db-refactor-decomposition.md` for the full 11-week plan.

**For now:** Use `modules/db.py` as before. New code should follow these patterns for future-proofing:
- Import from domain-specific modules when available (post-refactor)
- Avoid mixing concerns (e.g., don't add image queries to job functions)
- Keep functions focused and testable in isolation

### Keyword Storage (Phase 4 / Transition Period)

**Current state:** Keywords are stored in two places:
- **Primary (Postgres):** `IMAGE_KEYWORDS` junction table + `KEYWORDS_DIM` catalog
- **Deprecated:** `IMAGES.KEYWORDS` text column — still dual-written on Postgres by default for backward compatibility; set `database.write_legacy_keywords_column` to `false` in `config.json` to stop writing it once all readers use the normalized tables. Firebird-only deployments still use the column until migrated.

**For new code:**
1. Always **read** keywords via `IMAGE_KEYWORDS` / `KEYWORDS_DIM` (normalized schema)
   - Use `_add_keyword_filter()` helper for filtering by keyword
   - Use `keyword_discovery.py` helpers for cloud/autocomplete features

2. Always **write** keywords via `db.update_image_metadata()` (updates normalized tables; optional legacy column per config above)
   - Or call `db._sync_image_keywords()` directly to sync to normalized schema
   - Do NOT write directly to `IMAGES.KEYWORDS` from new code

3. Understand the **deprecation timeline:**
   - **v6.3 (Apr 2026):** Normalized schema becomes primary source
   - **v6.4 (May 2026):** Soft deprecation (logging warnings on legacy reads)
   - **v7.0 (Jul 2026):** Hard deprecation (legacy column removed)

**Example: Update image keywords programmatically**
```python
# ✅ CORRECT: Use db.update_image_metadata()
db.update_image_metadata(file_path, "nature,wildlife,sunset", title, desc, rating, label)

# ❌ WRONG: Direct legacy column write
conn.execute("UPDATE images SET keywords = ? WHERE file_path = ?", (keywords, file_path))

# ✅ ALSO CORRECT: Manual dual-write for special cases
db._sync_image_keywords(image_id, "nature,wildlife")  # → writes to IMAGE_KEYWORDS
```

**Related docs:**
- `docs/planning/database/PHASE4_KEYWORDS_HUB.md` — Index of Phase 4 keyword docs (current vs archived)
- `docs/planning/database/PHASE4_KEYWORDS_DEPRECATION.md` — Full deprecation roadmap
- `docs/archive/plans/database/PHASE4_CODE_AUDIT.md` — Archived code audit (pre–Phase 4b snapshot)

### Embedding storage (Postgres)

- **Primary:** `embedding_spaces` + `image_embeddings` (1280-d default `mobilenet_v2_imagenet_gap`); 512-d / 768-d use `image_embeddings_512` / `image_embeddings_768`.
- **Deprecated:** `images.image_embedding` — dual-write optional via `database.write_legacy_image_embedding_column` until Alembic **0024** drops the column. See `docs/planning/database/IMAGE_EMBEDDING_COLUMN_DEPRECATION.md` and `docs/technical/EMBEDDINGS.md`.
- **Writes:** Use `db.update_image_embedding()` / `update_image_embeddings_batch()` (fact table always); do not `UPDATE images SET image_embedding` from new code.

## Configuration

`config.json` at repo root. Access via:
```python
from modules.config import get_config_value, get_config_section
val = get_config_value("scoring.force_rescore_default", default=False)
```

## Documentation

Start with **[`docs/CANONICAL_SOURCES.md`](docs/CANONICAL_SOURCES.md)** (contract and schema authority), then **[`docs/WIKI_SCHEMA.md`](docs/WIKI_SCHEMA.md)** when adding or moving wiki pages.

**Agent infra:** **[`.agent/AGENT_INFRA_INVENTORY.md`](.agent/AGENT_INFRA_INVENTORY.md)**, **[`.agent/COMMANDS.md`](.agent/COMMANDS.md)**, **[`.agent/SAFETY.md`](.agent/SAFETY.md)**, **[`.agent/subagents/README.md`](.agent/subagents/README.md)**, **[`.agent/workflows/`](.agent/workflows/)**. **External CLI reviews:** MCP `imgscore-subagent-orchestrator` + `/check-subagents`, `/run-*-review` — [docs/technical/EXTERNAL_CLI_REVIEWS.md](docs/technical/EXTERNAL_CLI_REVIEWS.md).

- `docs/README.md` — Documentation hub and quick links
- `docs/technical/DB_SCHEMA.md` — Database schema reference
- `docs/planning/database/DB_SCHEMA_REFACTOR_PLAN.md` — Schema refactor spec
- `docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md` — Migration plan and status
- `docs/architecture/system-overview.md` — Architecture overview
- `docs/technical/API_CONTRACT.md` — REST API contract
- `docs/technical/AGENT_COORDINATION.md` — Cross-repo integration (canonical)
- `.agent/PROJECT_GUIDE.md` — Agent workflow guide
- `.agent/mcp_tools_reference.md` — MCP tools quick reference
- `AGENTS.md` — MCP server configuration for Cursor/AI agents


