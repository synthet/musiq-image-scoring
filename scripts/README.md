# Scripts

Utility scripts for the Image Scoring project. Most scripts that use the database or ML models should be run in **WSL** with the same environment as the WebUI (`~/.venvs/tf`).

## Subfolders

| Folder | Purpose |
|--------|---------|
| `backup/` | Backup drive sync, cleanup, structure reorganization |
| `maintenance/` | DB maintenance, backfill, cleanup, migrations |
| `python/` | Core Python utilities: scoring, gallery, keywords, batch processing |
| `analysis/` | Score analysis, normalization checks, progress monitoring |
| `debug/` | DB diagnostics (e.g. `debug_firebird.py`, `test_db_conn.py`) |
| `utils/` | Test DB creation, PyIQA model listing, remove empty dirs |
| `setup/` | GPU/WSL setup helpers (`setup_wsl.bat`, `setup_windows_native.bat`) |
| `batch/` | Windows batch wrappers |
| `powershell/` | PowerShell wrappers |
| `wsl/` | WSL test runner and setup |
| `archive/` | Archived one-time/debug scripts |

## Running Scripts

**From WSL** (recommended):

```bash
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
source ~/.venvs/tf/bin/activate
python scripts/path/to/script.py
```

**From Windows** — use the provided `.bat` wrappers (e.g. `run_backfill_exif_xmp.bat`, `run_recalc_v5.bat`, `run_analysis.bat`) or invoke via WSL.

## Key Scripts

| Script | Purpose |
|--------|---------|
| `backup/cleanup_backup.py` | Remove rejected/red images from backup drive |
| `backup/sync_backup.py` | Sync picked images to backup drive |
| `backup/fix_backup_structure.py` | Reorganize backup by EXIF or mirror source |
| `backup/fix_all_backups.py` | Orchestrate full backup drive cleanup |
| `maintenance/backfill_exif_xmp.py` | Backfill EXIF/XMP into cache tables |
| `maintenance/cleanup_orphans.py` | Remove orphan images and empty folders |
| `maintenance/check_stacks.py` | Report folders missing stacks |
| `maintenance/update_db_paths.py` | Update DB paths after backup reorganization |
| `python/recalc_scores.py` | Recalculate scores with new formula |
| `python/recalc_scores_v5.py` | Recalculate with v5 percentile normalization |
| `python/run_all_musiq_models.py` | Run MUSIQ models on images |
| `python/gallery_generator.py` | Generate MUSIQ gallery HTML |
| `python/keyword_extractor.py` | AI keyword extraction |
| `analysis/score_analysis.py` | Score statistics and normalization verification |
| `research_models.py` | Research NEF→model input parameters |


## Repository Safety Check

Run the unresolved conflict marker check locally before pushing:

```bash
scripts/check_conflict_markers.sh
```

The script scans tracked source files under `modules/`, `tests/`, and `scripts/`, and fails if it finds unresolved merge markers (start/split/end conflict marker lines).

## API Contract Scripts

| Script | Purpose |
|--------|---------|
| `generate-api-types.mjs` | Deterministically generate `electron/apiTypes.ts` from root `openapi.json`. |
| `validate-api-types.mjs` | Regenerate and fail with diff + regeneration command if `electron/apiTypes.ts` is stale. |

Use `npm run api:types:generate` (local + CI standard) and `npm run api:types:check` for validation.
