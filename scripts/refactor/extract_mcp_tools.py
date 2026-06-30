"""One-shot helper: extract MCP tool bodies into modules/mcp/tools/*.py (Batch 1 refactor)."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP_PATH = ROOT / "modules" / "mcp_server.py"

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
from typing import Any, Optional

from modules import config, db
from modules.mcp import tool_support as ts

logger = logging.getLogger(__name__)

'''


def _has_mcp_tool_decorator(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Attribute) and func.attr == "tool":
                return True
        if isinstance(dec, ast.Attribute) and dec.attr == "tool":
            return True
    return False


def _decorator_source_lines(node: ast.FunctionDef, lines: list[str]) -> tuple[list[str], ast.FunctionDef]:
    """Return decorator lines and function node without mcp.tool / _require_db decorators."""
    dec_start = min(d.lineno for d in node.decorator_list) - 1 if node.decorator_list else node.lineno - 1
    func_end = node.end_lineno
    func_src = "".join(lines[node.lineno - 1 : func_end])
    return lines[dec_start : node.lineno - 1], ast.parse(func_src).body[0]  # type: ignore


def main() -> None:
    source = MCP_PATH.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)

    by_module: dict[str, list[str]] = {}
    wrappers: dict[str, str] = {}

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not _has_mcp_tool_decorator(node):
            continue
        name = node.name
        mod = TOOL_MODULE.get(name)
        if not mod:
            print("SKIP unmapped tool:", name)
            continue

        dec_lines, func_node = _decorator_source_lines(node, lines)
        # Keep only @mcp.tool and @_require_db decorator lines for wrapper
        wrapper_decs = []
        for dl in dec_lines:
            if "@mcp.tool" in dl or "@_require_db" in dl or "ToolAnnotations" in dl:
                wrapper_decs.append(dl)

        func_lines = lines[node.lineno - 1 : node.end_lineno]
        func_text = "".join(func_lines)
        by_module.setdefault(mod, []).append(func_text)

        # Build wrapper with same signature
        args = ast.unparse(func_node.args) if hasattr(ast, "unparse") else ""
        returns = ""
        if func_node.returns:
            returns = " -> " + ast.unparse(func_node.returns)
        sig_params = func_text.split("(", 1)[1].split(")", 1)[0]
        call_args = []
        for arg in func_node.args.args:
            if arg.arg == "self":
                continue
            call_args.append(arg.arg)
        if func_node.args.vararg:
            call_args.append(f"*{func_node.args.vararg.arg}")
        if func_node.args.kwarg:
            call_args.append(f"**{func_node.args.kwarg.arg}")
        elif func_node.args.kwonlyargs:
            for a in func_node.args.kwonlyargs:
                if a.arg not in [x.split("=")[0].strip() for x in call_args]:
                    call_args.append(f"{a.arg}={a.arg}")

        # Simple call: pass same named args from signature
        param_names = [a.arg for a in func_node.args.args if a.arg != "self"]
        for a in func_node.args.kwonlyargs:
            param_names.append(a.arg)
        call = ", ".join(f"{p}={p}" for p in param_names)
        wrapper = "".join(wrapper_decs)
        wrapper += f"def {name}({sig_params}){returns}:\n"
        wrapper += f'    from modules.mcp.tools import {mod} as _tool_mod\n'
        wrapper += f"    return _tool_mod.{name}({call})\n\n"
        wrappers[name] = wrapper

    tools_dir = ROOT / "modules" / "mcp" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "__init__.py").write_text('"""MCP tool implementation modules (Batch 1 extraction)."\n', encoding="utf-8")

    for mod, funcs in by_module.items():
        path = tools_dir / f"{mod}.py"
        path.write_text(MODULE_HEADER.format(name=mod) + "\n\n".join(funcs) + "\n", encoding="utf-8")
        print("Wrote", path, "with", len(funcs), "functions")

    # Replace tool functions in mcp_server with wrappers
    new_lines: list[str] = []
    skip_until = 0
    i = 0
    while i < len(lines):
        line_no = i + 1
        if line_no <= skip_until:
            i += 1
            continue
        matched = False
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not _has_mcp_tool_decorator(node):
                continue
            if node.lineno == line_no and node.name in wrappers:
                dec_start = min(d.lineno for d in node.decorator_list) - 1
                new_lines.append(wrappers[node.name])
                skip_until = node.end_lineno
                matched = True
                break
        if not matched:
            new_lines.append(lines[i])
        i += 1

    MCP_PATH.write_text("".join(new_lines), encoding="utf-8")
    print("Updated mcp_server.py")


if __name__ == "__main__":
    main()
