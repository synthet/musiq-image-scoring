# OpenAPI Contract Across Projects

One REST OpenAPI contract describes the Vexlum Scoring FastAPI server (default port 7860). **image-scoring-backend** owns and generates it; **image-scoring-gallery** keeps a synced snapshot and partial TypeScript codegen. **image-scoring-ui** has no HTTP API contract (design tokens only).

## Ownership

| Project | Own OpenAPI spec? | Role |
|---------|-------------------|------|
| **image-scoring-backend** | Yes — canonical | Schema authority; FastAPI generates live spec |
| **image-scoring-gallery** | No — synced copy of backend | Consumer snapshot + generated TS types |
| **image-scoring-ui** | No | Design system package (`@synthet/image-scoring-design`) only |

The backend React SPA under `frontend/` uses hand-maintained types in `frontend/src/types/api.ts`; it calls the same REST surface documented by OpenAPI.

## Backend artifacts (canonical)

| Artifact | Path | Notes |
|----------|------|-------|
| Implementation | [modules/api.py](../../modules/api.py) | Routes and Pydantic models |
| Human summary | [API_CONTRACT.md](API_CONTRACT.md) | Endpoints, WebSocket events, models |
| OpenAPI YAML | [reference/api/openapi.yaml](../reference/api/openapi.yaml) | Committed machine schema (`openapi: 3.0.3`) |
| OpenAPI JSON (root) | [openapi.json](../../openapi.json) | Generated export; gallery sync input |
| OpenAPI JSON (docs copy) | [reference/api/openapi.json](../reference/api/openapi.json) | Mirror of root `openapi.json` |
| Export script | [scripts/export_openapi.py](../../scripts/export_openapi.py) | Builds minimal FastAPI app, writes JSON without full WebUI |
| Schema notes | [reference/api/API_SCHEMA_IMPLEMENTATION.md](../reference/api/API_SCHEMA_IMPLEMENTATION.md) | Runtime `/openapi.json`, `/docs`, `/api/schema` |

Regenerate JSON after API changes:

```bash
python scripts/export_openapi.py   # → openapi.json
```

When WebUI is running, live spec is also at `GET /openapi.json`.

**Source of truth for regeneration:** code in `modules/api.py` + `scripts/export_openapi.py`. Keep [openapi.yaml](../reference/api/openapi.yaml) and [API_CONTRACT.md](API_CONTRACT.md) aligned when REST behavior changes. Audit helpers under `scripts/audit/` compare routes to the YAML artifact.

## Gallery artifacts (consumer)

Gallery does **not** expose its own REST API with OpenAPI. It calls the backend via [electron/apiService.ts](https://github.com/synthet/image-scoring-gallery/blob/main/electron/apiService.ts) and/or DB providers.

| Artifact | Path (gallery repo) | Purpose |
|----------|---------------------|---------|
| Contract snapshot | `api-contract/openapi.json` | Committed copy of backend `openapi.json` |
| Generated types | `electron/api.generated.ts` | From `openapi-typescript` |
| Hand-written types | `electron/apiTypes.ts` | Legacy/manual types; migrate incrementally to generated |

Sync commands (sibling backend at `../image-scoring-backend`):

```bash
npm run contract:diff          # copy sibling openapi.json (no server)
npm run contract:update        # fetch live http://localhost:7860/openapi.json
npm run contract:check         # compare snapshot vs live/sibling
npm run generate:api-types     # regenerate electron/api.generated.ts
npm run contract:validate      # coverage check vs apiTypes.ts / apiService.ts
```

See gallery [docs/technical/OPENAPI_CONTRACT.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/OPENAPI_CONTRACT.md) for the consumer-side checklist.

## Cross-repo workflow

After backend REST changes:

1. Implement in `modules/api.py` (and related modules).
2. Run `python scripts/export_openapi.py`.
3. Update [openapi.yaml](../reference/api/openapi.yaml) and [API_CONTRACT.md](API_CONTRACT.md).
4. In **image-scoring-gallery**: `npm run contract:diff` (or `contract:update`) then `npm run generate:api-types`.
5. Update `electron/apiService.ts` / `electron/apiTypes.ts` when endpoints or payloads change.
6. Append both repos' `docs/log.md`.

Backend PRs that touch `openapi.json`, `modules/api.py`, or schema files trigger [.github/workflows/cross-repo-sync-notice.yml](../../.github/workflows/cross-repo-sync-notice.yml), which reminds reviewers to re-sync gallery `api-contract/openapi.json`.

Full protocol: [AGENT_COORDINATION.md](AGENT_COORDINATION.md), workflow [.agent/workflows/cross_repo_contract_change.md](../../.agent/workflows/cross_repo_contract_change.md).
