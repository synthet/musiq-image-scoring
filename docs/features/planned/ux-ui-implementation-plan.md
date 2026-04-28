# UX/UI Implementation Plan

Based on [UX_UI_REVIEW_2026-03-12.md](../reports/project-reviews/UX_UI_REVIEW_2026-03-12.md). All priorities (P0 + P1 + P2).

## Files Modified

| File | Changes |
|------|---------|
| `modules/ui/assets.py` | CSS additions: fix `running-pulse`, add status-badge variants, Quick Start panel, confirm rows, microcopy, filter presets/chips, accessibility focus ring |
| `modules/ui/tabs/pipeline.py` | Quick Start panel, confirmation dialogs for Stop/Skip, inline microcopy, ARIA labels, extend status update to 12 outputs |
| `modules/ui/tabs/gallery.py` | Filter preset buttons, active filter chips strip, reset all, chip builder helper |
| `modules/ui/app.py` | Extend `monitor_outputs` from 11 to 12 entries |

---

## P0 — Do Next

### 1. Quick Start Panel (Pipeline)

Add a context-aware 3-step guide at the top of the Pipeline main dashboard column, before the "Pipeline Progress" panel.

**New function:** `_build_quick_start_html(folder_path, summary_by_code, is_running)`

Steps shown:
1. **Select a folder** — current when no folder selected
2. **Run All Pending** — current when folder selected but phases remain
3. **Open Gallery** — current when all phases complete

State-aware: each step shows `current`/`done`/default styling. Updated every 2s via the timer (added as 12th output of `get_status_update()`).

**Layout insertion:** New `gr.HTML` component inside the main dashboard column, before the Pipeline Progress panel.

### 2. Confirmation Dialogs (Stop All + Skip)

**Pattern:** Two-step hidden `gr.Row(visible=False)` toggled visible on first click. Contains consequence text + "Yes, [Action]" + "Cancel" buttons.

Rationale for this pattern over alternatives:
- `gr.Modal` — limited styling control, not all Gradio versions support it
- JS `confirm()` — blocks browser thread, incompatible with Gradio's SSE model
- Hidden row — fits cleanly into existing event model, zero JS, uses existing CSS patterns

**Stop All:** After the pipeline-actions row, add a hidden confirm row:
> "This will halt all active jobs immediately. Running progress is preserved but the current batch will not complete."

**Per-phase Skip (×3):** Inside each phase card, after the skip button:
> "This marks [Phase] as skipped for the selected folder. Existing processed images are not affected."

**Rewiring:** Existing `.click()` handlers on `stop_all_btn` and `*_skip_btn` change from firing the action directly to showing the confirm row. The confirm button fires the actual action, then hides the row.

### 3. Inline Microcopy

**Under pipeline actions row:**
> **Run All Pending** — starts Scoring, Culling, and Keywords for images not yet processed. **Stop All** — halts the active job; progress is preserved.

**Under each phase card's action buttons (×3):**
> **Run** — scores unprocessed images. **Skip** — marks phase done without running. **Retry** — re-queues previously skipped images.

(Adjusted per phase for Culling and Keywords.)

---

## P1 — High Value

### 4. Gallery Filter Presets + Active Chips

**Preset buttons row** — inserted above the Filters & Search accordion:
- **Top Rated** — sets rating filter to [4, 5], sorts by score_general desc
- **Needs Review** — clears all filters, sorts by score_general desc (unrated images surface)
- **Has Keywords** — filters to images with non-empty keywords (requires `has_keywords` param in `db.get_images_paginated_with_count()` — deferred; button rendered but approximated initially)
- **Reset All** — clears all filter controls to defaults

**Active filter chips strip** — `gr.HTML` below presets, updated on every filter change. Shows read-only summary chips like "Rating: 4, 5", "Min General: 0.50", "Keyword: landscape". No per-chip dismiss (clearing via accordion controls or Reset All).

**New function:** `_build_active_chips_html(rating, label, keyword, min_gen, min_aes, min_tech, start_date, end_date)`

**Wiring:** Each filter `.change()` also updates `active_chips_html`. Preset buttons output to all filter components + chips + gallery refresh.

### 5. Consolidated Status/Error Messaging

**CSS additions:**
- `.status-badge.error` — red background/border/text
- `.status-badge.info` — blue background/border/text
- Fix missing `@keyframes running-pulse` animation (referenced but never defined)

**Phase card HTML:** Update `_build_phase_card_html()` to apply appropriate `.status-badge.{success|warning|error}` classes based on status (`done` → success, `running`/`partial` → info, `failed` → error, `skipped` → warning).

---

## P2 — Refinement

### 6. Accessibility Pass

**CSS:**
- Global `:focus-visible` ring — `2px solid var(--accent-primary)`, `outline-offset: 2px`
- `.sr-only` utility class for screen-reader-only text
- `.phase-card[role="region"]:focus-within` highlight

**HTML template changes:**
- Stepper: `role="list"` on `.stepper`, `role="listitem"` + `aria-label` on each `.step`
- Phase cards: `role="region"` + `aria-label="[Phase] phase status"`
- Quick Start steps: `role="listitem"`
- Active chips: `role="list"` + `role="listitem"`
- Gallery filter controls: explicit `elem_id` values for ARIA targeting

### 7. Microcopy Polish

- Consistent verb semantics across all phase cards (Run/Skip/Retry all explained)
- Helper text uses `.action-help` and `.section-microcopy` CSS classes
- Phase status labels standardized: "Done", "In Progress", "Failed", "Skipped", "Not Started"

---

## Implementation Sequence

| # | File | Change | Risk | Notes |
|---|------|--------|------|-------|
| 1 | `assets.py` | All CSS additions | Zero | Pure CSS, no behavior |
| 2 | `pipeline.py` | `_build_quick_start_html()` helper | Low | New function only |
| 3 | `pipeline.py` | Quick Start `gr.HTML` in layout | Low | Additive |
| 4 | `pipeline.py` | Microcopy `gr.HTML` blocks | Low | Additive |
| 5 | `pipeline.py` | Confirmation rows in layout | Medium | New components |
| 6 | `pipeline.py` | Rewire skip/stop to two-step | Medium | Replaces existing wires |
| 7 | `pipeline.py` | `get_status_update()` → 12 outputs | **High** | Must pair with step 8 |
| 8 | `app.py` | `monitor_outputs` → 12 entries | **High** | Must pair with step 7 |
| 9 | `gallery.py` | `_build_active_chips_html()` helper | Low | New function |
| 10 | `gallery.py` | Preset buttons + chips in layout | Low | Additive before accordion |
| 11 | `gallery.py` | Wire presets + chips update | Medium | New event bindings |
| 12 | All | ARIA attributes in HTML strings | Low | Additive |

**Critical:** Steps 7 and 8 must land together — a mismatch between `get_status_update()` returning 12 values and `monitor_outputs` expecting 11 will crash the timer.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Confirmation pattern | Hidden `gr.Row` two-step | Zero JS, fits Gradio event model, reusable CSS |
| Active chips | Read-only (no per-chip dismiss) | Per-chip dismiss needs 1 hidden button per dimension; cost > UX gain given accordion is available |
| Quick Start updates | Via 2s timer (12th output) | Consistent with existing polling; no additional timers |
| "Has Keywords" preset | Deferred DB filter | Needs `has_keywords` param in `db.get_images_paginated_with_count()`; button rendered but approximated |
| Accessibility scope | Focus ring + ARIA roles + sr-only | Pragmatic subset; full audit is separate effort |

---

## Follow-on Work (Out of Scope)

- `db.py`: Add `has_keywords` boolean filter to `get_images_paginated_with_count()` for the "Has Keywords" preset
- Toast/snackbar notification system (beyond current `.status-badge` approach)
- Full keyboard navigation audit with screen reader testing
- Collapsible Quick Start panel (dismiss after first use, persist preference)
