# Code & Design Review — 2026-04-18

> Comprehensive audit covering architecture, data integrity, error handling, concurrency, API contracts, pipeline orchestration, database layer, and security.

**Scope:** Full backend codebase (`modules/`) with focus on highest-risk files by size and coupling.  
**Method:** Static analysis via code reading, grep pattern search, and MCP tool cross-referencing.  
**Prior art:** [CODE_REVIEW_2026-04-15.md](CODE_REVIEW_2026-04-15.md), [CODE_DESIGN_REVIEW_legacy.md](../archive/reports/CODE_DESIGN_REVIEW_legacy.md)

---

## Summary of Findings

| Severity | Count | Key Themes |
|----------|-------|------------|
| 🔴 CRITICAL | 3 | Unsandboxed RCE, status value divergence, broken MCP tool |
| 🟠 HIGH | 5 | Connection leaks, stuck jobs, no circuit breaker, SQL validation gap |
| 🟡 MEDIUM | 7 | God object, race conditions, thread safety, no auth |
| 🟢 LOW | 4 | Firebird remnants, migration auto-run, transaction safety |

---

## 🔴 CRITICAL

### C-1. `execute_code` MCP Tool — Unrestricted `exec()` with Full Process Access

**File:** `modules/mcp_server.py:2046-2107`

**What's wrong:** The `execute_code` tool runs arbitrary Python via `exec()` in the WebUI process with no sandbox, no code filtering, and full access to `builtins`, `db`, `config`, all runners, and the `gradio` context. The only guard is `ENABLE_MCP_EXECUTE_CODE=1` env var.

**Evidence:**
```python
exec_globals["__builtins__"] = builtins  # Full builtins, including __import__, open(), eval()
exec(code, exec_globals)                 # Unrestricted exec
```

**Impact:** Any MCP client connected to the SSE endpoint can execute arbitrary code — file I/O, network access, database mutations, `os.system()`. If the WebUI is exposed beyond localhost (e.g., Docker with port forwarding), this is a remote code execution vector. The env-var guard is trivially bypassed if the attacker can set environment variables or if the user sets it and forgets.

**Suggested fix:**
1. Add an explicit allowlist of safe modules/functions or use `RestrictedPython`.
2. Remove `__builtins__` from `exec_globals` or replace with a curated safe subset.
3. Log all `execute_code` invocations with the full code string and client IP.
4. Consider requiring a per-session auth token rather than a persistent env var.

---

### C-2. `cancelled` vs `canceled` — Active Data Corruption from Dual Status Values

**Files:** `modules/db.py:33-46`, `modules/db.py:5327-5362`, `modules/pipeline_orchestrator.py:263`

**What's wrong:** Two different spelling variants of the same logical status are **actively written** to the `jobs` table by different code paths:

| Code Path | Writes |
|-----------|--------|
| `pipeline_orchestrator.stop()` | `"canceled"` |
| `request_cancel_job()` | `"cancelled"` |
| `api.py` cancel-run endpoint | `"canceled"` |
| `status_gradio.py` terminal set | `"canceled"` only ❌ |
| `mcp_server.py` performance metrics | queries `"cancelled"` only ❌ |

**Evidence:**
```python
# pipeline_orchestrator.py:263 writes "canceled"
db.update_job_status(self.root_job_id, "canceled", runner_state="canceled")

# db.py:5344 writes "cancelled"  
SET status = 'cancelled', cancel_requested = 1, queue_position = NULL,
```

**Impact:** 
- `status_gradio.py:375` terminal set is `{"completed", "failed", "canceled", "interrupted"}` — **missing `"cancelled"`** — so jobs cancelled via `request_cancel_job()` will never show "View" links in the status page.
- `mcp_server.py:1718` only counts `"cancelled"` — **missing `"canceled"`** — performance metrics undercount cancellations from orchestrator cancels.
- The `JOB_TERMINAL_STATES` set (db.py:33) includes both, but downstream consumers are inconsistent.

**Suggested fix:**
1. Canonicalize to one spelling (suggest `"cancelled"` per British English or `"canceled"` per American — pick one).
2. Add a one-shot migration to update all existing rows to the canonical spelling.
3. Add a normalizer in `update_job_status()` that maps the non-canonical variant to canonical before DB write.
4. Grep the entire codebase for both variants and unify.

---

### C-3. MCP Tool References Non-Existent DB Method — `list_stale_running_image_phase_rows`

**File:** `modules/mcp_server.py:740`, `modules/mcp_server.py:952`

**What's wrong:** The MCP tools `check_database_health` and `get_stale_running_phase_status` call `db.list_stale_running_image_phase_rows()`, which does not exist in `modules/db.py`.

**Evidence:** grep confirms the method is only referenced in `mcp_server.py` and never defined anywhere.

**Impact:** Two MCP tools crash with `AttributeError: module 'modules.db' has no attribute 'list_stale_running_image_phase_rows'`. The `check_database_health` tool is a primary diagnostic tool — this makes it partially broken. The `get_stale_running_phase_status` tool is completely broken.

**Suggested fix:** Implement `list_stale_running_image_phase_rows(min_age_seconds, limit)` in `db.py` as a query against `image_phase_status` where `status = 'running'` and `updated_at < NOW() - min_age_seconds`.

---

## 🟠 HIGH

### H-1. Connection Leaks from Raw `get_db()` Without Context Manager

**Files:** `modules/workflow_healing.py:58,93,144`, `modules/scoring.py:612`, `modules/api.py` (7 sites), `modules/similar_search.py` (5 sites), `modules/selector_resolver.py:156`, and others — **29+ call sites total**

**What's wrong:** At least **29 call sites** use `conn = db.get_db()` without `try/finally` or the `db.connection()` context manager. If any exception occurs between `get_db()` and `conn.close()`, the connection leaks.

**Evidence (workflow_healing.py):**
```python
conn = db.get_db()      # Line 58
c = conn.cursor()
c.execute(reset_query, (phase_code,))
false_positive_ids = [row[0] for row in c.fetchall()]
conn.close()             # Line 62 — skipped on exception!
```

Three instances in one file, plus `scoring.py:612` (`fix_image_metadata`), 5 in `similar_search.py`, 7 in `api.py`, etc.

**Impact:** Under load or transient DB errors, connections accumulate and are never returned to the pool. With PostgreSQL (psycopg2 connection pool), this exhausts `max_connections` and causes cascading failures.

**Suggested fix:** Replace all `conn = db.get_db()` patterns with `with db.connection() as conn:` or use `get_connector()` for new code. Do a global search-and-replace pass.

---

### H-2. No Circuit Breaker for Model Loading Failures

**File:** `modules/scoring.py:138-159`

**What's wrong:** When `MultiModelMUSIQ()` or `load_model()` fails, the error is logged and the job is marked failed — but the next job attempts model loading again with no backoff. If models fail to load (e.g., corrupt checkpoint, OOM), the system will repeatedly fail identical jobs.

**Evidence:**
```python
if self.shared_scorer is None:          # Every new batch tries again
    new_scorer = MultiModelMUSIQ()      # No circuit breaker
    for model_name in musiq_models:
        success = new_scorer.load_model(model_name)
        if not success:
             log(f"Warning: Failed to load {model_name}", "WARNING")
    self.shared_scorer = new_scorer     # Set even if load_model failed!
```

Note: even when `load_model` returns `False`, `shared_scorer` is still set, meaning subsequent jobs will use a scorer with partially loaded models.

**Impact:** The 4 consecutive `'MultiModelMUSIQ' object has no attribute 'load_model'` failures in the DB are evidence of this pattern. Without a circuit breaker, queued jobs continue to fail immediately in sequence, wasting resources and polluting logs.

**Suggested fix:**
1. Track consecutive failures in `ScoringRunner`. After N failures (e.g., 3), stop accepting new scoring jobs and surface the error to the UI/API.
2. Don't set `self.shared_scorer` unless all critical models loaded successfully.
3. Add a cooldown period before retrying model initialization.

---

### H-3. Jobs Can Get Permanently Stuck in "running" or "queued" Status

**Files:** `modules/job_dispatcher.py:86-101`, `modules/pipeline_orchestrator.py:225-244`, `modules/scoring.py:67-98`

**What's wrong:** Multiple scenarios leave jobs stuck:

1. **If the WebUI process is killed (SIGKILL):** `scoring.py` sets `is_running = True` on line 67 and only sets it `False` in the finally block (line 98). A SIGKILL bypasses the finally block, leaving the runner in `is_running=True` state (in-memory) — and the DB row stays as `"running"` with no timeout mechanism.

2. **If `_run_batch_internal` hangs:** The job stays `"running"` indefinitely. There's no watchdog or timeout.

3. **If `dequeue_next_job()` dequeues a job but `_start_job()` raises before setting DB status:** The job was already dequeued from the queue but never started — stuck in `"running"` (set by `dequeue_next_job`).

4. **Recovery is manual:** `workflow_healing.py` exists but is only invoked explicitly via API (`heal_phase_data`), not automatically. `recover_interrupted_jobs()` on the orchestrator runs once at startup but not for individual runner-level stuck jobs.

**Impact:** The 6 stuck "queued" jobs and 1 stuck "running" job reported in the database are evidence of this gap.

**Suggested fix:**
1. Add a `job_age_watchdog` background thread that marks jobs as `"interrupted"` if they've been `"running"` longer than a configurable timeout (e.g., 24 hours with no progress updates).
2. Make `dequeue_next_job()` use a DB-level optimistic lock (`UPDATE ... WHERE status = 'queued' ... RETURNING id`) to avoid TOCTOU races.
3. Register a `SIGTERM` handler that calls `orchestrator.stop(mode="graceful")` to clean up before exit.

---

### H-4. `validate_readonly_sql_for_api` — SQL Injection via Semicolons

**File:** `modules/db.py:372-396`

**What's wrong:** The SQL validation checks if the query starts with `SELECT` or `WITH`, then searches for dangerous keywords. But the `;` character is not blocked — a semicolon-separated batch of statements could inject a `DELETE` or `UPDATE` as the second statement. psycopg2 does not support multi-statement by default, but Firebird's `execute` does.

**Impact:** With Firebird engine (legacy), a crafted query could potentially execute destructive statements via the read-only API endpoint.

**Suggested fix:**
1. Add `;` to the blocklist (or disallow any query containing `;`).
2. Force `SET TRANSACTION READ ONLY` (already done for Firebird via `ro_tpb`; verify the Postgres path uses a read-only transaction).

---

### H-5. `status_gradio.py` Terminal State Set Missing `"cancelled"` Variant

**File:** `modules/ui/status_gradio.py:375`

**What's wrong:** The terminal state set used to render "View" links for completed jobs is `{"completed", "failed", "canceled", "interrupted"}` — it's **missing `"cancelled"`** (the variant written by `request_cancel_job()`).

**Evidence:**
```python
terminal = {"completed", "failed", "canceled", "interrupted"}  # Missing "cancelled"!
```

**Impact:** Jobs cancelled via the `request_cancel_job()` code path will never show "View" report links on the status page. Users won't be able to access execution reports for these jobs.

**Suggested fix:** Add `"cancelled"` to the set, or better, normalize the status before comparison (see C-2).

---

## 🟡 MEDIUM

### M-1. `db.py` Is 417 KB / 10,565 Lines — Extreme God Object

**File:** `modules/db.py` (417 KB)

**What's wrong:** This single file contains:
- Connection management (Firebird, PostgreSQL, proxies)
- SQL translation (FB → PG)
- All CRUD operations for images, folders, stacks, jobs, phases, keywords, embeddings, etc.
- Job state machine logic
- Pipeline telemetry
- Backup logic
- UUID generation
- Sort validation

**Impact:** Extremely high defect risk — any change to this file risks breaking unrelated functionality. Merge conflicts are likely. Testing individual concerns is difficult. The file is too large for most LLM context windows, making AI-assisted maintenance unreliable.

**Suggested decomposition:**
- `db_connection.py` — Connection management, proxies, SQL translation
- `db_images.py` — Image CRUD, querying, filtering
- `db_jobs.py` — Job lifecycle, state machine, phases
- `db_folders.py` — Folder operations
- `db_stacks.py` — Stack/cluster operations  
- `db_keywords.py` — Keyword normalized schema operations

---

### M-2. `workflow_healing.py` Uses Raw SQL with `get_db()` Instead of Connector

**File:** `modules/workflow_healing.py:47-97`

**What's wrong:** The module uses `conn = db.get_db()` + `c.execute()` with raw SQL instead of the `db.get_connector()` abstraction. The raw `?` placeholder SQL works because `PostgresCursorProxy` translates it — but the pattern bypasses the connector abstraction and introduces three connection leak sites (see H-1).

**Impact:** Maintenance burden and connection leak risk on exception paths.

---

### M-3. `PipelineOrchestrator.on_tick()` Doesn't Handle `"paused"` Phase Status

**File:** `modules/pipeline_orchestrator.py:225-244`

**What's wrong:** When `on_tick()` checks the phase job status, it only handles `"failed"` and implicitly `"completed"` (via the else branch). If a job transitions to `"paused"` or `"interrupted"`, the runner reports `is_running=False` but the job status is neither `"failed"` nor `"completed"`, so the orchestrator calls `set_job_phase_state(..., "completed")` — which is incorrect.

**Evidence:**
```python
if not is_running:
    phase_job = db.get_job_by_id(self.current_phase_job_id)
    if phase_job and phase_job.get("status") == "failed":
        # ...handle failure
    else:
        db.set_job_phase_state(..., "completed")  # BUG: may not be completed!
        self._start_next_phase()
```

**Impact:** A paused or interrupted phase job can be incorrectly marked as "completed", causing the orchestrator to advance to the next phase with incomplete work.

---

### M-4. `ScoringRunner.is_running` Is Not Thread-Safe

**File:** `modules/scoring.py:44,67,98`

**What's wrong:** `self.is_running` is a plain boolean read on line 64 and set on line 67 — a classic TOCTOU race. Two concurrent `start_batch` calls could both see `is_running=False` and both proceed. Partially mitigated by the dispatcher's `_dispatch_lock`, but API endpoints can also call `start_batch` directly.

**Suggested fix:** Use `threading.Lock` around the `is_running` check-and-set in `start_batch`.

---

### M-5. `EventManager.active_connections` Is Not Thread-Safe

**File:** `modules/events.py:30,35,39,56`

**What's wrong:** `active_connections` is a plain `list` modified by `connect()` (async, from the event loop), `disconnect()` (called from both async and sync contexts), and `broadcast()`. The broadcast iterates `self.active_connections[:]` (a snapshot), but `disconnect` can be called from the broadcast's error handler on the same list that `connect` is simultaneously appending to.

**Impact:** Potential `RuntimeError: list modified during iteration` or lost connections under high WebSocket concurrency.

---

### M-6. `mcp_server.py` Performance Metrics Only Counts `"cancelled"` Not `"canceled"`

**File:** `modules/mcp_server.py:1718`

**What's wrong:** The `get_performance_metrics` tool counts `jobs_by_status.get("cancelled", 0)` — it misses jobs stored as `"canceled"`.

**Impact:** Performance metrics underreport cancellations. The `success_rate` calculation is based on terminal counts that exclude half the cancelled jobs.

---

### M-7. No Authentication on API or MCP Endpoints

**File:** `modules/ui/security.py` (57 lines)

**What's wrong:** The security module provides rate limiting and path validation, but there is **no authentication** mechanism for the API or MCP endpoints. Any client that can reach the WebUI port can read all data, start/cancel jobs, and modify configuration.

**Impact:** In a shared network or Docker-forwarded environment, any user on the network can manipulate the system.

**Suggested fix:** Add basic auth (e.g., API key via header) for mutating endpoints. For local-only deployments, bind to `127.0.0.1` and document the risk.

---

## 🟢 LOW

### L-1. `validate_config()` Uses Firebird-Specific SQL

**File:** `modules/mcp_server.py:1899`

```python
c.execute("SELECT 1 FROM RDB$DATABASE")  # Firebird-only system table
```

When the engine is `postgres`, this will fail because `RDB$DATABASE` doesn't exist in PostgreSQL.

**Suggested fix:** Use `SELECT 1` which works on both engines.

---

### L-2. Alembic Migrations Exist but Auto-Run Not Verified  

**Files:** `alembic.ini`, `migrations/` (11 revisions: 0001–0011)

Alembic is set up with active revisions, but the ad-hoc column addition in `_init_db_impl()` suggests migrations may not always run at startup. Verify that `alembic upgrade head` is part of the deployment/startup sequence.

---

### L-3. `scoring.py:612` — `fix_image_metadata` Uses Raw Connection Without Transaction Safety

**File:** `modules/scoring.py:612-626`

Uses raw `get_db()` instead of `connection()` context manager (connection leak on exception), and commits the DB update before the XMP write — if XMP write fails, DB and sidecar are out of sync.

---

### L-4. `_compute_aggregate_after` Accesses `collector._pending` (Private Attribute)

**File:** `modules/scoring.py:346-348`

Directly accessing `ReportCollector._pending`, a private list. If the internal structure changes, this code breaks silently.

---

## Answers to Key Questions

| # | Question | Answer |
|---|----------|--------|
| 1 | Can a job get permanently stuck in "running"? | **Yes.** No timeout watchdog exists. Recovery is manual. |
| 2 | Race condition between dispatcher and orchestrator? | **Partially mitigated** by `_dispatch_lock`, but `is_running` check is not atomic. |
| 3 | Why do deleted images leave empty stacks? | Likely cascade delete gap — `delete_image()` doesn't clean up empty parent stacks. |
| 4 | Firebird↔PostgreSQL dual-write consistency? | **No longer relevant.** Dual-write removed (Firebird decommissioned 2026-03). |
| 5 | What happens on SIGKILL during scoring? | Partial results saved (per-image upserts). DB row stays "running" until manual recovery. |
| 6 | API endpoints without path sanitization? | `_validate_file_path()` exists but must be verified for all file-accepting endpoints. |
| 7 | Does `execute_code` have any sandbox? | **No.** Unrestricted `exec()` with full builtins. |

---

## Recommended Priority Order

1. **C-2 + H-5 + M-6**: Unify `cancelled`/`canceled` — one migration + codebase grep. Fast fix, broad impact.
2. **C-3**: Implement missing `list_stale_running_image_phase_rows`. Required for diagnostic tools.
3. **H-1**: Convert `get_db()` → `connection()` context managers across 29+ sites. Prevents pool exhaustion.
4. **H-3**: Add job timeout watchdog background thread. Prevents stuck jobs.
5. **H-2**: Add circuit breaker to model loading. Prevents cascading scoring failures.
6. **M-3**: Fix orchestrator `on_tick()` to handle paused/interrupted states.
7. **C-1**: Harden `execute_code` (lower priority if WebUI stays localhost-only).
8. **M-1**: Begin `db.py` decomposition (long-term, high-effort).
