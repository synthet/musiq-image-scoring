@echo off
REM Populate missing embeddings in DB. Runs in image-scoring-gpu-shell.
REM Docs: docs/technical/EMBEDDINGS.md  |  Legacy alias: run_populate_missing_embeddings.bat
call "%~dp0..\batch\docker_gpu_run.bat" scripts/maintenance/populate_missing_embeddings.py %*
pause
