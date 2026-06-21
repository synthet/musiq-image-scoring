# Agent Cull Review — API output vocabulary

**Audience:** clients that consume the agent cull review REST endpoints — primarily
the gallery's hand-maintained `src/types/agentCullReview.ts`.

**Source of truth:** [`modules/agent_cull/vocab.py`](../../modules/agent_cull/vocab.py).
The same values are served at runtime by
`GET /api/culling/agent-review/schema` under `output_vocabulary`, and guarded by
`tests/test_agent_cull_vocab.py`. Update `vocab.py` when an emitting path changes;
this doc and the endpoint follow.

> This is **not** the agent-input schema. What the LLM emits is described by
> [`AGENT_CULL_REVIEW_SCHEMA.json`](AGENT_CULL_REVIEW_SCHEMA.json) (`remove` /
> `keep` / `uncertain` decisions, advisory `issue` enum, etc.). The values below
> are what the backend **persists and serializes back to clients** after safety
> gating and operator actions — a different, derived vocabulary.

## Where these appear

The shapes are produced by
[`modules/agent_cull/api_helpers.py`](../../modules/agent_cull/api_helpers.py)
(`serialize_recommendation`, `serialize_group`) and returned by
`GET /api/culling/agent-review/groups` and `…/groups/{id}`.

## Recommendation fields

### `candidate_status`

| Value | Meaning | Emitted by |
|---|---|---|
| `none` | Not a remove candidate (keep / uncertain). | `apply.py` |
| `proposed` | Remove candidate from a **dry-run** group. | `apply.py` |
| `agent_remove_candidate` | Remove candidate from a **live** group, or a `proposed` candidate promoted via apply. | `apply.py` |
| `pick_quality_advisory` | Informational advisory on a **picked** image — never a remove candidate. | `apply.py` |
| `operator_approved` | Operator approved the removal. | `operator.py` |
| `operator_rejected` | Operator dismissed/rejected the removal. | `operator.py` |

> **`rolled_back` is not a recommendation status.** Rollback restores the
> recommendation's `prior_candidate_status`; only the *group* status becomes
> `rolled_back` (see group statuses). Do not add `rolled_back` to the
> recommendation candidate-status union.

### `agent_decision`

`remove` · `keep` · `uncertain` · `advisory`

The raw per-image decision from the agent (defaults to `uncertain` when absent),
plus `advisory`, which the backend applies to picked-image quality advisories.

### `final_decision`

`remove` · `keep` · `uncertain`

The post-safety decision. Safety **never upgrades** to `remove`; advisories always
persist `keep`. **`advisory` never appears here** — discriminate advisory cards on
`candidate_status === "pick_quality_advisory"` (or `agent_decision === "advisory"`),
not on `final_decision`.

### `better_alternatives`

Array of picked image IDs. For remove recommendations these are the agent's
preferred keepers; for advisories these are the `suggested_alternatives` echoed
through the same field.

## Group fields

### `status`

`discovered` · `validated` · `proposed` · `failed` · `applied` · `rolled_back`

`discovered` is the column default (`db_postgres.py`) a group carries before its
first status update. The gallery's `AgentCullGroupStatus` additionally lists
`payload_built`, `agent_pending`, and `agent_done` — these are **not emitted by
the backend** (no code path writes them); they are inert union members and can be
dropped from the gallery type when convenient.

### `group_decision`

`apply_removals` · `do_not_apply` · `null` (when no removable items survive gating)

## Gallery type-sync checklist (per `agent_cull_ux` plan, Phase 1d)

Reconciled against `src/types/agentCullReview.ts` as of this review:

- [ ] **Add** `pick_quality_advisory` to `AgentCullCandidateStatus` (missing).
- [ ] **Add** `advisory` to the **`agent_decision`** union **only** — not
      `final_decision` (missing).
- [ ] **Remove** `rolled_back` from `AgentCullCandidateStatus` — the backend
      never emits it as a recommendation status (rollback restores the prior
      value); it is only a *group* status. Inert today, but misleading.
- [ ] **Remove** `payload_built` / `agent_pending` / `agent_done` from
      `AgentCullGroupStatus` — no backend path emits them. `discovered` stays.
- [ ] Advisory cards: info styling, no Approve/Mark-safe; optional "View
      alternatives" from `better_alternatives`.
- ✓ `operator_approved` / `operator_rejected` already present — no change.
- ✓ `final_decision` union already correct (`remove`/`keep`/`uncertain`).
