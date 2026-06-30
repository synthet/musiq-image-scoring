"""Run MCP tool extraction (Batch 1). Usage: python scripts/refactor/extract_mcp_tools_v2.py"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_PATH = ROOT / "modules" / "mcp_server.py"
TOOLS_DIR = ROOT / "modules" / "mcp" / "tools"

TOOL_MODULE: dict[str, str] = {
    "get_database_stats": "data",
    "query_images": "data",
    "get_image_details": "data",
    "search_images_by_hash": "data",
    "get_db_schema": "data",
    "execute_sql": "data",
    "get_folder_tree": "data",
    "get_newly_imported_folders": "data",
    "process_newly_imported_folders": "data",
    "get_stacks_summary": "data",
    "get_incomplete_images": "diagnostics",
    "get_failed_images": "diagnostics",
    "get_error_summary": "diagnostics",
    "check_database_health": "diagnostics",
    "validate_file_paths": "diagnostics",
    "diagnose_phase_consistency": "diagnostics",
    "get_stale_running_phase_status": "diagnostics",
    "get_recent_jobs": "jobs",
    "get_job_details": "jobs",
    "get_job_phases": "jobs",
    "get_job_stage_images": "jobs",
    "get_run_diagnostics": "jobs",
    "get_drive_diagnostics": "jobs",
    "get_job_execution_report": "jobs",
    "get_image_pipeline_failures": "jobs",
    "get_location_stats": "jobs",
    "export_debug_bundle": "maintenance",
    "get_embedding_stats": "jobs",
    "get_database_engine_info": "diagnostics",
    "check_stack_invariants": "diagnostics",
    "rebase_file_paths": "maintenance",
    "set_image_metadata": "maintenance",
    "prune_missing_files": "maintenance",
    "verify_environment": "diagnostics",
    "get_system_resources": "diagnostics",
    "get_thread_dump": "diagnostics",
    "get_runner_status": "jobs",
    "get_pipeline_stats": "jobs",
    "get_performance_metrics": "jobs",
    "get_model_status": "config_logs",
    "run_processing_job": "jobs",
    "manage_runners": "jobs",
    "get_config": "config_logs",
    "validate_config": "config_logs",
    "set_config_value": "config_logs",
    "read_debug_log": "config_logs",
    "get_server_log_tail": "config_logs",
    "search_logs": "config_logs",
    "search_similar_images": "similarity",
    "search_images_by_text": "similarity",
    "find_near_duplicates": "similarity",
    "propagate_tags": "similarity",
    "find_outliers": "similarity",
}

MODULE_HEADER = '''"""MCP tool implementations — {name} (extracted from modules.mcp_server)."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Optional

from modules import config, db
from modules.mcp import tool_support as ts

logger = logging.getLogger(__name__)

'''


def _is_mcp_tool_func(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        target = dec
        if isinstance(dec, ast.Call):
            target = dec.func
        if isinstance(target, ast.Attribute) and target.attr == "tool":
            return True
    return False


def _rewrite_tool_source(text: str) -> str:
    text = text.replace("_sanitize_for_mcp", "ts.sanitize_for_mcp")
    text = text.replace("_IMS_OVERLAY_SUBQUERY", "ts.IMS_OVERLAY_SUBQUERY")
    text = text.replace("_PER_MODEL_FAIL_LABELS", "ts.PER_MODEL_FAIL_LABELS")
    text = text.replace("_AGGREGATE_FAIL_COLUMNS", "ts.AGGREGATE_FAIL_COLUMNS")
    text = text.replace("_normalize_job_payload_for_mcp", "ts.normalize_job_payload_for_mcp")
    text = text.replace("_registry_model_status", "ts.registry_model_status")
    text = text.replace("_strip_sql_comments_for_mcp", "ts.strip_sql_comments_for_mcp")
    text = text.replace("_is_mcp_read_only_sql", "ts.is_mcp_read_only_sql")
    text = text.replace("_mcp_sql_single_statement", "ts.mcp_sql_single_statement")
    # Runner / DB / gradio state via lazy import from mcp_server (avoids circular import at module load)
    for sym in (
        "_scoring_runner", "_tagging_runner", "_clustering_runner", "_selection_runner",
        "_orchestrator", "_bird_species_runner", "_indexing_runner", "_metadata_runner",
        "_maintenance_runner", "_db_available", "_last_db_error", "_gradio_context",
    ):
        text = re.sub(rf"(?<![.\w]){sym}(?![.\w])", f"_ms.{sym}", text)
    if "_ms." in text:
        text = "    from modules import mcp_server as _ms\n" + text
    return text


def _func_signature(node: ast.FunctionDef, source: str) -> str:
    lines = source.splitlines()
    header_lines = []
    for i in range(node.lineno - 1, node.end_lineno):
        header_lines.append(lines[i])
        if lines[i].rstrip().endswith(":"):
            break
    return "\n".join(header_lines)


def _param_names(node: ast.FunctionDef) -> list[str]:
    names = [a.arg for a in node.args.args if a.arg != "self"]
    names.extend(a.arg for a in node.args.kwonlyargs)
    return names


def main() -> None:
    source = MCP_PATH.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)

    tool_nodes: list[ast.FunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and _is_mcp_tool_func(node):
            tool_nodes.append(node)

    by_module: dict[str, list[str]] = {}
    replacements: dict[int, tuple[int, str]] = {}

    for node in tool_nodes:
        name = node.name
        mod = TOOL_MODULE.get(name)
        if not mod:
            print("unmapped:", name)
            continue
        func_src = "".join(lines[node.lineno - 1 : node.end_lineno])
        rewritten = _rewrite_tool_source(func_src)
        by_module.setdefault(mod, []).append(rewritten)

        dec_start = min(d.lineno for d in node.decorator_list) - 1
        dec_lines = [
            l
            for l in lines[dec_start : node.lineno - 1]
            if "@mcp.tool" in l or "@_require_db" in l or "ToolAnnotations" in l
        ]
        params = _param_names(node)
        call = ", ".join(f"{p}={p}" for p in params)
        sig = _func_signature(node, source)
        wrapper = "".join(dec_lines)
        wrapper += sig + "\n"
        wrapper += f"    from modules.mcp.tools import {mod} as _tool_mod\n"
        wrapper += f"    return _tool_mod.{name}({call})\n\n"
        replacements[dec_start + 1] = (node.end_lineno, wrapper)

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    (TOOLS_DIR / "__init__.py").write_text('"""MCP tool implementation modules."""\n', encoding="utf-8")
    for mod, funcs in by_module.items():
        out = MODULE_HEADER.format(name=mod) + "\n\n".join(funcs) + "\n"
        (TOOLS_DIR / f"{mod}.py").write_text(out, encoding="utf-8")
        print(f"wrote {mod}.py ({len(funcs)} tools)")

    # Rebuild mcp_server without tool bodies
    new_parts: list[str] = []
    idx = 0
    line_no = 1
    sorted_starts = sorted(replacements.keys())
    start_iter = iter(sorted_starts)
    next_start = next(start_iter, None)
    while idx < len(lines):
        if line_no == next_start:
            end_line, wrapper = replacements[line_no]
            new_parts.append(wrapper)
            idx += end_line - line_no + 1
            line_no = end_line + 1
            next_start = next(start_iter, None)
            continue
        new_parts.append(lines[idx])
        idx += 1
        line_no += 1

    MCP_PATH.write_text("".join(new_parts), encoding="utf-8")
    print("updated mcp_server.py")


if __name__ == "__main__":
    main()
