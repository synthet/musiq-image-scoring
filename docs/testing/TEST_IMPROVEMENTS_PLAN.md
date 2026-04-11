# Test Coverage Improvements Plan

**Created**: 2026-03-15
**Branch**: `claude/analyze-test-coverage-Z29sW`
**Status**: Phase 1 complete — 5 new test modules committed

---

## Executive Summary

Analysis of the existing test suite (58 test files) revealed significant gaps in
unit-level coverage for five high-value modules. Phase 1 adds **1,252 lines** across
five new files, targeting the modules most critical to correct end-to-end behaviour
with no new test dependencies (all tests use existing patterns).

---

## Gap Analysis

### Previously Untested Areas

| Module | Gap | Risk |
|--------|-----|------|
| `modules/api.py` — REST endpoints | No unit tests; only queue/security tests existed | High — silent regressions in endpoint contracts |
| `modules/db.py` — core CRUD | Schema tests (`test_ddl.py`) existed; no CRUD round-trips | High — data corruption goes undetected |
| `modules/scoring.py` — `ScoringRunner` | No state-machine coverage | High — guard clauses bypassed silently |
| `modules/utils.py` — path helpers | No tests | Medium — WSL↔Windows path bugs |
| `modules/xmp.py` — sidecar I/O | No tests | High — XMP corruption, silent write failures |

---

## Phase 1 — Delivered (2026-03-15)

Five new test modules, all following existing conventions (`unittest.mock`,
`monkeypatch`, `FastAPI TestClient`, `@pytest.mark.*` guards):

### `tests/test_api_endpoints.py` (419 lines)

Covers all major REST routes via `FastAPI TestClient` with mocked runners and
DB helpers — zero ML models, zero real database.

| Area | Tests |
|------|-------|
| `GET /api/health` | No runners → all False; with runners → flags correct |
| `GET /api/schema` | Returns `api_version` field |
| `POST /api/score` | Guards (no runner, already running, path/folder validation) |
| `POST /api/score` | Successful job submission returns `job_id` |
| `GET /api/score/status` | Idle and running states |
| `POST /api/score/stop` | Delegation to runner.stop() |
| `POST /api/tag` | Same guard + success pattern as scoring |
| `POST /api/cluster` | Same guard + success pattern |
| `POST /api/fix-db` | Starts fix, returns job_id |
| `POST /api/score-single` | File-not-found, success |
| `GET /api/jobs` | Returns list |
| `POST /api/jobs/{id}/cancel` | Cancel, not-found |
| Rate limiting | 429 returned on excess requests |
| Auth guard | 401 for missing/wrong API key |

### `tests/test_db_core.py` (261 lines)

Firebird integration tests isolated to `scoring_history_test.fdb`.
Marked `@pytest.mark.db` and `@pytest.mark.firebird`.

| Area | Tests |
|------|-------|
| Folder CRUD | Create, idempotent re-create, nested paths |
| Image registration | `register_image_for_import`, `image_exists`, `find_image_id_by_path` |
| Job queue | `create_job`, `enqueue_job`, `update_job_status`, `request_cancel_job`, `dequeue_next_job` |
| Phase status | `set_image_phase_status` insert + upsert, `get_image_phase_statuses` |
| Stacks | `create_stack`, `create_stack_from_images`, `get_images_in_stack`, `dissolve_stack` |
| XMP table | `upsert_image_xmp` insert + update, `get_image_xmp`, missing-row → None |
| Folder listing | `get_all_folders` returns list |

### `tests/test_scoring_runner.py` (170 lines)

Pure unit tests — no ML model loading, no filesystem at scale.

| Area | Tests |
|------|-------|
| Initial state | `get_status()` returns Idle, 0/0, empty log |
| `start_batch` guards | Already running → error string |
| `start_batch` guards | Path not found → error + `is_running=False` |
| `start_batch` success | `resolved_image_ids` provided → thread started, `is_running=True` |
| `run_single_image` | Missing file → `(False, "File not found…")` |
| `fix_image_metadata` | Missing file → `(False, "File not found…")` |
| `start_fix_db` guard | Already running → error string |
| `stop()` | `current_processor=None` → no raise |
| `stop()` | Processor with `stop_event` → `stop_event.set()` called |

### `tests/test_utils_paths.py` (180 lines)

Pure Python — no external dependencies.

| Area | Tests |
|------|-------|
| `convert_path_to_local` | WSL→Windows (drive letter upper), already-Windows, Windows→WSL, backslash, native Linux unchanged |
| `convert_path_to_wsl` | Windows slash, backslash, already-WSL, native Linux |
| `compute_file_hash` | SHA-256, MD5, missing file → None |
| `resolve_file_path` | Strategy 1 (DB resolved_paths), Strategy 2 (as-is), Strategy 3 (converted), all-fail → None |
| `get_image_creation_time` | Missing file → datetime fallback, real file → datetime |

### `tests/test_xmp_sidecar.py` (222 lines)

Real file I/O via `tmp_path` — no mocking needed (pure XML).

| Area | Tests |
|------|-------|
| Path helpers | `get_xmp_path` extension swap, `xmp_exists` before/after write |
| Rating | Write, zero, invalid (−1/6), overwrite |
| Label | Round-trip, all 5 valid values (parametrized), invalid, `"None"` clears label |
| Pick/reject | Round-trip (1/−1/0 parametrized), invalid (2), missing-file → 0 |
| UUID fields | `write_image_unique_id` round-trip + empty → False, `write_burst_uuid` + `read_burst_uuid_from_xmp`, missing-file → None |
| Batch write | `write_culling_results` full, partial update preserves existing fields |
| Read missing file | `read_xmp` → `{rating: None, label: None, picked: None}` |
| `read_xmp_full` | pick_status field, burst_uuid field |
| Delete | `delete_xmp` removes file, `xmp_exists` → False |

---

## Phase 2 — Recommended Next Steps

### 2a. `modules/engine.py` — Pipeline orchestrator

**Gap**: No tests. This module coordinates scoring→tagging→clustering phase
transitions and is the highest-risk untested component.

**Approach**: Mock each runner (`ScoringRunner`, `TaggingRunner`,
`ClusteringRunner`) and the DB phase-gate helpers; verify:
- Phase ordering is respected (scoring must finish before tagging)
- Job failure stops the pipeline
- Cancellation propagates across runners

**Effort**: ~200 lines, no ML deps needed.

### 2b. `modules/config.py` — Configuration validation

**Gap**: `test_config_secrets.py` covers secret leakage; no tests for schema
validation, defaults, or invalid-value rejection.

**Approach**: Unit tests with temp `config.json` files; parametrize edge cases
(missing keys, wrong types, negative thresholds).

**Effort**: ~100 lines, zero deps.

### 2c. `modules/db.py` — Advanced queries

**Gap**: Phase 1 covered basic CRUD; no tests for:
- `get_images_for_scoring()` filter combinations (folder, status, limit)
- `get_scoring_history()` pagination
- `get_similar_images()` embedding distance queries
- Tag propagation (`_sync_image_keywords`, `_backfill_keywords`)

**Effort**: ~150 lines, requires `@pytest.mark.db firebird`.

### 2d. `modules/mcp_server.py` — MCP tool coverage

**Gap**: No tests beyond launch smoke test.

**Approach**: Use `fastmcp` test client or mock the tool registry; verify each
MCP tool returns the expected JSON shape.

**Effort**: ~120 lines, no ML deps.

### 2e. Parametrize existing tests more aggressively

Several tests use fixed values where parametrize would give broader coverage at
low cost:

- `test_scoring_runner.py`: parametrize `start_batch` over different job_id values
- `test_db_core.py`: parametrize phase codes (`"scoring"`, `"tagging"`, `"clustering"`)
- `test_api_endpoints.py`: parametrize bad-auth header variants

---

## Phase 3 — Long-term Hardening

| Item | Description |
|------|-------------|
| Coverage reporting | Add `pytest-cov` to dev requirements; track line coverage per module in CI |
| Mutation testing | Run `mutmut` or `cosmic-ray` on `modules/utils.py` and `modules/xmp.py` (pure functions, easiest to mutate) |
| Contract tests | Snapshot-test the `/api/schema` response so Electron frontend is warned of any contract break |
| DB fixture reset | Extend `conftest.py` with a function-scoped `clean_test_db` fixture to avoid inter-test state leakage in `test_db_core.py` |
| CI matrix | Add a GitHub Actions step that runs `pytest -m "not gpu and not ml and not firebird"` on every PR — currently no CI coverage runs |

---

## Marker Reference

| Marker | Use | Skip condition |
|--------|-----|---------------|
| `db` | Requires DB connection | No Firebird service |
| `firebird` | Requires Firebird client | `firebird-driver` not installed |
| `ml` | Requires TensorFlow/PyTorch | Models not installed |
| `gpu` | Requires CUDA GPU | No GPU present |
| `network` | Requires outbound internet | Offline environment |
| `sample_data` | Requires local image files | No sample data |
| `wsl` | WSL/Linux-specific | Native Windows |

---


## Canonical Baseline Commands (Backend + Gallery)

Use these exact commands when capturing comparable baseline coverage artifacts.

### Backend baseline (pytest)

```bash
mkdir -p artifacts/coverage/backend
python -m pytest \
  -m "not gpu and not db and not ml and not firebird" \
  --ignore=tests/test_probe.py \
  --ignore=tests/test_exifread.py \
  --cov=modules \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml:artifacts/coverage/backend/coverage.xml \
  --junitxml=artifacts/coverage/backend/pytest-junit.xml \
  | tee artifacts/coverage/backend/pytest-term.txt
```

### Gallery baseline (Vitest)

```bash
mkdir -p artifacts/coverage/frontend
cd frontend
npm ci
npx vitest run --coverage \
  --coverage.reporter=text \
  --coverage.reporter=json-summary \
  --coverage.reporter=lcov \
  --coverage.reportsDirectory=../artifacts/coverage/frontend \
  | tee ../artifacts/coverage/frontend/vitest-term.txt
```

### How to refresh baseline quickly

1. Run both commands above.
2. Update `docs/testing/COVERAGE_BASELINE.md` with the new date and metric values.
3. Keep command lines unchanged so results stay comparable across runs.

---

## Running the New Tests

```bash
# All new tests that don't need Firebird or ML:
python -m pytest tests/test_scoring_runner.py tests/test_utils_paths.py tests/test_xmp_sidecar.py -v

# API tests (needs FastAPI, no DB/ML):
python -m pytest tests/test_api_endpoints.py -v

# DB CRUD tests (needs Firebird service + test DB):
python -m pytest tests/test_db_core.py -v -m "db and firebird"

# Full suite excluding GPU/ML/network:
python -m pytest -m "not gpu and not ml and not network" -v
```
