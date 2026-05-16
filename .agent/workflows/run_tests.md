---
description: Run pytest with correct markers and venv (image-scoring-backend)
---

## Purpose

Run automated tests without pulling in GPU, production DB, ML-only, or Firebird-only suites unless needed.

## When to use

- After code changes; before PR; when validating a fix.

## Canonical docs first

- [docs/TESTING.md](../../docs/TESTING.md)
- [AGENTS.md](../../AGENTS.md) (markers, E2E vocabulary)
- [.cursor/rules/python-wsl-webapp-env.mdc](../../.cursor/rules/python-wsl-webapp-env.mdc)

## Safe commands

**Fast gate (recommended default):**

```bash
# WSL + ~/.venvs/tf for most unit tests; use image-scoring-tests venv for pytest -m wsl only
source ~/.venvs/tf/bin/activate
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```

**If collection fails on optional deps:**

```bash
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py --ignore=tests/test_exifread.py
```

**Targeted:**

```bash
python -m pytest tests/test_<area>.py -v
```

**WSL-marked suite:** use `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1` with `~/.venvs/image-scoring-tests` — not the `tf` venv unless intentional.

## Files commonly touched

- `tests/`, `pytest.ini`, `conftest.py`

## Common failure modes

- **Collection errors:** `tests/test_probe.py` imports DB at import time — always `--ignore` for fast runs.
- **Wrong venv:** Missing packages or Firebird FFI when using Windows Python for WSL-only tests.

## Do not

- Do not run destructive tests against production DB URLs.
- Do not disable assertions or skip tests broadly without user approval.
