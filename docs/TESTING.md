# Testing

Hub page for backend test commands, marker usage, and status references.

## Status And Markers

- **[testing/TEST_STATUS.md](testing/TEST_STATUS.md)** - what is green / skipped in CI.
- **[testing/WSL_TESTS.md](testing/WSL_TESTS.md)** - `pytest -m wsl` and `~/.venvs/image-scoring-tests`.
- **[testing/AUTOMATED_VS_MANUAL_CHECKS.md](testing/AUTOMATED_VS_MANUAL_CHECKS.md)** - manual QA expectations.
- **[../pytest.ini](../pytest.ini)** - marker definitions.

Common markers:

- `gpu` - CUDA/GPU-dependent checks.
- `db` - tests that require a reachable database.
- `ml` - model or ML dependency checks.
- `wsl` - WSL-only environment checks.
- `network` - external network access.

Legacy Firebird tests are archived under `tests/archive_firebird/` and excluded
from collection via `pytest.ini` `norecursedirs`. Do not write new tests there.

## Fast Local Subset

From repo root, with the venv from [DEVELOPMENT.md](DEVELOPMENT.md):

```bash
python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py
```

Adjust `--ignore` only for known collection problems documented in [AGENTS.md](../AGENTS.md) or current test-status notes.

## Infra Checks

- `python scripts/doctor.py` - config + DB + pgvector (+ optional GPU); see [DIAGNOSTICS.md](DIAGNOSTICS.md).

## Cross-Repo Checks

For API, schema, or phase terminology changes, run backend checks first, then gallery checks. Start with:

- Backend: fast pytest subset above, plus doctor when config, database, pgvector, or environment behavior changed.
- Gallery: `npm run doctor`, `npx tsc --noEmit`, `npx tsc -p electron/tsconfig.json --noEmit`, and targeted Vitest files for touched API/DB/renderer paths.
