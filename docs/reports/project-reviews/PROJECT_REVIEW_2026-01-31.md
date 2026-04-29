## Project review (code + design)

**Project**: `image-scoring`  
**Date**: 2026-01-31  
**Scope**: Python WebUI/API + scoring/tagging pipeline + Firebird DB layer + scripts/tests + Windows WPF viewer.

### Executive summary
- **Whatâ€™s strong**: clear â€œprep â†’ score â†’ persistâ€ pipeline concept; good documentation footprint; useful DB-first workflow; thoughtful cross-platform path resolution helpers; XMP sidecar strategy to keep edits non-destructive.
- **Whatâ€™s risky**: the WebUI/API is currently **unauthenticated and exposed** by default; multiple endpoints can serve **arbitrary local files** by user-supplied path; DB layer has **hardcoded credentials and paths**; test suite is mostly **environment-dependent scripts** rather than portable assertions.

### Severity key
- **P0 (Critical)**: security exposure / data loss / obvious runtime failure
- **P1 (High)**: correctness, reliability, or maintainability issue likely to bite soon
- **P2 (Medium)**: suboptimal patterns; tech debt; performance issues
- **P3 (Low)**: style, polish, doc consistency

---

## Architecture overview (as implemented)

### Runtime shape
- **Entry point**: `webui.py` builds a FastAPI app (OpenAPI docs), mounts Gradio Blocks at `/`, and adds custom endpoints.
- **UI orchestrator**: `modules/ui/app.py:create_ui()` initializes DB/config, creates `ScoringRunner` + `TaggingRunner`, builds tabs, sets a periodic status poll.
- **Batch processing pipeline**: `modules/engine.py:BatchImageProcessor` uses three threaded workers defined in `modules/pipeline.py`:
  - **PrepWorker**: hashing, dedup/path updates, thumbnails, RAW-to-JPEG conversion staging
  - **ScoringWorker**: LIQE + TF models execution
  - **ResultWorker**: DB upsert, metadata write (XMP/embedded), temp cleanup
- **DB layer**: `modules/db.py` is the central data access module; it wraps `firebird-driver` to emulate some sqlite-like ergonomics.
- **WPF viewer**: `ImageGalleryViewer/` reads the Firebird DB and provides a native browsing experience.

### Boundary notes
Right now, â€œboundariesâ€ are **mostly by convention**. For example:
- `modules/ui/app.py` contains API endpoints (`/api/query`, `/source-image`, `/api/raw-preview`) in addition to UI wiring.
- `modules/db.py` mixes connection concerns, SQL dialect adaptation, schema management, and business queries.
- `modules/pipeline.py` contains both orchestration and business logic (dedup/path relocation, metadata writes).

---

## Findings (prioritized)

### P0 â€” Critical

- **Unauthenticated network exposure by default**
  - **Where**: `webui.py` runs Uvicorn with `host="0.0.0.0"`.
  - **Why it matters**: your UI and API are reachable from other machines on the network, with no auth.
  - **Fix**:
    - Default bind to `127.0.0.1` for dev.
    - Add an explicit `--host` / config option for LAN exposure.
    - Add auth (API key at minimum) before allowing `0.0.0.0`.

- **Arbitrary file read / path traversal via file-serving endpoints**
  - **Where**: `modules/ui/app.py` endpoints:
    - `GET /source-image?path=...`
    - `GET /api/raw-preview?path=...`
    - Many API endpoints validate only with `os.path.exists()` (see `modules/api.py` start handlers too).
  - **Why it matters**: a user (or attacker on LAN) can request any file the process can read (including outside your photo roots), as long as it exists.
  - **Fix**:
    - Implement **centralized path policy**: resolve + normalize + enforce â€œmust be under allowed rootsâ€ (e.g., configured photo roots + thumbnails dir).
    - Reject traversal (`..`) and symlink escapes.
    - Prefer streaming responses and add file-size caps.

- **Hardcoded Firebird credentials and WSL/Windows hardcoded paths**
  - **Where**: `modules/db.py`:
    - `connect(dsn, user='sysdba', password='masterkey')`
    - WSL fallback DB path and Firebird EXE path are hardcoded to `/path/to/image-scoring\...`
  - **Why it matters**: default credentials are well-known; hardcoded paths break portability and are dangerous for anyone running this outside your machine.
  - **Fix**:
    - Use env vars (e.g., `ISC_USER`, `ISC_PASSWORD`, `ISC_DB_PATH`, `FIREBIRD_HOST`) and fail fast if password not set in â€œnon-devâ€ mode.
    - Move all path assumptions into config with sane defaults.

- **Duplicate `ScoringRunner.__init__` overrides earlier init**
  - **Where**: `modules/scoring.py` defines `def __init__(self):` twice (the second overwrites the first).
  - **Why it matters**: dead code / confusion; if the two ever diverge, behavior will silently change.
  - **Fix**: delete the first definition; keep a single initializer.

- **`modules/utils.py` has a duplicated `except` block (syntax / correctness issue)**
  - **Where**: `modules/utils.py:get_image_creation_time()` shows two consecutive `except Exception:` blocks after the PIL EXIF attempt.
  - **Why it matters**: at best this is unreachable/duplicated logic; at worst it indicates an edit/merge mistake and is a red flag for runtime correctness.
  - **Fix**: collapse into one `except` and add a minimal unit test for this function.

- **Raw SQL endpoint is too permissive**
  - **Where**: `POST /api/query` in `modules/ui/app.py` only checks `query.strip().upper().startswith("SELECT")`.
  - **Why it matters**: â€œSELECT-onlyâ€ checks are bypassable in practice; also it enables data exfiltration and expensive queries.
  - **Fix options**:
    - Remove this endpoint in non-debug builds.
    - Or restrict it to a curated set of allowed queries.
    - Add query length/time limits and block comments/stacked statements.

### P1 â€” High

- **DB SQL dialect translation hook exists but does nothing**
  - **Where**: `modules/db.py` `FirebirdCursorProxy._translate_query()` contains comments for LIMIT/OFFSET conversion but currently returns `query` unchanged.
  - **Why it matters**: itâ€™s misleading and will cause subtle breakages when sqlite-ish queries sneak in.
  - **Fix**: either implement the translation (including parameter re-ordering), or delete the hook and enforce â€œFirebird-native SQL onlyâ€.

- **Config loading is cwd-dependent and fails silently**
  - **Where**: `modules/config.py` uses `CONFIG_FILE = "config.json"` and returns `{}` on missing/failed read.
  - **Why it matters**: running from a different working directory (scripts, MCP, service) changes behavior without making it obvious.
  - **Fix**:
    - Resolve config path relative to project root.
    - Validate config schema; on missing keys, log clearly with defaults.

- **UI module owns API endpoints (mixed responsibilities)**
  - **Where**: `modules/ui/app.py` includes `/api/query`, `/source-image`, `/api/raw-preview`.
  - **Why it matters**: makes the system harder to secure and test; pushes â€œserverâ€ concerns into the UI layer.
  - **Fix**: move these into `modules/api.py` (or a `modules/files_api.py`) with shared validation.

- **Threading model is fragile / stop behavior is ad-hoc**
  - **Where**: `modules/engine.py` manually injects `current_job_id` and pushes extra sentinels (`scoring_queue.put(None)` â€œsafetyâ€) after joins.
  - **Why it matters**: can cause early worker termination or deadlocks when queues are full; makes pipeline evolution risky.
  - **Fix**:
    - Establish a single sentinel protocol.
    - Consider `queue.join()` + task_done discipline, or explicit worker lifecycle manager.

- **Logging + error handling are inconsistent**
  - **Where**: many modules mix `print()`, bare `except: pass`, and structured logging.
  - **Why it matters**: hard to diagnose production issues; security risk if exceptions leak internal details to clients.
  - **Fix**:
    - Use module loggers consistently.
    - For API errors: return generic messages by default; keep detailed logs server-side.

### P2 â€” Medium

- **Portability / OS assumptions spread across code**
  - **Where**: multiple places do WSL/Windows path conversion inline (e.g., `modules/scoring.py` has its own WSL conversion logic in addition to `modules/utils.py`).
  - **Why it matters**: conversion bugs and inconsistent behavior.
  - **Fix**: â€œsingle source of truthâ€ path resolver + tests; remove ad-hoc conversions.

- **Performance hotspots likely for large libraries**
  - **Where**:
    - hashing large files (`utils.compute_file_hash`) during prep
    - per-image DB commits in `ResultWorker`
    - on-demand RAW preview generation at request time
  - **Fix ideas**:
    - make hashing optional / cached
    - batch DB operations or reduce commits
    - cache previews with TTL

- **HTML generation and potential XSS concerns**
  - **Where**: `modules/ui_tree.py` builds HTML strings from folder names/paths.
  - **Why it matters**: unexpected characters in folder names could create HTML/JS injection in the Gradio front-end.
  - **Fix**: HTML-escape all interpolated text (name/path) and avoid embedding raw values in `onclick` strings.

### P3 â€” Low

- **Docs and metadata polish**
  - **Where**:
    - `webui.py` FastAPI contact URL is a placeholder.
    - Some internal comments are duplicated (e.g., repeated â€œVersion identifierâ€ in `run_all_musiq_models.py`).
  - **Fix**: small cleanup for credibility and maintainability.

---

## Test suite review

### Current state
- Tests are a mix of **unit**, **integration**, and **system environment checks**, but they live side-by-side and often behave like runnable scripts.
- Many tests have **hardcoded local file paths** (e.g., `D:/Photos/...`) and therefore donâ€™t run on other machines.
- Many tests **print output** but donâ€™t assert expected behavior.

### Recommendations
- **Standardize on pytest** and add:
  - `pytest.ini` with markers: `gpu`, `firebird`, `wsl`, `integration`, `system`
  - `tests/conftest.py` with fixtures for:
    - temp output dirs
    - synthetic images
    - optional â€œrequires GPUâ€ detection
- Split tests into:
  - `tests/unit/`
  - `tests/integration/`
  - `tests/system/`

---

## WPF viewer review (ImageGalleryViewer)

### Strengths
- Sensible MVVM foundation, good Windows-native integration features.

### Key issues
- **Hardcoded DB path and credentials** (same risks as Python side).
- **Threading/UI responsiveness risks**: synchronous file checks and fire-and-forget async patterns can freeze UI or swallow exceptions.
- **Low test coverage**: core ViewModel and DB service not covered.

---

## Suggested remediation plan

### Immediate (same day)
- **Secure defaults**:
  - bind to `127.0.0.1`
  - disable `/api/query` unless an explicit â€œdebug modeâ€ is enabled
- **Enforce safe path policy** for all file-serving endpoints.
- **Fix obvious correctness bugs**: duplicate `ScoringRunner.__init__`, duplicated `except` in `utils.py`.
- **Prevent accidental secrets commits**: ensure `secrets.json` is ignored and never committed.

### Short-term (1â€“2 weeks)
- Move API endpoints out of UI module; centralize validation.
- Introduce a config schema + validation; resolve config relative to project root.
- Replace hardcoded Firebird credentials/paths with env/config.
- Add pytest baseline + a handful of true unit tests (`utils.resolve_file_path`, `db` query helpers, the SQL translation decision).

### Medium-term (1â€“2 months)
- Add authentication/authorization (API key is fine to start).
- Add rate limiting, request size caps, and streaming file responses.
- Refactor pipeline lifecycle/stop semantics; add retries for transient DB failures.
- Add CI that runs unit tests on every change and runs integration/system tests behind explicit flags.

---

## Appendix: concrete â€œred flagâ€ file list
- `webui.py` (network binding, broad allowed paths)
- `modules/ui/app.py` (file-serving endpoints, raw SQL endpoint)
- `modules/api.py` (path checks, existence-only validation)
- `modules/db.py` (hardcoded creds, hardcoded paths, translate hook)
- `modules/scoring.py` (duplicate `__init__`, path conversion duplication)
- `modules/utils.py` (duplicated `except`, broad exception swallowing)
- `tests/*` (hardcoded paths, missing assertions, environment coupling)
- `ImageGalleryViewer/*` (hardcoded DB config, UI thread blocking)

## Related Documents

- [Docs index](../../README.md)
- [Project review (detailed)](PROJECT_REVIEW_DETAILED_2026-01-31.md)
- [Technical summary](../../architecture/technical-summary.md)
- [Project structure](../../architecture/project-structure.md)
- [TODO / roadmap](../../project/TODO.md)

