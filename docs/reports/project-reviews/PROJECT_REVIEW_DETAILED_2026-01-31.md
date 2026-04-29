## Project review deep dive (topic-by-topic)

**Project**: `image-scoring`  
**Date**: 2026-01-31  
**Refined**: Yes (Verified against codebase)  
**Companion doc**: `docs/reports/project-reviews/PROJECT_REVIEW_2026-01-31.md`

This document expands each topic individually with:
- **Problem**: what is wrong/suboptimal
- **Evidence**: where/how it shows up in this repo (verified)
- **Impact**: why you should care
- **Options**: multiple solution paths (quick â†’ robust)
- **Recommended approach**: what Iâ€™d do first
- **Implementation notes**: concrete changes/architecture ideas
- **Test/verification**: how to prove itâ€™s fixed

---

## 1) Unauthenticated network exposure by default (P0)

### Problem
The server binds to all interfaces by default (`0.0.0.0`), exposing the UI and API to the entire LAN with no authentication.

### Evidence
- **Verified**: `webui.py` calls `uvicorn.run(app, host="0.0.0.0", port=7860)` at the bottom of the file.
- There is no middleware or config option to change this default without editing code.

### Impact
- Anyone on the same network can access the UI to:
  - Start/stop scoring jobs.
  - Delete files (via stack management or db fix operations).
  - Execute arbitrary SQL queries via `/api/query`.
  - View any file on the system via traversal bugs (see Item 2).
- If this port is forwarded or exposed to the internet, it is a critical vulnerability.

### Options
- **Option A (fastest)**: Bind to `127.0.0.1` by default; require explicit config/env var for `0.0.0.0`.
- **Option B**: Keep `0.0.0.0` but add API key/Basic Auth middleware.
- **Option C**: Split â€œdev WebUIâ€ (localhost) from â€œdeployable APIâ€ (secure).

### Recommended approach
**Option A immediately**, then **Option B** for non-local usage.
See `webui.py` -> `uvicorn.run` call.

---

## 2) Path traversal / arbitrary file read via custom endpoints (P0)

### Problem
Custom API endpoints accept user-provided paths and serve files from disk with insufficient validation.

### Evidence
- **Verified**: `modules/ui/app.py` defines `/source-image` and `/api/raw-preview` which accept a `path` parameter.
- **Verified**: `modules/api.py` checks `os.path.exists(path)` but does not enforce that the path is within a safe directory (chroot/jail).
- Gradio's built-in blocklist/allowlist only protects Gradio components, not these custom FastAPI routes.

### Impact
- Arbitrary File Read: An attacker could request `../../../../Windows/win.ini` or sensitive configuration files.
- Combined with Item 1, this gives any LAN user read access to the server's filesystem.

### Options
- **Option A (Secure)**: Serve content by **IDs** instead of paths. Endpoints should look like `/api/image/{id}/preview`. The backend looks up the path from the DB.
- **Option B (Defensive)**: Implement a `validate_path(path)` function that:
  - Resolves `os.path.realpath(path)`.
  - Checks if it starts with one of the `ALLOWED_ROOTS` (e.g., config `directories`).
  - Rejects `..` components explicitly.

### Recommended approach
**Option A** is the robust architectural fix. **Option B** is a good immediate patch.

---

## 3) Hardcoded Firebird credentials + hardcoded paths (P0)

### Problem
The database layer uses default credentials (`sysdba`/`masterkey`) and assumes specific Windows paths for the Firebird client DLLs.

### Evidence
- **Verified**: `modules/db.py` contains `connect(dsn, user='sysdba', password='masterkey')`.
- **Verified**: `modules/db.py` constructs DSNs using hardcoded paths like `/path/to/image-scoring\...`.
- **Verified**: Hardcoded `FB_DLL` path pointing to `..\Firebird\fbclient.dll`.

### Impact
- **Security**: Default credentials are a well-known target.
- **Portability**: The application cannot run on a machine with a different directory structure (e.g., `C:\Apps\ImageScoring`).
- **WSL/Linux compatibility**: Hardcoded drive letters (`d:`) break cross-platform usage without messy "translation" hacks.

### Recommended approach
1. **Config**: Move credentials to `config.json` or environment variables (`FB_USER`, `FB_PASSWORD`).
2. **Paths**: Use relative paths from `__file__` or a configured `PROJECT_ROOT` instead of absolute Windows paths.
3. **Privileges**: Create a specific `image_scoring` user in Firebird with limited privileges, rather than using `SYSDBA`.

---

## 4) `secrets.json` handling / secrets hygiene (P0)

### Problem
`secrets.json` is present in the root directory and is not consistently ignored/managed, limiting safe collaboration.

### Evidence
- Check of `.gitignore` confirmed `secrets.json` is generally ignored, but the file exists in the workspace root `?? secrets.json`.
- Accidental `git add .` could commit it.

### Impact
- Credential leakage if the repo is pushed public.

### Recommended approach
- **Move**: Use `.env` for secrets (supported by many libraries like `python-dotenv`).
- **Git**: Ensure `*.json` (specifically `secrets.json`) is strictly ignored.
- **Pre-commit**: Add a pre-commit hook to scan for high-entropy strings or known secret filenames.

---

## 5) Duplicate `ScoringRunner.__init__` (P0 correctness)

### Problem
The `ScoringRunner` class defines `__init__` twice, with the second definition technically overwriting the first (though they are nearly identical).

### Evidence
- **Verified**: `modules/scoring.py` lines 27 and 34 both define `def __init__(self):`.
- The code sets `self.shared_scorer` and `self.current_processor` to `None` in both.
- The second `__init__` also initializes `self.is_running`, `self.log_history`, etc.

### Impact
- **Confusion**: It looks like a merge error or copy-paste mistake.
- **Correctness**: While python allows it (last one wins), it shows a lack of code review. The first `__init__` is dead code.

### Recommended approach
**Delete the first `__init__`** (lines 27-31).

---

## 6) `modules/utils.py` duplicated `except` block (P0 correctness)

### Problem
`get_image_creation_time` contains two identical consecutive `except` blocks.

### Evidence
- **Verified**: `modules/utils.py` lines 341-344:
  ```python
  except Exception:
      pass

  except Exception:
      pass
  ```
- This occurs in the PIL EXIF extraction block.

### Impact
- **Code Hygiene**: Redundant code that looks sloppy.
- **Debugging**: If the first `except` catches an error, the second is unreachable. If it was intended to catch distinct exceptions, it fails to do so.

### Recommended approach
Remove the duplicate block.

---

## 7) Raw SQL endpoint (`/api/query`) is unsafe (P0)

### Problem
The `/api/query` endpoint allows execution of arbitrary SQL, guarded only by a trivial `startswith("SELECT")` check.

### Evidence
- **Verified**: `modules/api.py` and `modules/ui/app.py` checks:
  ```python
  if not query.strip().upper().startswith("SELECT"):
      raise HTTPException(...)
  ```
- This regex-like check is easily bypassed or misunderstand complex queries (CTEs, subqueries).

### Impact
- **Data Exfiltration**: Any user can dump the entire database (users, keys, if any existed).
- **DoS**: A user can run `SELECT * FROM images CROSS JOIN images ...` to hang the DB.

### Recommended approach
**Remove this endpoint completely.**
If a "query tool" is needed for debugging, it should be:
1. Local-only (CLI).
2. Authenticated.
3. Or restricted to a set of predefined, parameterized queries (Reporting API).

---

## 8) Firebird translation hook (P1)

### Problem
`FirebirdCursorProxy._translate_query` exists to map SQLite queries to Firebird but currently just returns the query unchanged.

### Evidence
- **Verified**: `modules/db.py` contains the method with comments about "LIMIT/OFFSET" but no implementation.

### Impact
- **Bugs**: If code writes `LIMIT 10 OFFSET 5` (SQLite style), Firebird (which often uses `FIRST 10 SKIP 5` or `OFFSET/FETCH` depending on version) might reject it or behave unexpectedly if the driver doesn't handle it. The 5.0 driver likely handles standard SQL standard `OFFSET/FETCH`, but older styles break.

### Recommended approach
- **Option A**: Delete the proxy if the underlying driver handles standard SQL well.
- **Option B**: Implement the translation or use an ORM (SQLAlchemy) that handles dialect differences automatically.

---

## 9) Config loading is CWD-dependent (P1)

### Problem
`config.py` looks for `config.json` in the *current working directory*.

### Evidence
- **Verified**: `modules/config.py`: `CONFIG_FILE = "config.json"`.
- If you run `python main.py` from root, it works. If you run `python modules/db.py` from `modules/`, it fails silently (`load_config` returns `{}`).

### Impact
- **Fragility**: Scripts in `scripts/` or tests in `tests/` will fail to load config unless CWD is carefully managed.
- **Silent Failure**: The app runs with defaults instead of crashing, potentially masking misconfiguration.

### Recommended approach
Use absolute paths resolved relative to `__file__`:
```python
BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
```

---

## 10) UI/API splitting (P1)

### Problem
`modules/ui/app.py` defines API routes alongside UI setup.

### Evidence
- **Verified**: `app.py` creates `fastapi_app` and adds routes like `/source-image`.

### Impact
- **Tangled Architecture**: Hard to run the API without the UI (headless mode).
- **Testing**: Hard to test API endpoints without instantiating the heavy UI components.

### Recommended approach
- Move all FastAPI routes to `modules/api_routes.py` (or similar).
- Mount the API router into the main app.
- Let UI be just a consumer or a separate mount.

---

## 11) Pipeline lifecycle & Complexity (P1)

### Problem
`modules/engine.py` uses manual thread management with "sentinel" objects (`None`) pushed to queues to signal stopping.

### Evidence
- **Verified**: `process_directory` manually manages `prep_worker`, `scoring_worker`, `result_worker`.
- It pushes `None` to queues to stop workers.
- Complex logic handles `stop_event` vs sentinels, risking "hanging" threads if a sentinel is lost or an exception occurs before cleanup.

### Impact
- **Deadlocks**: If a worker crashes and doesn't consume the queue, the pipeline hangs.
- **Maintenance**: Hard to reason about concurrent states.

### Recommended approach
- Use a `ThreadPoolExecutor` or `ProcessPoolExecutor` for parallel tasks.
- If pipelines are needed, use a robust library or a simplified pattern (Producer-Consumer with `queue.join()`).

---

## 12) Logging and error handling (P1)

### Problem
Inconsistent error handling (print vs log vs crash) and lack of structured logging.

### Evidence
- **Verified**: `modules/utils.py` prints errors to stdout: `print(f"Error computing hash...: {e}")`.
- **Verified**: `modules/scoring.py` appends to a list `self.log_history`.
- **Verified**: `modules/db.py` logs to `logging.error`.

### Impact
- **Observability**: Hard to centralize logs.
- **Debugging**: `print` statements get lost in production environments (e.g., systemd services).

### Recommended approach
- Standardize on Python's `logging` module.
- Configure a central logger layout (JSON or consistent text format).
- Remove all `print` statements in modules.

---

## 13) Path conversion consistency (P2)

### Problem
Ad-hoc WSL<->Windows path conversion logic is scattered across modules.

### Evidence
- **Verified**: `modules/utils.py` contains `convert_path_to_local`.
- **Verified**: `modules/db.py` has its own logic for DSN strings.
- **Verified**: `modules/scoring.py` has lines 69-77 attempting to detect WSL and mangle paths manually.

### Impact
- **Bugs**: Fixing a path issue in one place doesn't fix it in others.
- **Maintenance**: Adding support for a new platform (e.g. Mac/Linux native) requires changes in 5+ files.

### Recommended approach
- Centralize ALL path logic in `modules/paths.py` (or existing `utils.py`).
- Use `pathlib` consistently.

---

## 14) Performance hotspots (P2)

### Problem
`upsert_image` commits the database transaction for *every single record*.

### Evidence
- **Verified**: `modules/db.py` line 1722 `conn.commit()` is called inside `upsert_image`.
- `upsert_image` is called once per image by the `ResultWorker`.

### Impact
- **Bottleneck**: SQLite/Firebird (and disk I/O) cannot handle thousands of commits per second. This limits processing speed to ~50-100 images/sec maximum, regardless of GPU speed.
- **Wear**: Excessive write amplification on SSDs.

### Recommended approach
- **Batching**: Isolate the database writer loop. Accumulate results in a buffer (e.g., 50 items or 1 second) and commit in a batch.
- **Architecture**: `ResultWorker` should just collect objects; a periodic `DBFlusher` task writes them.

---

## 15) UI Tree XSS risk (P2)

### Problem
The folder tree UI constructs HTML by concatenating strings without sanitization.

### Evidence
- **Verified**: `modules/ui_tree.py` line 41:
  `content = f'<span ...>ðŸ“ {name}</span>'`
- `name` comes from `os.path.basename`.

### Impact
- **XSS**: If a user has a folder named `<img src=x onerror=alert(1)>`, viewing the tree executes the JavaScript.
- While "Self-XSS" (local app), it's a bad practice and could be weaponized if the app is shared or scans a shared drive.

### Recommended approach
- **Sanitize**: Use `html.escape(name)`.
- **Best Practice**: Use a frontend framework (Gradio component) that handles rendering safely, rather than injecting raw HTML.

---

## 16) WPF viewer code (P1/P2)

*Not verified in this pass (code not in python source tree), but gathered from project context.*
- Issues with hardcoded paths/config mentioned in Item 3 apply here too.
- Needs to share the same config (JSON) as the Python app to avoid drift.

---

## 17) Test strategy (P1/P2)

### Problem
Lack of a cohesive test suite (`tests/` contains ad-hoc scripts).

### Evidence
- **Verified**: `tests/` folder exists but contains loose scripts like `test_culling.py` (12KB), `verify_pipeline.py` (2KB).
- No `conftest.py` or standard `pytest` structure observed ensuring all tests run together.
- Review doc notes "Minimal test coverage."

### Impact
- **Regression**: Changes (like the `ScoringRunner` refactor) can easily break features without warning.
- **Confidence**: "Refactoring" becomes dangerous.

### Recommended approach
- **Structure**: explicit `tests/unit` and `tests/integration` folders.
- **Tooling**: Use `pytest`.
- **CI**: Minimal GitHub Actions workflow to run valid unit tests on push.

## Related Documents

- [Docs index](../../README.md)
- [Project review (summary)](PROJECT_REVIEW_2026-01-31.md)
- [Technical summary](../../architecture/technical-summary.md)
- [Project structure](../../architecture/project-structure.md)
- [Uncommitted changes analysis](../UNCOMMITTED_CHANGES_ANALYSIS.md)

