# Plan: Align Gallery Import with Pipeline Discovery (Indexing)

**Status:** Proposal  
**Date:** 2026-04-10  
**Repos:** [image-scoring-backend](https://github.com/synthet/image-scoring-backend) (primary), [image-scoring-gallery](https://github.com/synthet/image-scoring-gallery) (client)

---

## 1. Problem

Two paths register images and mark the **indexing** (“Discovery”) phase, but they are **not equivalent**:

| Aspect | Pipeline **Discovery** (`IndexingRunner`) | Gallery **Import** (`/api/import/register`, Electron fallback) |
|--------|-------------------------------------------|----------------------------------------------------------------|
| **Walk scope** | Recursive `os.walk`, pruning excluded dirs | **Non-recursive** — `os.listdir` / `readdir` (immediate files only) |
| **Extensions & exclusions** | `discovery_extensions()`, `path_is_indexing_excluded`, optional NEF-only mode | Fixed extension set in `_IMPORT_IMAGE_EXTENSIONS`; no shared exclusion policy |
| **Registration** | Content hash, hash dedupe, `upsert_image`, NEF-aware `folder_id` | `register_image_for_import`, UUID-from-EXIF; lighter path |
| **Job context** | `jobs` + `job_phases` + per-run progress | No workflow job; marks indexing DONE on inserted rows only |
| **Progress UX** | `job_progress` / run UI | WS `import_*` events or single-shot response (Electron notes API can feel frozen) |

Users expect **Import** to do what a **Discovery** stage does for a folder. Today it only registers **top-level files**, so large trees still require a full indexing run — often duplicating mental model and support questions.

---

## 2. Goals

1. **Semantic alignment:** “Import folder” should mean the same **discovery** work as “run Discovery on this folder” (modulo explicit user choices below).
2. **Single implementation:** One authoritative discovery/register path in the **backend** (gallery calls API; local DB fallback minimized or scoped).
3. **Predictable behavior:** Same recursive scope, extension filters, and exclusion rules as `IndexingRunner` unless the user opts into a **fast / shallow** mode.

**Non-goals (initially):**

- Automatically enqueue scoring/tagging after import (remains a separate Run or preset).
- Changing Electron’s backup/sync flows except where they call Import.

---

## 3. Proposed directions (choose one primary + optional add-ons)

### Option A — **Delegate Import to IndexingRunner** (recommended)

- **Behavior:** `POST /api/import/register` (or a new `POST /api/import/discover`) creates a **`jobs` row** with `job_type=indexing` (or a dedicated `import` type that maps to the same executor), sets scope to the selected folder, and runs the **same** `_run_batch_internal` / `discover_files` path as the Runs UI.
- **Pros:** Guaranteed parity; `image_phase_status`, `job_progress`, and logs match Runs.
- **Cons:** Import becomes **async** from the HTTP caller’s perspective (poll run id + `/api/jobs/{id}` or WS). Electron must switch from “wait for JSON body” to “start run + progress via existing run channels” or streaming status.

### Option B — **Shared library, synchronous HTTP**

- Extract **file discovery + per-file register** into a module (e.g. `modules/discovery_core.py`) used by **both** `IndexingRunner` and `_import_folder_iter`.
- **Behavior:** Import stays a **blocking** request but performs **full recursive** walk + same hash/folder logic as indexing; optionally still **no** `jobs` row (lighter) or optional `job_id` for telemetry.
- **Pros:** Simpler Electron changes; one code path for rules.
- **Cons:** Long HTTP requests for huge trees; duplicate orchestration unless carefully factored.

### Option C — **Recursive Import only** (minimal)

- Extend `_import_folder_iter` to use `IndexingRunner.discover_files()` (or equivalent walk) instead of `os.listdir`.
- Reuse `register_image_for_import` **or** switch to the same upsert/hash path as indexing per product decision.
- **Pros:** Small diff.
- **Cons:** Still two orchestration paths (Import vs Run) unless combined with A or B.

**Recommendation:** **Option A** for true parity, with **Option C** as a short-term milestone if async UX is blocked.

---

## 4. Implementation phases

### Phase 1 — Backend parity (no UI breakage)

1. Add **`recursive`** (default `true`) and **`shallow`** (default `false`) query/body flags to import API; document in OpenAPI.
2. Replace flat `listdir` in `_import_folder_iter` with **`IndexingRunner.discover_files()`** or shared helper emitting the same list as Runs.
3. Align **extension allowlist** with `discovery_extensions()` (or import the same frozenset).
4. Apply **`path_is_indexing_excluded` / `prune_indexing_excluded_walk_dirs`** where applicable.
5. For each file, either:
   - call into **one** internal function shared with `IndexingRunner`’s loop (hash + upsert + phase status), or
   - document why `register_image_for_import` remains (and fix parity gaps).

### Phase 2 — Job alignment (optional but ideal)

1. **Import starts an indexing job** (Option A): return `{ run_id, job_id }` immediately; progress via existing WebSocket **`job_progress`** / run APIs.
2. Deprecate duplicate **`import_started` / `import_progress`** events or map them to the same run-progress schema for backward compatibility.

### Phase 3 — Gallery (Electron + React)

1. **`import:run`:** Prefer **enqueue indexing run** via FastAPI (`/api/pipeline/submit` or dedicated import endpoint returning `run_id`) when API is available.
2. **Progress:** Subscribe to **`run_progress`** (or poll `/api/runs/{id}`) instead of only `import:progress` from a monolithic POST.
3. **Fallback:** If API down, either **shallow-only** local insert (current behavior) with a **visible warning** (“Recursive import requires backend”), or embed a **thin** client that mirrors Phase 1 rules (higher maintenance).

### Phase 4 — Docs & contracts

1. Update **[API_CONTRACT.md](../technical/API_CONTRACT.md)** (or OpenAPI) — import behavior, defaults, async vs sync.
2. Short **gallery** doc: link to this plan; describe “Import = discovery-equivalent when backend connected.”

---

## 5. Testing

- **Backend:** Extend `tests/test_api_v2_reorg.py` (import_register) with recursive fixture tree; assert counts match `IndexingRunner.discover_files` on same temp dir.
- **Integration:** Same folder via **Run Discovery** vs **Import** → same `images` rows and `image_phase_status` for indexing (modulo job_id when job-backed).
- **Electron:** Manual: Import large nested folder → progress matches Runs expectations.

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Long-running HTTP (Option B) | Timeouts, streaming NDJSON (`/import/register/stream`), or move to Option A. |
| Behavior change for users relying on **shallow** import | Default `recursive=true` with **`shallow=true`** UI toggle or config migration note. |
| Dual DB (gallery local vs API) | Keep fallback explicit and document parity limits. |

---

## 7. References (code)

- Backend indexing: `modules/indexing_runner.py` — `discover_files`, `_run_batch_internal`
- Backend import: `modules/api.py` — `_import_folder_iter`, `_IMPORT_IMAGE_EXTENSIONS`
- Gallery: `electron/main.ts` — `ipcMain.handle('import:run', …)`
- Phases: `modules/phases.py` — `PhaseCode.INDEXING`

---

## 8. Open questions

1. Should Import **always** create a **job** row for auditability, or only when “full discovery” mode is selected?
2. Should **hash-based dedupe** be mandatory for Import (same as indexing) or optional for speed?
3. Desktop users without backend: is **recursive local import** required, or is shallow + warning acceptable?
