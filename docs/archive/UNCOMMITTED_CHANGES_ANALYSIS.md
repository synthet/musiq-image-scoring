# Analysis and Summary of Uncommitted Changes

**Generated:** 2025-01-29  
**Scope:** All modified (M) and untracked (??) files per `git status`.

---

## 1. Overview

| Category | Files | Summary |
|----------|--------|---------|
| **Modified** | 14 | ~2,131 insertions, ~1,224 deletions |
| **Untracked** | 21 | New modules, docs, tests, and utilities |

The changes implement a **multi-model, multi-source image quality assessment system**: local TensorFlow/PyIQA models, optional PyIQA models (Q-Align, TOPIQ, MUSIQ-IAA, LIQE), and **remote cloud APIs** (EveryPixel, SightEngine). The pipeline, DB, UI, and scoring runner are updated to support **model selection**, **remote scoring**, **new score columns**, and **export/filter** by those scores.

---

## 2. Modified Files â€” Summary

### 2.1 Configuration & Ignore

| File | Changes |
|------|---------|
| **`.gitignore`** | Added `secrets.json` so API keys (EveryPixel, SightEngine) are not committed. |
| **`modules/config.py`** | New `SECRET_FILE = "secrets.json"`, `load_secrets()`, `get_secret(section, key?)` for EveryPixel/SightEngine credentials. |

### 2.2 Documentation

| File | Changes |
|------|---------|
| **`docs/technical/MULTI_MODEL_SCORING.md`** | Reworked for the expanded system: multi-model ensemble, TensorFlow + PyIQA + Cloud APIs; weighted General/Technical/Aesthetic formulas; model ranges table; rating/label rules; DB schema; WebUI/CLI usage; dependencies (PyTorch, PyIQA, etc.). |

### 2.3 Database (`modules/db.py`)

- **New score columns** (and upsert support): `score_qalign`, `score_topiq`, `score_musiq`, `score_qpt_v2`, `score_aesmamba`, `score_everypixel_quality`, `score_sightengine_quality`, `remote_scores_json`.
- **Export**: `_build_export_where_clause` and `export_db_to_csv` / `export_db_to_excel` extended with `min_score_qalign`, `min_score_topiq`, `min_score_musiq`, `min_score_liqe`; export column sets include the new score columns.
- **Upsert**: Reads new scores from the result dict, passes them into the INSERT/UPDATE, and stores `remote_scores_json`.
- **Debug logging**: Multiple `#region agent log` blocks writing JSON lines to `.cursor/debug.log` (hardcoded paths). **Recommendation:** Remove before commit or gate behind a debug flag.

### 2.4 Pipeline (`modules/pipeline.py`)

- **`ImageJob`**: New `selected_models: List[str]` and `remote_scoring_threshold: float`.
- **`ScoringWorker`**: Accepts `remote_clients`; fetches `job.selected_models` and `job.remote_scoring_threshold`; calls `run_all_models`; then **remote scoring**: if `score_general >= remote_scoring_threshold`, calls EveryPixel and/or SightEngine per selection, merges `score_everypixel_quality` / `score_sightengine_quality` and `remote_scores_json` into the result.
- **`PrepWorker`** (hash/dedupe): Backfill logic generalized. Preserves *all* existing `score_*` values from DB into `external_scores` (with normalized scores). Skip logic made **model-aware**: required models derived from `job.selected_models` (local_models, everypixel_stock/ugc, sightengine, qalign, topiq, musiq, etc.); skip only when required scores + version + rating/label exist.
- **`ResultWorker`**: Logs and uses EveryPixel/SightEngine in â€œused modelsâ€ and score breakdown.
- **LIQE in pipeline**: `LiqeScorer` usage removed from pipeline; LIQE is invoked via `run_all_models` (MultiModelMUSIQ + wrappers).
- **Debug logging**: Several `#region agent log` blocks logging to `.cursor/debug.log`. **Recommendation:** Remove or make conditional.

### 2.5 Scoring Runner (`modules/scoring.py`)

- **`ScoringRunner`**: Instantiates `remote_scoring.EveryPixelClient` and `SightEngineClient`; holds `remote_clients` dict.
- **`start_batch`** / **`_run_batch_internal`**: New parameters `selected_models` and `remote_threshold` (default `0.62`). Determines `models_to_load` and `remote_models_to_check` from `selected_models`; tests remote client connectivity; builds `effective_selected_models` (drops failed remotes); passes `effective_selected_models` and `remote_threshold` into the engine/processor.
- **Batch processor**: Gets `remote_clients` and passes `selected_models` / `remote_threshold` into `process_directory` / `process_list`.
- **Single-image flow**: Creates `ImageJob` with `selected_models`; uses `process_list` with the same model selection.
- **Config**: Reads `default_models` from config for model selection.
- **Debug logging**: Multiple `#region agent log` blocks. **Recommendation:** Remove or gate.

### 2.6 Engine (`modules/engine.py`)

- **`BatchImageProcessor`**: Constructor accepts `remote_clients`; `process_directory` and `process_list` accept `selected_models` and `remote_threshold`.
- **Folder skip**: When `skip_existing` is True, folder skip is **disabled** if any selected model is not `local_models` (e.g. remotes or specific PyIQA models). Ensures we still walk into folders to run remote/specific models even when â€œlocal-onlyâ€ would skip.
- **Workers**: `ScoringWorker` receives `remote_clients`; each `ImageJob` gets `selected_models` and `remote_scoring_threshold`.

### 2.7 UI â€” App (`modules/ui/app.py`)

- **`DETAIL_OUTPUTS_COUNT`**: 19 â†’ 20 (new `d_high_preview`).
- **Status timer**: 1s â†’ 2s to reduce load and avoid â€œBroken Connectionâ€ during heavy scoring.
- **Detail outputs**: New `d_high_preview`; unpack order updated.
- **Export / load**: Export and initial-load logic updated for `min_qalign`, `min_topiq`, `min_musiq`, `min_liqe`, and `stack_id`.
- **Monitor loop**: `monitor_status_wrapper` wrapped in try/except with `_status_fallback` so one tabâ€™s failure doesnâ€™t kill the status connection.

### 2.8 UI â€” Common (`modules/ui/common.py`)

- **`rerun_scoring_wrapper`** / **`rerun_keywords_wrapper`**: Return `gr.update(value=..., visible=True)` for the status component instead of a plain string, so the success/error message is shown reliably.
- **`get_empty_details()`**: Prepends `gr.update(value=None)` for `d_high_preview`.

### 2.9 UI â€” Navigation (`modules/ui/navigation.py`)

- **`open_folder_in_gallery`**, **`open_stack_folder_in_gallery`**, **`open_stack_in_gallery`**: All updated to pass `min_qalign`, `min_topiq`, `min_musiq`, `min_liqe` through to `update_gallery_fn`.

### 2.10 UI â€” Gallery (`modules/ui/tabs/gallery.py`)

- **`update_gallery`** / **`get_gallery_data`**: New filter params `min_qalign`, `min_topiq`, `min_musiq`, `min_liqe`; passed to DB query.
- **Sort dropdown**: New options: EveryPixel Quality, SightEngine Quality, Q-Align, TOPIQ, MUSIQ; LIQE retained.
- **Filters**: New sliders Min Q-Align, Min TOPIQ, Min MUSIQ, Min LIQE.
- **Advanced export**: `score_cols` extended with `score_qalign`, `score_topiq`, `score_musiq`, `score_everypixel_quality`, `score_sightengine_quality`; `metadata_cols` defined; **duplicate** `basic_cols` and `metadata_cols` assignments (lines 572â€“576). **Bug:** Remove duplicates.
- **Detail panel**: New `d_high_preview` (full-res preview image); `display_details` receives `sort_dropdown` in addition to `current_paths`.
- **Filter wiring**: `filter_inputs_base` includes the four new min-score sliders.

**Potential bug:** `f_min_liqe` slider is `0.0â€“5.0`. LIQE (PyIQA) uses a 0â€“1 range. Consider `max=1.0` for consistency.

### 2.11 UI â€” Scoring (`modules/ui/tabs/scoring.py`)

- **`run_scoring_wrapper`**: Now takes `selected_models` and `remote_threshold`; passes them to `runner.start_batch`.
- **New controls**: **Model selection** dropdown (`local_models`, `qalign`, `topiq`, `musiq`, `liqe`, `everypixel_ugc`, `everypixel_stock`, `sightengine`, multiselect) and **Remote threshold** slider (0â€“1, default 0.62) for â€œMin General Score for Remote APIsâ€.
- **Run button**: Wired to `model_selection` and `remote_threshold`.

### 2.12 Scripts & Lock

| File | Changes |
|------|---------|
| **`scripts/python/run_all_musiq_models.py`** | Project-root path setup and imports for `QAlignScore`, `TopiqScore`, `MusiqScore`, `LiqeScore`; RAW conversion fixes (ExifTool JpgFromRaw/PreviewImage validation, size/black checks, rawpy fallback, `_is_image_valid`); PyIQA model loading (qalign, topiq, musiq, liqe) and `model_ranges`; LIQE range 1â€“5 â†’ 0â€“1; `failed_predictions` only for actual inference failures; normalization fallbacks for EveryPixel/SightEngine; weighted summary; CLI `--models` extended (`qpt_v2`, `aesmamba`); one `#region agent log` block. |
| **`webui.lock`** | PID/port updated (running instance). No functional impact. |

---

## 3. Untracked Files â€” Summary

### 3.1 New Modules (used by scoring/pipeline)

| File | Purpose |
|------|---------|
| **`modules/liqe_wrapper.py`** | PyIQA-based LIQE wrapper; `LiqeScore` with `predict(image_path)` â†’ 0â€“1. |
| **`modules/musiq_wrapper.py`** | PyIQA MUSIQ wrapper for MUSIQ-IAA. |
| **`modules/qalign.py`** | PyIQA Q-Align wrapper; `QAlignScore`. |
| **`modules/topiq.py`** | PyIQA TOPIQ-IAA wrapper; `TopiqScore`; optional CPU fallback on OOM. |
| **`modules/remote_scoring.py`** | `EveryPixelClient` and `SightEngineClient`; `test_connection`, `score_image`; credentials via `config.get_secret(...)`. |

### 3.2 Documentation

| File | Purpose |
|------|---------|
| **`docs/reference/models/MODEL_WEIGHTS.md`** | Documents current General/Aesthetic/Technical weights (e.g. PaQ2PiQ, LIQE, AVA, KonIQ, SPAQ). |
| **`docs/planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md`** | Suggests alternative weights (e.g. more LIQE, less MUSIQ) and optional use of QPT V2 / AesMamba. |
| **`docs/reports/IAA_PAPER_ANALYSIS.md`** | Likely notes from API/docs analysis (e.g. EveryPixel, SightEngine). |

### 3.3 Tests & Utilities

| File | Purpose |
|------|---------|
| **`check_thumb.py`** | Thumbnail checking utility. |
| **`scripts/debug/reproduce_crash.py`** | Crash reproduction script. |
| **`scripts/debug/verify_fix_logic.py`** | Verification for fix logic. |
| **`scripts/utils/list_pyiqa_models.py`** | List PyIQA models. |
| **`scripts/python/check_topiq_range.py`** | Check TOPIQ output range. |
| **`scripts/unmark_folder.py`** | Unmark folder (e.g. scored flag). |

### 3.4 PDF Extraction & Data

| File | Purpose |
|------|---------|
| **`scripts/utils/extract_pdf.py`**, **`scripts/utils/extract_pdf_new.py`** | PDF extraction scripts. |
| **`pdf_content.txt`**, **`pdf_content_2024_2025.txt`** | Extracted PDF text. |

---

## 4. Technical Highlights

### 4.1 Model Selection & Remote Scoring

- Users choose **which** models/APIs run (local_models, qalign, topiq, musiq, liqe, everypixel_ugc/stock, sightengine).
- **Remote APIs** run only when `score_general >= remote_threshold` (default 0.62).
- Remote clients are tested at batch start; failed APIs are skipped; local models still run.

### 4.2 Skip / Backfill Logic

- **Folder skip**: Disabled when any nonâ€“local model is selected.
- **Per-image skip**: Required models derived from `selected_models`; skip only if all required scores exist, version matches, and rating/label present.
- **Backfill**: All existing `score_*` values are preserved and passed as `external_scores` so only missing models are run.

### 4.3 RAW Handling

- ExifTool JpgFromRaw/PreviewImage validated (dimensions, black image check).
- `_is_image_valid` rejects too-small or effectively black images.
- rawpy used as fallback for HE/HE* where appropriate.
- Reject invalid conversions instead of scoring bad intermediates.

### 4.4 UI Robustness

- Status polling interval increased; monitor wrapped with fallback to avoid broken connection.
- Rerun buttons return `gr.update(...)` for status.
- Full-res preview and new sort/filter options for additional scores.

---

## 5. Issues & Recommendations

### 5.1 Remove or Gate Debug Logging

- **Files:** `modules/db.py`, `modules/pipeline.py`, `modules/scoring.py`, `scripts/python/run_all_musiq_models.py` (and possibly `modules/ui/assets.py`).
- **Issue:** `#region agent log` blocks write to `.cursor/debug.log` with hardcoded paths (`/mnt/[drive]/...`, `d:\...`).
- **Recommendation:** Remove before commit, or gate behind a debug flag and use a configurable path.

### 5.2 Gallery Bugs

- **Duplicate `basic_cols` / `metadata_cols`** in `modules/ui/tabs/gallery.py` (Advanced export). Remove the duplicate lines.
- **Min LIQE slider:** `max=5.0` vs LIQE 0â€“1. Consider `max=1.0` and `step=0.05` for consistency.

### 5.3 Secrets and Config

- **`secrets.json`**: Add a `secrets.json.example` (or doc) listing expected keys for EveryPixel/SightEngine so deployers know the shape. Ensure `secrets.json` stays gitignored.

### 5.4 DB Migrations

- New columns (`score_*`, `remote_scores_json`) require migrations or schema updates for existing DBs. Confirm migration path (e.g. Firebird DDL or SQLite `ALTER TABLE`) before release.

### 5.5 Untracked Code

- **`modules/remote_scoring.py`**, **`modules/liqe_wrapper.py`**, **`modules/musiq_wrapper.py`**, **`modules/qalign.py`**, **`modules/topiq.py`** are **required** by the modified pipeline/scoring/scripts. Plan to add and commit them.
- Prefer adding **tests** (e.g. `test_musiq_inference`, extraction tests) to the test suite rather than keeping them only as adâ€‘hoc scripts.
- **`scripts/utils/extract_pdf*.py`** and **`pdf_content*.txt`** look auxiliary; keep or add only if relevant to the project.

---

## 6. Suggested Commit Structure

1. **Config & secrets:** `.gitignore`, `modules/config.py`, `secrets.json.example` (if added).
2. **Remote scoring:** `modules/remote_scoring.py`; optionally `docs/reports/IAA_PAPER_ANALYSIS.md` if useful.
3. **PyIQA wrappers:** `modules/liqe_wrapper.py`, `modules/musiq_wrapper.py`, `modules/qalign.py`, `modules/topiq.py`.
4. **DB:** `modules/db.py` (after removing debug logging and adding migrations if needed).
5. **Pipeline & engine:** `modules/pipeline.py`, `modules/engine.py` (debug logging removed).
6. **Scoring:** `modules/scoring.py` (debug logging removed).
7. **Scripts:** `scripts/python/run_all_musiq_models.py` (debug logging removed).
8. **UI:** `modules/ui/app.py`, `common.py`, `navigation.py`, `tabs/gallery.py`, `tabs/scoring.py`; fix gallery bugs (duplicates, Min LIQE).
9. **Docs:** `docs/technical/MULTI_MODEL_SCORING.md`, `docs/reference/models/MODEL_WEIGHTS.md`, `docs/planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md` (if desired).
10. **Tests & utilities:** Add chosen tests/scripts and wire them into the suite.

**Do not commit:** `webui.lock` (or keep as local-only), `secrets.json`, `pdf_content*.txt` (unless intentional), and any temporary debug-only edits.

---

## 7. Quick Reference

| Area | Key changes |
|------|-------------|
| **Models** | Local (SPAQ, AVA, KonIQ, PaQ2PiQ) + LIQE + Q-Align, TOPIQ, MUSIQ-IAA; EveryPixel, SightEngine. |
| **Config** | `secrets.json` + `get_secret` for API keys. |
| **DB** | New `score_*` and `remote_scores_json`; export/filter by min qalign/topiq/musiq/liqe. |
| **Pipeline** | `selected_models`, `remote_threshold`, `remote_clients`; model-aware skip and remote scoring. |
| **UI** | Model selection, remote threshold, new sort/filters, full-res preview, status robustness. |
| **RAW** | ExifTool validation, black/size checks, rawpy fallback, `_is_image_valid`. |

## Related Documents

- [Docs index](../INDEX.md)
- [Model weights](../reference/models/MODEL_WEIGHTS.md)
- [Suggested scoring adjustments](../planning/models/SUGGESTED_SCORING_ADJUSTMENTS.md)
- [IAA paper analysis](../reports/IAA_PAPER_ANALYSIS.md)
- [Project reviews](project-reviews/)
- [Technical summary](../architecture/technical-summary.md)

