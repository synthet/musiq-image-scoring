@echo off
REM Standalone MCP router stdio for Cursor (WSL + ~/.venvs/tf). No pause.
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
setlocal enabledelayedexpansion
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
set "WSL_PATH=!WSL_PATH:/mnt/E=/mnt/e!"
set "WSL_PATH=!WSL_PATH:/mnt/F=/mnt/f!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

wsl bash -c "cd '!WSL_PATH!' && export ENABLE_MCP_SERVER=1 && export MCP_TOOL_PROFILE=router && source ~/.venvs/tf/bin/activate && python -m modules.mcp.router_server"
