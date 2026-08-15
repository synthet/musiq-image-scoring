# Vexlum Scoring — Python backend

AI-powered image scoring, tagging, and clustering using MUSIQ, LIQE, TOPIQ, Q-Align, BLIP, and CLIP. Serves a FastAPI REST API, React SPA at `/ui/`, and a minimal Gradio operator page at `/app`.

## Related Projects

| Project | Repository | Role |
|---------|------------|------|
| **image-scoring-backend** (this) | [github.com/synthet/image-scoring-backend](https://github.com/synthet/image-scoring-backend) | AI scoring engine, FastAPI server, PostgreSQL schema authority |
| **image-scoring-gallery** | [github.com/synthet/image-scoring-gallery](https://github.com/synthet/image-scoring-gallery) | Electron desktop UI, IPC query layer, React/Vite |
| **image-scoring-ui** | [github.com/synthet/image-scoring-ui](https://github.com/synthet/image-scoring-ui) | Shared design tokens (`@synthet/image-scoring-design`) |
| **image-scoring-model** | [github.com/synthet/image-scoring-model](https://github.com/synthet/image-scoring-model) | `eye-quality` package: YOLO bird/eye localization, training, model contracts — **canonical source** for the bird detector defaults used by `modules/bird_detection.py` |

**Project layout:** Keep **image-scoring-backend**, **image-scoring-gallery**, and **image-scoring-ui** as sibling directories. The backend writes `webui.lock` with its port when running (default `7860`). Gallery discovers the API via that lock file; override with `config.api.url` or `config.api.port` in gallery `config.json`.

This project is the **schema authority** — DDL via `modules/db_postgres.py` and Alembic migrations in `migrations/versions/`.

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

### Pipeline phases

| Phase | Code | Description |
|-------|------|-------------|
| Indexing | `indexing` | Discover and register image files |
| Metadata | `metadata` | Extract EXIF, XMP, file metadata |
| Scoring | `scoring` | Run ML models (MUSIQ, LIQE, TOPIQ, Q-Align) |
| Culling | `culling` | Cluster similar images |
| Keywords | `keywords` | Generate tags via BLIP/CLIP captioning |

Phase status: `not_started | running | done | skipped | failed`. User-facing labels vs `phase_code`: [`docs/technical/PIPELINE_TERMINOLOGY.md`](docs/technical/PIPELINE_TERMINOLOGY.md).

### Key modules

| Module | Role |
|--------|------|
| `modules/api/` | FastAPI REST routers (`create_api_router` in `__init__.py`) |
| `modules/db/` | DB facade over `modules/db_legacy.py`; Postgres in `modules/db_postgres.py` |
| `modules/engine.py` | Batch processor; producer-consumer pipeline |
| `modules/phases.py` | Phase definitions (`PhaseCode`, `PhaseStatus`) |
| `modules/job_dispatcher.py` | Routes API job requests to phase executors |
| `modules/mcp_server.py` | MCP server; tool implementations in `modules/mcp/tools/` |
| `modules/ui/status_gradio.py` | Gradio operator status page at `/app` |
| `frontend/` | React SPA served at `/ui/` |

### Environment

- **Hybrid:** Windows host + Docker Desktop — app scripts use **`image-scoring-gpu-shell`**; WebUI uses **`image-scoring-webui`**. Ubuntu `~/.venvs/tf` is optional (see `.cursor/rules/python-wsl-webapp-env.mdc`).
- **DB (primary):** PostgreSQL + pgvector (`database.engine: "postgres"` in `config.json`). **Firebird is decommissioned.**

## Key files

- `webui.py` / `launch.py` — Application entry points
- `config.json` — Runtime configuration (model paths, DB, thresholds)
- `docs/reference/api/openapi.yaml` — REST contract artifact
- `migrations/versions/` — Alembic schema migrations
- `mcp-server/` — Node compact MCP (`is-be-mcp` search + dispatch)

## Commands

- `run_webui.bat` (Windows) or WSL: `python launch.py` — Start WebUI on port 7860
- `python scripts/doctor.py` — Config + DB + pgvector health check
- `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py` — Fast test subset

Full command list: [`.agent/COMMANDS.md`](.agent/COMMANDS.md).

## Testing

Disambiguate **Postgres API E2E** (`tests/integration/*_e2e.py`, `pytest -m postgres`) vs **Docker inference E2E** (`tests/e2e_docker/`) vs **unit/fast subset** — see **AGENTS.md** (Pytest E2E vocabulary). WSL-marked tests use `~/.venvs/image-scoring-tests`, not `~/.venvs/tf`.

## MCP

Compact **search + dispatch** on Cursor keys **`is-be-mcp`** (stdio) and optional **`is-be-live`** (SSE when WebUI is running). Contract: [`docs/technical/MCP_SEARCH_DISPATCH.md`](docs/technical/MCP_SEARCH_DISPATCH.md). Tool catalog: [`AGENTS.md`](AGENTS.md).

## Cross-repo (gallery)

- Gallery reads PostgreSQL or backend HTTP API; REST at `http://localhost:7860` via `webui.lock`.
- API/schema/phase changes flow **backend → gallery** — procedure: [`.agent/workflows/cross_repo_contract_change.md`](.agent/workflows/cross_repo_contract_change.md).
- Gallery types from `openapi.yaml` via `npm run generate:api-types` in **image-scoring-gallery**.

## Development guidelines

- **Do not invent** endpoints, columns, `phase_code` values, or config keys — cite [`docs/CANONICAL_SOURCES.md`](docs/CANONICAL_SOURCES.md).
- **Minimal diffs**; use `logging`, not `print()`, in library code.
- **Secrets** in `secrets.json` (git-ignored), never in `config.json`.
- **Never modify `.git/config`** or add non-standard git extensions (see rationale in `.cursorrules`).
- **Keywords / embeddings / DB refactor:** normalized keyword schema and legacy-column status — [`docs/planning/database/PHASE4_KEYWORDS_HUB.md`](docs/planning/database/PHASE4_KEYWORDS_HUB.md); embeddings — [`docs/EMBEDDINGS.md`](docs/EMBEDDINGS.md); DB decomposition plan — [`docs/planning/db-refactor-decomposition.md`](docs/planning/db-refactor-decomposition.md).

## Documentation

Start with **[`docs/CANONICAL_SOURCES.md`](docs/CANONICAL_SOURCES.md)** and **[`docs/WIKI_SCHEMA.md`](docs/WIKI_SCHEMA.md)** when adding or moving wiki pages.

**Agent infra:** [`.agent/AGENT_INFRA_INVENTORY.md`](.agent/AGENT_INFRA_INVENTORY.md), [`.agent/COMMANDS.md`](.agent/COMMANDS.md), [`.agent/SAFETY.md`](.agent/SAFETY.md), [`.agent/workflows/`](.agent/workflows/). **External CLI reviews:** MCP `imgscore-subagent-orchestrator` + `/check-subagents`, `/run-*-review` — [docs/technical/EXTERNAL_CLI_REVIEWS.md](docs/technical/EXTERNAL_CLI_REVIEWS.md).
