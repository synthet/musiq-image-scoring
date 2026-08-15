@echo off
setlocal
cd /d "%~dp0..\.."

REM Run an arbitrary command inside image-scoring-gpu-shell.
REM Usage: scripts\batch\docker_gpu_exec.bat python scripts/doctor.py --no-gpu
REM        scripts\batch\docker_gpu_exec.bat bash scripts/research/clip_culling/resume_recluster.sh
REM Long jobs: set GPU_SHELL_DETACH=1

if "%~1"=="" (
    echo Usage: %~nx0 ^<command^> [args...]
    echo Example: %~nx0 python scripts/doctor.py --no-gpu
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' %*; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
