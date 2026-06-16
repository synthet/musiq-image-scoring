# Agent-assisted cull review (planned)



*Status: **In progress — MVP coded (unmerged); backlog filed** · See [spec hub](../../specs/agent-assisted-cull-review/INDEX.md)*



Conservative AI-assisted workflow for small already-clustered stack/substack groups. External vision-capable CLI agents return JSON-only redundancy verdicts for **rejected** images; the backend validates output with deterministic local safety gates and persists **metadata-only** removal candidates. No physical deletion, move-to-trash, RAW/EXIF changes, or renderer DB access in MVP.



**Gallery consumer:** [image-scoring-gallery](https://github.com/synthet/image-scoring-gallery) — IPC/API bridge only; see [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md).



**Backlog:** Backend epic [#253](https://github.com/synthet/image-scoring-backend/issues/253) · Gallery epic [#134](https://github.com/synthet/image-scoring-gallery/issues/134)



## Canonical verification (2026-06-12)



Verified against authoritative sources before schema/API work:



| Item | Confirmed value | Source |

|------|-----------------|--------|

| Latest Alembic head (pre-0031) | `0030` | [`migrations/versions/`](../../../migrations/versions/) |

| Feature migration | `0031_agent_cull_recommendations.py` | This feature |

| Manual cull flag | `images.pick_status` — `1` pick, `-1` reject, `0` neutral | [`modules/db_postgres.py`](../../../modules/db_postgres.py), OpenAPI |

| Auto cull policy | `images.cull_decision` — do **not** overload | [`CULLING_ANALYTICS.md`](../../technical/CULLING_ANALYTICS.md) |

| Stack membership | `images.stack_id`, `images.sub_stack_id` | Migration `0028_sub_stacks.py` |

| Pick writes | `PATCH /api/images/{image_id}` with `pick_status` | OpenAPI |

| Audit | `auditlog` + [`modules/audit.py`](../../../modules/audit.py) | Migration `0027_auditlog.py` |

| Phase code | `culling` | [`PIPELINE_TERMINOLOGY.md`](../../technical/PIPELINE_TERMINOLOGY.md) |



**Firebird:** out of scope; Postgres-only like culling analytics.



## Non-goals (MVP)



- Physical file deletion or move-to-trash

- RAW/NEF/EXIF/orientation changes

- Overloading `images.cull_decision`

- Renderer or Electron renderer direct DB/filesystem access

- Hiding images from Gallery by default



## Review unit



1. **Sub-stack leaf** — one `sub_stack_id` within a root stack (when substacks exist).

2. **Flat root stack** — all members have `sub_stack_id IS NULL`.



Skip degenerate `singleton_root` tiers ([`hierarchy.classify_stack_tier`](../../../modules/culling_analytics/hierarchy.py)).



## Eligibility (discovery)



All must hold:



- Usable image count `< max_group_size` (default 9)

- At least one rejected image (`pick_status = -1` by default)

- At least one picked image (`pick_status = 1`)

- At least `min_usable_images` (default 2) with readable source or thumbnail when vision required

- When `picked_count < rejected_count`, the agent prompt and local gates apply extra conservatism (advisory only; not a hard skip)



## Status model



**Group (`agent_cull_review_groups.status`):** `discovered`, `payload_built`, `agent_pending`, `agent_done`, `validated`, `proposed`, `applied`, `failed`, `rolled_back`



**Recommendation (`agent_cull_recommendations.candidate_status`):** `none`, `proposed`, `agent_remove_candidate`, `operator_approved`, `operator_rejected`, `rolled_back`



## Configuration



See [`config.example.json`](../../../config.example.json) → `culling.agent_review`. Full reference: [spec summary](../../specs/agent-assisted-cull-review/summary.md).



## JSON schema



[`docs/technical/AGENT_CULL_REVIEW_SCHEMA.json`](../../technical/AGENT_CULL_REVIEW_SCHEMA.json)



## Implementation



| Area | Location |

|------|----------|

| Spec + worklog | [`docs/specs/agent-assisted-cull-review/`](../../specs/agent-assisted-cull-review/INDEX.md) |

| Python package | `modules/agent_cull/` (incl. `fingerprint.py`) |

| CLI | `scripts/agent_cull_review.py` |

| Migration | `migrations/versions/0031_agent_cull_recommendations.py` |

| Tests | `tests/test_agent_cull_*.py` (51 tests) |

| Gallery panel | `image-scoring-gallery/src/components/CullingAnalytics/AgentCullReviewPanel.tsx` |



## Related



- [CULLING_ANALYTICS.md](../../technical/CULLING_ANALYTICS.md)

- [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md)


