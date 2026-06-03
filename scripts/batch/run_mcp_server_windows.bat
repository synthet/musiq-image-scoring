@echo off
REM Standalone MCP stdio for Cursor (Windows .venv). No pause — stdio must stay open.
setlocal enabledelayedexpansion

cd /d "%~dp0..\.."
set "PROJECT_ROOT=%CD%"
set "PATH=%PROJECT_ROOT%\Firebird;%PATH%"
set ENABLE_MCP_SERVER=1

if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
) else (
    echo ERROR: .venv not found. Run scripts\setup\setup_windows_native.bat first. 1>&2
    exit /b 1
)

python -m modules.mcp_server
