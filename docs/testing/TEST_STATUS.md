# Unit Test Status

**Last updated**: 2026-04-19

## Overview

The test suite is split into:

- **Windows-safe tests**: Should run on native Windows.
- **WSL-only tests**: Marked with `@pytest.mark.wsl` and expected to run in WSL/Linux (TensorFlow/CUDA, Firebird, Linux tooling).

## Current State

### Windows (native)

- **Status**: Not the target for the full suite (WSL-only tests are skipped).
- **Primary blockers historically**:
  - Linux artifacts / Firebird-related instability on Windows
  - TensorFlow + GPU stack not expected to be set up natively
  - Firebird integration tests can hard-crash (access violation)

### WSL (Ubuntu) – `pytest -m wsl -ra`

- **WSL test venv**: `~/.venvs/image-scoring-tests`
- **Setup**: `bash ./scripts/wsl/setup_wsl_test_env.sh`
- **Run**: `bash ./scripts/wsl/run_wsl_tests.sh` (default: `-m "wsl and not network"`)

#### WSL marker inventory (current)

- Total files marked with `@pytest.mark.wsl`: **17**
- Coverage includes:
  - TensorFlow/GPU and model stack tests (`test_tf_gpu`, `test_vila`, `test_model_sources`, `test_gpu`, `test_cuda_manual`, `test_launch`, `test_selector_runner_behavior`, `test_verify_thumbnail`, `test_verify_patching`, `test_culling`)
  - Linux RAW/tooling tests (`test_raw_extraction`, `test_resolution`, `test_dcraw_thumb`, `test_rawpy`, `test_thumb_gen`)
  - Archived Firebird WSL smoke tests (`tests/archive_firebird/test_fb_wsl.py`, `tests/archive_firebird/test_fb_wsl_integration.py`)

#### Recent fixes (2026-03-14)

1. **`tests/test_events.py`** — Refactored to use minimal FastAPI app (no `webui` import); avoids Gradio/TensorFlow.
2. **`tests/test_selector_runner_behavior.py`** — Marked with `@pytest.mark.wsl`; skips when ML deps unavailable.
3. **`tests/test_culling.py`** — Now uses `scoring_history_test.fdb` (per test DB rule); added XMP format verification (`xmpDM:pick`, `xmpDM:good`); added optional `test_full_workflow_real_data` (env: `IMAGE_SCORING_TEST_CULLING_FOLDER`).
4. **`scripts/setup_test_db.py`** — Clears `culling_picks` and `culling_sessions` tables.

#### WSL skips (expected)

- **`tests/test_resolution.py`**: Skipped because `pyiqa` is not installed. Set `INSTALL_PYIQA_TORCH=1` when running `setup_wsl_test_env.sh` to enable.

### PostgreSQL (`@pytest.mark.postgres`)

- **Purpose**: Integration tests against a **dedicated database** `image_scoring_test` (never the default `image_scoring` used by Docker/app data).
- **Opt-in** (default `pytest` does not require Postgres):
  - Set `RUN_POSTGRES_TESTS=1`, or
  - Run `pytest -m postgres`
  - Optional hard-disable: `SKIP_POSTGRES_TESTS=1` (takes precedence over opt-in flags/markers)
- **Dependencies**: `psycopg2-binary` and `pgvector` (see `requirements/requirements_wsl_gpu.txt`). If drivers are missing, tests **skip** with a clear reason.
- **Server**: e.g. `docker compose up -d db` from the repo root (`pgvector/pgvector:pg17` on port `5432`).
- **Pytest + `database.engine: postgres`**: `modules.db_postgres.get_pg_config()` always uses **`image_scoring_test`** while pytest is active (`POSTGRES_DB` and config `dbname` are ignored), matching Firebird’s `scoring_history_test.fdb` rule. To point pytest at another database (dangerous), set **`IMAGE_SCORING_POSTGRES_PRODUCTION_IN_PYTEST=1`** and **`IMAGE_SCORING_I_ACCEPT_PRODUCTION_PYTEST_RISK=1`**. Do not use **`image_scoring_test`** as a production database name on machines where you run tests.
- **Session setup activation policy**: `tests/conftest.py` only activates Postgres setup when explicitly opted in (`RUN_POSTGRES_TESTS=1` or marker expression includes `postgres`) and does nothing for default test runs.
- **Session setup behavior**: once activated, `pytest_sessionstart` calls `ensure_database_exists(image_scoring_test)` when the resolved engine is `postgres` and the two-variable escape hatch is not set, so the test database exists before any test opens a pool.
- **Connection**: Same env/config as the app: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; the `postgres_test_session` fixture sets `POSTGRES_DB=image_scoring_test` for clarity (effective name is still forced under pytest without the escape hatch).
- **Fixtures** (in `tests/conftest.py`): `postgres_test_session` creates the DB if needed and runs `modules.db_postgres.init_db()`; `clean_postgres` truncates app tables before each test.
- **Tests**: `tests/test_postgres_integration.py`

## Related Documents

- [WSL_TESTS.md](WSL_TESTS.md) — WSL test setup and markers
- [ENVIRONMENTS.md](../setup/ENVIRONMENTS.md) — Virtual environment overview

## CI Guard

- `scripts/ci/check_wsl_marker_collection.py` runs `pytest -m wsl --collect-only` against WSL-marked files and fails if zero tests are collected.
- GitHub Actions workflow: `.github/workflows/wsl-marker-guard.yml`.

**Note:** Periodically re-run `pytest -m wsl -ra` (WSL test venv) and update the “Current State” sections above. Former meta-tracker: [archive/testing/DOCUMENTATION_ISSUES.md](../archive/testing/DOCUMENTATION_ISSUES.md).
