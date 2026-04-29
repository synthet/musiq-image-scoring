# Vexlum Scoring — project TODO

**Last evaluated:** 2026-04-25

Consolidated backlog (Python backend). **Quick filter:** **[Electron]** = image-scoring-gallery (sibling repo); **[Python]** / **[Gradio]** / **[DB]** = this repo.

> **Source of truth and update order:** Edit **this file first**, then follow the sync order in [`docs/project/00-backlog-workflow.md`](docs/project/00-backlog-workflow.md). That doc is aligned with the gallery’s [`docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) ([`docs/planning/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/planning/00-backlog-workflow.md) redirects).

| Marker | Use when |
|--------|----------|
| `[Python]` | Backend (`modules/`, FastAPI, tests) |
| `[Gradio]` | Gradio WebUI / operator UI |
| `[DB]` | PostgreSQL, Alembic, `modules/db.py` |
| `[Electron]` | Coordinated work in **image-scoring-gallery** or IPC/API contract with the desktop app |

### Count snapshot rules

- **Open item:** each unchecked `- [ ]` line counts as one.
- **Gallery-dependent:** any open line tagged `[Electron]` (cross-repo or gallery-side work).
- **Backend scope:** open items with **no** `[Electron]` tag (this repository only).

#### Current status snapshot (2026-04-25)

- **Total open items:** 35
- **Gallery-dependent (`[Electron]`):** 6  
- **Backend scope (no `[Electron]`):** 29  
- **Recent:** Embedding map multi-space + PCA (App 05 phase 1) shipped — `space_code` & `pca_dim` on `GET /api/embedding_map`, `embedding_space` on `GET /api/similarity/search`, new `GET /api/images/{id}/similar`, plus `GET /api/embedding_spaces` for UI dropdowns (Postgres-backed; static fallback on Firebird). See [EMBEDDING_APP_05](docs/features/planned/embeddings/EMBEDDING_APP_05_2D_EMBEDDING_MAP.md) §Phase 1.

### Highest-Impact Next Steps (recommended sequence)

Order follows [`docs/planning/INDEX.md`](docs/planning/INDEX.md) priority tiers (P0 → P3).

1. **Cross-repo coordination (P0)** — Notify gallery when API/schema changes; keep [`AGENT_COORDINATION.md`](docs/technical/AGENT_COORDINATION.md) aligned with [**image-scoring-gallery** `TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/TODO.md); sync `electron/apiTypes.ts` / `apiService.ts` when endpoints move.
2. **Database Phase 4–5 (P0 / P1)** — Gallery **normalized keyword** read-path coordination ahead of Phase 4d (v7.0); Phase **5** PostgreSQL optimizations ([`POSTGRES_SCHEMA_OPTIMIZATIONS.md`](docs/planning/database/POSTGRES_SCHEMA_OPTIMIZATIONS.md)) — vectors + integrity constraints first. Status narrative: [`docs/planning/database/NEXT_STEPS.md`](docs/planning/database/NEXT_STEPS.md), [`DB_STATUS_REPORT.md`](docs/planning/database/DB_STATUS_REPORT.md).
3. **Contract hygiene (P0)** — Keep [`openapi.yaml`](docs/reference/api/openapi.yaml) and [`API_CONTRACT.md`](docs/technical/API_CONTRACT.md) aligned with `modules/api.py` when endpoints change.
4. **Embedding & UI wiring (P1)** — Bidirectional control + IPC/WebSocket per [`EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md`](docs/features/planned/embeddings/EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md) and [`docs/features/planned/embeddings/NEXT_STEPS.md`](docs/features/planned/embeddings/NEXT_STEPS.md); gallery embedding wave in sibling repo.
5. **Operator UI polish (P1)** — Pipeline Quick Start, confirmations, microcopy per [`UX_UI_IMPLEMENTATION_PLAN.md`](docs/features/planned/ux-ui-implementation-plan.md) (see High Priority).
6. **Verification debt (P1)** — In-browser RAW preview manual test pass (High Priority section below).
7. **Larger proposals (P2+)** — Pipeline tab redesign [`UI_PIPELINE_REDESIGN.md`](docs/features/planned/ui-pipeline-redesign.md); stack/culling unification [`STACK_CULLING_REFACTOR_PLAN.md`](docs/planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md); Windows native WebUI [`WINDOWS_NATIVE_WEBUI_PLAN.md`](docs/planning/setup/WINDOWS_NATIVE_WEBUI_PLAN.md); model stack research [`IQA_MODEL_STACK_UPDATE_PROPOSAL.md`](docs/planning/models/IQA_MODEL_STACK_UPDATE_PROPOSAL.md).

**Residual docs cleanup (optional):** Align user-facing [`README.md`](README.md) strings with PostgreSQL-native reality wherever legacy wording still appears.

---

## High Priority

### Operator UI (plans)

- [ ] **[Gradio]** Pipeline UX (P0 per plan): Quick Start panel, Stop/Skip confirmation rows, inline action microcopy — [`UX_UI_IMPLEMENTATION_PLAN.md`](docs/features/planned/ux-ui-implementation-plan.md)

### Testing & Verification

- [ ] **[Gradio]** In-browser RAW preview tests: Select NEF → Extract Preview → Verify canvas renders
- [ ] **[Gradio]** In-browser RAW preview tests: Select JPG → Verify warning message shows
- [ ] **[Gradio]** In-browser RAW preview tests: No image selected → Verify error message
- [ ] **[Gradio]** In-browser RAW preview tests: Verify no JS errors on page load
- [ ] **[Gradio]** In-browser RAW preview tests: Large files (>50MB) → Verify progress bar works
- [x] **AI culling**: Integration test with real scored folder (test suite exists; set `IMAGE_SCORING_TEST_CULLING_FOLDER` to run)
- [x] **AI culling**: Verify XMP sidecar creation — check file creation and format (`xmpDM:pick`, `xmpDM:good`)
- [ ] **[Python]** **[Gradio]** AI culling: Import into Lightroom Cloud — verify ratings and labels apply correctly
- [ ] **[Python]** **[Gradio]** AI culling: Test pick/reject flags — verify Lightroom recognizes culling decisions

### API & Embedding

- [x] **[Python]** Similarity endpoints: `/api/similarity/search`, `/api/similarity/duplicates`, `/api/similarity/outliers` (legacy paths may redirect; see [API_CONTRACT.md](docs/technical/API_CONTRACT.md))
- [ ] **[Electron]** **[DB]** Notify **image-scoring-gallery** when API/schema changes; update `apiService.ts`, `db.ts` (see [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md))

---

## Medium Priority

### RAW & Culling

- [ ] **[Gradio]** Web Worker for non-blocking RAW decode — offload RAW processing to background thread
- [ ] **[Gradio]** LibRaw WASM integration — full RAW decode capability (currently only embedded JPEG extraction)
- [ ] **[Python]** **[Gradio]** AI-Assisted Mode — user picks with AI suggestions (currently only automated mode)
- [ ] **[Python]** **[Gradio]** Face detection — prioritize expressions for portrait photography
- [ ] **[Python]** **[Gradio]** Capture One support — additional XMP fields for Capture One compatibility

### Tag Propagation

- [x] **[Python]** REST endpoint for tag propagation (`POST /tagging/propagate`) — dry-run and live modes
- [ ] **[Electron]** Tag Propagation UI: AI Suggestions sidebar in `ImageViewer.tsx`, Accept/Reject interaction logic (see Electron backlog)

### Clustering & Embeddings

- [x] **[Python]** Add `stack_representative_strategy` config option to `ClusteringEngine`
- [x] **[Python]** Centroid / balanced strategies in `modules/clustering.py` (`_select_best_image`) when per-image embeddings are provided (visual stacks). Burst stack creation still passes scores only — representative stays score-based there until embeddings are wired into that path
- [x] **[Python]** 2D embedding map: `modules/projections.py`, `GET /api/embedding_map`, tests in `tests/test_api_embedding_map.py`
- [x] **[Python]** WebSocket `/ws/updates` with inbound command dispatch (`modules/command_dispatcher.py`, `webui.py`) — backend channel exists
- [ ] **[Electron]** **[Gradio]** End-to-end UI wiring: gallery IPC/WebSocket bridge + Gradio/Electron flows per [EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md](docs/features/planned/embeddings/EMBEDDING_APP_08_GRADIO_INTEGRATION_PLAN.md)
- [ ] **[Electron]** **[DB]** Pipeline mode selector, headless lifecycle, `INTEGRATION_QUEUE` table
- [ ] **[Gradio]** "Similarity Search" tab or context menu in Gradio WebUI using `similar_search.py`

### API & Contract

- [x] **[Python]** Streaming progress for folder import: `POST /api/import/register/stream` (NDJSON); non-stream endpoint broadcasts progress via WebSocket events
- [x] **[Python]** Keep OpenAPI schema ([docs/reference/api/openapi.yaml](docs/reference/api/openapi.yaml)) aligned with `modules/api.py` — regenerated from FastAPI (131 paths, 37 schemas)
- [x] **[Python]** Add request/response examples for new endpoints to `API.md`
- [ ] **[Electron]** Update `electron/apiService.ts` and `electron/apiTypes.ts` when adding endpoints

### Model & Performance

- [ ] **[Python]** Additional Vision-Language Models — BLIP-2, LLaVA, InternVL integration

---

## Database & Migration [DB]

### Schema refactor — keywords / metadata ([DB_SCHEMA_REFACTOR_IMPLEMENTATION](docs/planning/database/DB_SCHEMA_REFACTOR_IMPLEMENTATION.md))

**Phase 4 Status:** 4a, 4b, 4c COMPLETE on Python side; 4d scheduled for v7.0 (July 2026)  
See [PHASE4_STATUS_SUMMARY.md](docs/planning/database/PHASE4_STATUS_SUMMARY.md) for full timeline.

- [x] **[Python]** **[DB]** Phase 4a: Data consistency checks (0 mismatches), performance benchmarks (12.10x improvement)
- [x] **[Python]** **[DB]** Phase 4b: Primary source cutover — `get_image_details()`, `get_images_by_folder()` use normalized keywords (v6.3.1)
- [x] **[Python]** **[DB]** Phase 4c: Soft deprecation logging — warnings when legacy column accessed (v6.4.0 unreleased)
- [ ] **[Python]** **[DB]** Phase 4d: Hard deprecation — remove `IMAGES.KEYWORDS` column (v7.0, July 2026)
- [ ] **[Electron]** Phase 4 (coordinated): Query/read path updates for normalized keywords when gallery cuts over (see [AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md))
- [ ] **[Python]** **[DB]** Phase 5: PostgreSQL optimizations roadmap — embedding storage consolidation (`image_embeddings` SSOT), integrity constraints (job/phase status), JSONB where appropriate — [POSTGRES_SCHEMA_OPTIMIZATIONS.md](docs/planning/database/POSTGRES_SCHEMA_OPTIMIZATIONS.md)

### Firebird → PostgreSQL ([FIREBIRD_POSTGRES_MIGRATION.md](docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md))

Python backend is **PostgreSQL-native**; Firebird runtime and dual-write queue were **removed** (2026-03). `_translate_fb_to_pg()` remains for translating legacy-dialect SQL to PostgreSQL where needed.

- [x] **[Python]** **[DB]** Phases 0–3: Postgres schema, migration tooling, Python cutover to `database.engine: postgres`
- [x] **[Electron]** Phase 4: DB provider in `electron/db.ts`, Postgres client — **complete** in image-scoring-gallery (see gallery [`TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/TODO.md) Database section)

---

## Low Priority

### Infrastructure

- [ ] **[DB]** **[Python]** Database migration tooling — ongoing Alembic revisions and runbooks
- [ ] **[Python]** Batch API endpoints — REST API for programmatic access
- [ ] **[Python]** Cloud processing support — remote GPU inference (RunPod, Lambda Labs)

### UI & Future

- [ ] **[Gradio]** Gallery themes and customization — user-selectable color themes
- [ ] **[Gradio]** Keyboard navigation — full keyboard support for gallery navigation
- [ ] **[Python]** Video quality assessment — extend scoring to video files
- [ ] **[Python]** Real-time camera assessment — live feed quality analysis
- [ ] Mobile app support — native mobile application
- [ ] **[Python]** Web API/service — deployable scoring service
- [ ] **[Python]** Adobe Lightroom Classic plugin — native Lightroom integration
- [ ] **[Python]** Capture One workflow — culling workflow for Capture One
- [ ] **[Python]** Photo Mechanic integration — ingest workflow support

---

## Related Docs

- [docs/project/00-backlog-workflow.md](docs/project/00-backlog-workflow.md) — Hierarchy, sync order, picking tasks, counts (aligned with gallery repo)
- [docs/project/BACKLOG_GOVERNANCE.md](docs/project/BACKLOG_GOVERNANCE.md) — Alias to `00-backlog-workflow.md`
- [docs/planning/database/NEXT_STEPS.md](docs/planning/database/NEXT_STEPS.md) — DB refactor Phase 4 details
- [docs/technical/AGENT_COORDINATION.md](docs/technical/AGENT_COORDINATION.md) — Electron sync protocol
- [docs/features/planned/embeddings/](docs/features/planned/embeddings/) — Embedding roadmap and [NEXT_STEPS.md](docs/features/planned/embeddings/NEXT_STEPS.md)
- [docs/planning/database/](docs/planning/database/) — DB migration and vector refactor plans
