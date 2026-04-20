---
name: scoring-pipeline
description: Python scoring pipeline architecture — models, workers, engine, and how to extend the system.
---

# Scoring Pipeline

The image-scoring project uses a multi-stage pipeline to assess image quality using neural network models. This skill covers the architecture, key modules, and how to safely make changes.

## Architecture Overview

```
Input (folder/file)
  → PrepWorker (RAW conversion, thumbnails, skip checks)
    → ScoringWorker (GPU inference: MUSIQ, LIQE, TOPIQ)
      → ResultWorker (DB upsert, XMP metadata write, cleanup)
```

The pipeline uses **producer-consumer queues** with `threading.Thread` workers.

## Key Modules

| Module | Purpose |
|--------|---------|
| `modules/pipeline.py` | Worker classes: `PrepWorker`, `ScoringWorker`, `ResultWorker`, `ImageJob` dataclass |
| `modules/scoring.py` | `ScoringRunner` — orchestrates batch/single scoring, Fix DB, and metadata repair |
| `modules/engine.py` | `BatchImageProcessor` — low-level batch processing engine |
| `modules/config.py` | `load_config()`, `get_config_value()` — reads `config.json` |
| `modules/utils.py` | Path conversion (WSL ↔ Windows), hashing, thumbnail utilities |

## Model Wrappers

| File | Model | Framework | Score Range |
|------|-------|-----------|-------------|
| `musiq/run_all_musiq_models.py` | MUSIQ (SPAQ, AVA, KonIQ, PaQ2PiQ) | TensorFlow | 0–100 (normalized to 0–1) |
| `modules/liqe.py` | LIQE (language-image quality evaluator) | PyTorch (pyiqa) | 1–5 (normalized to 0–1) |
| `modules/topiq.py` | TOPIQ-IAA | PyTorch (pyiqa) | 0–1 |
| `modules/qalign.py` | Q-Align | PyTorch | 1–5 |

## Scoring Formulas (Current)

```
General  = 0.50 × LIQE + 0.30 × AVA + 0.20 × SPAQ
Technical = LIQE (primary)
Aesthetic = 0.60 × AVA + 0.40 × SPAQ
```

All composite scores are stored as floats 0.0–1.0 in the database.

## Hybrid Environment

- **Windows**: Runs the WebUI, PostgreSQL DB (port 5432), and file management.
- **WSL 2 (Linux)**: Runs GPU inference (TensorFlow + PyTorch with CUDA).
- Path conversion is handled automatically (`/mnt/d/...` ↔ `D:\...`) in `modules/utils.py`.
- **CRITICAL**: Database access from WSL must use TCP (port 3050), never direct file access.

## Test Database Safety

When running or writing tests:
- **Use only** the test database **`image_scoring_test`** (PostgreSQL).
- **Never** use production database names (`scoring_history.fdb` / `image_scoring`) in test code or config.
- Enforcement is automatic in `modules/db.py` and `modules/db_postgres.py` via `DB_FILE` and `POSTGRES_TEST_DB` constants when `pytest` is active.

## Backend Implementer Persona

When acting as `imgscore-backend-implementer`:
- **Scope**: `modules/*`, REST/API, phase logic, DB layer, migrations.
- **Out of Scope**: Gallery/Electron UI unless COORDINATED contract change.
- **Minimal Diff**: One logical change per pass; no drive-by refactors or formatting sweeps.
- **Style**: Match existing style, imports, and error-handling.

## How to Add a New Model

1. Create a wrapper in `modules/` (e.g., `modules/newmodel.py`) that exposes a `score(image_path) → float` method.
2. Import and call it in `ScoringWorker.process()` inside `modules/pipeline.py`.
3. Add the raw score column to the DB schema in `modules/db.py` → `_init_db_impl()`.
4. Update the composite formulas in `modules/scoring.py` → `ScoringRunner.fix_image_metadata()`.
5. Add normalization logic if the model's native range isn't 0–1.
6. Update `SCORING_CHANGES.md` and `CHANGELOG.md`.

## Common Tasks

### Run scoring on a folder
```powershell
.\Run-Scoring.ps1 -InputPath "C:\path\to\photos"
```

### Run scoring via WebUI
Start the WebUI (`python webui.py`) and use the **Scoring** tab.

### Fix metadata without re-running models
Use `ScoringRunner.fix_image_metadata(file_path)` — recalculates composite scores from existing raw scores.

## Configuration

All config lives in `config.json` at the project root. Key sections:
- `database` — filename, user, password
- `scoring` — force_rescore_default, model weights
- `system` — allowed_paths, log_dir
