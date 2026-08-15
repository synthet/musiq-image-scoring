@echo off
REM Recalculate all scores using v5.0 percentile normalization
REM Runs in image-scoring-gpu-shell.
REM Usage: scripts\run_recalc_v5.bat [--dry-run]

call "%~dp0batch\docker_gpu_run.bat" scripts/python/recalc_scores_v5.py %*
