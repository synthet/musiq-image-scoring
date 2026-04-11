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

### P2.1. `modules/engine.py` — Pipeline orchestrator failure/cancel/order paths

**Gap**: No tests. This module coordinates scoring→tagging→clustering phase
transitions and is the highest-risk untested component.

**Fixture strategy checklist**
- [ ] Use `FakeScoringRunner`, `FakeTaggingRunner`, and `FakeClusteringRunner`
      with deterministic `start`, `stop`, and status behavior.
- [ ] Stub DB phase-gate helpers to model success, failure, and cancel states.
- [ ] Use per-test callback/event fixtures so cancellation and failures can be
      asserted without sleeps.

**Done = specific assertions**
- [ ] Tagging never starts before scoring is marked complete.
- [ ] Clustering never starts before tagging is marked complete.
- [ ] A scoring failure prevents both tagging and clustering from starting.
- [ ] A tagging failure prevents clustering from starting.
- [ ] Cancellation propagates to all active runners (each fake runner records
      exactly one `stop` call).
- [ ] Job terminal state is persisted as `failed` or `cancelled` consistently
      with runner outcomes.

**Effort**: ~200 lines, no ML deps needed.

### P2.2. `modules/config.py` — Validation/boundary/type coercion

**Gap**: `test_config_secrets.py` covers secret leakage; no tests for schema
validation, defaults, or invalid-value rejection.

**Fixture strategy checklist**
- [ ] Use `tmp_path` to write temporary `config.json` variants per test case.
- [ ] Add factory fixtures that generate minimal-valid config dicts for focused
      mutation in each test.
- [ ] Use parametrized invalid payload fixtures for boundary and type cases.

**Done = specific assertions**
- [ ] Missing required keys raise validation errors with key-specific messages.
- [ ] Numeric boundaries reject out-of-range values (e.g., negatives where only
      non-negative is allowed).
- [ ] Boolean/number/string coercion is explicit and deterministic (accepted
      coercions produce normalized values; invalid coercions raise).
- [ ] Default values are applied only when keys are absent (not when invalid
      values are supplied).
- [ ] Unknown config keys are either rejected or ignored according to current
      module contract, and tests assert that exact behavior.

**Effort**: ~100 lines, zero deps.

### P2.3. `modules/db.py` + `modules/mcp_server.py` — Query behavior + MCP response shapes

#### `modules/db.py` complex query behavior

**Gap**: Phase 1 covered basic CRUD; no tests for:
- `get_images_for_scoring()` filter combinations (folder, status, limit)
- `get_scoring_history()` pagination
- `get_similar_images()` embedding distance queries
- Tag propagation (`_sync_image_keywords`, `_backfill_keywords`)

**Fixture strategy checklist**
- [ ] Reuse Postgres/DB fixtures from `tests/conftest.py` for seeded datasets.
- [ ] Add helper fixtures that create mixed folder/status/embedding rows for
      deterministic query expectations.
- [ ] Use transaction or teardown fixtures to ensure isolation between query tests.

**Done = specific assertions**
- [ ] `get_images_for_scoring()` returns only rows matching each filter
      combination, with stable ordering and enforced `limit`.
- [ ] `get_scoring_history()` pagination returns non-overlapping pages with
      consistent total/count metadata.
- [ ] `get_similar_images()` orders results by ascending distance (or descending
      similarity per contract) and excludes the query image itself when required.
- [ ] `_sync_image_keywords` and `_backfill_keywords` modify only targeted rows
      and preserve unrelated keywords.

#### `modules/mcp_server.py` response shape tests

**Gap**: No tests beyond launch smoke test.

**Fixture strategy checklist**
- [ ] Use a mocked MCP tool registry or test client with deterministic tool outputs.
- [ ] Patch DB-dependent helpers so response-shape tests do not require live DB/ML.
- [ ] Add shared response-schema assertions (required keys, value types, error format).

**Done = specific assertions**
- [ ] Tool success responses include required keys (`ok`/`status`/payload keys as
      defined by each tool contract) with correct value types.
- [ ] Tool error responses use a consistent error envelope and message field.
- [ ] DB-independent tools return valid shapes when DB is unavailable.
- [ ] DB-dependent tools return predictable error shapes when dependencies fail.

**Effort**: ~270 lines total (~150 DB + ~120 MCP), DB tests require `@pytest.mark.db firebird`.

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
