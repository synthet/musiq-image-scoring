# Static Analysis & Code Review — 2026-05-23

> Multi-pass static analysis of the v7.20.0 release: LLM-judge scoring engines (Claude, Cursor), Runs auto-drive, DB Explorer, and model-scores API merge. Three independent finder angles (line-by-line diff scan, removed-behavior audit, cross-file tracer) verified by a fourth-pass judge.

**Scope:** `modules/runs_autodrive.py`, `modules/claude_scorer.py`, `modules/cursor_scorer.py`, `modules/engines/{claude_model,cursor_model,host}.py`, `modules/pipeline.py` (registry injection), `modules/api.py` (model-scores merge + new endpoints), `modules/api_db.py`, `modules/db_legacy.py` (SQL validators), `frontend/src/pages/DbPage.tsx`, `frontend/src/api/db.ts`.  
**Commit:** `89d7149` (v7.20.0)  
**Method:** Three-angle finder (line diff / removed-behavior / cross-file) + independent verifier pass.  
**Prior art:** [CODE_DESIGN_REVIEW_2026-04-18.md](CODE_DESIGN_REVIEW_2026-04-18.md), [SECURITY_FIXES_2026_04_19.md](SECURITY_FIXES_2026_04_19.md)

---

## Summary of Findings

| Severity | Count | Key Themes |
|----------|-------|------------|
| 🔴 CRITICAL | 1 | SQL deny-list missing PG file-exfiltration functions |
| 🟠 HIGH | 3 | /transaction bypasses SQL validation; write validator missing `;`; loop-guard blind to in-flight jobs |
| 🟡 MEDIUM | 5 | limit=200 hard-coded cap; thread-timeout no detection; shadow failures inflate counter; CTE bypass; write token not in secrets store |
| 🟢 LOW | 0 | — |

---

## 🔴 CRITICAL

### C-1. `validate_readonly_sql_for_api` — PostgreSQL File-Exfiltration Functions Not Blocked

**Files:** `modules/db_legacy.py:449–468`, `modules/api_db.py:60–109`

**What's wrong:** The read-only SQL validator uses a deny-list of keywords (`DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, `;`, `--`, `/*`, `COPY`, `LOAD`, `INTO OUTFILE`). The list does not include PostgreSQL built-in functions that can read or exfiltrate server-side files: `pg_read_file()`, `pg_read_binary_file()`, `pg_ls_dir()`, `pg_stat_file()`, `lo_export()`, `lo_import()`, `dblink()`. Read queries require **zero authentication** — the write-token gate is only applied when `write: true`.

**Evidence:**
```python
# db_legacy.py:446-468 — full blocklist; none of the pg_ file functions appear
if not (upper.startswith("SELECT") or upper.startswith("WITH")):
    return "Only read-only SELECT or WITH...SELECT queries are allowed"
dangerous_patterns = [
    r"\bDROP\b", r"\bDELETE\b", r"\bINSERT\b", r"\bUPDATE\b", r"\bALTER\b",
    r"\bCREATE\b", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bREVOKE\b",
    r";", r"--", r"/\*", r"\bCOPY\b", r"\bLOAD\b", r"\bINTO\s+OUTFILE\b",
]
# → pg_read_file, pg_ls_dir, lo_export, dblink: not listed
```

**Impact:** Any process that can reach port 7860 (or any host when `WEBUI_HOST=0.0.0.0` is set) can exfiltrate arbitrary server-side files with a single unauthenticated POST:
```
POST /api/db/query
{"sql": "SELECT pg_read_file('/home/user/image-scoring-backend/secrets.json')", "write": false}
```
This returns the full contents of `secrets.json` (Anthropic API key, Cursor API key, write token, any other credentials) with no credentials required. With `dblink` installed, cross-database lateral movement is also possible.

The same bypass works through a CTE: `WITH s AS (SELECT pg_read_file('/etc/passwd')) SELECT * FROM s` — starts with `WITH`, no blocked keyword, executes fine. (See also M-3 below.)

**Suggested fix:**

Replace the deny-list approach with connection-level enforcement. This is the only reliable defence:

```python
# In execute_readonly_sql_for_api — PostgreSQL path:
with db_postgres.PGConnectionManager() as conn:
    conn.set_session(readonly=True)          # ← enforce at transport level
    with conn.cursor(...) as cur:
        cur.execute(pg_sql, ...)
        ...
```

Additionally, run the DB user with the minimum required PostgreSQL role — do not grant `pg_read_server_files`, `SUPERUSER`, or `pg_execute_server_program`. For defense-in-depth, add the most dangerous known functions to the deny-list as a secondary check:

```python
r"\bpg_read_file\b",
r"\bpg_read_binary_file\b",
r"\bpg_ls_dir\b",
r"\bpg_stat_file\b",
r"\blo_export\b",
r"\blo_import\b",
r"\bdblink\b",
r"\bpg_execute_server_program\b",
```

---

## 🟠 HIGH

### H-1. `POST /api/db/transaction` — SQL Bypasses `validate_write_sql_for_api` Under PostgresConnector

**Files:** `modules/api_db.py:117–167`, `modules/db_connector/postgres.py:64–68`

**What's wrong:** The `/transaction` endpoint authenticates the write token, then calls `get_connector().run_transaction(_tx)` where `_tx` calls `tx.execute(sql, params)` directly. When `database.engine = "postgres"` (the primary/default), `get_connector()` returns `PostgresConnector`; `_PgTx.execute()` translates the placeholder dialect and executes directly via psycopg2 — **with no call to `validate_write_sql_for_api`**. DDL (`DROP`, `ALTER`, `TRUNCATE`) is unrestricted.

By contrast, the `/query` write path goes through `db.execute_write_sql_for_api()` which does call `validate_write_sql_for_api()`. The two endpoints have inconsistent security posture.

**Evidence:**
```python
# api_db.py:131–147 — no validation before the transaction
def _tx(tx):
    for stmt in statements:
        sql = (stmt.get("sql") or "").strip()
        ...
        tx.execute(sql, params)          # → _PgTx.execute() → cur.execute() — no guard

get_connector().run_transaction(_tx)    # PostgresConnector path: goes straight to psycopg2
```

**Impact:** A caller with a valid `X-DB-Write-Token` can issue:
```json
{"statements": [{"sql": "DROP TABLE images", "params": []}]}
```
and drop the primary images table with no additional guard. The `/query` write path blocks `DROP`; `/transaction` does not.

**Suggested fix:** Apply the same validation inside `_tx` before dispatching each statement:
```python
def _tx(tx):
    for stmt in statements:
        sql = (stmt.get("sql") or "").strip()
        if not sql:
            continue
        from modules.db_legacy import validate_write_sql_for_api
        err = validate_write_sql_for_api(sql)
        if err:
            raise ValueError(f"Statement rejected: {err}")
        ...
        tx.execute(sql, params)
```

---

### H-2. `validate_write_sql_for_api` — Bare Semicolon Not Blocked, Inconsistent With Read Validator

**File:** `modules/db_legacy.py:541–553`

**What's wrong:** The write validator's `dangerous_patterns` list contains `r";--"` (the semicolon-comment sequence) but **not** a bare `r";"`. The read validator at line 459 correctly blocks any `r";"` as a multi-statement separator. The write validator does not, so a write query like:

```sql
UPDATE images SET score = 0 WHERE 1=0; DROP TABLE stacks
```

passes `validate_write_sql_for_api`. psycopg2's `cursor.execute()` rejects multi-statement strings under default settings, but this is a driver-level coincidence, not an explicit guard. The Firebird path and `execute_many` path may behave differently; future driver changes could silently permit it.

**Evidence:**
```python
# db_legacy.py:541-549
dangerous_patterns = [
    r"\bDROP\b", r"\bALTER\b", r"\bCREATE\b", r"\bTRUNCATE\b",
    r"\bGRANT\b", r"\bREVOKE\b",
    r";--",         # ← only the comment-terminated variant; bare ";" absent
]
# vs read validator (line 459):
r";",               # ← correct: blocks any semicolon
```

**Suggested fix:** Add `r";"` to `validate_write_sql_for_api`'s `dangerous_patterns`. Also add `r"--"` and `r"/\*"` for parity with the read validator.

---

### H-3. `_recent_auto_attempt_counts` — Loop-Guard Blind to In-Flight Jobs

**File:** `modules/runs_autodrive.py:197`

**What's wrong:** `auto_drive_runs` uses `_recent_auto_attempt_counts` to detect repeated queueing of the same folder/phase plan and skip it once `max_repeats` is reached. The function fetches only **terminal** jobs via `db.get_jobs(limit=500, offset=0, history_only=True)`. `history_only=True` resolves to statuses `("completed", "failed", "canceled", "cancelled", "interrupted")`. Running or queued jobs are invisible.

```python
# runs_autodrive.py:197
rows = db.get_jobs(limit=scan_limit, offset=0, history_only=True)

# db_legacy.py:7129,7172-7173
_JOB_HISTORY_STATUSES = ("completed", "failed", "canceled", "cancelled", "interrupted")
elif history_only:
    statuses = [s.lower() for s in _JOB_HISTORY_STATUSES]
```

**Impact:** If a folder has been auto-queued twice and both jobs are still `running` or `pending`, `attempts = 0`. The loop guard does not trip. A third (and fourth, and fifth…) job is enqueued. Simultaneous scoring jobs for the same folder race over the same images, producing duplicate writes to `image_model_scores`, conflicting phase status updates, and wasted GPU/API resources. The guard only engages after all prior runs finish.

**Suggested fix:** Count **all** auto-drive jobs for the plan key, not just terminal ones:
```python
# Either remove history_only=True:
rows = db.get_jobs(limit=scan_limit, offset=0)

# Or add a separate in-flight check using _active_job_path_keys() correlation,
# or query active job payloads for matching auto_drive_plan_key.
```

---

## 🟡 MEDIUM

### M-1. `auto_drive_runs` — Hard-Coded `limit=200` in `build_folder_buckets` Call

**File:** `modules/runs_autodrive.py:489`

**What's wrong:** `auto_drive_runs` validates `limit` up to 500 (line 482), then calls `build_folder_buckets(limit=200, ...)` with a hard-coded 200 regardless of the caller's value. `candidates[:limit]` then slices a list that is already capped at 200 items.

```python
# runs_autodrive.py:482,489
limit = max(1, min(_as_int(limit, 50), 500))   # user limit accepted up to 500
...
planned = build_folder_buckets(
    ...
    limit=200,      # ← ignores user limit; effectively caps at 200
    ...
)
candidates = [...planned["items"]...][:limit]   # slices at most 200 items
```

**Impact:** `auto_drive_runs(limit=400)` silently queues at most 200 folders. The response shows `candidates: 200` and `total_outstanding: N` where N > 200, giving no indication that 200 were skipped. At `limit=50` (default) this is invisible; at `limit > 200` the discrepancy grows.

**Suggested fix:**
```python
planned = build_folder_buckets(
    ...
    limit=limit,    # pass through the validated user limit
    ...
)
```

---

### M-2. `ClaudeScorer._run_in_thread` — Thread Timeout Not Detected; Daemon Thread Leaks

**File:** `modules/claude_scorer.py:229–243`

**What's wrong:** `_run_in_thread` joins the worker thread with a deadline (`thread.join(self.timeout_seconds + 30)`) but does not check `thread.is_alive()` after the join. If the thread is still running when `join()` returns (the SDK hung before reaching `asyncio.wait_for`), `box` is empty, `box.get("value")` returns `None`, and `parse_rubric(None)` returns `None` — the call surface-treats this as a normal failure. The hung thread is never cancelled; it continues running as a daemon, holding a Claude API connection slot until the process exits.

```python
thread.join(self.timeout_seconds + 30)
if "error" in box:          # "error" not set either → no raise
    raise box["error"]
return box.get("value")     # returns None; thread still alive
```

**Impact:** Each image scored under these conditions leaks one background thread and one API concurrency slot. On a pipeline run of N images, up to N threads can accumulate. The per-image scoring loop in `ScoringWorker` is synchronous (images processed one at a time), so in practice only one thread leaks per hung prediction. Still: no timeout exception is raised, the pipeline logs a generic `"status": "failed"`, and the root cause (SDK hang) is undiagnosable from the log.

**Suggested fix:**
```python
thread.join(self.timeout_seconds + 30)
if thread.is_alive():
    # Thread is stuck — we cannot cancel it, but we can report clearly.
    raise TimeoutError(
        f"Claude SDK thread did not finish within {self.timeout_seconds + 30}s"
    )
if "error" in box:
    raise box["error"]
return box.get("value")
```

---

### M-3. CTE Wrapper Bypasses Read Validator for Unblocked PostgreSQL Functions

**File:** `modules/db_legacy.py:446`

**What's wrong:** A query starting with `WITH` is accepted by the read validator's `startswith("WITH")` check. The body of the CTE is subject to the same incomplete deny-list as a bare `SELECT`. Any unblocked function (see C-1) can be called inside a CTE:

```sql
WITH s AS (SELECT pg_read_file('/etc/passwd')) SELECT * FROM s
```

This is a secondary attack surface that survives independently. Even if C-1 is partially fixed by adding some PG functions to the deny-list, the CTE shape provides an additional obfuscation layer. The root fix is the same as C-1 (connection-level `readonly=True`), but it warrants its own entry because it requires separately testing the `WITH` code path.

**Suggested fix:** Same as C-1. Apply `conn.set_session(readonly=True)` at the PostgreSQL connection level. Add the CTE path to the test matrix for the SQL validator.

---

### M-4. Shadow Model Load Failures Inflate `summary.failed_predictions`

**File:** `modules/engines/host.py` (MultiModelHost), `modules/pipeline.py:355–388`

**What's wrong:** `_run_registry_models` catches exceptions from `model.load()` and `model.predict()` and inserts a `{"status": "failed", "is_shadow": True}` entry into `external`. `MultiModelHost._merge_external_scores` counts entries with `status != "success"` as `failed_predictions` without checking `is_shadow`. Shadow models that are enabled in config but have no API key (the default out-of-the-box state for `claude` and `cursor`) will reliably inject a failure record for every image processed.

**Impact:** Any monitoring or alerting on `summary.failed_predictions / total_predictions` fires false positives on every image. Production score quality is unaffected (shadow results are excluded from fusion), but operators cannot distinguish a real scoring regression from an always-failing shadow model. The `not_loaded` status path avoids this (it is not counted as failed), but if `load()` raises rather than returning `False`, the exception path writes `"failed"`.

**Suggested fix:** Make `MultiModelHost` shadow-aware in its counter:
```python
# In _merge_external_scores or wherever failed_predictions is incremented:
if not payload.get("is_shadow"):
    results["summary"]["failed_predictions"] += 1
```
And/or ensure `ClaudeModelWrapper.load()` / `CursorModelWrapper.load()` always returns `False` on missing credentials rather than raising.

---

### M-5. `query_token` Stored in `config.json`, Compared Without Timing-Safe Equality

**File:** `modules/api_db.py:74–85`

**What's wrong:** The write gate secret lives at `config.database.query_token` in `config.json`. The codebase has a `secrets.json` facility (git-ignored, documented as the home for API keys) that is explicitly distinct from `config.json` (which is version-controlled or world-readable on a developer machine). The token comparison uses plain `!=`:

```python
if x_db_write_token != token:   # plain string equality — timing side-channel
    raise HTTPException(status_code=403, detail="Invalid X-DB-Write-Token")
```

**Impact:** Two separate issues:
1. **Exposure via config.json:** Any process that can read `config.json` (or the unauthenticated `pg_read_file` path in C-1) learns the write token. Using `secrets.json` with restricted file permissions would limit exposure.
2. **Timing oracle:** A local attacker making many rapid requests to `/api/db/transaction` can measure response time to enumerate the token byte by byte. On localhost this is low-practicality but is a correctness issue.

**Suggested fix:**
```python
import hmac
if not hmac.compare_digest(x_db_write_token or "", token):
    raise HTTPException(status_code=403, detail="Invalid X-DB-Write-Token")
```
Move `query_token` to `secrets.json` and load it via `config.get_secret("db_write_token")`.

---

## Design Notes

### SQL Bridge Threat Model

The `POST /api/db/query` + `POST /api/db/transaction` bridge was designed for the Electron gallery (`database.engine = "api"`) where the gallery process is the sole trusted client on localhost. With the DB Explorer page now accessible from any browser pointed at port 7860, the threat model has quietly shifted. Concretely:

- **Read path:** zero auth, full schema access. Acceptable for a developer tool on `127.0.0.1`; unacceptable when `WEBUI_HOST=0.0.0.0`.
- **Write path:** token auth with a weak secret store.
- **No rate limiting, no row-level restrictions, no audit log.**

Recommended guardrail: add a config flag `database.db_explorer_read_requires_token` (default `false` for backward compat) and enforce it in the DB Explorer `fetchTables`/`fetchTablePage`/`query` paths. Document clearly that enabling `0.0.0.0` binding with `db_explorer_enabled=true` opens full DB read to the network.

### Loop-Detection Architecture

`auto_drive_runs` implements loop detection via a scan of recent historical jobs filtered by `auto_drive_plan_key` in the queue payload. This approach has two structural weaknesses (H-3 above and the 500-job scan window). A more robust approach is a dedicated `auto_drive_plans` table with columns `(plan_key, queued_at, job_id, status)`, giving O(1) lookups and full visibility into in-flight runs.

---

## Prioritised Fix Plan

### Immediate (before next deployment with `WEBUI_HOST=0.0.0.0`)

1. **C-1 / M-3:** Apply `conn.set_session(readonly=True)` in `execute_readonly_sql_for_api` PostgreSQL path. Add file-function deny-list entries as belt-and-suspenders.
2. **H-1:** Add `validate_write_sql_for_api` call inside the `_tx` closure in `/transaction`.
3. **H-2:** Add `r";"`, `r"--"`, `r"/\*"` to `validate_write_sql_for_api` dangerous patterns.

### Short-Term

4. **H-3:** Pass full job set (not history-only) to `_recent_auto_attempt_counts`, or add an active-job intersection check using `_active_job_path_keys` correlation.
5. **M-1:** Change `build_folder_buckets(limit=200)` to `build_folder_buckets(limit=limit)` in `auto_drive_runs`.
6. **M-5:** Move `query_token` to `secrets.json`; switch comparison to `hmac.compare_digest`.

### Long-Term

7. **M-2:** Add `thread.is_alive()` check + `TimeoutError` raise in `_run_in_thread`.
8. **M-4:** Make `MultiModelHost.failed_predictions` counter shadow-aware.
9. **SQL bridge:** Add optional read-auth gate for non-localhost deployments; add per-request audit log for write operations.
10. **Loop detection:** Replace payload-scan approach with a lightweight `auto_drive_plans` tracking table.

---

*Generated by static analysis + three-angle code review pass on commit `89d7149` (v7.20.0), 2026-05-23.*
