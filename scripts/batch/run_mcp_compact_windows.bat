@echo off
REM Compact MCP stdio (search + dispatch only). No pause — stdio must stay open.
setlocal enabledelayedexpansion

cd /d "%~dp0..\.."
set "PROJECT_ROOT=%CD%"
set ENABLE_MCP_SERVER=1
set MCP_TOOL_PROFILE=compact

if exist "%PROJECT_ROOT%\.venv\Scripts\activate.bat" (
    call "%PROJECT_ROOT%\.venv\Scripts\activate.bat"
) else (
    echo ERROR: .venv not found. Run scripts\setup\setup_windows_native.bat first. 1>&2
    exit /b 1
)

python -m modules.mcp.router_server
