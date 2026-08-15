@echo off
REM Run score analysis in image-scoring-gpu-shell.
REM Usage: scripts\run_analysis.bat [--stats] [--distribution] [--spot-check N] [--verify-norm] [-o report.txt]

call "%~dp0batch\docker_gpu_run.bat" scripts/analysis/score_analysis.py %*
pause
