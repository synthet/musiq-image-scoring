@echo off
REM Backfill EXIF and XMP metadata into IMAGE_EXIF/IMAGE_XMP tables.
REM Runs in image-scoring-gpu-shell.
REM
REM Usage: run_backfill_exif_xmp.bat [--limit N] [--folder path] [--dry-run] [--all]
REM By default processes only images without cached EXIF/XMP. Use --all to reprocess everything.
call "%~dp0..\batch\docker_gpu_run.bat" scripts/maintenance/backfill_exif_xmp.py %*
pause
