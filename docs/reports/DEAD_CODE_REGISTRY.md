# Dead Code Registry

Chronological record of confirmed orphan/dead code removed from the image-scoring monorepo. Each row cites GitHub history so removed code can be recovered from git if needed.

**Tracking issue:** [synthet/image-scoring-backend#252](https://github.com/synthet/image-scoring-backend/issues/252)

Sibling gallery registry: [image-scoring-gallery/docs/reports/DEAD_CODE_REGISTRY.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/reports/DEAD_CODE_REGISTRY.md)

---

## image-scoring-backend

| Item | Path(s) | Lines (approx.) | Reason | Introduced | Orphaned / disabled | Removed |
|------|---------|-----------------|--------|------------|---------------------|---------|
| Gradio Gallery tab | `modules/ui/tabs/gallery.py` | ~947 | No importers after React `/ui` SPA; `create_ui()` returns empty `gallery_components` | Pre-React Gradio product UI | [bf46137](https://github.com/synthet/image-scoring-backend/commit/bf46137) React SPA migration; CHANGELOG v3.x notes tab orphaned | #252 |
| Gradio Settings tab | `modules/ui/tabs/settings.py` | ~263 | No importers | Gradio era | [d3747b0](https://github.com/synthet/image-scoring-backend/commit/d3747b0) operator status shrink | #252 |
| Gradio pipeline fallback tab | `modules/ui/tabs/pipeline_fallback.py` | ~265 | PR #46 fallback; `ui.use_gradio_fallback` never wired from `app.py` | [25a3a61](https://github.com/synthet/image-scoring-backend/commit/25a3a61) | No `create_tab` caller | #252 |
| Gradio Pipeline tab (bulk) | `modules/ui/tabs/pipeline.py` | ~1550 | Only `get_runner_activity_snapshot` was live; extracted to `runner_snapshot.py` | Gradio era | [d3747b0](https://github.com/synthet/image-scoring-backend/commit/d3747b0) | #252 |
| Runner snapshot extract | `modules/ui/runner_snapshot.py` | ~55 | Replacement for live export from deleted `pipeline.py` | — | — | #252 |
| Gradio CSS/JS assets | `modules/ui/assets.py` | ~3400 | Zero imports of `get_css` / `get_tree_js`; `/app` uses inline CSS in `status_gradio.py` | Gradio era | [d3747b0](https://github.com/synthet/image-scoring-backend/commit/d3747b0) | #252 |
| Remote scoring clients | `modules/remote_scoring.py` | ~204 | EveryPixel/SightEngine HTTP scorers; no `modules/` imports | [e6df2a2](https://github.com/synthet/image-scoring-backend/commit/e6df2a2) (CHANGELOG L2122) | Never wired to pipeline | #252 |
| Culling page wrapper | `frontend/src/features/culling/pages/CullingPage.tsx` | ~10 | Route/nav removed; culling APIs/inspector/FolderPage stacks remain | [0b414da](https://github.com/synthet/image-scoring-backend/commit/0b414da) v7.11.0 | [89d7149](https://github.com/synthet/image-scoring-backend/commit/89d7149) v7.20.0 replaced `/culling` with `/db` | #252 |
| Unused React hook field | `frontend/src/hooks/useConfig.ts` → `isCullingEnabled` | ~1 | No consumers; `enable_culling` API flag retained | [0b414da](https://github.com/synthet/image-scoring-backend/commit/0b414da) | [89d7149](https://github.com/synthet/image-scoring-backend/commit/89d7149) | #252 |
| Deprecated XMP writer | `modules/xmp.py` → `write_pick_flag()` | ~47 | Zero callers; use `write_pick_reject_flag()` | Legacy XMP | Deprecated in-place | #252 |
| Firebird dual-write stub | `modules/db_legacy.py` → `get_dual_write_stats()` | ~4 | Always returned `enabled: False`; dual-write removed 2026-03 | Firebird era | Comment L285 dual-write removed | #252 |
| Firebird archived tests | `tests/archive_firebird/` | — | Excluded via `pytest.ini` `norecursedirs`; Postgres primary | Firebird era | Migration complete | #252 |
| Firebird archived scripts | `scripts/archive_firebird/` | — | One-off migration/check scripts | Firebird era | Migration complete | #252 |
| Debug archive scripts | `scripts/archive/` | ~10 files | One-off repro/debug; not in documented workflows | Various | Superseded by MCP/tests | #252 |

### Intentionally retained (not dead)

| Item | Why kept |
|------|----------|
| Firebird paths in `modules/db_legacy.py`, `FirebirdLinux/` | Deprecated compat shim until v7.0 hard removal |
| Deprecated REST aliases (`GET /api/similar`, etc.) | Still called from `frontend/src/api/gallery.ts` |
| `GET /api/config` → `enable_culling` | Public API flag + tests |
| `frontend/src/features/culling/` (except deleted page) | Inspector, FolderPage stacks, pick mutations |
| QPT V2 modules | Disabled pending #185 — feature scaffold |
| Config-gated UI (Atlas, DB Explorer, MCP `execute_code`) | Off by default but wired |

### Last-known-good SHAs (archive trees)

Before deleting archive directories, recover full trees from:

- `tests/archive_firebird/`: `git show HEAD~1:tests/archive_firebird/` (or pre-#252 commit)
- `scripts/archive_firebird/`: same pattern
- `scripts/archive/`: same pattern

---

## image-scoring-gallery

See [gallery DEAD_CODE_REGISTRY.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/reports/DEAD_CODE_REGISTRY.md).

---

## image-scoring-ui

See package CHANGELOG / registry note in gallery sibling doc; unused public exports trimmed in #252 cross-repo slice.
