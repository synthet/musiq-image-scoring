@echo off
setlocal
cd /d "%~dp0..\.."

REM One-shot: run python inside image-scoring-gpu-shell.
REM Usage: scripts\batch\docker_gpu_run.bat scripts\doctor.py --no-gpu
REM        scripts\batch\docker_gpu_run.bat -c "import torch; print(torch.cuda.is_available())"
REM Long jobs: set GPU_SHELL_DETACH=1

if "%~1"=="" (
    echo Usage: %~nx0 [python args...]
    echo Example: %~nx0 scripts\doctor.py --no-gpu
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' python %*; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
