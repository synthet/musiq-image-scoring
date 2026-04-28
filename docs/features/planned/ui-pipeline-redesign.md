# Pipeline-Centric UI Redesign

**Status:** Proposal
**Date:** 2026-03-05
**Version:** 1.0

## Problem Statement

The current WebUI evolved tab-by-tab as features were added. The backend now has a proper 5-phase pipeline (INDEXING > METADATA > SCORING > CULLING > KEYWORDS) with per-image tracking in `IMAGE_PHASE_STATUS`, but the UI still presents processing as disconnected tabs. Users must:

- Switch to Folder Tree to select a folder and see phase badges
- Switch to Scoring tab to start/monitor scoring
- Switch to Keywords tab to start/monitor tagging
- Switch to Selection tab to start/monitor culling
- Switch back to Folder Tree to check overall status

The UI should reflect the pipeline as a **single, unified workflow**.

---

## Proposed Tab Structure

### Before: 7+ Tabs
```
[ Folder Tree ] [ Scoring ] [ Keywords ] [ Selection ] [ Gallery ] [ (Stacks) ] [ (Culling) ] [ Configurations ]
```

### After: 3 Tabs
```
[ Pipeline ] [ Gallery ] [ Settings ]
```

- **Pipeline** absorbs Folder Tree + Scoring + Keywords + Selection
- **Gallery** remains unchanged (browsing/inspection tool)
- **Settings** remains unchanged (renamed from "Configurations")
- **Stacks** and **Culling** legacy tabs are removed entirely

---

## Pipeline Tab Layout

The Pipeline tab is the default landing page. Two-column layout with persistent folder tree on the left and pipeline dashboard on the right.

```
+------------------------------------------------------------------+
| Vexlum Scoring WebUI                                               |
| [ Pipeline (active) ]  [ Gallery ]  [ Settings ]                  |
+------------------------------------------------------------------+
|                          |                                        |
|  FOLDER TREE PANEL       |  PIPELINE DASHBOARD                    |
|  (scale=1, ~280px)       |  (scale=3)                             |
|                          |                                        |
|  [Refresh]               |  A. PIPELINE STEPPER                   |
|                          |  ●----●----●----●----●                 |
|  / Photos                |  IDX  META SCORE CULL  KEYS            |
|    +-- D300/             |                                        |
|    |   +-- 28-70mm/      |  B. ACTION BAR                         |
|    |       +-- 2015/ [V] |  [Run All Pending]  [Stop All]         |
|    +-- D90/              |                                        |
|        +-- 10.5mm/       |  C. PHASE CARDS                        |
|            +-- 2013/ [P] |  +--------+ +--------+ +--------+     |
|                          |  | Score  | | Cull   | | Keyw.  |     |
|  -- Selected Folder --   |  | 32/48  | | 0/48   | | 0/48   |     |
|  D300/28-70mm/2015       |  | [Run]  | | [Run]  | | [Run]  |     |
|  48 images               |  +--------+ +--------+ +--------+     |
|                          |                                        |
|  [Open in Gallery]       |  D. ACTIVE JOB MONITOR                 |
|                          |  Scoring: 32/48 (66.7%)                |
|                          |  [================-------]             |
|                          |  > Console Output (expandable)         |
|                          |                                        |
+------------------------------------------------------------------+

Legend: [V] = all phases done, [P] = partial, [X] = failed
```

### Detailed UI Mockup (Desktop 1440x900)

```text
+--------------------------------------------------------------------------------------+
| Vexlum Scoring WebUI                                                  [Help] [Profile]|
| [ Pipeline ] [ Gallery ] [ Settings ]                                                 |
+-------------------------------+------------------------------------------------------+
| Folder Tree                   | Pipeline Dashboard                                   |
| [Refresh] [Collapse]          | Folder: /Photos/D300/28-70mm/2015      48 images    |
|-------------------------------|                                                      |
| > Photos                      | (1) IDX ---- (2) META ---- (3) SCORE ---- (4) CULL ---- (5) KEYS
|   > D300                      |     48/48       48/48          32/48         0/48         0/48
|     > 28-70mm                 |                                                      |
|       • 2015        [P]       | [Run All Pending]  [Stop All]  [Open in Gallery]    |
|   > D90                       |                                                      |
|     > 10.5mm                  | +----------------+ +----------------+ +----------------+
|       • 2013        [V]       | | SCORING        | | CULLING        | | KEYWORDS       |
|                               | | Running        | | Not Started    | | Not Started    |
| Selected Folder               | | 32/48          | | 0/48           | | 0/48           |
| D300/28-70mm/2015             | | [========--]   | | [----------]   | | [----------]   |
| 48 images                     | | [Run] [Opts]   | | [Run] [Opts]   | | [Run] [Opts]   |
| [Open in Gallery]             | +----------------+ +----------------+ +----------------+
|                               |                                                      |
|                               | Active Job Monitor                                   |
|                               | Scoring: Embeddings + Aesthetic (32/48, 66.7%)      |
|                               | [=========================------------]               |
|                               | > Console Output                                     |
|                               |   [10:12:21] model loaded                            |
|                               |   [10:12:24] scored IMG_1832.jpg                     |
+-------------------------------+------------------------------------------------------+
```

### Responsive UI Mockup (Mobile 390x844)

```text
+--------------------------------------------+
| [=] Vexlum                          |
| [Pipeline] [Gallery] [Settings]            |
+--------------------------------------------+
| Folder: D300/28-70mm/2015 (48)   [Change] |
|--------------------------------------------|
| IDX -> META -> SCORE -> CULL -> KEYS      |
| 48/48  48/48   32/48    0/48    0/48      |
|--------------------------------------------|
| [Run All Pending] [Stop]                   |
|--------------------------------------------|
| SCORING (Running) 32/48                    |
| [===================-----]                 |
| [Run] [Options]                            |
|--------------------------------------------|
| CULLING (Not Started)                      |
| [-------------------------]                |
| [Run] [Options]                            |
|--------------------------------------------|
| KEYWORDS (Not Started)                     |
| [-------------------------]                |
| [Run] [Options]                            |
|--------------------------------------------|
| Active Job: Scoring 66.7%                  |
| [===================-----]                 |
| [Expand Console]                           |
+--------------------------------------------+
```

Responsive behavior: the desktop left sidebar becomes a slide-out drawer on mobile; phase cards stack vertically; the active job monitor remains pinned below cards.

### Gradio Implementation

```python
with gr.TabItem("Pipeline", id="pipeline"):
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            # Section: Folder Tree Sidebar
            ...
        with gr.Column(scale=3):
            # Section A: Pipeline Stepper
            # Section B: Action Bar
            # Section C: Phase Cards
            # Section D: Active Job Monitor
            ...
```

---

## Section A: Pipeline Stepper

A horizontal visualization showing the 5-phase progression for the selected folder. Rendered as `gr.HTML()` with inline CSS, updated on folder selection.

```
  (1)---------(2)---------(3)---------(4)---------(5)
 INDEX       META       SCORE       CULL      KEYWORDS
  48/48       48/48      32/48       0/48        0/48
```

### Visual States

| State | Node Style | Color | Connector |
|-------|-----------|-------|-----------|
| Done | Filled circle | #3fb950 (green) | Green line to next |
| Running/Partial | Filled + pulse | #58a6ff (blue) | Blue animated line |
| Not Started | Outlined circle | #6e7681 (gray) | Gray line |
| Failed | Filled circle | #f85149 (red) | Red line |

### Implementation

Reuse `db.get_folder_phase_summary(folder_path)` which returns per-phase `{status, done_count, total_count}`. Build HTML in a new `_build_pipeline_stepper_html()` function.

INDEXING and METADATA appear in the stepper for visibility but have no independent "Run" button -- they execute implicitly during the Scoring pipeline's PrepWorker.

---

## Section B: Action Bar

A single row with two primary actions:

- **"Run All Pending"** (variant="primary") -- Runs all incomplete phases in sequence for the selected folder
- **"Stop All"** (variant="stop") -- Stops the active runner

### "Run All Pending" Logic

1. Call `db.get_folder_phase_summary(folder)`
2. Identify incomplete actionable phases (SCORING, CULLING, KEYWORDS)
3. Start the first incomplete phase's runner
4. On completion, automatically start the next (via pipeline orchestrator)

This requires a new `PipelineOrchestrator` class (see Backend Changes below).

---

## Section C: Phase Cards

Three interactive cards for the user-actionable phases: **Scoring**, **Culling**, **Keywords**.

Each card is a `gr.Group()` containing:

```
+----------------------------------+
| [icon] SCORING           [badge] |
| 32/48 images processed           |
| [============------]             |
|                                  |
| [Run Scoring]                    |
|                                  |
| > Options (collapsed)            |
|   [ ] Force Re-score             |
+----------------------------------+
```

### Per-Card Options (Collapsed Accordion)

| Phase | Options |
|-------|---------|
| Scoring | Force Re-score checkbox |
| Culling | Force Re-run checkbox |
| Keywords | Overwrite checkbox, Generate Captions checkbox |

### Tag Propagation

Currently lives in the Keywords tab as an accordion. Moves to a **utility section below the phase cards**, or inside the Keywords card's expanded options:

```
> Tag Propagation
  [Propagate Tags from Similar Images]
  [ ] Dry Run
  Results: ...
```

### Status Badge Colors (Left Border)

- Green left border = done
- Blue left border + pulse = running
- Gray left border = not started
- Red left border = failed

---

## Section D: Active Job Monitor

Replaces the three separate status cards + console outputs. Shows whichever runner is currently active.

Components:
- `gr.HTML()` -- Status card with phase name, progress bar, image count
- `gr.Accordion("Console Output", open=False)` containing `gr.Textbox(lines=12)`

The status timer polls all three runners and displays the active one:

```python
def unified_monitor_status():
    for runner, name in [(scoring_runner, "Scoring"),
                         (selection_runner, "Culling"),
                         (tagging_runner, "Keywords")]:
        is_running, log, msg, cur, tot = runner.get_status()
        if is_running:
            return build_status_html(name, msg, cur, tot), log
    return build_idle_html(), ""
```

When idle, shows a subtle "No active jobs" message or the last completed job's summary.

---

## Left Panel: Folder Tree Sidebar

Migrated from the Folder Tree tab into a persistent left column. No functional changes to the tree itself.

Components:
- `gr.Button("Refresh")` -- rebuilds folder cache
- `gr.HTML()` -- interactive folder tree (reuses `ui_tree.get_tree_html()`)
- `gr.Textbox(visible=False)` -- hidden selection target for JS
- Divider
- `gr.Markdown()` -- selected folder name + image count
- `gr.Button("Open in Gallery")` -- navigates to Gallery filtered by folder

The folder tree's inline status indicators simplify to a single icon per folder:
- Checkmark = all phases done
- Partial circle = some phases done
- X = any phase failed
- Empty = not started

Detailed per-phase breakdown is shown in the Pipeline Stepper when a folder is selected.

---

## Gallery Tab

Minimal changes:
- Remove navigation links to Scoring/Keywords/Selection tabs (they no longer exist)
- Keep "Re-Run Scoring" and "Re-Run Keywords" buttons on individual images (single-image operations)
- Keep "Find Similar" and all filtering/export functionality
- "Open in Gallery" from Pipeline tab folder tree still works via `navigation.open_folder_in_gallery()`

---

## Settings Tab

Renamed from "Configurations". Content unchanged. Consolidate legacy Stacks & Culling settings accordion into the Culling phase section (or remove if unused).

---

## Backend Changes

### New: PipelineOrchestrator

A lightweight class to manage "Run All Pending" sequential execution.

**File:** `modules/pipeline_orchestrator.py`

```
class PipelineOrchestrator:
    folder_path: str
    pending_phases: list[PhaseCode]
    current_phase: PhaseCode | None
    auto_continue: bool

    start(folder_path) -> starts first incomplete phase
    on_tick() -> checks if current runner finished, starts next phase
    stop() -> stops current runner, clears queue
```

Integrated into the monitor loop in `app.py`. Each timer tick calls `orchestrator.on_tick()` to detect phase completion and chain to the next phase.

### Timer Simplification

Current timer updates 13+ components across 4 tabs. New timer updates ~10 components all within the Pipeline tab:

| Component | Update Source |
|-----------|-------------|
| Pipeline stepper HTML | `get_folder_phase_summary()` |
| Phase card 1 (Scoring) status | Phase summary |
| Phase card 2 (Culling) status | Phase summary |
| Phase card 3 (Keywords) status | Phase summary |
| Active job status HTML | `unified_monitor_status()` |
| Console log textbox | Active runner log |
| Run All button state | Any runner active? |
| Stop All button state | Any runner active? |
| Phase Run button states | Per-runner active check |

---

## Feature Migration Map

| Current Location | Feature | New Location |
|---|---|---|
| Folder Tree tab: tree view | Folder browsing | Pipeline tab: left sidebar |
| Folder Tree tab: phase badges | Phase overview | Pipeline tab: stepper (enhanced) |
| Folder Tree tab: Run buttons | Quick launch | Pipeline tab: phase cards + Run All |
| Scoring tab: input path | Folder selection | Eliminated (use tree) |
| Scoring tab: Force Re-score | Option | Scoring phase card accordion |
| Scoring tab: Fix Database | Utility | Scoring phase card action |
| Scoring tab: status + console | Monitoring | Active Job Monitor (unified) |
| Keywords tab: input path | Folder selection | Eliminated (use tree) |
| Keywords tab: Overwrite/Captions | Options | Keywords phase card accordion |
| Keywords tab: Tag Propagation | Utility | Keywords card or utility section |
| Keywords tab: status + console | Monitoring | Active Job Monitor (unified) |
| Selection tab: input path | Folder selection | Eliminated (use tree) |
| Selection tab: Force Re-run | Option | Culling phase card accordion |
| Selection tab: status + console | Monitoring | Active Job Monitor (unified) |
| Stacks tab (legacy) | Manual stacking | Removed (replaced by Selection runner) |
| Culling tab (legacy) | Manual pick/reject | Removed (replaced by Selection runner) |

---

## Visual Design

### Color Palette (Existing Theme)

| Token | Value | Usage |
|-------|-------|-------|
| `--accent-primary` | #58a6ff | Running/active states |
| `--accent-success` | #3fb950 | Completed states |
| `--accent-danger` | #f85149 | Failed states |
| `--text-muted` | #6e7681 | Not started/inactive |
| `--bg-secondary` | #161b22 | Card backgrounds |
| `--border-color` | #30363d | Card borders |

### Phase Card Style

```css
.phase-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-left: 3px solid var(--status-color);
    border-radius: 8px;
    padding: 16px;
}
```

### Stepper Node Style

```css
.phase-node .node-circle {
    width: 36px; height: 36px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 600;
    border: 2px solid var(--status-color);
    background: var(--status-bg);
}
.phase-connector {
    flex: 1; height: 2px;
    background: var(--connector-color);
}
```

---

## Implementation Sequence

### Phase 1: Backend
1. Create `modules/pipeline_orchestrator.py`
2. Add `run_all_pending()` and `stop_all()` methods
3. Integrate phase-completion detection into monitor loop

### Phase 2: New Pipeline Tab
4. Create `modules/ui/tabs/pipeline.py`
5. Implement `_build_pipeline_stepper_html()`
6. Implement phase card rendering
7. Implement unified monitor status
8. Wire folder tree sidebar (migrate from `folder_tree.py`)

### Phase 3: App Integration
9. Update `modules/ui/app.py` -- replace 7 tabs with 3
10. Simplify `monitor_status_wrapper()` for unified outputs
11. Update `modules/ui/navigation.py` -- remove dead tab references

### Phase 4: Cleanup
12. Remove `modules/ui/tabs/scoring.py`
13. Remove `modules/ui/tabs/tagging.py`
14. Remove `modules/ui/tabs/selection.py`
15. Remove `modules/ui/tabs/folder_tree.py`
16. Remove `modules/ui/tabs/stacks.py` and `culling.py`
17. Clean up navigation.py
18. Add stepper/card CSS to `modules/ui/assets.py`

### Phase 5: Polish
19. "Open in Gallery" from sidebar
20. Test all phase transitions and error states
21. Update documentation and screenshots

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Pipeline orchestrator phase chaining fails silently | Explicit error handling + status reporting in monitor loop |
| Gradio timer output count must be fixed at build time | Design component list carefully upfront |
| Folder tree JS must work inside Column (not its own Tab) | Uses elem_id targeting, not tab-specific logic -- test early |
| Loss of manual path input (no tree selection) | Add collapsed "Custom path" textbox in Action Bar |
| Gallery navigation to old tabs breaks | Replace with direct pipeline actions |

---

## Open Questions

1. **Custom path input** -- Should we keep a textbox for manually typing a path, or is tree selection always sufficient?
2. **Phase dependencies** -- Should "Run All Pending" enforce that SCORING must complete before CULLING can start, or allow the user to override?
3. **Multiple folder queuing** -- Should "Run All Pending" support queuing multiple folders, or one at a time?
4. **Notification on completion** -- Should we add browser notifications when a long-running pipeline completes?
