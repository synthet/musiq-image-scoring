# Code Quality Audit — Vexlum Scoring Backend

**Date:** 2026-05-14  
**Scope:** `modules/` — core backend Python codebase  
**Reviewer:** AI-assisted (Antigravity)

---

## Executive Summary

The codebase is a mature, feature-rich image-scoring backend that has evolved organically. It functions correctly for its primary use case but carries significant technical debt from its Firebird→PostgreSQL migration, a monolithic database module, and inconsistent threading patterns across runners. This audit identifies **43 findings** across 5 severity tiers.

| Severity | Count | Description |
|----------|-------|-------------|
| 🔴 Critical | 3 | Potential data loss or race conditions under load |
| 🟠 High | 8 | Functional defects, fragile patterns likely to cause bugs |
| 🟡 Medium | 14 | Code smells that impair maintainability |
| 🔵 Low | 12 | Style and consistency issues |
| ⚪ Info | 6 | Observations and improvement opportunities |

---

## 🔴 Critical Findings

### C-1. Thread-unsafe `disconnect_sync` in EventManager

**File:** [events.py](file:///d:/Projects/image-scoring-backend/modules/events.py#L47-L51)

The `EventManager` uses an `asyncio.Lock` for `connect()` and `disconnect()`, but `disconnect_sync()` mutates `self.active_connections` (a plain `list`) **without any lock**. If a background thread calls `disconnect_sync` while the async `broadcast()` is iterating over a snapshot, or while `connect()` appends, a `list.remove()` during concurrent modification can cause `ValueError` or silently skip elements.

```python
# Current — no lock, thread-unsafe
def disconnect_sync(self, websocket: WebSocket):
    if websocket in self.active_connections:
        self.active_connections.remove(websocket)
```

> [!CAUTION]
> This is invoked from non-async cleanup paths (e.g. WebSocket error handlers). Under load with multiple connected clients, this can corrupt the connection list.

**Recommendation:** Use a `threading.Lock` (not an `asyncio.Lock`) that is also acquired inside `connect`, `disconnect`, and `broadcast`'s snapshot section, or migrate to a thread-safe `set`/`deque`.

---

### C-2. `is_running` flag not protected by lock in most Runners

**Files:** [scoring.py](file:///d:/Projects/image-scoring-backend/modules/scoring.py), [tagging.py](file:///d:/Projects/image-scoring-backend/modules/tagging.py), [clustering.py](file:///d:/Projects/image-scoring-backend/modules/clustering.py), [selection_runner.py](file:///d:/Projects/image-scoring-backend/modules/selection_runner.py)

The `is_running` boolean on most runners is read by the `JobDispatcher._any_runner_busy()` method (from the dispatcher thread) and written by the runner's own background thread — without synchronization. `ScoringRunner` properly uses a `_start_lock` for `start_batch`, but all other runners (Tagging, Clustering, Selection, BirdSpecies, Metadata, Indexing) set `self.is_running = True` and `self.is_running = False` without any lock.

```python
# TaggingRunner.start_batch — no lock
if self.is_running:
    return "Error: Already running."
self.is_running = True  # TOCTOU gap
```

While CPython's GIL makes individual attribute reads/writes atomic, the check-then-act pattern (`if self.is_running: ... self.is_running = True`) is a classic **TOCTOU race**. Two near-simultaneous `start_batch` calls could both pass the `if` guard.

> [!CAUTION]
> The `JobDispatcher` serializes via `_dispatch_lock`, so in practice this only fires when `start_batch` is called from both the API *and* the dispatcher at the same time — unlikely but possible when a user clicks "Start" while the dispatcher is dequeuing.

**Recommendation:** Add a `threading.Lock` to every runner's `start_batch` entry point, matching the pattern `ScoringRunner` already uses.

---

### C-3. `db/__init__.py` monkey-patches `sys.modules` with a different module

**File:** [db/\_\_init\_\_.py](file:///d:/Projects/image-scoring-backend/modules/db/__init__.py#L67-L68)

```python
_sys.modules[__name__] = _db_legacy
```

This replaces the `modules.db` package reference in `sys.modules` with `modules.db_legacy` — a 12,500-line monolith. While it works, it causes:
- **Import confusion:** `from modules.db import X` and `from modules.db_legacy import X` are the same object, but IDEs and linters treat them as different.
- **Namespace pollution:** Any new function added to `db_legacy.py` is automatically exposed on `modules.db` without explicit re-export.
- **Fragile boot order:** The `_ensure_new_helpers()` call at import time can fail if `db_legacy` hasn't finished defining `get_connector()`.

> [!WARNING]
> This is a known tech-debt item from the Firebird→PostgreSQL migration. The audit flags it as Critical because it's the single biggest obstacle to modularization.

**Recommendation:** Begin extracting `db_legacy.py` into `modules/db/` submodules (e.g., `queries.py`, `migration.py`, `connection.py`) and replace the `sys.modules` hack with explicit re-exports.

---

## 🟠 High Severity Findings

### H-1. Duplicate `_thread` assignment in `JobDispatcher.__init__`

**File:** [job_dispatcher.py](file:///d:/Projects/image-scoring-backend/modules/job_dispatcher.py#L39-L40)

```python
self._thread: Optional[threading.Thread] = None
self._thread: Optional[threading.Thread] = None  # ← duplicate
```

While harmless at runtime, this is a clear copy-paste error and a code smell indicating insufficient review coverage.

---

### H-2. `engine.py` sends duplicate sentinel to `scoring_queue`

**File:** [engine.py](file:///d:/Projects/image-scoring-backend/modules/engine.py#L246-L257)

```python
if not self.stop_event.is_set():
    prep_queue.put(None)    # sentinel → PrepWorker

prep_worker.join()
scoring_queue.put(None)     # safety sentinel (line 253)
# PrepWorker ALSO puts None on scoring_queue when it gets None
```

The comment says "Safety incase prep didn't?" — but `PrepWorker` *does* forward sentinels. This means `ScoringWorker` will receive **two** `None` sentinels. If `ScoringWorker`'s run loop exits on the first, the second stays in the queue. If the same `BatchImageProcessor` instance is reused (it isn't currently, but there's no guard), the stale sentinel could cause the next run to exit immediately.

**Recommendation:** Remove the redundant `scoring_queue.put(None)` on line 253, or add a comment explaining why it's deliberately defensive.

---

### H-3. `process_list` has a blocking spin-wait on `prep_queue.full()`

**File:** [engine.py](file:///d:/Projects/image-scoring-backend/modules/engine.py#L348-L354)

```python
try:
    prep_queue.put(job, timeout=2.0)
    while prep_queue.full() and not self.stop_event.is_set():
        time.sleep(0.1)    # spin-wait after already enqueued!
except KeyboardInterrupt:
    ...
```

After `put(job, timeout=2.0)` succeeds (the job is already enqueued), the code enters a `while prep_queue.full()` spin-wait. This delays enqueueing the *next* job but doesn't help processing — the job is already in the queue. Contrast with `process_directory`, which correctly retries `put()` in a `while` loop without the post-enqueue spin.

**Recommendation:** Replace with the same retry-loop pattern used in `process_directory`.

---

### H-4. `config.py` re-reads JSON from disk on every call

**File:** [config.py](file:///d:/Projects/image-scoring-backend/modules/config.py#L46-L52)

`load_config()` reads and parses both `config.json` and `environment.json` from disk on every invocation. `get_config_section()` and `get_config_value()` call `load_config()`. These are called thousands of times during batch processing (e.g., inside `_cluster_images_impl` which calls `config.get_config_section('clustering')` three times in succession, lines 488-495).

**Recommendation:** Add a simple in-memory cache with a TTL or file-modification-time check. The `save_config_value` path already has the file handle — it can invalidate the cache.

---

### H-5. Tagging runner doesn't set `daemon=True` on its thread

**File:** [tagging.py](file:///d:/Projects/image-scoring-backend/modules/tagging.py#L424)

```python
self._thread = threading.Thread(target=target)  # not daemon
```

Most other runners (Selection, BirdSpecies, Maintenance) use `daemon=True`. The scoring runner also omits it. Non-daemon threads prevent the Python process from exiting cleanly if the runner is still active during shutdown, which can cause hanging on `Ctrl-C` or during Docker container stops.

**Recommendation:** Set `daemon=True` on all runner threads, and rely on the graceful shutdown logic (stop events, `safe_runner_thread`) for clean termination.

---

### H-6. `clustering.py` uses `import datetime` in method scope but also imports at module level

**File:** [clustering.py](file:///d:/Projects/image-scoring-backend/modules/clustering.py#L423-L467)

Both `cluster_images` and `_cluster_images_impl` have `import datetime` and `import json` at the top of their method bodies, despite `datetime` already being imported at the module level (line 8). This shadowing is confusing and suggests copy-paste code drift.

---

### H-7. `_get_image_time` uses `datetime.datetime` but imports only `datetime` (the module)

**File:** [clustering.py](file:///d:/Projects/image-scoring-backend/modules/clustering.py#L373)

```python
return datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S").timestamp()
```

Line 8 has `from datetime import datetime`, making `datetime` the *class*, not the module. But line 373 uses `datetime.datetime.strptime(...)`, which would fail with `AttributeError: type object 'datetime' has no attribute 'datetime'`. 

However, line 423 (`import datetime`) in `cluster_images` re-binds `datetime` to the *module* in the local scope. This means `_get_image_time` works **only** because it's called after `cluster_images` has executed `import datetime` — which changes the module-level binding. This is extremely fragile.

> [!WARNING]
> If `_get_image_time` is ever called standalone (e.g., in tests), it will crash.

---

### H-8. No input validation on `rating` query param splitting

**Files:** [api.py](file:///d:/Projects/image-scoring-backend/modules/api.py#L368), [api.py](file:///d:/Projects/image-scoring-backend/modules/api.py#L423)

```python
rating_filter = [int(r) for r in rating.split(",")] if rating else None
```

If a client sends `?rating=abc`, this raises an unhandled `ValueError` that propagates as a 500 Internal Server Error rather than a 400 Bad Request. This pattern appears in both `_images_list_payload` and `_image_neighbors_payload`.

**Recommendation:** Wrap in a try/except and raise `HTTPException(status_code=400)`.

---

## 🟡 Medium Severity Findings

### M-1. `db_legacy.py` is 12,592 lines / 500 KB

This file is the single largest contributor to cognitive load. It contains:
- Database initialization and migration DDL
- Connection pooling and Firebird/PostgreSQL proxies
- SQL dialect translation (regex-based)
- ~200 query/mutation functions
- Caching logic
- Backup utilities
- WSL/Docker connection resolution

> [!IMPORTANT]
> This is the highest-priority refactoring target. Even extracting 3-4 coherent subsystems (connection management, query translation, folder operations, job operations) would dramatically improve navigability.

### M-2. `api.py` is 7,630 lines / 327 KB

Similarly oversized. Contains 100+ route handlers, request models, helper functions, and global runner references.

### M-3. `mcp_server.py` is 105 KB with extensive global state

Uses 6 `global` declarations for runner references and DB availability flags. The global runner references are set via `set_runners()`, making the module's state dependent on external initialization order.

### M-4. Inconsistent logging: `logging` vs `logger` usage

Multiple files (e.g., `clustering.py`) mix `logging.info()` (root logger) and `logger.info()` (module-specific logger). This causes some messages to bypass module-level log filtering.

```python
# Same file, different patterns:
logging.info(f"Created feature cache directory: {self.cache_dir}")  # root logger
logger.info("[Clustering] Computing embeddings...")                  # module logger
```

### M-5. `np.load(..., allow_pickle=True)` in clustering feature cache

**File:** [clustering.py](file:///d:/Projects/image-scoring-backend/modules/clustering.py#L64)

`allow_pickle=True` is necessary for the `.item()` call but is a well-known deserialization risk. If the cache file is tampered with, arbitrary code execution is possible.

**Recommendation:** Migrate the feature cache to a safer format (e.g., HDF5, or separate `.npy` files keyed by hash).

### M-6. Redundant `from modules import config` inside methods

`clustering.py` imports `from modules import config` at the top of the file (line 11) but also has `from modules import config` inside `_cluster_images_impl` (line 467) and `extract_features` (line 278). These are no-ops but add noise.

### M-7. `KeywordScorer.predict` always returns `top_k` keywords regardless of `threshold`

**File:** [tagging.py](file:///d:/Projects/image-scoring-backend/modules/tagging.py#L286-L293)

The `threshold` parameter (default 0.2) is accepted but never used in filtering:

```python
valid_results = []
for i, score in enumerate(probs_list):
    valid_results.append((target_keywords[i], score))  # threshold not checked
```

All keywords are always included before sorting and slicing to `top_k`. The `threshold` parameter is dead code.

### M-8. f-string logging throughout (performance anti-pattern)

Many modules use f-string formatting in log calls:
```python
logger.info(f"Found {len(files)} images to process.")
```

When the log level is higher than INFO, the f-string is still evaluated (string formatting + interpolation cost). Use lazy `%`-style formatting:
```python
logger.info("Found %d images to process.", len(files))
```

This is especially impactful in hot paths like `extract_features` and the scoring pipeline.

### M-9. `_select_best_image` can return `None` for non-empty lists

**File:** [clustering.py](file:///d:/Projects/image-scoring-backend/modules/clustering.py#L116-L117)

```python
if not img_ids:
    return None
```

Callers (line 751, 990) don't guard against `None`. If `img_ids` is unexpectedly empty (e.g., filtered away), `best_id = None` flows into `create_stacks_batch`, potentially creating a stack with `best_image_id = NULL`.

### M-10. `engine.py` comments reference stale design decisions

Lines 201-217 contain extended stream-of-consciousness comments about passing `job_id`:
```python
# HACK: Retrieve job_id from somewhere or update signature?
# Update signature is better but requires changing base class or calls.
# Let's check `scoring.py` again...
```

These should be cleaned up — the signature was eventually updated to accept `job_id`.

### M-11. `config.py` `save_config_value` silently fails on write errors

**File:** [config.py](file:///d:/Projects/image-scoring-backend/modules/config.py#L71-L75)

```python
try:
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
except Exception as e:
    logging.error(f"Failed to save config: {e}")
    # No return value, no exception — caller assumes success
```

The function has no return value; callers can't tell if the save succeeded.

### M-12. `_parse_queue_payload` double-parses JSON strings

**File:** [job_dispatcher.py](file:///d:/Projects/image-scoring-backend/modules/job_dispatcher.py#L143-L146)

```python
parsed = json.loads(raw_payload)
if isinstance(parsed, str):
    parsed = json.loads(parsed)  # double-encoded JSON
```

This suggests some callers store double-encoded JSON. The root cause should be fixed rather than compensating at the consumer.

### M-13. Multiple config reads in succession without caching

**File:** [clustering.py](file:///d:/Projects/image-scoring-backend/modules/clustering.py#L487-L495)

```python
if distance_threshold is None:
    clustering_config = config.get_config_section('clustering')
    distance_threshold = clustering_config.get('default_threshold', 0.15)
if time_gap_seconds is None:
    clustering_config = config.get_config_section('clustering')  # re-read
    time_gap_seconds = clustering_config.get('default_time_gap', 120)
if force_rescan is None:
    clustering_config = config.get_config_section('clustering')  # re-read again
    force_rescan = clustering_config.get('force_rescan_default', False)
```

Three separate reads of the same section, each triggering a full disk read and JSON parse.

### M-14. `_images_list_payload` fetches phase statuses without error handling

**File:** [api.py](file:///d:/Projects/image-scoring-backend/modules/api.py#L392)

`db.get_batch_image_phase_statuses(img_ids)` is called inside a try/except that catches `Exception`, but the phase status map is assumed to return a dict. If it returns `None`, `.get()` on line 395 would raise `AttributeError`.

---

## 🔵 Low Severity Findings

### L-1. Inconsistent daemon thread flags

| Runner | `daemon=True`? |
|--------|----------------|
| ScoringRunner | ❌ |
| TaggingRunner | ❌ |
| SelectionRunner | ✅ |
| BirdSpeciesRunner | ✅ |
| MaintenanceRunner | ✅ |
| IndexingRunner | ❌ |
| MetadataRunner | ❌ |
| ClusteringRunner | ❌ |
| PipelineOrchestrator | ✅ |
| JobDispatcher | ✅ |
| StallDetector | ✅ |

### L-2. `sqlite3` imported but unused in `clustering.py` (line 5)

### L-3. `uuid` imported inside loop body in `clustering.py` (line 725)

`import uuid` is inside the per-folder loop rather than at the top of the method or module.

### L-4. Inconsistent error message patterns across runners

Some runners use `"Error: Already running."`, others use `"Already running"`, others return early silently.

### L-5. `_to_win_path` converts all `/` to `\\` even for non-WSL paths

**File:** [db_legacy.py](file:///d:/Projects/image-scoring-backend/modules/db_legacy.py#L827)

The final `return p_str.replace("/", "\\")` converts any path's forward slashes to backslashes, even on Linux. This is only called from WSL-specific code paths, but the function name doesn't convey that.

### L-6. Dead `import glob` reference in `engine.py` (line 90)

```python
# import glob # No longer used
```

Should be fully removed rather than commented out.

### L-7. `_firebird_path_is_production_scoring_file` uses `re.fullmatch` with `\Z`

The `\Z` anchor inside `re.fullmatch` is redundant — `fullmatch` already anchors to end of string.

### L-8. `TaggingRunner._run_batch_internal` has nested `import textwrap` inside a conditional block (lines 637, 647)

This import is repeated twice within the same method body.

### L-9. `CaptionGenerator.generate()` imports `from modules import config` inside the method (line 344)

Config is already imported at the module level in other parts of the same file.

### L-10. `_any_runner_busy` uses `any()` with a list literal

**File:** [job_dispatcher.py](file:///d:/Projects/image-scoring-backend/modules/job_dispatcher.py#L507)

```python
return any([...])  # list is eagerly evaluated
```

Should be `any((...))` (generator) for short-circuit evaluation.

### L-11. `process_directory` constructs `extensions` as a function call result but treats it as a set

The `discovery_extensions()` function returns extensions, but the code builds a list then deduplicates with `set()`. Could be simplified.

### L-12. Magic numbers in `score_normalization.py` config cache TTL

The config cache uses `global _config_cache` without any documented TTL or invalidation policy.

---

## ⚪ Informational Observations

### I-1. The project has ~71 Python files in `modules/` plus 6 subdirectories

This is a reasonable structure for the functionality scope, but the size distribution is extremely skewed: `db_legacy.py` (500 KB), `api.py` (327 KB), and `mcp_server.py` (106 KB) account for ~60% of all code. The remaining 68 files average ~13 KB.

### I-2. Strong use of defensive programming patterns

The `safe_runner_thread` wrapper, circuit breaker on model loading, and stale-phase reconciliation at startup are well-designed resilience patterns. The pipeline orchestrator's drain-tick mechanism for stragglers is particularly thoughtful.

### I-3. Good separation of concerns in pipeline workers

The `PrepWorker` → `ScoringWorker` → `ResultWorker` chain in `pipeline.py` is a clean producer-consumer pipeline. The `ImageJob` dataclass cleanly carries state between stages.

### I-4. Config validation is comprehensive

`config.validate_config()` checks types, required fields per engine, path existence, and boolean constraints. This is well above average for a project of this size.

### I-5. The MCP server provides excellent observability

52 tools covering diagnostics, querying, monitoring, and maintenance is an impressive integration surface for AI-assisted debugging.

### I-6. Test infrastructure uses proper markers and environment guards

The `RUN_POSTGRES_TESTS` env var, `@pytest.mark.postgres`, and production-file guards in `get_db()` show good test hygiene for preventing accidental production data access.

---

## Prioritized Remediation Roadmap

### Phase 1 — Quick Wins (1-2 days)

| Item | Effort |
|------|--------|
| C-1: Fix `disconnect_sync` thread safety | 30 min |
| H-1: Remove duplicate `_thread` assignment | 5 min |
| H-8: Add `try/except ValueError` on `rating` param | 15 min |
| L-2, L-3, L-6: Remove dead/misplaced imports | 15 min |
| M-10: Clean up stale `engine.py` comments | 15 min |
| M-7: Remove dead `threshold` param or implement it | 15 min |

### Phase 2 — Safety Hardening (3-5 days)

| Item | Effort |
|------|--------|
| C-2: Add start locks to all runners | 2 hrs |
| H-2: Remove duplicate sentinel in `engine.py` | 30 min |
| H-3: Fix `process_list` spin-wait pattern | 30 min |
| H-5: Standardize `daemon=True` across runners | 30 min |
| H-7: Fix `datetime` import shadowing in `clustering.py` | 30 min |
| M-5: Migrate feature cache away from `allow_pickle` | 2 hrs |

### Phase 3 — Architecture (2-4 weeks)

| Item | Effort |
|------|--------|
| C-3, M-1: Begin `db_legacy.py` modularization | 1-2 weeks |
| M-2: Extract API route groups into separate routers | 1 week |
| H-4, M-13: Add config caching layer | 1 day |
| M-3: Refactor MCP server global state to DI | 2 days |
| M-4: Standardize logging across all modules | 1 day |

---

## Appendix: File Size Distribution

| File | Lines | Size (KB) | Category |
|------|-------|-----------|----------|
| `db_legacy.py` | 12,592 | 500 | 🔴 Extreme |
| `api.py` | 7,630 | 327 | 🔴 Extreme |
| `mcp_server.py` | — | 106 | 🟠 Very Large |
| `clustering.py` | 1,159 | 53 | 🟡 Large |
| `db_postgres.py` | — | 54 | 🟡 Large |
| `tagging.py` | 947 | 42 | 🟡 Large |
| `indexing_runner.py` | — | 40 | 🟡 Large |
| `scoring.py` | 831 | 35 | Normal |
| `maintenance_runner.py` | — | 34 | Normal |
| `xmp.py` | — | 33 | Normal |
| `pipeline.py` | 641 | 30 | Normal |
| All others (57 files) | — | ~250 total | Normal |
