# CI Gates and Branch Protection

This repository uses a split CI model: **required checks** are fast and block merges, while heavier checks are **informational** until stabilized.

## Canonical contract gate

Use **`contract:check`** as the single canonical contract verification command.

- Canonical command: `python scripts/ci/contract_check.py`
- Frontend wrapper: `npm run contract:check` (from `frontend/`)

`contract:validate` is intentionally **not** used as a gate name in this repo to avoid ambiguity.

## Check matrix

| Check | CI job name | Command | Gate type |
|---|---|---|---|
| Fast backend pytest slice | `backend-pytest-fast` | `python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py --ignore=tests/test_exifread.py` | **Required** |
| Gallery unit tests | `gallery-test-run` | `npm run test:run` (in `frontend/`) | **Required** |
| API contract parity | `contract-check` | `python scripts/ci/contract_check.py` | **Required** |
| Integration/smoke pytest slice | `integration-smoke` | `python -m pytest tests/integration -m "not gpu and not ml and not firebird" -q` | **Informational** (non-blocking) |

## Branch protection guidance

Configure branch protection for `main` with these **required status checks**:

1. `backend-pytest-fast`
2. `gallery-test-run`
3. `contract-check`

Keep `integration-smoke` non-required while the suite is maturing; convert it to required once runtime and fixture stability are consistently green.
