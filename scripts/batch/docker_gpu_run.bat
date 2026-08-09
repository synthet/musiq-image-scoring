@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0..\.."

REM One-shot: run python inside the persistent gpu-shell container.
REM Usage: scripts\batch\docker_gpu_run.bat scripts\doctor.py --no-gpu
REM        scripts\batch\docker_gpu_run.bat -c "import torch; print(torch.cuda.is_available())"

if "%~1"=="" (
    echo Usage: %~nx0 [python args...]
    echo Example: %~nx0 scripts\doctor.py --no-gpu
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker daemon not ready. Start Docker Desktop and retry.
    exit /b 1
)

docker compose --profile gpu-shell up -d db gpu-shell
if errorlevel 1 (
    echo [ERROR] compose up failed. Build first: docker compose build webui
    exit /b 1
)

REM Prefer exec against long-lived shell (named container + persistent /root volumes).
REM Paths: use Linux-style under /app (compose mounts repo at /app).
docker exec -i image-scoring-gpu-shell python %*
exit /b %ERRORLEVEL%
