# /ui/runs — Deep Code & Design Review (2026-04-18)

**Reviewer:** senior staff engineer persona (defect-oriented review)
**Scope:** full execution chain for `http://127.0.0.1:7860/ui/runs` — React SPA pages, FastAPI endpoints, DB helpers, orchestration globals, WebSocket store.
**Status:** findings only; no code changes applied.

---

## 1. System map

### Entrypoints
- Routes: `/ui/runs` → `frontend/src/pages/RunsPage.tsx`; `/ui/runs/:runId` → `RunDetailPage.tsx`.
- Static bundle served by FastAPI from `static/app/` (hashed `index-*.js` + `index-*.css`).

### Frontend surface
- `pages/RunsPage.tsx` — list, tabs (Active / Queued / History / Tools), polling, pagination.
- `pages/RunDetailPage.tsx` — header, header-level mutations, stages, report, logs.
- `components/runs/RunCard.tsx`, `StagePanel.tsx`, `LogPanel.tsx`, `ReportPanel.tsx`, `WorkflowGraph.tsx`, `RunQueuePayloadPanel.tsx`, `RunsToolsTab.tsx`.
- `api/runs.ts` — REST client.
- `stores/wsStore.ts`, `hooks/useWebSocket.ts` — live push plumbing.
- `types/api.ts` — client contracts.

### Backend surface (`modules/api.py`)
- `GET /api/jobs/recent` (list; `history=true` → `{runs, total}`)
- `GET /api/jobs/{job_id}` (detail + phases + capabilities)
- `POST /api/runs/submit`
- `POST /api/runs/{id}/pause|resume|cancel|retry|force`
- `GET /api/runs/{id}/stages`
- `POST /api/runs/{id}/stages/{code}/retry|skip`
- `GET /api/runs/{id}/stages/{code}/steps|items`
- `GET /api/runs/{id}/diagnostics|report|report/images`
- `GET /api/queue` / `POST /api/queue/reorder`
- `WS /ws/updates`

### Orchestration / runners
- Module-level globals in `modules/api.py`: `_scoring_runner`, `_tagging_runner`, `_clustering_runner`, `_selection_runner`, `_bird_species_runner`, `_indexing_runner`, `_metadata_runner`, `_maintenance_runner`, `_orchestrator`, `_job_dispatcher`.
- Dispatcher at `modules/job_dispatcher.py`; phase execution via `modules/phase_executors.py`, `modules/pipeline_orchestrator.py`, `modules/phases.py`.

### DB layer
- Schema authority: `modules/db.py` (FB→PG translation), `modules/db_postgres.py`.
- Connector abstraction: `modules/db_connector/*`.
- Tables touched: `jobs`, `job_phases`, `image_phase_status`, `pipeline_phases`, `image_actions`, `image_incidents`.
- Key helpers: `get_jobs`, `count_jobs`, `get_job_phases`, `resume_job_phases`, `enqueue_job`, `requeue_job`, `update_job_status`, `reconcile_stale_running_phases_for_jobs`, `get_run_diagnostics`, `get_job_report`.

### Data flow
- **List**: `RunsPage` → `runsApi.list` → `GET /api/jobs/recent` → `db.get_jobs` → `_normalize_jobs_table_row` → `_json_response_db` → React Query → card render; WS bumps `runsVersion` → invalidation.
- **Detail**: `RunDetailPage` → parallel `runsApi.get` + `runsApi.getStages` → `/api/jobs/{id}` and `/api/runs/{id}/stages`; `StagePanel` fetches steps/items; `ReportPanel` fetches `/runs/{id}/report`.

---

## 2. Execution trace

1. User loads `/ui/runs`. `RunsPage` fires `runsApi.list({ limit: 120 })` → `GET /api/jobs/recent?limit=120`.
2. Backend `get_recent_jobs` runs `db.get_jobs(120, 0, history_only=False)` ordered by `created_at DESC`.
3. Each row normalized: `scope_paths` + `queue_payload` JSON parsed, `capabilities.execution_report` added.
4. Response serialized via `_json_response_db` (custom defaults for odd DB types).
5. Client filters into `active` (`running|paused`), `queued` (`queued|pending`), `overviewHistory` (`completed|failed|canceled|interrupted`).
6. UI renders `RunCard`s with `RunBadge`, optional `run_progress` from `wsStore`.
7. Switching to History tab fires a second query with `history=true` returning `{runs,total}`.
8. Polling every 5 s; WS `stage_transition` / `queue_update` bumps `runsVersion` triggering re-key + refetch.
9. Card actions: pause/resume/cancel/retry/force → `POST /api/runs/{id}/...` → DB mutations; success invalidates `RUNS_QUERY_ROOT`.
10. Retry creates a new job id; success handler navigates to the new detail page.
11. Detail page fetches `/jobs/{id}`, `/runs/{id}/stages`, then children (steps/items/report/logs). WS appends log lines to store ring buffer (500-line cap).

---

## 3. Findings

### Finding 1 — `cancel` on a live indexing/metadata/bird_species job never stops the runner
- **Severity:** High · **Confidence:** High · **Category:** Orchestration
- **Location:** `modules/api.py:5430-5465` (`cancel_run`), `modules/api.py:1377+` (`_stop_runner_for_phase`).
- **Problem:** Fallback loop iterates `("indexing", "metadata", "scoring", "tagging", "clustering", "selection", "bird_species")`, but `_stop_runner_for_phase` only handles `scoring`, `keywords/tagging`, `culling/selection`, `clustering`. `indexing`, `metadata`, `bird_species` are silently ignored.
- **Why it matters:** DB flips to `canceled`, but the runner thread keeps executing, burning CPU/GPU, writing phase rows, potentially re-transitioning status. User sees "canceled" while the work continues.
- **Failure scenario:** User hits Cancel on a running indexing job → status shows canceled → runner still traverses the scope.
- **Evidence:** `_stop_runner_for_phase` lines 1377–1395 enumerate only 4 phases.
- **Fix:** route cancel through a dispatcher-level abort that knows every runner; extend `_stop_runner_for_phase` to handle indexing/metadata/bird_species.
- **Tests:** integration test cancelling an active run of each job_type; assert runner thread exits within N seconds.

### Finding 2 — `/api/jobs/recent?limit=120` can silently drop Active/Queued runs
- **Severity:** High · **Confidence:** High · **Category:** Data contract / UI state
- **Location:** `frontend/src/pages/RunsPage.tsx:24`; `modules/api.py:3115`.
- **Problem:** Active / Queued tabs are computed by client-side filtering of the 120 most-recent rows. If >120 jobs exist since the oldest running/queued row was created (common during bulk imports + retries), older running or queued rows vanish from the UI; tab badge counts also become wrong.
- **Evidence:** `queryFn: () => runsApi.list({ limit: 120 })` with no `status=` filter; backend orders by `created_at DESC`.
- **Fix:** server-side filtered queries by status for the active/queued tabs.
- **Tests:** seed >150 jobs including old `running` rows; assert they appear.

### Finding 3 — Enqueue-vs-create-phases race
- **Severity:** High · **Confidence:** Medium · **Category:** Concurrency
- **Location:** `modules/api.py:5335-5349` (`submit_run`), `5641-5662` (`_reenqueue_job`), `5695-5711` (`retry_run`).
- **Problem:** `db.enqueue_job(...)` inserts `jobs` and makes the row dequeueable; `db.create_job_phases(...)` runs *after*. The dispatcher can dequeue and invoke a runner that reads `get_job_phases(job_id)` before the rows exist, producing empty-phase behavior or default-phase fallbacks.
- **Failure scenario:** Under load, some runs execute with the wrong phase plan or 500 on phase lookup.
- **Fix:** wrap enqueue + phases in a single transaction (same engine), or insert the job in a non-dequeueable pre-state, then flip to `queued` after phases exist.
- **Tests:** parallel-submit stress test asserting `get_job_phases` non-empty at every observed state.

### Finding 4 — `retry_run` has no status guard
- **Severity:** Medium · **Confidence:** High · **Category:** Validation
- **Location:** `modules/api.py:5665-5716`.
- **Problem:** Endpoint creates a new job regardless of source job status. The UI only shows Retry for `failed|interrupted`, but any programmatic call against a `running`/`queued` job spawns a duplicate that can execute on overlapping scope.
- **Fix:** require `status in ("failed","interrupted","canceled","cancelled","completed")` else 409.
- **Tests:** POST retry to running/queued jobs → expect 409.

### Finding 5 — `pause_run` check-then-write can overwrite a terminal status
- **Severity:** Medium · **Confidence:** High · **Category:** Concurrency / Orchestration
- **Location:** `modules/api.py:5359-5390`.
- **Problem:** Non-atomic: `db.get_job(...)` asserts `status=='running'`, then `db.update_job_status(..., 'paused')`. If the runner completes in between, `paused` silently overwrites `completed`/`failed`. The following `reconcile_stale_running_phases_for_jobs(..., in_flight_to="not_started")` can then clobber already-completed phase rows.
- **Fix:** conditional UPDATE (`WHERE status='running' RETURNING id`) and branch on affected rows; skip reconciliation if not flipped.

### Finding 6 — `cancel_run` on `queued` returns "canceled" without actually canceling
- **Severity:** Medium · **Confidence:** High · **Category:** Data contract / UI
- **Location:** `modules/api.py:5438-5461`.
- **Problem:** For queued jobs, `db.request_cancel_job(run_id)` sets a flag, but the response message says `Run {run_id} canceled`. Depending on `request_cancel_job` semantics, the dispatcher may still pick up the job; UI shows "canceled" while the job runs later.
- **Fix:** `UPDATE jobs SET status='canceled' WHERE id=? AND status='queued'`; verify affected rows; distinguish in toast between "requested" and "terminated".

### Finding 7 — `resume_job_phases` wipes `error_message` and timestamps for all non-terminal phases
- **Severity:** Medium · **Confidence:** High · **Category:** Data contract / Observability
- **Location:** `modules/db.py:5404-5442`.
- **Problem:** Resets `started_at=NULL, completed_at=NULL, error_message=NULL` for every non-`completed`/`skipped` row, including phases that were `running` or `cancel_requested`. Post-mortem diagnostics are erased. Also, the "first-incomplete → queued" rule doesn't distinguish user-intent (retry first failed vs. skip it and continue).
- **Fix:** preserve last `error_message` (archive or keep), make behavior mode-aware.

### Finding 8 — Double-JSON payload hack hides upstream corruption
- **Severity:** Medium · **Confidence:** High · **Category:** Data contract / Observability
- **Location:** `modules/api.py:5408-5414`, `5596-5602`.
- **Problem:** `payload = json.loads(raw); if isinstance(payload, str): payload = json.loads(payload)` silently recovers from double-encoded strings. Non-str/dict results become `{}` without signal. Masks a real bug producing `"\"{...}\""` (likely `update_job_payload` double-`json.dumps`).
- **Fix:** log a warning on double-encoded payloads; find and fix root cause.

### Finding 9 — `force_run._reset_ghost_runners` is racy for non-selection runners
- **Severity:** Medium · **Confidence:** Medium · **Category:** Concurrency
- **Location:** `modules/api.py:5499-5524`.
- **Problem:** Only `selection` branch takes a lock. Scoring/tagging/clustering read-then-write `is_running` without synchronization. A concurrent `start_batch` can race across the check-write window.
- **Fix:** add per-runner lock; centralize `reset_ghost_if_dead()` method.

### Finding 10 — Frontend spelling mismatch: `canceled` vs `cancelled`
- **Severity:** Low · **Confidence:** High · **Category:** Data contract
- **Location:** `frontend/src/pages/RunsPage.tsx:44-50`; `modules/db.py:6078`.
- **Problem:** `_JOB_HISTORY_STATUSES` includes both US and UK spellings; frontend `overviewHistory` filter and `RunStatus` union only include `'canceled'`. UK rows mis-classified on non-History tabs (neither active/queued/history) → effectively hidden.
- **Fix:** extend TS union and filters; ideally normalize server-side.

### Finding 11 — `runsApi.getReport` crashes on non-404 errors
- **Severity:** Low · **Confidence:** High · **Category:** Error handling
- **Location:** `frontend/src/api/runs.ts:90-115`.
- **Problem:** Only 404 is mapped to `{available:false}`; 5xx re-throws into React Query and crashes `ReportPanel` (no error boundary). Envelope duck-typing (`'available' in res && typeof res.available === 'boolean'`) lets older backends silently drop the envelope.
- **Fix:** treat `>=500` as `{available:false, reason:'error'}`; harden envelope check.

### Finding 12 — History pagination clamp can ping-pong
- **Severity:** Low · **Confidence:** Medium · **Category:** UI state
- **Location:** `frontend/src/pages/RunsPage.tsx:60-65`.
- **Problem:** When new runs arrive while user is on last page, `maxPage` shrinks/grows, `useEffect` keeps flipping page index → repeated refetches.
- **Fix:** clamp only once after first settled payload; debounce changes.

### Finding 13 — `useWebSocket` subscribes to the entire `wsStore`
- **Severity:** Low · **Confidence:** High · **Category:** Performance
- **Location:** `frontend/src/hooks/useWebSocket.ts:12`.
- **Problem:** `const store = useWsStore()` (no selector) rerenders the hook's host component on every store mutation — one per WS message; combined with growing `logLines`/`runProgress` maps this scales poorly.
- **Fix:** read actions via `useWsStore.getState()` inside handlers or select shallow slices.

### Finding 14 — Progress percent not clamped
- **Severity:** Low · **Confidence:** High · **Category:** UI state
- **Location:** `frontend/src/components/runs/RunCard.tsx:48-50`, `StagePanel.tsx:85`.
- **Problem:** If `items_done > items_total` (re-counts on resume), bar renders >100%. Negative values render inverted.
- **Fix:** clamp `Math.max(0, Math.min(100, pct))`.

### Finding 15 — `activeStage` fallback picks last phase for fresh runs
- **Severity:** Low · **Confidence:** Medium · **Category:** UI state
- **Location:** `frontend/src/pages/RunDetailPage.tsx:88-93`.
- **Problem:** With no running or failed stage, falls back to `stages[stages.length - 1]` rather than the first queued/pending. A new indexing-only run shows "Keywords" selected by default.
- **Fix:** prefer queued → pending → running → failed → last.

### Finding 16 — `get_run_diagnostics` swallows aggregate-query failure
- **Severity:** Low · **Confidence:** High · **Category:** Observability
- **Location:** `modules/db.py:5098-5116`.
- **Problem:** On exception returns `by_phase={}` with only `logger.exception`; UI cannot distinguish "no data" from "query failed".
- **Fix:** include `counts_error: str(e)` in the response; render warning.

### Finding 17 — `/runs/{id}/stages/{code}/retry` writes illegal state transition
- **Severity:** Medium · **Confidence:** Medium · **Category:** Orchestration / Validation
- **Location:** `modules/api.py:5737-5744`; `modules/db.py:5445-5463` (`allowed` map).
- **Problem:** Endpoint calls `set_job_phase_state(run_id, stage_code, 'pending')`, but `allowed` prevents `pending` from most states (e.g. `running`, `queued`, `cancel_requested`). Depending on strictness → 500 or silent no-op. Also, no dispatcher bump after reset.
- **Fix:** reset to `queued`; validate transitions; trigger dispatcher.

### Finding 18 — `retry_run` / `_reenqueue_job` copy-paste divergence
- **Severity:** Low · **Confidence:** High · **Category:** Maintainability / Logic
- **Location:** `modules/api.py:5610-5663` vs `5665-5716`.
- **Problem:** Near-identical functions with divergent defaults. `orig_job_type` default is `"indexing"` in `_reenqueue_job` vs `"scoring"` in `retry_run`. Default-phase recovery differs.
- **Fix:** consolidate into one helper.

### Finding 19 — `submit_run` overwrites `augment_queue_payload_for_audit`'s `post_run_audit`
- **Severity:** Low · **Confidence:** Medium · **Category:** Logic
- **Location:** `modules/api.py:5305` then `5314-5315`.
- **Problem:** Ordering is fragile: client's `post_run_audit` always wins, including `False`. Future re-ordering will silently flip behavior.
- **Fix:** make precedence explicit and documented in one place.

### Finding 20 — Tools tab count inert
- **Severity:** Low · **Confidence:** Low · **Category:** UI
- **Location:** `RunsPage.tsx:113`. Minor.

### Finding 21 — `/ws/updates` has no origin/auth check
- **Severity:** Low (Medium if exposed off-loopback) · **Confidence:** Medium · **Category:** Security
- **Location:** `hooks/useWebSocket.ts:6`; backend WS handler (not re-read in this pass).
- **Problem:** Client derives WS URL from `location.host`; backend likely accepts any Origin. Any browser tab on the same machine can subscribe to run logs.
- **Fix:** validate Origin / CSRF-safe upgrade header; bind to loopback only by default.

### Finding 22 — `toLocaleTimeString` on unvalidated `line.ts` can throw
- **Severity:** Low · **Confidence:** Medium · **Category:** UI robustness
- **Location:** `LogPanel.tsx:130`.
- **Problem:** No try/catch around `new Date(line.ts).toLocaleTimeString()`. A malformed WS producer breaks the whole log panel.

### Finding 23 — `_normalize_jobs_table_row` silently coerces bad `scope_paths` to `[]`
- **Severity:** Low · **Confidence:** High · **Category:** Observability
- **Location:** `modules/api.py:166-175`.
- **Problem:** `JSONDecodeError` → `[]` without log context; UI shows "(unknown)".
- **Fix:** `logger.warning` including row id.

### Finding 24 — `resume_run`/`force_run` don't verify `job_phases` exist before requeue
- **Severity:** Low-Medium · **Confidence:** Medium · **Category:** Orchestration
- **Location:** `modules/api.py:5404-5428`, `_resume_job_inplace:5591-5608`.
- **Problem:** If Finding 3 manifested at creation (phases never created), resume re-queues an empty-phase job.

### Finding 25 — `wsStore.addLogLine` copies a 500-element array per message
- **Severity:** Low · **Confidence:** High · **Category:** Performance
- **Location:** `wsStore.ts:62-67`. Under busy runs this is N events × O(500) copy × re-renders on all subscribers (amplified by Finding 13).

### Finding 26 — `get_jobs` uses `SELECT *`
- **Severity:** Low · **Confidence:** Medium · **Category:** Security / Contract
- **Location:** `modules/db.py:6116`. New columns flow to API without explicit contract review (including potentially sensitive internal columns).

### Finding 27 — Empty-state flicker on tab switch
- **Severity:** Low · **Confidence:** High · **Category:** UI state
- **Location:** `RunsPage.tsx:118-124`. On first History open, `historyLoading` may resolve quickly with stale empty array; EmptyState flashes before data.
- **Fix:** gate EmptyState on `historyPayload !== undefined`.

### Finding 28 — Force on queued returns success even when it did nothing
- **Severity:** Low · **Confidence:** High · **Category:** UX / Contract
- **Location:** `RunCard.tsx:146-157`; `modules/api.py:5560-5568`. Response says `"no ghost runners found — dispatcher should dequeue normally"` but UI shows generic success with no differentiation.

### Finding 29 — Polling + `runsVersion` invalidation doubles fetches
- **Severity:** Low · **Confidence:** High · **Category:** Performance
- **Location:** `RunsPage.tsx:25-40` + `RunDetailPage.tsx:32-46`. WS bumps re-key the query and the 5-s `refetchInterval` still fires; under WS traffic fetch rate becomes effectively per-message.

### Finding 30 — Static bundle deletions/adds in git status
- **Severity:** Low · **Confidence:** Medium · **Category:** Build / deployment
- **Location:** `static/app/index.html`, `static/app/assets/*`. Deleted `index-fUQr6KKJ.js` + `index-BxSCy5JP.css` and new `index-BxXg3rOS.js` + `index-CnvFmigM.css`. If `index.html` still references the deleted hash in any served copy, `/ui/runs` 404s on the bundle.

---

## 4. Cross-layer contract mismatches

| Area | Backend behavior | Frontend assumption | Risk |
|------|------------------|---------------------|------|
| `RunSubmitRequest` | Pydantic `extra="forbid"`; knows `run_mode`, `generate_captions` | TS type omits both; sends legacy `skip_done/force_rerun/fix_incomplete_stages` | UI cannot set `run_mode` directly; any future extra field → 422. |
| `Run.scope_paths` | Always list after normalize | Array + fallback to `[input_path]` | OK, but null status falls through to "(unknown)" silently. |
| Job status enum | DB contains `canceled` and `cancelled` | TS union only `'canceled'` | UK rows mis-classified (Finding 10). |
| `StageState` | DB emits `pending|queued|running|paused|cancel_requested|restarting|completed|failed|interrupted|skipped|canceled` | TS union `pending|running|completed|failed|skipped|interrupted` | `queued`, `paused`, `cancel_requested`, `restarting`, `canceled` render raw. |
| `WorkItem.status` | Backend emits varied values | TS union `pending|running|done|skipped|failed` | Unknown strings silently passed through. |
| `reportSupported` | Backend sends `capabilities.execution_report` | Frontend duplicates logic via `job_type` | Two sources of truth. |
| `/runs/{id}/stages/{code}/retry` | Writes `pending` | Backend `allowed` map disallows most transitions → 500 or silent no-op (Finding 17). |
| `/runs/{id}/cancel` on queued | Flips only `cancel_requested` | UI shows "canceled" (Finding 6). |

---

## 5. Highest-risk bug candidates (explain most likely user-visible failures)

1. **Cancel does nothing for indexing/metadata/bird_species** (Finding 1).
2. **Active/Queued rows dropped beyond limit=120** (Finding 2).
3. **Enqueue-vs-create_job_phases race** (Finding 3).
4. **pause_run overwriting terminal status** (Finding 5) + **resume wiping error_message** (Finding 7).
5. **Queued-cancel illusion** (Finding 6).
6. **force_run ghost reset race** (Finding 9).
7. **StageState / status enum drift** — badges and gating silently mis-render for paused/restarting/cancel_requested/canceled(UK).

---

## 6. Test gaps

- No pytest covers end-to-end submit → phases present → dispatcher pickup.
- No test for cancel on each of seven phase types.
- No test for pause race (status flip during pause window).
- No test that `retry_run` refuses non-terminal sources (because it doesn't).
- No test asserting `resume_job_phases` preserves `error_message`.
- No frontend integration test with >120 jobs.
- No test covering `canceled` vs `cancelled` client-side.
- No test covering `get_run_diagnostics` aggregate failure path.
- No contract test ensuring Pydantic `RunSubmitRequest` matches TS `RunSubmitRequest`.
- No test covering `/runs/{id}/stages/{code}/retry` transition legality.

---

## 7. Observability gaps

- `_normalize_jobs_table_row` swallows JSON decode errors without row id.
- `get_run_diagnostics` swallows phase-aggregate failures (no field in response).
- `resume_job_phases` destroys `error_message` history without archiving.
- No structured log when `cancel_run` enters its phase-loop fallback (ops can't tell which phase was stopped).
- No metric for "jobs enqueued without phases rows" (Finding 3).
- No WS heartbeat / last-seen timestamp in `wsStore` — UI cannot distinguish "silent" from "dead" connection.
- No request ID threading API → runner → logs, making diagnostics un-stitchable.
- `_json_response_db` logs only on serialization failure; no success sampling for contract drift detection.

---

## 8. Suggested remediation plan

### Quick wins (≤1 day each)
1. Add `'cancelled'` + missing `StageState` values to TS unions; normalize server-side.
2. Gate `retry_run` on terminal statuses.
3. Add warnings in `_normalize_jobs_table_row` + `get_run_diagnostics` error paths.
4. Use shallow selectors in `useWebSocket`; drop `const store = useWsStore()`.
5. Clamp UI progress percent.
6. Return 202 from `cancel_run` on queued when only flag set; distinguish in toast.

### Medium (1–3 days)
7. Rewrite cancel → single `dispatcher.cancel(run_id)` with full phase coverage.
8. Server-side filtering endpoints for Active/Queued tabs.
9. Atomic pause via conditional UPDATE + affected-row branching.
10. Wrap `enqueue_job + create_job_phases` in a transaction; or flip status after phases exist.
11. Preserve phase `error_message` history (new `job_phase_events` table or archive JSON).
12. Consolidate `retry_run` / `_reenqueue_job`.
13. Contract test (Pydantic ↔ TS) via schema codegen / snapshot.

### Deeper refactors
14. Unify capability source (kill frontend duplicate of `supportsExecutionReport`).
15. Shared run_state enum (Python/TS via generated schema).
16. WS-first refresh with polling as watchdog.
17. `RunnerHealth` abstraction with per-runner locks for ghost detection.

### Tests to add first
- Cancel × every `job_type`.
- Pause race (threaded test: runner completes mid-pause).
- Enqueue → phases invariant under parallel submit.
- Frontend: 150-job list, tab counts correct; history pagination clamp stability.

### Instrumentation to add first
- Structured log on every `update_job_status` transition incl. rows affected.
- Metric: `jobs_without_phases_total`.
- Counter: `cancel_fallback_phase_iterated_total`.
- WS heartbeat every 10 s + UI "stale WS" indicator.

---

## Caveats

- Did not read `db.request_cancel_job`, `augment_queue_payload_for_audit`, `job_dispatcher.get_state`, WS origin/auth handler, or individual runner internals. Several Medium findings (6, 9, 17, 19, 21) are inferred from call sites; confirm before remediation.
- The review is current as of commit at branch `master` (tree state from `git status` at review time).
