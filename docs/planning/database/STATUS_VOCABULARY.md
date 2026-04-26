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

**DB guard rails:** none. The `VARCHAR(20)` accepts any string; the enum is enforced only in Python.

**Recommendation for D2:** add `CHECK (status IN (...))` covering exactly the nine `PhaseStatus` values. Keep VARCHAR rather than a Postgres `ENUM` type so adding a new state remains a single migration without a `ALTER TYPE` dance.

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

**Open question for D2:**
- `error` vs `failed` — these are written from different call sites and are not normalized. Pick one canonical terminal-error value and migrate the other before adding a CHECK constraint, or include both in the allowed set and accept the redundancy.

**Recommendation for D2:** once `error`/`failed` is reconciled, add `CHECK (status IN ('pending', 'queued', 'running', 'paused', 'user_pause', 'completed', 'failed', 'cancelled', 'interrupted'))`. Consider tightening to `NOT NULL DEFAULT 'pending'` in the same migration.

---

## 3. `job_phases.state` — per-phase plan tracker

| Property | Value |
|----------|-------|
| Column | `job_phases.state VARCHAR(20) NOT NULL` (no default) |
| DDL    | [`db_postgres.py`](../../../modules/db_postgres.py) `CREATE TABLE job_phases` |

**Values observed in code** (grep of `state = "..."` and `first_phase_state` defaults in `job_dispatcher` / `pipeline_orchestrator`):

| Value | Notes |
|-------|-------|
| `queued` | Default for `enqueue_job_with_phases(first_phase_state="queued")`. |
| `running` | Phase is executing. |
| `completed` | Terminal success. |
| `failed` | Terminal failure. |
| `cancelled` | Terminal cancel. |

**DB guard rails:** none.

**Recommendation for D2:** add `CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled'))`. **Naming nit:** the column is named `state`, not `status`, unlike its siblings — leave the column name alone (rename is high-churn for low value), but document this in `DB_SCHEMA.md` so consumers do not grep for the wrong key.

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

| Column | Has CHECK today? | Recommended CHECK in D2 | Blocked by |
|--------|------------------|--------------------------|------------|
| `image_phase_status.status` | No | Yes — 9 `PhaseStatus` values | None |
| `jobs.status` | No | Yes — 9–10 values | Reconcile `error` vs `failed` first |
| `job_phases.state` | No | Yes — 5 values | None |
| `job_steps.status` | No | Defer | No active writer |
| `culling_sessions.status` | No | Defer | No active writer |

**Estimated D2 migration size:** one Alembic revision adding three CHECK constraints (`image_phase_status`, `jobs`, `job_phases`). Each is a no-data-rewrite operation provided the existing rows already match the allowed set; spot-check with `SELECT DISTINCT status FROM <table>` before applying.

---

## Related docs

- [POSTGRES_SCHEMA_OPTIMIZATIONS.md](POSTGRES_SCHEMA_OPTIMIZATIONS.md) — full Phase 5 roadmap (this file is the **D1** deliverable)
- [`modules/phases.py`](../../../modules/phases.py) — `PhaseStatus`, `FolderPhaseStatus`, `ALLOWED_TRANSITIONS`
- [`modules/db_postgres.py`](../../../modules/db_postgres.py) — DDL for every table listed above
