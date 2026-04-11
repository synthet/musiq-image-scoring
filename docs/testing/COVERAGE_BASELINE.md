# Coverage Baseline

**Date captured (UTC): 2026-04-11**

This document records the canonical commands and baseline coverage format for both backend (pytest) and gallery/frontend (Vitest).

## Canonical commands

### Backend (pytest)

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

### Gallery/frontend (Vitest)

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

## Baseline metrics

### Python (pytest-cov)

- **Line coverage**: _Not captured in this environment (missing `pytest-cov`/`coverage` install due network restrictions)._
- **Branch coverage**: _Not captured in this environment (missing `pytest-cov`/`coverage` install due network restrictions)._

### Vitest

- **Lines**: _Not captured in this environment (`npm ci` failed due registry/network policy restrictions)._
- **Functions**: _Not captured in this environment (`npm ci` failed due registry/network policy restrictions)._
- **Branches**: _Not captured in this environment (`npm ci` failed due registry/network policy restrictions)._
- **Statements**: _Not captured in this environment (`npm ci` failed due registry/network policy restrictions)._

## How to refresh baseline

1. Run the backend command above from the repo root.
2. Run the frontend command above from the repo root.
3. Copy metric values from:
   - `artifacts/coverage/backend/pytest-term.txt` (line/branch)
   - `artifacts/coverage/frontend/coverage-summary.json` (Vitest lines/functions/branches/statements)
4. Update:
   - **Date captured** in this file
   - all baseline metric values in this file
5. Commit the updated baseline document and artifacts-producing workflow changes together.
