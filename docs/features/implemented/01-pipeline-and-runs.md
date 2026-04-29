# Pipeline and runs

**Purpose:** Orchestrate discovery through tagging (and optional clustering/bird-ID) as persisted **jobs** / **runs**, with queueing, pause/resume/cancel, and live status.

**User-visible behavior:** Operators submit work on folder or selector scope; the UI shows per-stage progress, queue position, and history. Stage names in product copy map to DB `phase_code` values — see [PIPELINE_TERMINOLOGY](../../technical/PIPELINE_TERMINOLOGY.md).

**Primary code paths:** `modules/phases.py` (`PhaseCode`), `modules/phases_policy.py`, `modules/pipeline_orchestrator.py`, `modules/job_dispatcher.py`, `modules/phase_executors.py`, enqueue paths in `modules/api.py`. **Policy introspection:** `GET /api/phases/decision` (query `image_id`, `phase_code`, …) surfaces why a phase would run or skip for one image.

**Main HTTP API (prefix `/api`):**

- **Legacy / runner-aligned:** `POST /api/pipeline/submit`; `POST /api/pipeline/run/pause|cancel|restart`; `POST /api/pipeline/phase/restart-from`; `POST /api/pipeline/phase/skip|retry`; `POST /api/pipeline/step/rerun`; `POST /api/pipeline/phase/backfill-index-meta`
- **Runs (preferred UI surface):** `POST /api/runs/submit`, `POST /api/runs/validation-repair/preview`, `GET|POST /api/runs/{run_id}/…` (pause, resume, cancel, force, retry, stages, steps, items, diagnostics)
- **Scope & queue:** `POST /api/scope/preview`, `GET /api/scope/tree`, `GET /api/queue`, `POST /api/queue/reorder`
- **Jobs:** `GET /api/jobs/recent`, `GET /api/jobs/queue`, `GET /api/jobs/{job_id}`, `POST /api/jobs/{job_id}/cancel`, lifecycle under `/api/workflow-runs/…`, `/api/stage-runs/…`, `/api/step-runs/…`
- **Unified snapshot:** `GET /api/tasks/active`
- **Incidents:** `GET /api/incidents`, `GET /api/incidents/{incident_id}`

**Real-time:** WebSocket `ws://<host>:<port>/ws/updates` (see `webui.py`) pushes job/run events to the React SPA.

**Related docs:** [PIPELINE_PHASE_RUNNERS](../../technical/PIPELINE_PHASE_RUNNERS.md) · [API_CONTRACT](../../technical/API_CONTRACT.md) · [RUNS_QUEUE_AND_RESTART](../../technical/RUNS_QUEUE_AND_RESTART.md)
