# Gradio WebUI UX/UI Specification (Current State)

This document captures the **implemented** UX/UI behavior of the current Gradio WebUI so it can be migrated to an Electron app with parity.

## 1) Application Shell & Information Architecture

- App root is a Gradio `Blocks` app titled **Vexlum Scoring WebUI**, mounted by FastAPI at `/app` (root redirects to `/app`).
- Top-level IA is 3 tabs:
  - **Pipeline** (`id="pipeline"`)
  - **Gallery** (`id="gallery"`) — initially hidden, opened contextually by navigation.
  - **Settings** (`id="settings"`)
- Global states shared across tabs:
  - `current_page` (gallery pagination)
  - `current_paths` (raw file paths for current gallery page)
  - `image_details` (selected image record)
  - `current_folder_state` (folder context from tree navigation)
  - `current_stack_state` (stack context)
- A global timer polls status every 2 seconds to refresh pipeline progress and monitor widgets.

## 2) Visual Design System (Dark Theme)

- Custom CSS defines a dark theme token set:
  - Backgrounds: `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-elevated`, `--bg-input`, `--bg-console`
  - Text: `--text-primary`, `--text-secondary`, `--text-muted`
- Styling emphasizes card/panel UI, badges, subtle hover states, custom scrollbars, and status color semantics (success/info/warning/error).
- Hidden textboxes are deliberately rendered in DOM (`visible=True`) and visually hidden via `.hidden-path-storage` for JS interop/state sync.

## 3) Tab: Pipeline (Primary Workflow Surface)

## 3.1 Layout

Two-column layout:

1. **Sidebar** (left)
   - Section title: “Folders”
   - `Refresh` button
   - Folder tree HTML viewer
   - Hidden textbox `folder_tree_selection` used for JS-driven selection updates
   - Folder summary card (selected path + image count)

2. **Main dashboard** (right)
   - Quick Start panel (context-aware step hints)
   - Pipeline Progress panel (stepper + Run/Stop global controls)
   - Per-phase card grid (Scoring, Culling, Keywords)
   - Active Job Monitor panel + collapsible console output

## 3.2 Folder Tree UX

- Tree is generated from cached DB folder paths, normalized to local platform path style.
- Click on a tree node runs `selectFolder(event, path)` JS:
  - clears previous node highlighting
  - applies selected style to clicked node
  - updates hidden Gradio textbox value
  - dispatches `input` event to trigger Python `.change()` callback
- Refresh invalidates folder phase aggregate cache and rebuilds tree + selection-dependent panels.

## 3.3 Quick Start Behavior

Quick Start is a dynamic 3-step guide with step states (`current`, `done`, inactive):

1. Select folder
2. Run pending pipeline phases
3. Open Gallery for review

It changes based on:
- no folder selected
- pipeline currently running
- pending phases still incomplete
- all phases complete/skipped

## 3.4 Pipeline Progress & Monitor

- 5-step progress stepper: **Index → Meta → Scoring → Culling → Keywords**.
- Each step displays counts (`done / total`) and state class (done/running/idle).
- A monitor card shows active runner progress (message, counts, progress bar) plus queue preview.
- If idle, monitor shows no-active-jobs plus job recovery summary and queue snapshot.
- UI is polled every 2 seconds; SSE updates are skipped when content hash is unchanged to reduce redundant UI pushes.

## 3.5 Phase Cards & Controls

Per phase (Scoring/Culling/Keywords):
- Status card with badge and progress bar.
- Primary action button (`Run ...`).
- Phase options in accordions:
  - Scoring: `Force Re-score`
  - Culling: `Force Re-scan`
  - Keywords: `Overwrite Existing`, `Generate Captions`
- `Skip ...` with two-step confirmation row.
- `Retry Skipped` action.
- Help/microcopy explaining Run/Skip/Retry semantics.

Global actions:
- `Run All Pending` starts orchestrator.
- `Stop All` has two-step confirmation and stops orchestrator + all runners.

Safety/interaction rules:
- While a job is running:
  - run buttons become non-interactive
  - stop button becomes interactive
- When idle, inverse button interactivity applies.

## 4) Tab: Gallery (Review & Curation Surface)

## 4.1 Visibility & Context

- Tab declared with `visible=False`; opened programmatically via navigation from folder/stack context.
- Context bar (when filtering by folder) shows selected folder card and `✕ Clear Filter` button.

## 4.2 Header Controls

- `🔄 Refresh` button
- Sort controls:
  - field dropdown (Date Added, Capture Date EXIF, ID, General, Technical, Aesthetic, SPAQ, AVA, KonIQ, PaQ2PiQ, LIQE)
  - order dropdown (Highest First / Lowest First)

## 4.3 Presets & Active Chips

- Preset quick buttons:
  - Top Rated
  - Needs Review
  - Has Keywords
  - Reset All
- Active filters are summarized into non-editable chips strip (rating, label, keyword, min scores, date range).

## 4.4 Filter Panel

Accordion: “🔍 Filters & Search” containing:
- Rating checkbox group (1..5)
- Color label checkbox group (Red/Yellow/Green/Blue/Purple/None)
- Min score sliders (General/Aesthetic/Technical)
- Date textboxes (`From Date`, `To Date`, format hint `YYYY-MM-DD`)
- Keyword search textbox

Filter behavior:
- Any filter change resets to page 1 and refreshes results.
- Slider/filter updates use `trigger_mode="always_last"` for debounce-like behavior.

## 4.5 Export Panel

Accordion: “📤 Export Data”:
- Format dropdown: JSON / CSV / XLSX
- `Export All Images` button
- hidden status output area for success/failure
- advanced options include column selection + template operations (save/load/delete) and folder/scope-aware export behavior.

## 4.6 Pagination

- First/Prev/Next/Last buttons (`⏮ ◀ ▶ ⏭`)
- Page indicator button (non-interactive)
- Pagination clamps to valid page range after operations like deletion.

## 4.7 Main Content Split

- Left: Gallery grid (`gr.Gallery`) with 5 columns, height 600, `object_fit="cover"`, preview enabled.
- Right: Details panel (min width 320) containing:
  - Summary markdown
  - Score labels: General, Weighted, Models
  - Culling status HTML area
  - Accordion “Image Details”:
    - Title, Description (read-only)
    - Keyword chips (`HighlightedText`) with custom high-contrast color map
    - Rating & Label dropdowns (read-only in current flow)
    - Save button/status (currently hidden unless enabled by flow)
  - Action buttons:
    - Fix Data
    - Re-Run Scoring
    - Re-Run Keywords
    - Find Similar
    - Remove from DB
    - Delete NEF (mostly hidden by default)
  - Similar Images accordion with secondary gallery + status text
  - Status textboxes (fix/delete)
  - Hidden textbox `gallery-selected-path` for JS features (full-res/raw preview path retrieval)

## 4.8 Gallery Item Interaction

- Selecting gallery item populates detail outputs (metadata + scores + state).
- `Find Similar` runs visual similarity search around selected image.
- `Remove from DB` deletes DB record only and refreshes gallery.
- `Delete NEF` attempts file delete (NEF + thumb) then DB cleanup.
- `Fix Data` and rerun actions trigger runner wrappers for selected image.

## 5) Tab: Settings (Configuration Surface)

Single advanced settings page using collapsible sections:

1. **Scoring Configuration**
   - Force re-score default
   - Default sort field/order

2. **Processing Configuration**
   - prep/scoring/result queue sizes
   - clustering batch size

3. **Stacks & Culling (Legacy)**
   - default similarity threshold
   - default time gap
   - force rescan default
   - auto export default

4. **UI Preferences**
   - gallery page size
   - default export format

5. **Tagging Configuration**
   - overwrite existing default
   - generate captions default
   - max BLIP tokens
   - CLIP model selection

Actions:
- `💾 Save All Configuration` persists to `config.json` sections.
- `🔄 Reset to Defaults` restores predefined defaults into form controls.
- Status textbox displays success/error outcome.

## 6) Navigation & Cross-Tab UX Contracts

- `open_folder_in_gallery(...)`:
  - switches tab to `gallery`
  - applies folder state + filters + resets to page 1
  - shows folder context bar with folder name + parent path
- Clearing folder context hides context bar and returns to global gallery scope.
- `open_folder_in_pipeline(folder)` switches tab to pipeline and updates folder selection state.

## 7) JavaScript-Dependent UX Behaviors

Current Gradio UI relies on injected JS for critical UX:

- folder tree click-to-select (`window.selectFolder`)
- robust gallery close/back-to-grid helper for lightbox preview
- full-resolution / raw preview path resolution with fallbacks
- DOM queries resilient to Gradio-generated dynamic IDs

Migration implication: these should become first-class renderer logic in Electron (not brittle DOM scraping).

## 8) Accessibility & Interaction Notes (Current State)

- Some generated HTML includes ARIA roles/labels (e.g., stepper list, phase regions).
- Many interactions remain button/visual-first; keyboard-first and screen-reader semantics are partial.
- Hidden state fields are implementation-driven; should become explicit state in Electron architecture.

## 9) Functional UX Invariants to Preserve in Electron

1. Pipeline-first workflow with folder selection and explicit phase control.
2. Real-time job visibility with actionable stop/retry/skip controls.
3. Rich gallery filtering + presets + chips + pagination.
4. Side-panel detail context and per-image remediation actions.
5. Folder-context navigation between pipeline and gallery.
6. Configurability through a persisted advanced settings UI.
7. Dark theme with strong status affordances and high scanability.

## 10) Suggested Electron Migration Boundaries (Spec-Level)

- **Shell**: Native menu/window chrome + router tabs/panes mirroring Pipeline/Gallery/Settings.
- **State model**: Replace hidden textbox/DOM bridges with explicit store state.
- **Polling/events**: Keep 2s status cadence initially; later switch monitor areas to websocket/event-driven updates.
- **Component mapping**:
  - Pipeline cards/stepper/monitor => reusable status widgets
  - Gallery grid + side panel => split-view module
  - Settings accordions => schema-driven form sections
- **Parity-first phase**: Keep labels/ordering/defaults/actions equivalent before introducing UX redesign.

---

## 11) REST API Contract for Electron

The Python backend (`webui.py`) serves a FastAPI application on `http://127.0.0.1:7860` (default). All REST endpoints are prefixed `/api`. CORS is pre-configured for Electron dev-server origins: **5173**, **4173**, **7860**.

### 11.1 Job Control Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/scoring/start` | Start batch scoring job |
| `POST` | `/api/scoring/stop` | Stop running scoring job |
| `GET` | `/api/scoring/status` | Poll scoring status |
| `POST` | `/api/scoring/single` | Score a single image file |
| `POST` | `/api/tagging/start` | Start batch tagging job |
| `POST` | `/api/tagging/stop` | Stop running tagging job |
| `GET` | `/api/tagging/status` | Poll tagging status |
| `POST` | `/api/tagging/single` | Tag a single image file |
| `POST` | `/api/clustering/start` | Start clustering/culling job |
| `POST` | `/api/clustering/stop` | Stop clustering job |
| `GET` | `/api/clustering/status` | Poll clustering status |
| `GET` | `/api/status` | Unified status for all runners |
| `GET` | `/api/health` | Health check + runner availability |
| `POST` | `/api/pipeline/submit` | Chain operations (score → tag → cluster) |
| `POST` | `/api/pipeline/phase/skip` | Mark all images in a folder phase as skipped |
| `POST` | `/api/pipeline/phase/retry` | Retry skipped phase (starts runner) |

**Status response shape** (`GET /api/{scoring,tagging,clustering}/status`):
```json
{
  "is_running": true,
  "status_message": "Scoring 45/142",
  "progress": { "current": 45, "total": 142 },
  "log": "...",
  "job_type": "scoring"
}
```

Recommended polling interval: **2 seconds** (matches current Gradio timer).

### 11.2 Job Queue Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/jobs/queue` | List queued jobs with position |
| `GET` | `/api/jobs/recent` | Recent completed/failed jobs |
| `GET` | `/api/jobs/{job_id}` | Get specific job details |
| `POST` | `/api/jobs/{job_id}/cancel` | Cancel a queued job |

### 11.3 Data Query Endpoints

#### Images

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/images` | Paginated, filtered image list |
| `GET` | `/api/images/{image_id}` | Full image record with scores, metadata, file paths |
| `PATCH` | `/api/images/{image_id}` | Update rating / label / title / description / keywords |
| `DELETE` | `/api/images/{image_id}` | Remove image record; optionally delete file |

**GET /api/images — query params:**
`page`, `page_size`, `sort_by`, `order`, `rating` (CSV), `label` (CSV), `keyword`, `min_score_general`, `min_score_aesthetic`, `min_score_technical`, `folder_path`, `stack_id`

**GET /api/images response:**
```json
{
  "images": [...],
  "total": 420,
  "page": 1,
  "page_size": 50,
  "total_pages": 9
}
```

**PATCH /api/images/{image_id} body:**
```json
{
  "rating": 4,
  "label": "Green",
  "title": "Sunset",
  "description": "...",
  "keywords": "sunset,landscape",
  "write_sidecar": true
}
```
All fields are optional. `write_sidecar: true` (default) also writes XMP sidecar + embedded tags via tagging runner, keeping DB and file metadata in sync.

**DELETE /api/images/{image_id}:**
`?delete_file=true` also removes the source file and thumbnail from disk.

> **IPC contract:** Column names in image records match the `images` table schema (schema authority: `modules/db.py`). Do **not** rename columns without updating `electron/db.ts`.

#### Folders

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/folders` | Flat folder list with paths |
| `POST` | `/api/folders/rebuild` | Rebuild folder cache from images table |
| `GET` | `/api/folders/tree` | Hierarchical folder tree (for sidebar) |
| `GET` | `/api/folders/phase-status` | Pipeline phase aggregate for a folder |

**GET /api/folders/tree response:**
```json
{
  "tree": [
    {
      "name": "photos",
      "path": "/mnt/d/photos",
      "children": [
        { "name": "2024", "path": "/mnt/d/photos/2024", "children": [] }
      ]
    }
  ],
  "count": 12
}
```

**GET /api/folders/phase-status — query params:** `path` (required), `force_refresh` (bool, default false)

**GET /api/folders/phase-status response:**
```json
{
  "folder_path": "/mnt/d/photos/2024",
  "phases": [
    { "code": "index",    "name": "Index",    "total_images": 142, "done_count": 142, "failed_count": 0, "running_count": 0, "skipped_count": 0, "optional": false },
    { "code": "scoring",  "name": "Scoring",  "total_images": 142, "done_count": 98,  "failed_count": 0, "running_count": 1,  "skipped_count": 0, "optional": false },
    { "code": "culling",  "name": "Culling",  "total_images": 142, "done_count": 0,   "failed_count": 0, "running_count": 0,  "skipped_count": 0, "optional": true  },
    { "code": "keywords", "name": "Keywords", "total_images": 142, "done_count": 0,   "failed_count": 0, "running_count": 0,  "skipped_count": 0, "optional": true  }
  ]
}
```

#### Export

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/gallery/export` | Export filtered image set to JSON / CSV / XLSX |

**POST /api/gallery/export body:**
```json
{
  "format": "csv",
  "columns": ["file_name", "score_general", "rating", "keywords"],
  "folder_path": "/mnt/d/photos/2024",
  "rating": [4, 5],
  "min_score_general": 0.7,
  "date_from": "2024-01-01",
  "date_to": "2024-12-31"
}
```
Response: file download attachment (`Content-Disposition: attachment`).

#### Other Data Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/stacks` | Stacks with cover images |
| `GET` | `/api/stacks/{stack_id}/images` | All images in a stack |
| `GET` | `/api/stats` | Database statistics |
| `GET` | `/api/images/similar` | Visually similar images (embedding cosine) |
| `GET` | `/api/images/outliers` | Visual outlier detection |
| `POST` | `/api/duplicates/find` | Near-duplicate pairs |
| `POST` | `/api/import/register` | Register images from folder without scoring |
| `GET` | `/api/raw-preview` | Extract/generate JPEG preview for RAW file (`?path=...`) |

### 11.4 WebSocket — Real-Time Events

**Endpoint:** `ws://127.0.0.1:7860/ws/updates`

Connect once on app start. The server broadcasts JSON messages for all job lifecycle events. The Electron renderer can use this to update progress indicators without polling.

**Message shape:**
```json
{ "type": "<event_type>", "data": { ... } }
```

**Event catalog:**

| Event type | Trigger | Key data fields |
|------------|---------|-----------------|
| `job_started` | Runner begins processing | `job_type`, `input_path`, `total` |
| `progress_update` | Per-image/batch progress tick | `job_type`, `current`, `total`, `message` |
| `job_completed` | Runner finishes (success or error) | `job_type`, `success`, `message` |
| `image_updated` | Image metadata written to DB | `file_path`, `fields` (dict of changed values) |

> **Fallback:** If WebSocket is unavailable, poll `GET /api/status` every 2 seconds for equivalent runner status information.

### 11.5 Settings Persistence

`GET /api/config` / `POST /api/config` — reads and writes `config.json` sections used by the Settings tab. Sections: `scoring`, `processing`, `culling`, `ui`, `tagging`.

