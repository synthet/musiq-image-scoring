# Run options (ScopeSelector) vs backend behavior

The **New Run** modal ([`frontend/src/components/scope/ScopeSelector.tsx`](../../frontend/src/components/scope/ScopeSelector.tsx)) exposes four options. They map to [`POST /api/runs/submit`](../../modules/api.py) fields, then to a canonical **`run_mode`** ([`modules/run_modes.py`](../../modules/run_modes.py)) and queue payload flags.

## Audit findings (logged 2026-05-07)

These items were verified against [`modules/job_dispatcher.py`](../../modules/job_dispatcher.py), [`modules/run_modes.py`](../../modules/run_modes.py), [`modules/workflow_healing.py`](../../modules/workflow_healing.py), and the React Runs UI.

| Finding | Severity | Resolution / notes |
|---------|----------|---------------------|
| **Validation-repair vs `run_mode`** | Correctness | With `validation_repair_mode=True`, the request validator previously returned early and left **`run_mode`** at its default **`process_unprocessed_or_empty`**. Submit still set `payload["skip_existing"]=False`, but **`JobDispatcher._run_mode_flags`** recomputes flags from **`run_mode`** (+ booleans) and ignored that lone override—so indexing/metadata/scoring could still behave like “skip done” internally. **`RunSubmitRequest`** now forces **`run_mode="validate_and_repair"`** when `validation_repair_mode` is true ([`modules/api.py`](../../modules/api.py)). |
| **Dispatcher vs payload `skip_existing`** | Design | Runners are driven by flags derived from canonical `run_mode`, not by mutating `queue_payload` in isolation. Any future mode must keep **`run_mode`** and payload booleans aligned. |
| **Culling + repair queues** | Gap | `resolved_image_ids` / per-stage queues are **not** applied to **`SelectionRunner`** (culling); dispatch logs this. Full-folder culling runs even when a repair plan targeted a subset. |
| **Bird species + overwrite** | Gap | Bird-species dispatch uses **`payload.get("overwrite", False)`** only; global **`process_all_overwrite`** does not automatically set that field on the payload today. |
| **Runs → Tools “Heal”** | UX / safety | Workflow heal ([`POST /api/maintenance/heal/{phase_code}`](../../modules/api.py)) should only spawn jobs with **`validate_and_repair`** (`fix_incomplete_stages` semantics). The Runs **Tools** tab no longer exposes other execution modes; it always sends `validate_and_repair` ([`frontend/src/components/runs/RunsToolsTab.tsx`](../../frontend/src/components/runs/RunsToolsTab.tsx)). |
| **Tests** | Coverage | [`tests/integration/test_runs_submit_modes_e2e.py`](../../tests/integration/test_runs_submit_modes_e2e.py) (`pytest -m postgres`) asserts queue payload and scoring `skip_existing` for all four SPA-shaped modes. |

**Related walkthrough:** [RUNS_WALKTHROUGH.md](RUNS_WALKTHROUGH.md) §3.

## 1. Canonical `run_mode` and flag matrix

| UI option | `skip_done`¹ | `force_rerun`¹ | `fix_incomplete_stages`¹ | `validation_repair_mode` | Canonical **`run_mode`** | `skip_done`² | `skip_existing`² | `force_rerun`² | `fix_incomplete_stages`² | `overwrite`² | `force_rescan`² |
|-----------|-------------|----------------|---------------------------|---------------------------|--------------------------|-------------|------------------|----------------|-------------------------|-------------|----------------|
| Process NEW / NOT processed | true | false | false | false | `process_unprocessed_or_empty` | true | true | false | false | false | false |
| Process ALL (overwrite) | false | true | false | false | `process_all_overwrite` | false | false | true | false | true | true |
| Fix missing/incomplete data | true | false | true | false | `validate_and_repair`³ | false | false | false | true | false | true |
| Validation-repair pipeline | true | false | false | true | `validate_and_repair`⁴ | false | false | false | true | false | true |

¹ Fields sent by the SPA (legacy-shaped); ignored when the client sends an explicit `run_mode` on the request body.

² From [`resolve_run_mode_flags`](../../modules/run_modes.py) after normalization. Submit also runs [`build_validation_repair_plan`](../../modules/db_legacy.py) when `validation_repair_mode` **or** `fix_incomplete_stages` is true, and attaches `resolved_image_ids_by_stage` / `validation_repair_summary`.

³ Inferred by [`infer_run_mode`](../../modules/run_modes.py) when `fix_incomplete_stages=True`.

⁴ `RunSubmitRequest` sets `run_mode` to `validate_and_repair` whenever `validation_repair_mode=True` so enqueue/dispatch semantics match **Fix missing/incomplete** (see §3).

### Behavior intents (cross-check UI copy)

| Question | NEW | ALL | Fix incomplete | Validation-repair |
|----------|-----|-----|----------------|-------------------|
| Skip images already **done** for a stage (`skip_existing`)? | Yes | No | No | No |
| Replace existing stage outputs (`overwrite` / forced recompute)? | No | Yes | Only where incomplete / queued | Only where preview queue says so |
| Build repair queues from validation scan? | No | No | Yes (same plan hook) | Yes (preview encouraged first) |

## 2. Dispatcher → runner wiring

[`JobDispatcher._run_mode_flags`](../../modules/job_dispatcher.py) derives flags from **`run_mode`** and payload booleans (`skip_done`, `force_rerun`, `fix_incomplete_stages`), **not** from a lone `payload["skip_existing"]` override unless `run_mode` matches. That is why **Validation-repair** must normalize to `validate_and_repair`.

Per phase, the dispatcher passes roughly:

| Phase | Primary arguments from flags / payload |
|--------|----------------------------------------|
| **Indexing** | `skip_existing` from flags; **`resolved_image_ids`** from repair plan narrows scope |
| **Metadata** | `skip_existing` from flags; **`resolved_image_ids`** narrows rows |
| **Scoring** | `skip_existing` from flags unless `fix_incomplete_stages` **and** `resolved_image_ids` → forced `skip_existing=False` for that dispatch |
| **Keywords** | `overwrite` from flags |
| **Clustering** | `force_rescan` from flags (or clustering API `force_rescan`) |
| **Culling (selection)** | `force_rescan`; **`resolved_image_ids` not applied** — full folder pass (logged as advisory-only) |

**Bird species** uses `overwrite` from the payload boolean, not from `RUN_MODE_FLAGS` in the dispatcher (only `payload.get("overwrite", False)`).

## 3. Orchestration (`PipelineOrchestrator`)

The queue-based **`job_phases`** flow advances phases after each runner completes; the orchestrator coordinates ordering and aggregates. Run mode affects **what each runner skips or overwrites**, not the high-level phase order table in [`PipelineOrchestrator.PHASE_ORDER`](../../modules/pipeline_orchestrator.py).

## 4. Deliberate limitations / drift

| Area | Notes |
|------|--------|
| Culling | Per-image queues from validation-repair are **not** passed into `SelectionRunner` today. |
| Bird species | `process_all_overwrite`’s overwrite intent is **not** wired through mode flags on dispatch. |
| Preview | Validation-repair UI copy recommends **Refresh** on preview before apply; **`validation_repair_dry_run`** on submit is separate from modal preview. |

## 5. Related files

- UI: [`frontend/src/components/scope/ScopeSelector.tsx`](../../frontend/src/components/scope/ScopeSelector.tsx) — `RUN_OPTION_COPY_BY_MODE`, `submit()`.
- API: [`modules/api.py`](../../modules/api.py) — `RunSubmitRequest`, `submit_run` (normalization of `validation_repair_mode` → `run_mode`).
- Flags: [`modules/run_modes.py`](../../modules/run_modes.py).
- Dispatch: [`modules/job_dispatcher.py`](../../modules/job_dispatcher.py).
- Integration coverage: [`tests/integration/test_runs_submit_modes_e2e.py`](../../tests/integration/test_runs_submit_modes_e2e.py).
