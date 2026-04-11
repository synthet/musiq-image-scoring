# Cross-App Integration Audit

Date: 2026-03-15

This audit evaluates the current automated integration coverage between the Python backend (**image-scoring-backend**) and the sibling Electron frontend (**image-scoring-gallery**).

Target environment:
- Local Windows developer workflow
- Sibling repo layout: **image-scoring-backend** and **image-scoring-gallery** (paths on disk vary)
- Shared Firebird database plus backend REST/WebSocket interfaces

This is not a new end-to-end harness. It is a coverage audit, a list of verified failures, and a minimum next-step test matrix.

## Scope

The audit treats these as the shared integration surfaces:

| Surface | Backend owner | Frontend consumer |
|---|---|---|
| REST API contract | `openapi.json`, `modules/api.py` | `electron/apiService.ts`, `electron/apiTypes.ts` |
| Runtime discovery | `webui.lock` written by backend | `electron/apiUrlResolver.ts`, `system:get-api-config` |
| Shared DB contract | `modules/db.py` schema authority | `electron/db.ts` query layer |
| Real-time channel | `/ws/updates`, `modules/events.py` | `src/services/WebSocketService.ts` |

## Existing Automated Coverage

### Coverage by surface

| Surface | Backend evidence | Electron evidence | Coverage status |
|---|---|---|---|
| REST API contract | `tests/test_api_queue.py` exercises FastAPI routes in isolation | `scripts/validate-api-types.mjs` checks Electron client/types against backend OpenAPI | Partial |
| Runtime discovery | Backend writes `webui.lock`, but no backend-side test was found for lock-file generation | `electron/apiUrlResolver.test.ts` covers explicit URL, host/port, `webui.lock`, and fallback behavior | Covered for resolver library, partial for full IPC path |
| Shared DB contract | Backend schema and DDL live in `modules/db.py`; backend DB tests exist | No automated Electron tests were found for `electron/db.ts` or query parity against backend schema | Uncovered |
| Real-time channel | `tests/test_events.py` validates `/ws/updates` broadcasting with a minimal FastAPI app | `src/services/WebSocketService.test.ts` validates URL resolution, handler dispatch, reconnect, and malformed message handling | Partial |
| Job lifecycle from Electron | Backend route tests cover enqueue behavior and failure responses | No automated Electron tests were found for `ApiService` submit flows or `electron/main.ts` IPC handlers | Uncovered |

### Tests and checks inspected

Backend repo:
- `tests/test_api_queue.py`
- `tests/test_events.py`
- `tests/test_selection_integration.py`
- `tests/test_raw_ui.py`

Electron repo:
- `electron/apiUrlResolver.test.ts`
- `src/services/WebSocketService.test.ts`
- `scripts/validate-api-types.mjs`

No true cross-repo automated smoke harness was found. Coverage remains split across backend `pytest`, frontend `vitest`, and the OpenAPI contract validator.

## Lightweight Checks Run

### Commands executed

| Command | Result |
|---|---|
| `node scripts/validate-api-types.mjs` in **image-scoring-gallery** | Failed with 28 contract mismatches |
| `npm run test:run -- electron/apiUrlResolver.test.ts src/services/WebSocketService.test.ts` in **image-scoring-gallery** | Passed: 2 files, 16 tests |
| `.venv\Scripts\pytest.exe tests/test_api_queue.py tests/test_events.py -q` in `image-scoring` | Blocked by local Python environment |

### Environment blockers

| Blocker | Evidence | Impact |
|---|---|---|
| Broken local Windows Python venv entrypoint | `.venv\pyvenv.cfg` points at the Windows Store Python shim and `pytest.exe` fails with `Unable to create process using ... WindowsApps ... python.exe` | Backend pytest execution is not reliable from this shell |
| Agent sandbox child-process restriction | Initial Electron `vitest` run failed with `spawn EPERM` while loading Vite config | Electron tests pass when run unrestricted, but agent-side sandboxing can mask real test status |

### Verified product failure

The Electron API contract validator failed with 28 mismatches:

| Category | Count | Notes |
|---|---|---|
| Endpoint mismatches | 6 | Missing client coverage for `/api/jobs/queue`, `/api/folders/rebuild`, `/api/stacks/{stack_id}/images`, `/api/phases/decision`, `/api/pipeline/phase/skip`, `/api/pipeline/phase/retry` |
| Missing schema interfaces | 3 | `OutlierResponse`, `PhaseDecisionResponse`, `PipelinePhaseControlRequest` |
| Field mismatches | 19 | Drift across `ScoringStartRequest`, `TaggingStartRequest`, `ClusteringStartRequest`, `PipelineSubmitRequest`, and `StatusResponse` |

This is the main verified cross-app defect found by the audit. It is not an environment problem.

## Scenario Scorecard

| Scenario | Score | Evidence | Notes |
|---|---|---|---|
| Electron resolves backend URL correctly from explicit config and `webui.lock` | Covered | `electron/apiUrlResolver.test.ts` passed | Resolver library is covered; `system:get-api-config` in `electron/main.ts` is still not directly tested |
| Electron health check detects backend availability | Uncovered | `ApiService.healthCheck()` and `isAvailable()` are wired in code, but no test was found | Add focused `ApiService` tests with mocked `net.fetch()` |
| Electron typed client matches backend OpenAPI paths and request/response fields | Covered, failing | `scripts/validate-api-types.mjs` failed with 28 mismatches | Keep this check mandatory and fix the drift |
| Electron can submit a real backend operation and backend persists the expected job row | Uncovered | Backend route tests exist, but no Electron-to-backend smoke was found | Highest-value missing automation |
| Backend `/ws/updates` events are consumable by Electron `WebSocketService` | Partial | Backend and Electron units both exist | No single test proves the live backend event stream reaches the Electron consumer |
| Electron DB reads still match backend-owned schema and expected column names | Uncovered | No Electron tests were found for `electron/db.ts` | This is a major regression risk because backend owns schema and Electron owns query assumptions |
| One local Windows happy-path flow works end to end | Uncovered | No cross-repo smoke harness was found | Current repo state does not verify `backend running -> Electron connected -> job visible` |
| One negative-path flow is covered | Partial | Contract validator catches type drift; `WebSocketService.test.ts` covers config/init failure | No end-user Electron flow asserts clear behavior when backend health/API calls fail |

## Gap Classification

### Contract drift

- Confirmed by `scripts/validate-api-types.mjs`.
- Current drift is large enough that backend and Electron cannot be treated as contract-synchronized.

### Startup and discovery gaps

- URL resolution logic is tested at the library level.
- No automated check covers the full `electron/main.ts` IPC path that exposes backend URL/config to the renderer.

### DB query parity gaps

- Backend is the schema authority.
- Electron has no automated parity check against the backend-owned schema or a test DB.
- No automated check proves `electron/db.ts` still matches backend column names and result shapes.

### Job lifecycle gaps

- Backend route tests verify enqueue behavior in isolation.
- No test proves Electron can submit a job through its actual API layer and then observe the resulting backend state.

### Live update gaps

- Backend WebSocket broadcasting and Electron WebSocket consumption are both unit-tested.
- No combined smoke proves `job_started`, `job_progress`, `job_completed`, `image_updated`, or `folder_updated` can traverse the full boundary.

### Full UI workflow gaps

- No automated Electron UI workflow was found for the shared backend integration.
- `tests/test_raw_ui.py` is backend-browser focused, incomplete, and unrelated to the Electron workflow.

## Recommended Next-Step Matrix

### Tier 1: Keep existing split tests, but make contract checks authoritative

| Priority | Change | Value | Effort |
|---|---|---|---|
| 1 | Fix the 28 Electron API contract mismatches and keep `scripts/validate-api-types.mjs` as a required check | High | Low |
| 2 | Add focused Electron tests for `ApiService.healthCheck()` and `ApiService.isAvailable()` using mocked `net.fetch()` | High | Low |
| 3 | Repair or document a supported local Windows Python runner so backend pytest is runnable without the Windows Store shim issue | High | Low |

### Tier 2: Add one cross-repo smoke path

| Priority | Change | Value | Effort |
|---|---|---|---|
| 1 | Add a local Windows smoke script that: starts or targets a running backend, resolves backend URL from Electron logic, submits one pipeline or scoring job, and verifies job visibility through API or DB | High | Medium |
| 2 | Add one Electron DB parity check against the backend test database created by `scripts/setup_test_db.py` | High | Medium |
| 3 | Add one backend-to-Electron event smoke that confirms the renderer-side WebSocket consumer receives a real backend broadcast | Medium | Medium |

### Tier 3: UI automation after the smoke path is stable

| Priority | Change | Value | Effort |
|---|---|---|---|
| 1 | Add UI-driven Electron automation for one happy path and one negative path | Medium | High |

## E2E Start Gates (Quantitative)

The project should begin broader E2E automation only after the following measurable entry gates are met:

| Gate | Metric | Threshold to open E2E work |
|---|---|---|
| Contract stability | `scripts/validate-api-types.mjs` result | **Green for 10 consecutive runs** on the main branch |
| Smoke reliability | Tier 2 cross-repo smoke script success rate | **>= 95% pass rate** over the most recent **20 CI runs** (excluding explicitly infra-labeled outages) |
| Core backend confidence | Coverage for core integration modules (`modules/api.py`, `modules/events.py`, queue/job submission path) | **>= 80% line coverage** in the backend CI coverage report |
| Core frontend confidence | Coverage for Electron integration entry points (`electron/apiService.ts`, `electron/main.ts` IPC API path, `src/services/WebSocketService.ts`) | **>= 75% line coverage** in frontend CI coverage report |
| Blocking defect trend | Open P0/P1 integration defects tagged `cross-app` | **0 P0** and **<= 2 P1** open for 14 consecutive days |

Notes:
- These gates are intended to reduce flaky E2E investment before contract and smoke stability are proven.
- If any gate regresses after E2E starts, continue maintaining existing E2E tests but pause adding new scenarios until gates recover.

## Decision Checkpoint: Re-evaluate E2E

Re-evaluate E2E scope at **Milestone X**, defined as whichever comes first:

1. **Date trigger:** **2026-05-15**
2. **Criteria trigger:** All E2E start gates above are satisfied

At Milestone X, run a 30-minute checkpoint with backend + Electron maintainers and record one of:
- **Proceed:** Start planned E2E build-out for next sprint.
- **Hold:** Keep Tier 1/2 only and document the blocking gate(s) with owner and ETA.
- **Reduce scope:** Start only one scenario if partial gates are met and risk is acceptable.

## First E2E Scenario Candidate and Ownership

To avoid indefinite deferral, define the first scenario now and assign clear ownership.

| Item | Definition |
|---|---|
| Scenario ID | `E2E-01-electron-submit-job` |
| Goal | Verify **backend running -> Electron resolves backend URL -> submit one scoring/pipeline job -> job row/status visible via API** |
| Minimum assertions | (1) health check passes, (2) submit returns job/run id, (3) job appears in `/api/jobs` (or direct DB verification), (4) terminal status is observed or timeout is explicit |
| Primary owner | **Electron maintainer** (test harness + client-side orchestration) |
| Secondary owner | **Backend maintainer** (stable fixtures, API/DB observability hooks, test data seed) |
| Target start condition | Begin implementation immediately when Milestone X = Proceed |
| Timebox | First executable scenario merged within **1 sprint** of Milestone X proceed decision |

## Local Audit Runner

Use the local audit helper to rerun the lightweight checks without building a new E2E harness:

```powershell
.\scripts\powershell\Run-CrossAppAudit.ps1
```

It currently runs:
- Electron contract validation
- Electron `apiUrlResolver` and `WebSocketService` tests
- Backend `pytest` checks for `test_api_queue.py` and `test_events.py`

The script classifies results as `PASS`, `FAIL`, or `BLOCKED` so environment problems are separated from product failures.
