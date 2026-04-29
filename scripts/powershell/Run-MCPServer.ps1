# Run MCP server for Vexlum
# Provides debugging tools for Cursor IDE

param(
  [switch]$Help
)

if ($Help) {
  Write-Host @"
Vexlum MCP server
========================

This script starts the MCP (Model Context Protocol) server that provides
debugging tools accessible from Cursor IDE.

Available Tools (28 total — see modules/mcp_server.py):
  - get_database_stats, query_images, get_image_details, search_images_by_hash, execute_sql
  - get_failed_images, get_incomplete_images, get_error_summary, check_database_health
  - validate_file_paths, diagnose_phase_consistency
  - get_recent_jobs, get_runner_status, get_pipeline_stats, get_performance_metrics, run_processing_job
  - get_model_status, validate_config, get_config, set_config_value, read_debug_log
  - get_folder_tree, get_stacks_summary
  - search_similar_images, find_near_duplicates, propagate_tags, find_outliers
  - execute_code (SSE WebUI + ENABLE_MCP_EXECUTE_CODE=1)

Usage:
  .\Run-MCPServer.ps1       # Start the server
  .\Run-MCPServer.ps1 -Help # Show this help

Configuration:
  Add to Cursor's MCP settings:
  {
    "name": "imgscore-py-stdio",
    "command": "python",
    "args": ["-m", "modules.mcp_server"],
    "cwd": "${workspaceFolder}",
    "env": { "PYTHONPATH": "${workspaceFolder}" }
  }
"@
  exit 0
}

# Change to project root
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Join-Path $scriptDir "../.." -Resolve
Set-Location $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Vexlum MCP server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Debugging tools for Cursor IDE" -ForegroundColor Yellow
Write-Host "Run with -Help for tool list" -ForegroundColor Yellow
Write-Host ""

# Check if mcp package is installed
$mcpCheck = python -c "import mcp; print('ok')" 2>&1
if ($mcpCheck -ne "ok") {
  Write-Host "Warning: MCP SDK not installed. Installing..." -ForegroundColor Yellow
  pip install mcp
}

# Run the server
python -m modules.mcp_server

