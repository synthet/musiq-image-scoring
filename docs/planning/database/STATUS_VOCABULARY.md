# Status vocabulary inventory

Catalog of every status-style column in the PostgreSQL schema, the allowed values used by application code today, and the DB-layer guard rails that exist (or are missing). This is the **D1** deliverable of the [PostgreSQL optimization roadmap](POSTGRES_SCHEMA_OPTIMIZATIONS.md) — `D2` (CHECK constraints / ENUMs) consumes this list.

**Scope:** `jobs`, `job_phases`, `job_steps`, `image_phase_status`, `culling_sessions`, plus the pure-application `PhaseStatus` / `FolderPhaseStatus` enums in [`modules/phases.py`](../../../modules/phases.py).

**Out of scope:** boolean flags (`enabled`, `optional`, `cancel_requested`), label/decision columns (`culling_picks.decision`, `images.label`), and free-form `runner_state`.

---

## 1. `image_phase_status.status` — canonical, enum-backed

| Property | Value |
|----------|-------|
| Column | `image_phase_status.status VARCHAR(20) DEFAULT 'not_started' NOT NULL` |
| DDL    | [`db_postgres.py`](../../../modules/db_postgres.py) `_init_db_transaction()` |
| Source of truth | [`modules/phases.py`](../../../modules/phases.py) `PhaseStatus` |

**Allowed values (string `Enum`):**

| Value | Meaning |
|-------|---------|
| `not_started` | Default after image discovery; phase has never been attempted. |
| `queued` | Picked up by the dispatcher, awaiting a runner slot. |
| `running` | A worker has the row checked out. |
| `paused` | Runner-level pause (graceful stop). |
| `cancel_requested` | Operator/parent asked the runner to abandon the row. |
| `restarting` | Explicit re-run requested from a terminal state. |
| `done` | Terminal — phase produced output and committed it. |
| `skipped` | Terminal — phase intentionally not run for this image. |
| `failed` | Terminal — runner crashed or returned an error. |

**Allowed transitions** are codified in `phases.ALLOWED_TRANSITIONS`:

```
not_started      -> queued | running
queued           -> running | cancel_requested | skipped
running          -> paused | done | failed | skipped | cancel_requested | restarting
paused           -> running | cancel_requested | restarting
cancel_requested -> skipped | failed | not_started
restarting       -> queued | running | failed
done             -> restarting | running                  # rerun
failed           -> restarting | running                  # retry
skipped          -> restarting | running                  # explicit rerun
```

**DB guard rails:** `CHECK ck_image_phase_status_status` covering the nine `PhaseStatus` values (added in Alembic revision `0014`, 2026-04-25). Empirical inventory before the constraint showed only `done`, `skipped`, `not_started`, `running` in production data — all members of the enum, no rewrite needed.

**Rationale for VARCHAR + CHECK rather than Postgres `ENUM`:** adding a new state remains a single migration that updates the CHECK list, without an `ALTER TYPE … ADD VALUE` dance and the transactional constraints that come with it.

---

## 2. `jobs.status` — VARCHAR, application-managed

| Property | Value |
|----------|-------|
| Column | `jobs.status VARCHAR(50)` (no default, nullable) |
| DDL    | [`db_postgres.py`](../../../modules/db_postgres.py) `CREATE TABLE jobs` |
| Initial value | `pending` (set by [`db.create_job()`](../../../modules/db_legacy.py) default arg) |

**Values written by application code** (grep of `update_job_status(...)` literals):

| Value | Set by | Notes |
|-------|--------|-------|
| `pending` | `create_job()` default | Pre-enqueue. |
| `queued` | `enqueue_job_with_phases()` first-phase state default | Awaiting dispatch. |
| `running` | runner threads | Worker holds the job. |
| `paused` | runner pause path | Generic pause. |
| `user_pause` | UI-initiated pause | Distinguishes operator action from auto-pause. |
| `completed` | `pipeline.safe_runner_thread` happy path | Terminal. |
| `failed` | runner crash path | Terminal. |
| `error` | error-from-API surface | Terminal — overlap with `failed`; see open question below. |
| `cancelled` | cancel propagation | Terminal. |
| `interrupted` | graceful stop / shutdown | Terminal — see `safe_runner_thread` contract in v7.4.8 changelog. |

**DB guard rails:** none.

**Empirical inventory (2026-04-25, production):**

| Value | Rows | In code path? |
|-------|------|---------------|
| `completed` | 1236 | ✅ |
| `failed` | 184 | ✅ |
| `interrupted` | 97 | ✅ |
| `cancelled` | 48 | ✅ (UK spelling) |
| `canceled` | 21 | ⚠️ (US spelling — orphan; no current writer) |
| `queued` | 9 | ✅ |
| `running` | 1 | ✅ |

`error`, `pending`, `paused`, and `user_pause` do **not** appear in current data despite being writable from code paths.

**Open questions for D2:**
1. `error` vs `failed` — `error` not currently written to `jobs.status` in any code path searched (only to `runner_state` and to dataclass return values such as `SelectionSummary`). Treat as **resolved**: keep `failed` as the canonical terminal-error value; do not include `error` in the allowed set unless a writer is added.
2. `canceled` vs `cancelled` — both spellings exist in production data. Code uses `cancelled` (UK). The 21 `canceled` rows likely originate from a removed code path; data-normalization step required before constraint.

**Recommendation for D2:** before adding a CHECK constraint, run a normalization pass:

```sql
UPDATE jobs SET status = 'cancelled' WHERE status = 'canceled';
```

Then add `CHECK (status IN ('pending', 'queued', 'running', 'paused', 'user_pause', 'completed', 'failed', 'cancelled', 'interrupted'))`. Tightening to `NOT NULL DEFAULT 'pending'` is a separate decision (existing nullable column allows historical `NULL`s if any).

---

## 3. `job_phases.state` — per-phase plan tracker

| Property | Value |
|----------|-------|
| Column | `job_phases.state VARCHAR(20) NOT NULL` (no default) |
| DDL    | [`db_postgres.py`](../../../modules/db_postgres.py) `CREATE TABLE job_phases` |

**Empirical inventory (2026-04-25, production):**

| Value | Rows | In code path? |
|-------|------|---------------|
| `completed` | 2023 | ✅ |
| `pending` | 275 | ⚠️ (not in code grep — likely historical/migrated default) |
| `failed` | 123 | ✅ |
| `queued` | 79 | ✅ (default for `enqueue_job_with_phases`) |
| `interrupted` | 53 | ⚠️ (not in code grep — likely written from runner crash paths) |
| `running` | 23 | ✅ |
| `canceled` | 17 | ⚠️ (US spelling) |
| `skipped` | 5 | ⚠️ (not surfaced in code grep) |
| `paused` | 4 | ⚠️ (not surfaced in code grep) |

**DB guard rails:** none.

**Open questions for D2:**
1. The empirical vocab is **larger** than the code-grep vocab. Before adding a CHECK we need to either (a) add the missing writers/transitions to documentation, or (b) confirm those rows came from now-removed paths.
2. `canceled` vs `cancelled` — same UK/US split as `jobs.status`. Normalize first.

**Recommendation for D2:** defer until a code-vs-data audit reconciles the writer set. Tentative full vocabulary: `pending`, `queued`, `running`, `paused`, `completed`, `failed`, `interrupted`, `cancelled`, `skipped`. **Naming nit:** the column is named `state`, not `status`, unlike its siblings — leave the column name alone (rename is high-churn for low value), but document this in `DB_SCHEMA.md` so consumers do not grep for the wrong key.

---

## 4. `job_steps.status` — sub-phase telemetry

| Property | Value |
|----------|-------|
| Column | `job_steps.status VARCHAR(20) DEFAULT 'pending'` |
| DDL    | [`db_postgres.py`](../../../modules/db_postgres.py) `CREATE TABLE job_steps` |

**Values observed in code:** `pending` (default; no other writers found in the current codebase). The column is read by reporting / runs-audit views but not actively transitioned by phase executors today — it is essentially dormant telemetry.

**DB guard rails:** none.

**Recommendation for D2:** before adding a CHECK constraint, decide whether this column is being kept (then formalize the vocabulary alongside whichever runner is supposed to write it) or removed (then drop the column and the CHECK question disappears). Defer until a writer is wired up.

---

## 5. `culling_sessions.status` — semi-dormant

| Property | Value |
|----------|-------|
| Column | `culling_sessions.status VARCHAR(50) DEFAULT 'active'` |
| DDL    | [`db_postgres.py`](../../../modules/db_postgres.py) `CREATE TABLE culling_sessions` |

**Values observed in code:** only the `'active'` default; no application writer transitions it today. `culling_picks` carries the per-image decision (`pick`/`reject`/etc.) — that is a separate vocabulary documented under the culling design notes.

**Recommendation for D2:** treat the same as `job_steps.status` — defer constraint work until a writer (likely "session completed" when the operator closes the cull) is added.

---

## 6. `FolderPhaseStatus` — pure-application enum

| Property | Value |
|----------|-------|
| Source | [`modules/phases.py`](../../../modules/phases.py) `FolderPhaseStatus` |
| Persisted to DB? | **No** — derived per-call from `image_phase_status` aggregates and folder-level cache columns. |

**Allowed values:** `not_started`, `partial`, `done`, `failed`. These appear in API payloads under `folder.phase_agg_*` and gallery filters. No DB constraint applies because no column stores them directly; if a future migration persists this rollup (e.g. into a `folders.summary_status` column), copy this enum into the CHECK list.

---

## Summary table for D2 planning

| Column | Has CHECK today? | D2 status | Blocked by |
|--------|------------------|-----------|------------|
| `image_phase_status.status` | **Yes** (`ck_image_phase_status_status`, rev. 0014) | **Done** | — |
| `jobs.status` | **Yes** (`ck_jobs_status`, rev. 0020) | **Done** | — |
| `job_phases.state` | No | Pending CHECK | Spelling normalized in rev. 0015; reconcile code-vs-data writer set before CHECK |
| `job_steps.status` | No | Defer | No active writer |
| `culling_sessions.status` | No | Defer | No active writer |

**Realized D2 work so far (2026-05-09):**
- Alembic revision `0014_status_check_constraints.py` adds the `image_phase_status` CHECK; production rows verified non-violating (`done`/`skipped`/`not_started`/`running` only).
- Alembic revision `0015_normalize_canceled_status.py` rewrites `jobs.status = 'canceled'` → `'cancelled'` (21 rows) and `job_phases.state = 'canceled'` → `'cancelled'` (17 rows). Idempotent; downgrade is a no-op.
- Alembic revision `0020_jobs_status_check.py` adds the `jobs.status` CHECK pinning the §2 vocabulary. Idempotent (guarded by `pg_constraint` lookup); downgrade drops the constraint.

**Remaining D2 work:** for `job_phases.state`, audit the empirical-only values (`pending`, `interrupted`, `paused`, `skipped`) against current writers before finalizing the allowed set.

---

## Related docs

- [POSTGRES_SCHEMA_OPTIMIZATIONS.md](POSTGRES_SCHEMA_OPTIMIZATIONS.md) — full Phase 5 roadmap (this file is the **D1** deliverable)
- [`modules/phases.py`](../../../modules/phases.py) — `PhaseStatus`, `FolderPhaseStatus`, `ALLOWED_TRANSITIONS`
- [`modules/db_postgres.py`](../../../modules/db_postgres.py) — DDL for every table listed above
