# Automated tests vs manual checks

## Automated tests

Automated tests are files under `tests/` that match `test_*.py` and are collected by `pytest`.

Use these for repeatable CI/local verification.

## Manual checks

Manual checks live under `manual-checks/`.

Use this folder for scripts that are intentionally operator-driven (for example DB probes, migration diagnostics, or one-off validation scripts).

## Guardrail: import-time side-effect checker

To prevent accidental import-time execution in automated test modules, run:

```bash
python scripts/check_test_import_side_effects.py
```

- The checker scans `tests/test_*.py`.
- It fails when a non-allowlisted test module executes code at import time.
- Legacy files can be temporarily listed in `scripts/check_test_import_side_effects.allowlist` while they are being cleaned up.

## `tests/test_probe.py`

`tests/test_probe.py` is now a proper pytest test function and does not execute at import time.

It is opt-in and only runs when:

```bash
RUN_MANUAL_DB_PROBE=1 pytest tests/test_probe.py -q
```
