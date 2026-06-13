# Agent-assisted cull review — worklog

Append-only session log. Newest entries at top (below this paragraph).

---

## [2026-06-12] backlog + spec hub

- Filed GitHub epics and child issues on Project board #1:
  - Backend epic [#253](https://github.com/synthet/image-scoring-backend/issues/253) + [#254–#258](https://github.com/synthet/image-scoring-backend/issues/254)
  - Gallery epic [#134](https://github.com/synthet/image-scoring-gallery/issues/134) + [#135–#137](https://github.com/synthet/image-scoring-gallery/issues/135)
- Added spec hub: `docs/specs/agent-assisted-cull-review/` (this file, [summary.md](summary.md), [INDEX.md](INDEX.md))

## [2026-06-12] stale-state fingerprint

- Implemented `modules/agent_cull/fingerprint.py` — SHA-256 fingerprint of `pick_status` + `cull_decision` per group member from stored `request_json` vs live `images` rows
- `apply_candidates_action` and `approve_action` return `stale_group_state`; API maps to **409**
- Tests: `tests/test_agent_cull_fingerprint.py` (+ updates to `test_agent_cull_actions.py`)
- **51** backend unit tests green

## [2026-06-12] review hardening (P1–P3)

Addressed static review findings:

| Finding | Fix |
|---------|-----|
| Dry-run promoted via apply | Block in `apply.py`; hide gallery button when `dry_run` |
| Unusable alternatives | `alternative_unusable` gate in `safety.py` |
| `recommendation_ids` ignored on apply | Wired through API → actions → apply |
| Write endpoints when disabled | `_require_enabled()` on apply/approve/reject/rollback |
| `max_retries` unused | Bounded transient retry in `cli_adapter.py` |

## [2026-06-12] gallery actions + REST write paths

- POST apply-candidates, approve, reject, rollback under `/api/culling/agent-review/*`
- Gallery IPC + `AgentCullReviewPanel` interactive actions (metadata-only copy)
- Vitest: `AgentCullReviewPanel.test.tsx`

## [2026-06-12] backend MVP modules

- Planned spec: `docs/features/planned/agent-assisted-cull-review.md`
- Alembic `0031`, `modules/agent_cull/*`, `scripts/agent_cull_review.py`
- Initial unit tests `tests/test_agent_cull_*.py`
- OpenAPI read + write routes in `docs/reference/api/openapi.yaml`

## [2026-06-12] canonical verification

Verified Alembic head, `pick_status` / `cull_decision`, stack columns, auditlog, phase `culling` before schema/API design. Documented in planned feature page.
