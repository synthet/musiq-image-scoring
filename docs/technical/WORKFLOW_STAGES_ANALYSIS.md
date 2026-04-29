# Vexlum Scoring — workflow architecture

## Overview
The application processes image collections through a structured pipeline of sequential phases. This pipeline is managed by orchestrators, background runners, and queue-based workers.

## Phases / Stages

### 1. Discovery (indexing)
* **Trigger:** Initiated by UI actions (Refresh, Run All, or selecting a folder for the first time). Orchestrated via the `PrepWorker` traversing directories (`os.walk`).
* **Processing:** Scans folders for supported image extensions (.jpg, .png, .nef, etc.), avoiding previously fully processed distinct ones if `skip_existing=True`.
* **Actions:** Registers new files.
* **Data/Artifacts:** Inserts/Upserts rows into the `images` table (`file_path`, `folder_id` attributes).
* **Completion/State:** Implicitly completed once the directory is traversed and items are enqueued to the next stage.
* **Gaps:** Tightly coupled with the Scoring pipeline inside `engine.py` (`PrepWorker`). It lacks an independent job runner context, making phase-level tracking (Image Phase Status - IPS) prone to desync if interrupted.

### 2. Inspection (metadata)
* **Trigger:** Initiated alongside Discovery or explicitly via "Run Inspection" in the UI target `target_phases=["indexing", "metadata"]`.
* **Processing:** Uses extraction tools to read embedded EXIF/XMP tags and generate lightweight thumbnails for UI display.
* **Actions:** Reads metadata, writes thumbnail files.
* **Data/Artifacts:** Inserts rows into the `image_exif` table. Updates `metadata` and `thumbnail_path` on the `images` table.
* **Completion/State:** Marked `done` in `image_phase_status` (IPS) upon success.
* **Gaps:** Also tightly coupled with the Prep phase of Scoring. The UI contains a dedicated "Repair Discovery/Inspection" button specifically to backfill states for images that scored fine but dropped their inspection status.

### 3. Quality Analysis (scoring)
* **Trigger:** Enqueued via `db.enqueue_job(phase_code="scoring", job_type="scoring")`. Picked up by the `ScoringWorker`.
* **Processing:** Executes Deep Learning models evaluating SPAQ, KonIQ, Aesthetic, and Technical scores.
* **Actions:** Batch GPU processing of images.
* **Data/Artifacts:** Populates `score_general`, `score_technical`, `score_aesthetic`, etc., in the `images` table.
* **Completion/State:** The `ResultWorker` consumes outputs from the ML queue and updates the DB with scores, setting the IPS row to `done`. Logs success or failure.

### 4. Similarity Clustering (culling)
* **Trigger:** Enqueued via `db.enqueue_job(phase_code="culling", job_type="selection")`. Supported by isolated runners.
* **Processing:** Uses embeddings (`image_embedding`) to calculate cosine similarity. Groups highly similar images into stacks and selects the best shot based on composition/score.
* **Actions:** Clustering algorithms, selection heuristics.
* **Data/Artifacts:** Generates rows in the `stacks` table. Updates `stack_id` on the `images` table.
* **Completion/State:** Updates folder/image phase statuses. Marks `culling` as `done`.
* **Gaps:** Relies on embeddings generated during Scoring. If Scoring fails to generate an embedding, Culling silently skips or fails for that subset.

### 5. Tagging (keywords)
* **Trigger:** Enqueued via `db.enqueue_job(phase_code="keywords", job_type="tagging")`. Picked up by `tagging_runner`.
* **Processing:** Employs CLIP for zero-shot keyword extraction and BLIP for caption generation.
* **Actions:** Evaluates text-image similarity to map predefined concepts.
* **Data/Artifacts:** Updates `keywords` string on `images`, populates `image_keywords` junction table.
* **Completion/State:** Sets IPS `keywords` to `done`.
* **Gaps:** A known defect exists regarding dual-write synchronicity (recently addressed in `implementation_plan.md.resolved`). Batch keyword applications can update the raw string but miss updating the junction tables, causing search misses.

### 6. Bird Species ID (bird_species)
* **Trigger:** Specialized job `job_type="bird_species"` running selectively over images already tagged with `birds`.
* **Processing:** Uses BioCLIP 2 to generate specialized softmax probabilities for known species dictionaries.
* **Actions:** Identifies species.
* **Data/Artifacts:** Prepends `species:[Name]` to existing strings in the `keywords` column.
* **Completion/State:** This is a disjointed phase logically—synthesized dynamically in `_synthetic_bird_species_job_phases` inside `api.py`.
* **Gaps:** Not tracked homogeneously in the UI phase stepper. Uses synthetic states when DB rows are missing.

---

## Architecture Gaps and Defects

1. **Job ID Propagation & Tracking Loss:**
   The `BatchImageProcessor` in `engine.py` notes a hack regarding `job_id` propagation:
   `# HACK: Retrieve job_id from somewhere or update signature?`
   If jobs lose their `job_id` context inside the memory queue, their completion status cannot correctly notify the caller or update the parent `jobs` payload, resulting in stuck `running` jobs or `pending` states.

2. **Phase Order and State Coupling:**
   Discovery and Inspection are implicitly wrapped by `Quality Analysis`. They do not possess a decoupled state machine. Ergo:
   - `ips_done_no_data` or `phase_order_violation` arise when one of these sub-steps fails silently but the overarching Scoring wrapper succeeds.
   - The system requires secondary backfill scripts (`repair_index_meta_btn`) to fix cache invalidation.

3. **Status Enumeration:**
   As highlighted in the analyzer script design, `pending` exists in a CHECK constraint but is missing from the underlying `PhaseStatus` enumeration entirely in certain dialects, polluting standard queries.

4. **Aggregate Drifts (Folder Metadata):**
   `folders.phase_agg_json` drifts from the explicit Image Phase Status. Updates inside workers do not reliably traverse up the tree to invalidate parent aggregates safely, causing mismatched "completed" frontend views while images are still processing.

---

## Operations: diagnostics and repairs

Use the **same environment as the webapp** (WSL + `~/.venvs/tf`, plus Firebird `LD_LIBRARY_PATH` as in `run_webui.bat`).

### Read-only: phase status vs. data

**Script:** [`scripts/analysis/analyze_phase_status.py`](../../scripts/analysis/analyze_phase_status.py)

Cross-checks `image_phase_status` against real columns (`scores`, `keywords`, `image_keywords`, embeddings, etc.), folder cache flags, bird-species keyword patterns, and stuck `running` IPS rows. Reports are labeled with **[GAP-A]** … **[GAP-K]** matching the gaps above.

```bash
# From WSL at repo root (adjust drive in /mnt/d/ if needed)
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
source ~/.venvs/tf/bin/activate
python scripts/analysis/analyze_phase_status.py
python scripts/analysis/analyze_phase_status.py --folder /mnt/d/Photos/Z8 --output /tmp/phase_report.json
```

### Write: targeted DB repairs

**Script:** [`scripts/maintenance/repair_analyzer_gaps.py`](../../scripts/maintenance/repair_analyzer_gaps.py)

| Flag | What it fixes |
|------|----------------|
| `--keywords` | **GAP-E** — `images.keywords` present but `image_keywords` empty (`db.repair_legacy_keywords_junction`) |
| `--index-meta` | **GAP-D** — scoring IPS `done` but indexing/metadata not (`db.backfill_index_meta_global`) |
| `--stuck-running` | **GAP-K** — IPS stuck in `running`/`queued` past N hours → `failed` (`db.repair_stuck_running_ips`) |
| `--folder-agg` | **GAP-F** — refresh `folders.phase_agg_json` (slow; use `--folder-agg-limit N` for batches) |

`--all` runs keywords + index-meta + stuck-running **only** (not folder aggregates). Add `--folder-agg` when you want cache rebuild.

**Not repaired here:** **Bird species** (**GAP-I**) — re-run the Bird Species job from the UI/API.

```bash
python -u scripts/maintenance/repair_analyzer_gaps.py --dry-run --all
python -u scripts/maintenance/repair_analyzer_gaps.py --all
python -u scripts/maintenance/repair_analyzer_gaps.py --folder-agg --folder-agg-limit 500
```

### Post-restore: analyze + repair suite

**Script:** [`scripts/maintenance/restore_consistency_suite.py`](../../scripts/maintenance/restore_consistency_suite.py)

Orchestrates the analyzer and `repair_analyzer_gaps` in a fixed order: optional pre-analysis JSON, `repair --all`, optional `--with-folder-agg` (rebuilds `folders.phase_agg_json` and related folder flags), optional `--with-embeddings` / `--with-exif-xmp` / `--with-hashes`, then optional `--verify` and `--report-json` with before/after `summary` blocks.

```bash
python scripts/maintenance/restore_consistency_suite.py full --dry-run --with-folder-agg
python scripts/maintenance/restore_consistency_suite.py full --with-folder-agg --report-json /tmp/restore_report.json
```

**Related DB helpers** (callable from Python): `repair_legacy_keywords_junction`, `backfill_index_meta_global`, `repair_stuck_running_ips`, `backfill_folder_phase_aggregates` in [`modules/db.py`](../../modules/db.py).

## Conclusion & Proposed Path Forward
To establish a rigid state machine where each phase handles triggers, processing, completion, and notifications reliably:
1. **Decouple Indexing/Metadata** out of `engine.py`'s `PrepWorker` into genuine independent queue jobs.
2. **Enforce Job_ID Context Injection** in constructor signatures rather than relying on `getattr(self, "current_job_id", 0)`.
3. **Event-Driven Rollups:** Use standard events (or DB triggers) to update folder/job-level run states immediately when child `image_phase_status` checks finalize, replacing the polling/periodic dual-sync mechanics.
