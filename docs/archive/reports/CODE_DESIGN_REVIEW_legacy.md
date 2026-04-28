# Comprehensive Code & Design Review Summary Report

**Date:** March 2, 2026

This document contains the consolidated Code and Design Review for both the **Vexlum Scoring system (Backend/Pipeline)** and the **electron-image-scoring (Frontend)** components.

---

## Part 1: Vexlum Scoring system (Backend/Pipeline)

### Project Overview
A sophisticated AI-powered digital asset management system for photographers. Multi-model scoring (MUSIQ, LIQE), multi-threaded pipeline, Gradio WebUI + FastAPI backend, Firebird SQL database, MCP integration for AI agent automation.
**Codebase**: ~14,350 LOC (modules) | 40 test files (~4,729 LOC) | Python 3.11

### Architecture Assessment

**Strengths:**
- Modular pipeline design (PrepWorker → ScoringWorker → ResultWorker) with queue-based communication
- Comprehensive MCP integration (17 tools)
- Intelligent backfilling avoids re-computation
- Good separation of concerns
- Cross-platform support (Windows, WSL2, Docker with GPU)
- Event-driven WebSocket for real-time updates

**Weaknesses:**
- Insufficient test coverage (~20%)
- Thread safety issues and race conditions
- Security vulnerabilities (SQL injection, path traversal, lacking auth)
- Exception handling relies heavily on bare `except` blocks
- Dependency management issues (unpinned/missing explicit declarations)

### Findings by Severity

#### CRITICAL
1. **SQL injection** via string interpolation in ORDER BY clauses (`db.py`).
2. **Path traversal** in `/api/raw-preview` and `/source-image` (`app.py`).
3. **Unauthenticated API** — all endpoints open.
4. **Raw SQL endpoint** accepts arbitrary queries.
5. **Thread safety** — shared `MultiModelMUSIQ` instance.
6. **Race condition** in DB upsert (check-then-insert).
7. **Score normalization** defaults missing scores to 0, corrupting composites.
8. **Missing `get_secret()` function** in `remote_scoring.py`.
9. **No rate limiting** on job submission endpoints.
10. **XMP sidecar XML injection** due to unescaped special chars.
11. **Hardcoded default DB password** "masterkey".
12. **TensorFlow CVE-2024-27314** — DoS via malformed image.

#### HIGH
- 50+ bare `except:` clauses.
- Completely missing pipeline, MCP, API, and DB consistency tests.
- Orphaned temp directories.
- I/O bottleneck during XMP writes blocking ResultWorker thread.
- `db.py` is a 3,600-line god module with duplicated query logic.
- Potential DB deadlocks and inconsistent path format handling.
- Debug statements left in production code.

#### MEDIUM
- Hardcoded CORS origins, missing explicit deps, unpinned package versions.
- Tight coupling (e.g., global EventManager, UI/Server setup).
- Missing health checks, structured error logging, and processing metrics.
- No retry logic for transient pipeline/DB failures.

### Recommendations (Backend)
1. **Security Hardening:** Add path validation, whitelist ORDER BY fields, upgrade TF, add API auth & rate limiting, remove raw SQL endpoints (or restrict).
2. **Testing:** Adopt pipeline integration tests, endpoint tests, and DB concurrency tests.
3. **Thread Safety:** Instantiate per-worker scorers, add explicit transaction isolation + lock timeouts.
4. **Error Handling:** Replace bare excepts, capture tracebacks, use structured logging.
5. **Architecture & Deps:** Split `db.py`, use PathManager, pin explicit dependencies.

---

## Part 2: electron-image-scoring (Frontend)

### Architecture Overview
Electron 40 + React 19 + Vite 7 + TypeScript 5.9 app with Firebird backend. Features image browsing with scoring/rating, stacking, folder navigation, RAW/NEF support, and real-time WebSocket updates from a Python API. MCP server provides debugging tools.
**Key files:** `electron/main.ts` | `electron/db.ts` | `electron/preload.ts` | `src/App.tsx` | `src/hooks/useDatabase.ts`

### Critical Issues
1. **No Database Connection Pooling:** Every query creates/detaches a connection. Causes 50+ handshakes per paginated scroll action.
2. **No Test Coverage:** Zero test files for complex logic and hooks. No mocks.
3. **Monolithic App.tsx (~450 lines):** Needs decomposition into context providers and feature hooks.
4. **Inconsistent IPC Error Handling:** Frontend unable to reliably distinguish errors from empty results.
5. **Unbounded Image Array Growth:** Loaded pages append to memory forever, causing memory bloat with 10k+ images.

### High Severity
6. **WebSocket Reconnection:** No max retries or exponential backoff.
7. **NEF Buffer Serialization:** Multi-MB binary buffers serialized as slow JSON number arrays instead of IPC native buffers.
8. **Race Conditions in State Hooks:** Stale closures, recreated `useEffect` string dependencies, and conflicting state updates.
9. **Excessive `any` Types:** Weak typing across critical `useState` and IPC updates.

### Medium & Low Severity
- **UX & Styling:** All inline styles, no design system, massive prop drilling. Missing loading UI/error boundaries, and fixed non-responsive layout. Accessibility issues.
- **Security:** `media://` protocol handler has path traversal risks.
- **Tech Debt:** Outdated `node-firebird` driver, generic/duplicated hook logic, minimal MCP server tools.

### What's Done Well (Frontend)
- Security fundamentals (`contextIsolation`, no `nodeIntegration`).
- Virtual scrolling handles large image sets effectively.
- WebSocket integration and RAW file support.
- Stack caching and Zustand for notifications.

### Recommended Actions (Frontend)
1. Add connection pooling to `electron/db.ts`.
2. Standardize IPC error envelope (`{ ok, data, error }`).
3. Extract `App.tsx` into context providers + feature hooks.
4. Add React error boundary + user-facing error states.
5. Set up Vitest with IPC mocks, and test critical hooks.

---

## Part 3: Remediation Status (March 3, 2026)

The following fixes were implemented against the backend findings above.

### Critical Findings — Fixed

| # | Finding | Fix | Files Changed |
|---|---------|-----|---------------|
| 1 | SQL injection in ORDER BY | Added `ALLOWED_SORT_COLUMNS` whitelist + `_validate_sort()` helper | `modules/db.py` |
| 2 | Path traversal in endpoints | Added `_validate_file_path()` — rejects `..`, checks against allowed roots | `modules/ui/app.py` |
| 4 | Raw SQL endpoint accepts arbitrary queries | Added `_SQL_FORBIDDEN_PATTERNS` regex blocking DML keywords + semicolons | `modules/ui/app.py` |
| 7 | Score normalization defaults missing to 0 | Re-normalize weights over only present models in `weighted_sum()` | `modules/score_normalization.py` |
| 8 | Missing `get_secret()` function | Implemented — reads from `secrets.json` | `modules/config.py` |
| 9 | No rate limiting | Added in-memory rate limiter (10 req/min) on scoring/tagging start | `modules/ui/app.py`, `modules/api.py` |
| 10 | XMP XML injection | Validated: ElementTree API auto-escapes; added label value whitelist | `modules/xmp.py` |
| 11 | Hardcoded DB password | Now checks `FIREBIRD_PASSWORD` env var first; warns if using default | `modules/db.py` |
| 12 | TensorFlow CVE-2024-27314 | Upgraded `tensorflow-cpu` to `>=2.15.1` | `requirements.txt` |

### High Findings — Fixed

| Finding | Fix | Files Changed |
|---------|-----|---------------|
| 50+ bare `except:` clauses | Replaced with specific types (`ValueError`, `TypeError`, `OSError`, `Exception`) | 15 files across `modules/` |
| Debug `print()` in production | Converted all to `logger.debug()` / `logger.warning()` | `modules/db.py` |
| Unpinned dependency versions | Pinned `rawpy`, `imageio`, `scikit-learn`, `mcp` with version bounds | `requirements.txt` |

### New Tests Added

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_db_security.py` | 8 | Sort validation, SQL injection vectors |
| `tests/test_api_security.py` | 8 | SQL restriction regex, path traversal, rate limiting |
| `tests/test_config_secrets.py` | 4 | `get_secret()` — missing file, valid file, bad JSON, missing key |
| `tests/test_score_normalization.py` | 7 | Missing models, empty scores, partial scores, re-normalization |
| **Total** | **27** | All passing |

### Remaining (Not Yet Fixed)

| # | Finding | Status | Notes |
|---|---------|--------|-------|
| 3 | Unauthenticated API | **Open** | Requires architectural decision on auth method (API key, OAuth, etc.) |
| 5 | Thread safety — shared scorer | **Open** | Requires performance testing of per-worker instantiation |
| 6 | Race condition in DB upsert | **Open** | Needs Firebird 4.0+ MERGE or app-level locking |
| — | `db.py` god module split | **Open** | Refactoring effort — lower priority |
| — | I/O bottleneck in XMP writes | **Open** | Needs async write queue design |
| — | Missing pipeline integration tests | **Open** | Requires mock infrastructure for model inference |

---

## Conclusion
Both the backend and frontend systems demonstrate strong core capabilities (intelligent backfilling, virtualized rendering, comprehensive pipelines) but share deep similarities in technical debt: a lack of testing infrastructure, tight coupling/god-files (`db.py`, `App.tsx`), scaling risks (connection limits, unbounded memory arrays), and scattered security vulnerabilities (path traversal, SQL injection, missing auth). Resolving these foundational stability and security issues should take priority over new feature development.

The March 3 remediation addressed 9 of 12 critical findings, eliminated all bare `except:` clauses, pinned dependencies, and added 27 new security/normalization tests. Three critical items (API auth, thread safety, DB race conditions) remain open as they require architectural decisions.
