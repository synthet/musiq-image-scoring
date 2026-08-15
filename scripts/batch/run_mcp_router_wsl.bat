@echo off
REM Standalone MCP router stdio for Cursor (gpu-shell). No pause.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' -Env ENABLE_MCP_SERVER=1 -Env MCP_TOOL_PROFILE=router python -m modules.mcp.router_server; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
