@echo off
REM Standalone MCP compact stdio for Cursor (gpu-shell). No pause.
REM Prefer node mcp-server/dist/compactIndex.js (see .cursor/mcp.example.json).
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0..\powershell\Invoke-GpuShell.ps1' -Env ENABLE_MCP_SERVER=1 -Env MCP_TOOL_PROFILE=compact python -m modules.mcp.router_server; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
