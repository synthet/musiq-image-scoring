# Refactoring & Redesign Plan: Unified Stack + Culling Feature

## 1) Executive Summary

This plan replaces the current **Stacks** and **Culling** features with one simplified workflow-oriented feature that behaves like existing **Scoring** and **Keywords** tabs: single input path, run/stop controls, console log, and status/progress updates.

The new feature keeps using the same existing quality scores/models already used in the project (no new ML model family), but unifies the downstream operations:

1. Build stack/burst groups in DB.
2. Write stack/burst IDs to metadata files.
3. Mark the bottom 33% as rejected.
4. Mark the top 33% as picked.
5. Keep the middle 34% unflagged.

Old Stacks and Culling UIs remain temporarily available during migration, then are deprecated and removed.

---

## 2) Product Requirements (from request)

### Required behavior
- **Input**: folder path.
- **Process**:
  - Create stacks/bursts in DB.
  - Persist stack/burst IDs into files (sidecar/metadata layer).
  - Mark worst 33% as rejected.
  - Mark best 33% as picked.
- **Output UX**:
  - Console + status only (same style as Scoring/Keywords).
  - No grids, no gallery views, no manual visual review UI.
- **Clustering**:
  - Ignore `Default Time Gap` setting (do not expose/use it in the new feature).

### Explicit simplifications
- No stack gallery browsing.
- No manual selection/editing flow for stack content.
- No separate culling session browser.
- No duplicate UI complexity across Stacks/Culling.

---

## 3) Current-State Diagnosis

### Why current Stacks/Culling should be consolidated
1. **Two-feature overlap**: stack formation and culling decisions are currently split across separate tabs and flows.
2. **UI complexity mismatch**: existing Stacks/Culling include image galleries and manual operations, while requested workflow is batch automation only.
3. **Runner inconsistency**: Scoring/Keywords use a clear run/stop/status model; Stacks/Culling currently behave differently and are harder to operate consistently.
4. **Configuration confusion**: time-gap handling and stack settings are mixed between components; requested redesign explicitly wants this simplified and time-gap default ignored.

---

## 4) Target Feature Definition

## Feature name (working)
- **"Selection"** or **"Stack + Selection"** tab.

## User contract
- User provides folder path and starts job.
- System performs full pipeline end-to-end.
- System reports progress + summary in console/status.
- System updates DB and sidecar metadata in one run.

## Decision policy (fixed)
For each stack/burst:
- Sort by chosen score field (default: `score_general`).
- Mark:
  - top 33% => `pick`
  - bottom 33% => `reject`
  - middle => neutral
- Deterministic rounding policy must be explicit and stable.

Recommended deterministic rule:
- `k = floor(n * 0.33)` for pick and reject.
- For very small stacks (`n < 3`), apply safe fallback:
  - `n=1`: neutral (or pick if business wants one best always).
  - `n=2`: 1 pick, 1 reject only if explicitly desired; otherwise 1 pick, 1 neutral.

> Final rounding policy should be decided once and documented in config/help text to avoid behavior ambiguity.

---

## 5) Architecture Changes

## 5.1 Backend service unification
Create a dedicated orchestrator service (example module):
- `modules/selection.py`

Responsibilities:
1. Validate input path.
2. Resolve image scope.
3. Trigger stack/burst creation (reuse clustering/db logic).
4. Compute pick/reject bands from existing score columns.
5. Persist decisions to DB.
6. Write stack/burst IDs + decisions to sidecar metadata.
7. Emit structured progress/log events.

This service should become the **single source of truth** for this workflow.

## 5.2 Runner integration (Scoring/Keywords style)
Add runner class (example):
- `SelectionRunner` in `modules/engine.py` or dedicated runner file.

Runner contract should match existing pattern:
- `start_batch(input_path, ...)`
- `stop()`
- `get_status() -> (running, log, status_msg, cur, tot)`

This guarantees simple polling-based UI integration with no gallery dependencies.

## 5.3 UI tab redesign
Add new tab module:
- `modules/ui/tabs/selection.py`

UI should mirror Scoring/Keywords style:
- Input folder textbox.
- Start button.
- Stop button.
- Status card.
- Console output accordion.

No gallery, no stack browser, no review controls.

## 5.4 Metadata writer extension
Extend metadata layer (likely `modules/xmp.py`) to include:
- stack/burst identifier fields (namespaced custom fields if needed).
- pick/reject flags consistent with current culling export strategy.

Must support idempotent re-runs (safe overwrite of same IDs/flags).

## 5.5 DB layer updates
DB requirements:
- Ensure stack table + image linkage supports fast re-clustering per folder.
- Ensure decision states are stored in a normalized, queryable way.
- Add/confirm indexes for batch updates and status summary queries.

Potential additions:
- Job table entry type for selection runs.
- Audit fields: last selection run timestamp, policy version.

---

## 6) Deprecation & Migration Strategy

## Phase A (parallel rollout)
1. Ship new unified feature as primary recommended workflow.
2. Keep old Stacks/Culling tabs but mark as deprecated in labels/help text.
3. Route new docs/scripts to unified feature only.

## Phase B (soft deprecation)
1. Hide old tabs behind config flag (default off).
2. Keep backend compatibility shims for any scripts/API still calling old entrypoints.
3. Emit deprecation warnings in logs when legacy entrypoints are used.

## Phase C (removal)
1. Remove old Stacks and Culling tab code.
2. Remove unused session/gallery legacy functions.
3. Keep migration note and changelog for users.

---

## 7) Implementation Plan (Work Breakdown)

## WP1 — Domain Contract & Policy Lock
- Define final 33/33 split rounding behavior.
- Define tie-breaking order (e.g., score desc, created_at asc, id asc).
- Define small-stack fallback behavior.
- Define exactly which score field is authoritative.

Deliverables:
- Policy constants.
- Technical doc snippet + inline help text.

## WP2 — Orchestrator Service
- Implement unified service with staged pipeline methods:
  - `scan_images`
  - `create_or_refresh_stacks`
  - `assign_pick_reject`
  - `write_metadata`
  - `finalize_summary`
- Add robust error handling with partial-failure reporting.

Deliverables:
- New service module and unit tests for policy math.

## WP3 — Runner + UI Tab
- Add runner with Scoring/Keywords-compatible status interface.
- Add new tab with minimal controls and output.
- Register tab in app navigation.

Deliverables:
- New UI tab and status polling integration.

## WP4 — Metadata/DB Integration
- Implement stack/burst ID writing.
- Ensure pick/reject write path reuses stable existing culling-compatible exporter.
- Add DB updates for decisions and run metadata.

Deliverables:
- Integration tests validating DB + sidecar outputs.

## WP5 — Legacy Deprecation
- Mark old tabs deprecated.
- Add compatibility wrappers and warnings.
- Add removal timeline.

Deliverables:
- Deprecated notices + changelog entry.

## WP6 — Removal (after validation period)
- Remove old stacks/culling UI and dead code.
- Keep only unified feature paths.

Deliverables:
- Cleaned codebase and updated docs.

---

## 8) Testing Strategy

## Unit tests
- 33/33 assignment function for stack sizes 1..N.
- Tie-break deterministic behavior.
- Ignore-default-time-gap behavior (ensure no default gap config path is used).

## Integration tests
- End-to-end on sample folder:
  - stacks created in DB,
  - decisions persisted,
  - sidecar metadata contains stack/burst IDs and pick/reject flags.
- Re-run idempotency test (same input path twice).

## Regression tests
- Scoring and Keywords tabs still unaffected.
- Legacy Stacks/Culling (during Phase A/B) still callable if enabled.

## Operational checks
- Console status increments across all stages.
- Stop behavior safe mid-run and leaves DB in consistent state.

---

## 9) Risk Register & Mitigations

1. **Rounding ambiguity risk**
   - Mitigation: lock policy in constants + docs + tests before coding.

2. **Metadata compatibility risk**
   - Mitigation: continue using existing proven pick/reject writer path; add verification read-back tests.

3. **Large-folder performance risk**
   - Mitigation: batch DB updates, incremental logging, and optional chunked writes.

4. **Legacy breakage risk**
   - Mitigation: phased deprecation and compatibility wrappers.

5. **User expectation mismatch (no visual review)**
   - Mitigation: explicit UI text: "automated batch mode, no gallery review in this tab."

---

## 10) Minimal UX Specification

Tab title: `Selection` (or `Stack + Selection`)

Controls:
- `Input Folder Path`
- `Force Re-run` (optional)
- `Start`
- `Stop`

Outputs:
- Status message (current stage + %)
- Console log stream
- Final summary block:
  - total images
  - total stacks
  - picks count (%), rejects count (%), neutral count (%)
  - metadata write success/failure counts

No galleries, thumbnails, stack browser, or culling review widgets.

---

## 11) Rollout Milestones

- **M1**: Policy locked + tests green.
- **M2**: Unified backend service complete.
- **M3**: New runner and tab integrated.
- **M4**: Deprecation notices added to old tabs.
- **M5**: Production validation complete.
- **M6**: Legacy stacks/culling removed.

---

## 12) Definition of Done

The redesign is complete when:
1. One unified feature performs stack creation + pick/reject assignment in one run.
2. It uses scoring/keywords-style run/stop/status/console UX.
3. It writes stack/burst IDs and pick/reject decisions to metadata.
4. It applies the fixed 33% worst reject / 33% best pick policy.
5. Default Time Gap is not used in this workflow.
6. Legacy Stacks and Culling are formally deprecated (and later removed per phase plan).

---

## 13) Step-by-Step Evaluation Matrix ("Evaluate each step")

This section defines how each implementation step is evaluated before moving forward.

### Step 1 / WP1 — Domain Contract & Policy Lock
**Evaluation goal**: policy is unambiguous and testable.

**Pass criteria**
- One documented rounding policy for 33% pick / 33% reject exists.
- One deterministic tie-break order is documented and implemented.
- Small-stack behavior (`n=1`, `n=2`) is explicitly defined.
- Unit tests cover at least stack sizes `1..10` and edge score ties.

**Evidence to collect**
- Policy constants in code.
- Unit test output.
- Short design note/changelog entry.

**Fail signals**
- Conflicting behavior between docs and implementation.
- Any non-deterministic test result for tie scenarios.

### Step 2 / WP2 — Orchestrator Service
**Evaluation goal**: one end-to-end backend entrypoint executes all stages reliably.

**Pass criteria**
- Orchestrator exposes a single public run method.
- Stage-level progress and logs emitted for all stages.
- Controlled failure in one stage returns actionable error summary.
- Stop/cancel path leaves DB in consistent state.

**Evidence to collect**
- Integration test logs with stage transitions.
- Simulated failure test output (e.g., metadata write failure case).

**Fail signals**
- Partial completion without status/reporting.
- Silent failures or orphaned intermediate records.

### Step 3 / WP3 — Runner + UI Tab
**Evaluation goal**: UX matches Scoring/Keywords interaction model.

**Pass criteria**
- Tab has only: input path, start, stop, status, console.
- Polling status contract matches existing runners.
- No grid/gallery/manual review elements rendered.
- Run/stop button interactivity toggles correctly.

**Evidence to collect**
- UI smoke test results.
- Optional screenshot of final tab state.

**Fail signals**
- Additional complex controls reintroduced.
- Runner status fields inconsistent with existing tabs.

### Step 4 / WP4 — Metadata + DB Integration
**Evaluation goal**: core business outputs are correct and persistent.

**Pass criteria**
- DB stacks/bursts created/updated for target folder.
- Top 33% flagged pick, bottom 33% flagged reject per policy.
- Stack/burst IDs written to sidecar metadata.
- Re-run is idempotent (no duplicate/conflicting state).

**Evidence to collect**
- DB query snapshots before/after run.
- Sidecar validation sample set.
- Idempotency test output from two consecutive runs.

**Fail signals**
- Decision percentages deviate from policy.
- Metadata write succeeds in DB but not in sidecars (or vice versa) without error reporting.

### Step 5 / WP5 — Legacy Deprecation
**Evaluation goal**: migration is safe and visible.

**Pass criteria**
- Legacy tabs/features visibly labeled deprecated.
- Config flag can disable legacy UIs by default.
- Legacy API calls produce deprecation warnings.
- Migration notes available for users.

**Evidence to collect**
- UI label verification.
- Deprecation log samples.
- Documentation/changelog references.

**Fail signals**
- Hidden breaking changes without warnings.
- Legacy paths still used by default.

### Step 6 / WP6 — Legacy Removal
**Evaluation goal**: cleanup complete with no regression in supported flows.

**Pass criteria**
- Legacy stacks/culling UI code removed.
- Dead code and unused DB/session helpers removed.
- Regression tests for Scoring/Keywords and new feature pass.
- Release note confirms removal and replacement workflow.

**Evidence to collect**
- Test run summary.
- Diff summary showing removed legacy modules/handlers.

**Fail signals**
- Broken imports/routes after removal.
- New feature missing parity with promised workflow.

### Global Go/No-Go Rule
Move to next step only when:
1. Current step pass criteria are all met.
2. Required evidence is attached to PR.
3. No unresolved fail signals remain.


---

## 14) Detailed Technical Design (Implementation-Ready)

## 14.1 Proposed module/class layout

```text
modules/
  selection.py                # New orchestrator service
  selection_policy.py         # Pure policy math + deterministic ranking
  selection_metadata.py       # Metadata writers/readers (stack ids + flags)
  engine.py                   # Add SelectionRunner (or separate runner module)
  ui/tabs/selection.py        # New simple tab (scoring/keywords style)
```

**Responsibilities split**
- `selection_policy.py`: no I/O, pure deterministic functions; easiest place for unit tests.
- `selection.py`: orchestrates DB + policy + metadata side effects.
- `selection_metadata.py`: sidecar/XMP write abstractions and verification helpers.
- `SelectionRunner`: lifecycle (`start_batch`, `stop`, `get_status`) for UI polling.

## 14.2 Core orchestrator contract

```python
# modules/selection.py
from dataclasses import dataclass
from typing import Callable, Optional

ProgressCb = Callable[[float, str], None]

@dataclass
class SelectionConfig:
    score_field: str = "score_general"
    pick_fraction: float = 0.33
    reject_fraction: float = 0.33
    force_rescan: bool = False
    write_stack_ids: bool = True
    write_pick_reject: bool = True
    verify_sidecar_write: bool = True

@dataclass
class SelectionSummary:
    total_images: int
    total_stacks: int
    picked: int
    rejected: int
    neutral: int
    sidecar_written: int
    sidecar_errors: int
    status: str

class SelectionService:
    def run(self, input_path: str, cfg: SelectionConfig, progress_cb: Optional[ProgressCb] = None) -> SelectionSummary:
        ...

    def stop(self) -> None:
        ...
```

## 14.3 Deterministic policy implementation

Decision must be deterministic across reruns, including ties.

**Recommended ranking order**
1. `score_field` DESC (higher is better)
2. `created_at` ASC
3. `id` ASC

**Reference policy helper**

```python
# modules/selection_policy.py
from math import floor

def band_sizes(n: int, frac: float = 0.33) -> tuple[int, int]:
    if n <= 0:
        return 0, 0
    k = floor(n * frac)
    return k, k  # picks, rejects


def classify_sorted_ids(sorted_ids: list[int], frac: float = 0.33) -> dict[int, str]:
    n = len(sorted_ids)
    picks, rejects = band_sizes(n, frac)

    # optional small-n override (must be fixed by policy)
    if n == 1:
        return {sorted_ids[0]: "neutral"}
    if n == 2:
        return {sorted_ids[0]: "pick", sorted_ids[1]: "neutral"}

    out = {}
    for i, image_id in enumerate(sorted_ids):
        if i < picks:
            out[image_id] = "pick"
        elif i >= n - rejects:
            out[image_id] = "reject"
        else:
            out[image_id] = "neutral"
    return out
```

## 14.4 End-to-end run pipeline (stage sequence)

```text
1) Validate input path and normalize path
2) Resolve candidate images from DB for folder
3) Create/refresh stacks (clustering)
4) Load stack members + score fields
5) Apply deterministic 33/33 policy per stack
6) Persist decisions to DB in batches
7) Write stack/burst IDs + pick/reject to sidecars
8) Verify sidecar write (optional but recommended)
9) Emit summary and finalize job state
```

Each stage should emit progress text like:
- `"Scanning images..."`
- `"Clustering stacks..."`
- `"Assigning pick/reject bands..."`
- `"Writing metadata..."`
- `"Verifying metadata..."`

## 14.5 DB transaction strategy

**Suggested transaction boundaries**
- Tx A: stack creation/refresh updates
- Tx B: decision writes (`pick/reject/neutral`) in chunked batches
- Tx C: job summary + audit metadata

This avoids long-running monolithic transactions while keeping rollback scope sensible.

**Suggested batch size**
- 500–2000 rows/update batch depending on DB latency and lock behavior.

**Pseudo-SQL examples**

```sql
-- Upsert/refresh stack assignment for image
UPDATE IMAGES
SET STACK_ID = ?, UPDATED_AT = CURRENT_TIMESTAMP
WHERE ID = ?;

-- Persist selection decision
UPDATE IMAGES
SET CULL_DECISION = ?, CULL_POLICY_VERSION = ?, UPDATED_AT = CURRENT_TIMESTAMP
WHERE ID = ?;

-- Optional run audit
INSERT INTO JOBS (JOB_TYPE, INPUT_PATH, STATUS, STARTED_AT)
VALUES ('selection', ?, 'running', CURRENT_TIMESTAMP);
```

## 14.6 Metadata writing format suggestions

Use one authoritative flag representation already compatible with existing culling export.

**Suggested fields**
- Stack/burst ID:
  - `xmp:Subject` token pattern: `stack:<id>` (fallback)
  - or dedicated custom namespace field `sel:stackId`
- Decision:
  - existing pick/reject writer pathway (do not invent second decision schema)

**Write verification**
- after write, read back subset and assert:
  - stack ID exists and matches DB
  - pick/reject state matches DB

## 14.7 Runner details (Scoring/Keywords parity)

```python
# shape only
class SelectionRunner:
    def start_batch(self, input_path: str, force_rescan: bool = False) -> str: ...
    def stop(self) -> None: ...
    def get_status(self) -> tuple[bool, str, str, int, int]: ...
```

**Behavior contract**
- `start_batch` returns immediate "starting" message and spawns thread.
- `get_status` is poll-safe and lock-protected.
- `stop` sets cancellation token checked between all major stages and batch loops.

## 14.8 UI tab skeleton (minimal only)

```python
# modules/ui/tabs/selection.py (skeleton)
import gradio as gr


def create_tab(runner, app_config):
    with gr.TabItem("Selection", id="selection"):
        input_dir = gr.Textbox(label="📁 Input Folder Path", value=app_config.get("selection_input_path", ""))
        with gr.Row():
            run_btn = gr.Button("▶ Start Selection", variant="primary")
            stop_btn = gr.Button("⏹ Stop", variant="stop", interactive=False)
        status_html = gr.HTML(label="Status")
        log_output = gr.Textbox(lines=15, interactive=False, show_label=False)

        run_btn.click(fn=lambda p: runner.start_batch(p), inputs=[input_dir], outputs=[log_output])
        stop_btn.click(fn=runner.stop, inputs=[], outputs=[])

    return {"input_dir": input_dir, "run_btn": run_btn, "stop_btn": stop_btn, "status_html": status_html, "log_output": log_output}
```

## 14.9 Configuration additions (explicit, simple)

```json
{
  "selection": {
    "score_field": "score_general",
    "pick_fraction": 0.33,
    "reject_fraction": 0.33,
    "force_rescan_default": false,
    "verify_sidecar_write": true,
    "legacy_tabs_enabled": false
  }
}
```

Important: no `default_time_gap` dependency in this feature path.

## 14.10 Backward compatibility shims

During deprecation phase, old entrypoints should route into the new service where possible.

```python
# conceptual shim

def legacy_run_culling(folder_path, **kwargs):
    logger.warning("Deprecated: run_culling -> use SelectionService")
    return selection_service.run(folder_path, SelectionConfig())
```

## 14.11 Observability and diagnostics

Minimum logs per run:
- run_id, input_path, policy_version
- counts: images, stacks, picks, rejects, neutral
- sidecar success/failure counts
- elapsed time per stage

If MCP server is enabled, expose read-only run summary via existing diagnostic tool pattern.

## 14.12 Failure handling policy

- **Hard fail**: path invalid, DB unavailable, clustering fatal.
- **Soft fail**: subset of sidecars failed; run ends `completed_with_warnings`.

Summary should include first N failures (e.g., 20) + total count.

## 14.13 Concrete test matrix examples

```python
# unit tests (policy)
def test_band_sizes_small_values():
    assert band_sizes(1) == (0, 0)
    assert band_sizes(3) == (0, 0)
    assert band_sizes(4) == (1, 1)


def test_classify_sorted_ids_deterministic():
    ids = [10, 11, 12, 13, 14, 15]
    out1 = classify_sorted_ids(ids)
    out2 = classify_sorted_ids(ids)
    assert out1 == out2
```

```text
integration cases:
- folder with only singletons
- folder with large bursts (>100)
- folder with missing sidecar write permissions
- rerun same folder twice (idempotency)
- stop mid-run during metadata stage
```

## 14.14 Suggested delivery sequence (engineering)

1. Implement `selection_policy.py` + full unit tests first.
2. Build `SelectionService` with dry-run mode (no writes) for validation.
3. Add DB writes and idempotency checks.
4. Add metadata writing + verification.
5. Add `SelectionRunner` and simple UI tab.
6. Deprecate old tabs with warnings/config flag.
7. Remove legacy code after stabilization window.
