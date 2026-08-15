@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0..\.."

REM Interactive GPU shell (scripts / research). Reuses image-scoring:latest.
REM Prerequisites: Docker Desktop with GPU, image built (docker compose build webui).
REM Closes #326 / docs: guides/setup/DOCKER_SETUP.md (GPU shell)

if not defined DOCKER_BUILDKIT set "DOCKER_BUILDKIT=1"

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker daemon not ready. Start Docker Desktop and retry.
    exit /b 1
)

echo [INFO] Starting db + gpu-shell (profile gpu-shell)...
docker compose --profile gpu-shell up -d db gpu-shell
if errorlevel 1 (
    echo [ERROR] compose up failed. Build first: docker compose build webui
    exit /b 1
)

echo [INFO] Entering image-scoring-gpu-shell. Exit with Ctrl+D or "exit".
echo        One-shot python:    scripts\batch\docker_gpu_run.bat scripts\doctor.py --no-gpu
echo        Arbitrary command:  scripts\batch\docker_gpu_exec.bat python scripts/doctor.py --no-gpu
echo        Optional bootstrap: bash scripts/docker_gpu_shell_bootstrap.sh
echo        Student extras:     set INSTALL_STUDENT_SCORER=1 then re-run bootstrap
docker exec -it image-scoring-gpu-shell bash
exit /b %ERRORLEVEL%
