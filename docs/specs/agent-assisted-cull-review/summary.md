# Agent-assisted cull review — summary

*Last updated: 2026-06-12*

## Goal

Conservative AI-assisted redundancy review for **small stack/substack groups** (<10 images). An external vision-capable CLI returns JSON-only verdicts for **rejected** images; the backend validates locally, applies hard safety gates, and persists **metadata-only** removal candidates. **No physical deletion in MVP.**

## Hard rules (non-negotiable)

| Rule | Implementation |
|------|----------------|
| No file delete/trash/RAW/EXIF changes | `apply.py` only updates `candidate_status`; no `os.remove` paths |
| Do not overload `cull_decision` | `agent_cull_recommendations.candidate_status` |
| Local gates override agent | `modules/agent_cull/safety.py` |
| Fail-closed on bad JSON | `schema.py` → group `failed` |
| Dry-run = `proposed` only | Apply/approve blocked when `dry_run=true` on group |
| Concurrency guard | `fingerprint.py` → `stale_group_state` (409) on apply/approve |

## Architecture

```text
Discovery (discovery.py + discovery_db.py)
  → Payload (payload.py)
  → CLI adapter (cli_adapter.py) + prompt template
  → Schema validation (schema.py)
  → Safety gates (safety.py)
  → Persist (apply.py + repository.py)
  → Operator actions (operator.py, rollback.py)
  → REST (modules/api.py /api/culling/agent-review/*)
  → Gallery IPC (image-scoring-gallery electron/apiService.ts)
```

## Database (Postgres)

- Migration: `migrations/versions/0031_agent_cull_recommendations.py`
- Tables: `agent_cull_review_groups`, `agent_cull_recommendations`
- **Operator must run:** `alembic upgrade head` before enabling in config

## Configuration

`config.json` → `culling.agent_review` (see `config.example.json`). Default **`enabled: false`**, **`dry_run_default: true`**.

## REST surface

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/culling/agent-review/groups` | List groups |
| GET | `/api/culling/agent-review/groups/{id}` | Detail + recommendations |
| GET | `/api/culling/agent-review/schema` | Response JSON schema |
| POST | `/api/culling/agent-review/discover` | Eligible units |
| POST | `/api/culling/agent-review/run` | Requires `enabled` |
| POST | `/api/culling/agent-review/groups/{id}/apply-candidates` | Partial via `recommendation_ids`; blocked if dry-run/stale/disabled |
| POST | `/api/culling/agent-review/groups/{id}/approve` | Same guards |
| POST | `/api/culling/agent-review/groups/{id}/reject` | Respects `enabled` shutoff |
| POST | `/api/culling/agent-review/recommendations/{id}/rollback` | Respects `enabled` shutoff |

OpenAPI: `docs/reference/api/openapi.yaml`

## Gallery (sibling repo)

- `AgentCullReviewPanel` — list groups, per-rec approve/reject/rollback, clear pick flag
- Dry-run groups: **Mark safe candidates** hidden
- **Not yet:** run review from UI, stale-state UX, regenerated API types

## Test coverage

- **51** unit tests: `tests/test_agent_cull_*.py` (discovery, schema, safety, apply, fingerprint, actions, CLI adapter, operator, rollback)
- Gallery: `AgentCullReviewPanel.test.tsx` (3 tests)
- **Gap:** Postgres integration tests ([#255](https://github.com/synthet/image-scoring-backend/issues/255))

## Safety gates implemented

- No picked / picked < rejected
- Group + image confidence floors
- Missing or non-picked `better_alternatives`
- **Unusable picked alternatives** (`alternative_unusable`)
- Higher rejected scores, unique species/keywords, embedding outliers
- Unreadable rejected preview
- Vision-off + metadata-only remove disabled
- CLI transient retry (`max_retries`)

## Backlog (GitHub)

### Backend ([#253](https://github.com/synthet/image-scoring-backend/issues/253))

| Issue | Priority | Topic |
|-------|----------|-------|
| [#254](https://github.com/synthet/image-scoring-backend/issues/254) | p1 | PR-ready, migration 0031, merge |
| [#255](https://github.com/synthet/image-scoring-backend/issues/255) | p2 | Postgres integration tests |
| [#256](https://github.com/synthet/image-scoring-backend/issues/256) | p2 | Thumbnail downscale (`max_thumbnail_edge_px`) |
| [#257](https://github.com/synthet/image-scoring-backend/issues/257) | p2 | Export/filter semantics |
| [#258](https://github.com/synthet/image-scoring-backend/issues/258) | p2 | Real Gemini CLI E2E |

### Gallery ([#134](https://github.com/synthet/image-scoring-gallery/issues/134))

| Issue | Priority | Topic |
|-------|----------|-------|
| [#135](https://github.com/synthet/image-scoring-gallery/issues/135) | p1 | Run dry-run review from UI |
| [#136](https://github.com/synthet/image-scoring-gallery/issues/136) | p2 | `stale_group_state` / 409 UX |
| [#137](https://github.com/synthet/image-scoring-gallery/issues/137) | p2 | OpenAPI sync + `generate:api-types` |

## Out of scope (MVP)

- Physical deletion / move-to-trash
- Hiding candidates from gallery grid by default
- Subagent-orchestrator for cull JSON (dedicated CLI adapter instead)
