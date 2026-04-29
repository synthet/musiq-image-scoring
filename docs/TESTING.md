# Testing

Hub page — canonical detail lives in linked docs.

## Status and markers

- **[testing/TEST_STATUS.md](testing/TEST_STATUS.md)** — what is green / skipped in CI.
- **[testing/WSL_TESTS.md](testing/WSL_TESTS.md)** — `pytest -m wsl` and `~/.venvs/image-scoring-tests`.
- **[testing/AUTOMATED_VS_MANUAL_CHECKS.md](testing/AUTOMATED_VS_MANUAL_CHECKS.md)** — manual QA expectations.
- **[../pytest.ini](../pytest.ini)** — markers (`gpu`, `db`, `ml`, `wsl`, `network`, …).

## Fast local subset (no GPU / DB / ML)

From repo root (venv per [DEVELOPMENT.md](DEVELOPMENT.md)):

```bash
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```

(Adjust `--ignore` per [AGENTS.md](../AGENTS.md) Cursor Cloud notes if a file breaks collection.)

## Infra checks

- `python scripts/doctor.py` — config + DB + pgvector (+ optional GPU); see [DIAGNOSTICS.md](DIAGNOSTICS.md).
