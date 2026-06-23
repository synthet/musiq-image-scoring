# Agent-assisted cull review — summary

*Last updated: 2026-06-21*

## Goal

Conservative AI-assisted redundancy review for **small stack/substack groups** (<10 images). An external vision-capable CLI returns JSON-only verdicts for **rejected** images; the backend validates locally, applies hard safety gates, and persists **metadata-only** removal candidates. **No physical deletion in MVP.**

**Editorial alignment:** The production prompt template `cull_redundancy_v3_vision_strict` follows the same principles as [carousel-pick curation](https://github.com/synthet/image-scoring-skills/blob/main/.cursor/skills/photo-carousel/SKILL.md) in **image-scoring-skills**: ML scores (0–1) inform the shortlist; **visual duplicate and pose-diversity rules override pure score rank**; every reject rationale cites filename, scores, and what was seen in thumbnails.

**Production defaults (post live-matrix v4, 2026-06-21):** `prompt_template_version=cull_redundancy_v3_vision_strict`, `require_vision_evidence=true`, `agent.timeout_seconds=180`, `review_picked_quality=true`. Misfocus-prone stacks (e.g. #29157) may use `--mode-profile technical_focus`.

## Picked-image quality advisories

The live matrix found that a **picked hero** (image 195193, stack #29157) had a misleading `score_technical` (~83%) yet a vision-detectable soft foreground — but rejected-only review never inspects picks. With `review_picked_quality=true`, the agent additionally audits **every picked** thumbnail and may return an optional `picked_image_advisories` array (response schema `agent-cull-response-v1`).

- Each advisory: `image_id` (a picked id), `filename`, `issue` (`misfocus`|`blur`|`exposure`|`composition`|`other`), `confidence`, `reason`, `suggested_alternatives` (picked ids), `risk_flags`.
- Persisted as **advisory-only** recommendations: `agent_decision='advisory'`, `final_decision='keep'`, `candidate_status='pick_quality_advisory'`. They **never** participate in `apply-candidates`/remove gates and never change `pick_status`.
- Validation (`schema.py`): advisory `image_id` must be picked, `suggested_alternatives ⊆ picked_image_ids`, and visual issues require the pick to be in `viewed_image_ids` when `require_vision_evidence` is on.
- **Prompt fix (2026-06-21):** default `picked_audit_snippet` is **`picked_quality_audit_snippet_strict_v2.txt`** (mandatory per-pick checklist + worked example). Research: [reports/PICKED_ADVISORY_GAP_195193_2026-06-21.md](../reports/PICKED_ADVISORY_GAP_195193_2026-06-21.md).

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

**Gemini CLI (operator):** When the WebUI runs in Docker, use container path `/app/scripts/wsl/gemini_agent.sh`, bake Gemini into the image, and mount host `~/.gemini` via `GEMINI_CONFIG_SOURCE`. Full matrix (Docker / WSL / Windows): [guides/setup/agent-cull-review-gemini-cli.md](../guides/setup/agent-cull-review-gemini-cli.md).

## Payload thumbnails

When `agent.include_thumbnails=true`, `payload.py` resolves DB thumbnail paths via `modules.thumbnails._resolve_thumbnail_filesystem_path` (so Docker host WSL paths in Postgres map to `/app/thumbnails/...` inside the container), then adds a `thumbnail_manifest` entry per image. Each entry carries `path`, `mode`, `max_edge_px`, `width`, `height`, and `downscaled`.

**Vision:** The `cull_redundancy_v3_vision_strict` prompt instructs the agent to open every manifest path before recommending `remove`. Response fields `vision_used` and `viewed_image_ids` are validated; with the production default `agent.require_vision_evidence=true`, removals (and visual picked advisories) are blocked without them. When `review_picked_quality=true`, a shared `prompts/picked_quality_audit_snippet.txt` is appended by `build_prompt()` directing the agent to audit picked thumbnails too.

## Payload scores

When `agent.include_all_model_scores=true` (default), each image includes a `model_scores` map from `image_model_scores` (including auxiliary **`clip_quality_v0`**). Names in `agent.flatten_model_scores` are also copied into `scores` for prompt readability. Missing required scores can trigger JIT `clip_quality_v0` when `agent.jit_clip_quality=true`.

`agent.max_thumbnail_edge_px` (default **512**) bounds the longest edge sent to the agent to control vision token cost/latency:

- Source longest edge **≤** `max_edge` → passed through unchanged (`downscaled: false`).
- Source longest edge **>** `max_edge` → a downscaled JPEG (aspect preserved, quality 85) is written to a deterministic cache dir `thumbnails/agent_review/<max_edge>/<sha1>.jpg`; the manifest `path` points to it, `downscaled: true`, and `source_path` retains the original. The cache is idempotent across runs (re-uses an existing file).
- `max_edge ≤ 0`, Pillow unavailable, or any resize error → **fail-safe**: the original path is emitted and the packet is never broken.

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

- `AgentCullReviewPanel` — list groups, per-rec approve/reject/rollback, clear pick flag, **Run dry-run review**
- Dry-run groups: **Mark safe candidates** hidden
- Operator setup when UI shows “Gemini CLI not found”: [gallery guide](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/04-agent-cull-review.md) → backend [Gemini CLI setup](../guides/setup/agent-cull-review-gemini-cli.md)

## Test coverage

- **58** unit tests: `tests/test_agent_cull_*.py` (discovery, schema, safety, apply, fingerprint, actions, CLI adapter, operator, rollback, payload/thumbnail downscale)
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
| [#256](https://github.com/synthet/image-scoring-backend/issues/256) | p2 | Thumbnail downscale (`max_thumbnail_edge_px`) — **done** |
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
