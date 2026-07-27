"""
MCP (Model Context Protocol) server for the Vexlum Scoring WebUI

Provides debugging and management tools for Cursor IDE and AI agents.
Uses FastMCP for automatic schema generation from type annotations.

Usage:
    python -m modules.mcp_server          # standalone
    ENABLE_MCP_SERVER=1 python webui.py   # integrated
"""

import asyncio
import io
import ipaddress
import json
import logging
import os
import re
import sys
from functools import lru_cache
from typing import Any

# MCP SDK imports
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

try:
    import importlib.util

    MCP_SSE_AVAILABLE = importlib.util.find_spec("mcp.server.sse") is not None
except Exception:
    MCP_SSE_AVAILABLE = False

# Add parent directory for imports when running standalone
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import config, db

logger = logging.getLogger(__name__)

# Global reference to runners (set by webui when integrating)
_scoring_runner = None
_tagging_runner = None
_clustering_runner = None
_selection_runner = None
_orchestrator = None
_bird_species_runner = None
_indexing_runner = None
_metadata_runner = None
_maintenance_runner = None

# Gradio context (set by webui when MCP runs in integrated/SSE mode)
_gradio_context: dict | None = None

# Set False if db.init_db() fails; DB-using tools then return a clear error
_db_available = True
_last_db_error = None

# Annotation presets
_RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
_RW = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
_RW_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _sanitize_for_mcp(obj: Any) -> Any:
    """Make dict/list values JSON-safe for MCP responses (e.g. strip BLOB bytes)."""
    # Handle RowWrapper or other dict-like objects
    if hasattr(obj, "to_dict"):
        return _sanitize_for_mcp(obj.to_dict())
    if hasattr(obj, "keys") and not isinstance(obj, dict):
        return {k: _sanitize_for_mcp(obj[k]) for k in obj.keys()}
    
    if isinstance(obj, dict):
        return {k: _sanitize_for_mcp(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_mcp(x) for x in obj]
    if isinstance(obj, (bytes, memoryview)):
        return f"<binary len={len(obj)}>"
    return obj


def _require_db(fn):
    """Decorator that returns an error dict if the database is not available. 
    Attempts to re-initialize if currently marked as unavailable."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        global _db_available, _last_db_error
        if not _db_available:
            # Try to re-initialize if we previously failed
            prepare_mcp_embedded()
            
        if not _db_available:
            msg = "Database not available. Ensure PostgreSQL is running and migrations are applied."
            if _last_db_error:
                msg += f" Last error: {_last_db_error}"
            return {"error": msg}
        return fn(*args, **kwargs)
    return wrapper


def _strip_sql_comments_for_mcp(sql: str) -> str:
    """Strip leading line comments and /* */ blocks so SELECT/WITH guards work."""
    s = (sql or "").strip()
    while True:
        m = re.search(r"/\*.*?\*/", s, flags=re.DOTALL)
        if not m:
            break
        s = (s[: m.start()] + " " + s[m.end() :]).strip()
    lines_out: list[str] = []
    for line in s.splitlines():
        ls = line.strip()
        if ls.startswith("--"):
            continue
        if "--" in line:
            line = line.split("--", 1)[0].rstrip()
        if line.strip():
            lines_out.append(line)
    return " ".join(lines_out).strip()


def _is_mcp_read_only_sql(normalized: str) -> bool:
    u = normalized.lstrip().upper()
    return u.startswith("SELECT") or u.startswith("WITH")


def _mcp_sql_single_statement(normalized: str) -> tuple[bool, str | None]:
    core = normalized.rstrip().rstrip(";").strip()
    if ";" in core:
        return False, "Multiple SQL statements are not allowed"
    return True, None


def set_runners(
    scoring_runner,
    tagging_runner,
    clustering_runner=None,
    selection_runner=None,
    orchestrator=None,
    bird_species_runner=None,
    indexing_runner=None,
    metadata_runner=None,
    maintenance_runner=None,
):
    """Set references to the runner instances from webui."""
    global _scoring_runner, _tagging_runner, _clustering_runner, _selection_runner, _orchestrator, _bird_species_runner, _indexing_runner, _metadata_runner, _maintenance_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner
    _clustering_runner = clustering_runner
    _selection_runner = selection_runner
    _orchestrator = orchestrator
    _bird_species_runner = bird_species_runner
    _indexing_runner = indexing_runner
    _metadata_runner = metadata_runner
    _maintenance_runner = maintenance_runner


def set_gradio_context(
    demo=None,
    pipeline_components=None,
    gallery_components=None,
    settings_components=None,
    main_tabs=None,
    runner=None,
    tagging_runner=None,
    orchestrator=None,
):
    """Set Gradio context for execute_code tool. Called from webui when MCP runs in integrated mode."""
    global _gradio_context
    components = {}
    if pipeline_components:
        components.update(pipeline_components)
    if gallery_components:
        components.update(gallery_components)
    if settings_components:
        components.update(settings_components)
    _gradio_context = {
        "demo": demo,
        "components": components,
        "main_tabs": main_tabs,
        "runner": runner,
        "tagging_runner": tagging_runner,
        "orchestrator": orchestrator,
    }


# --- Create FastMCP server instance ---

if MCP_AVAILABLE:
    mcp = FastMCP("image-scoring")
else:
    # Fallback mock so module can be imported without MCP SDK
    class _MockMCP:
        def tool(self, *a, **kw):
            return lambda fn: fn
        def resource(self, *a, **kw):
            return lambda fn: fn
    mcp = _MockMCP()


# ============================================================
# Database & Query Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_database_stats() -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.get_database_stats()



@mcp.tool(annotations=_RO)
@_require_db
def query_images(
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc",
    min_score: float | None = None,
    max_score: float | None = None,
    rating: int | None = None,
    label: str | None = None,
    keyword: str | None = None,
    folder_path: str | None = None
) -> list:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.query_images(limit=limit, offset=offset, sort_by=sort_by, order=order, min_score=min_score, max_score=max_score, rating=rating, label=label, keyword=keyword, folder_path=folder_path)



@mcp.tool(annotations=_RO)
@_require_db
def get_image_details(file_path: str) -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.get_image_details(file_path=file_path)



@mcp.tool(annotations=_RO)
@_require_db
def search_images_by_hash(image_hash: str, hash_version: int | None = None) -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.search_images_by_hash(image_hash=image_hash, hash_version=hash_version)



@mcp.tool(annotations=_RO)
@_require_db
def get_db_schema(
    table_name_prefix: str | None = None,
    max_tables: int = 200,
    max_column_rows: int = 8000,
) -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.get_db_schema(table_name_prefix=table_name_prefix, max_tables=max_tables, max_column_rows=max_column_rows)



@mcp.tool(annotations=_RO)
@_require_db
def execute_sql(query: str, params: list = None) -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.execute_sql(query=query, params=params)



@mcp.tool(annotations=_RO)
@_require_db
def get_folder_tree(root_path: str | None = None) -> list:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.get_folder_tree(root_path=root_path)



@mcp.tool(annotations=_RO)
@_require_db
def get_newly_imported_folders(days: int = 7, min_images: int = 1, path_pattern: str | None = None) -> list[dict]:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.get_newly_imported_folders(days=days, min_images=min_images, path_pattern=path_pattern)



@mcp.tool(annotations=_RW)
@_require_db
def process_newly_imported_folders(days: int = 7, job_type: str = "scoring", path_pattern: str | None = None) -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.process_newly_imported_folders(days=days, job_type=job_type, path_pattern=path_pattern)



@mcp.tool(annotations=_RO)
@_require_db
def get_stacks_summary(folder_path: str | None = None) -> dict:
    from modules.mcp.tools import data as _tool_mod
    return _tool_mod.get_stacks_summary(folder_path=folder_path)





# ============================================================
# Error & Diagnostics Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_incomplete_images(limit: int = 100) -> list:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_incomplete_images(limit=limit)



@mcp.tool(annotations=_RO)
@_require_db
def get_failed_images(limit: int = 50, offset: int = 0) -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_failed_images(limit=limit, offset=offset)



@mcp.tool(annotations=_RO)
@_require_db
def get_error_summary() -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_error_summary()



@mcp.tool(annotations=_RO)
@_require_db
def check_database_health() -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.check_database_health()



@mcp.tool(annotations=_RO)
@_require_db
def validate_file_paths(
    limit: int = 100,
    folder_path: str | None = None,
    missing_only: bool = False,
) -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.validate_file_paths(limit=limit, folder_path=folder_path, missing_only=missing_only)



@mcp.tool(annotations=_RO)
@_require_db
def diagnose_phase_consistency(image_id: int, folder_path: str | None = None) -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.diagnose_phase_consistency(image_id=image_id, folder_path=folder_path)



@mcp.tool(annotations=_RO)
@_require_db
def get_stale_running_phase_status(min_age_seconds: int = 3600, limit: int = 50) -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_stale_running_phase_status(min_age_seconds=min_age_seconds, limit=limit)



# ============================================================
# Monitoring & Jobs Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_recent_jobs(limit: int = 10) -> list:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_recent_jobs(limit=limit)



@mcp.tool(annotations=_RO)
@_require_db
def get_job_details(job_id: int) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_job_details(job_id=job_id)



@mcp.tool(annotations=_RO)
@_require_db
def get_job_phases(job_id: int) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_job_phases(job_id=job_id)



@mcp.tool(annotations=_RO)
@_require_db
def get_job_stage_images(
    job_id: int,
    phase_code: str,
    limit: int = 50,
    offset: int = 0,
    include_steps: bool = False,
) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_job_stage_images(job_id=job_id, phase_code=phase_code, limit=limit, offset=offset, include_steps=include_steps)



@mcp.tool(annotations=_RO)
@_require_db
def get_run_diagnostics(run_id: int) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_run_diagnostics(run_id=run_id)



@mcp.tool(annotations=_RO)
@_require_db
def get_drive_diagnostics() -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_drive_diagnostics()



@mcp.tool(annotations=_RO)
@_require_db
def get_job_execution_report(run_id: int, phase_code: str | None = None, action: str | None = None, offset: int = 0, limit: int = 20) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_job_execution_report(run_id=run_id, phase_code=phase_code, action=action, offset=offset, limit=limit)



@mcp.tool(annotations=_RO)
@_require_db
def get_image_pipeline_failures(
    image_id: int | None = None,
    file_path: str | None = None,
    limit: int = 50,
) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_image_pipeline_failures(image_id=image_id, file_path=file_path, limit=limit)



@mcp.tool(annotations=_RO)
@_require_db
def get_location_stats() -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_location_stats()



@mcp.tool(annotations=_RO)
def export_debug_bundle(output_path: str | None = None) -> dict:
    from modules.mcp.tools import maintenance as _tool_mod
    return _tool_mod.export_debug_bundle(output_path=output_path)



@mcp.tool(annotations=_RO)
@_require_db
def get_embedding_stats(
    folder_path: str | None = None,
    embedding_space: str | None = None,
) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_embedding_stats(folder_path=folder_path, embedding_space=embedding_space)



@mcp.tool(annotations=_RO)
def get_database_engine_info() -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_database_engine_info()



@mcp.tool(annotations=_RO)
@_require_db
def check_stack_invariants(limit: int = 20) -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.check_stack_invariants(limit=limit)



# ============================================================
# Maintenance & Mutation Tools (Write Access)
# ============================================================

@mcp.tool(annotations=_RW_DESTRUCTIVE)
@_require_db
def rebase_file_paths(old_root: str, new_root: str, dry_run: bool = True) -> dict:
    from modules.mcp.tools import maintenance as _tool_mod
    return _tool_mod.rebase_file_paths(old_root=old_root, new_root=new_root, dry_run=dry_run)



@mcp.tool(annotations=_RW)
@_require_db
def set_image_metadata(file_path: str, rating: int | None = None, label: str | None = None) -> dict:
    from modules.mcp.tools import maintenance as _tool_mod
    return _tool_mod.set_image_metadata(file_path=file_path, rating=rating, label=label)



@mcp.tool(annotations=_RW_DESTRUCTIVE)
@_require_db
def prune_missing_files(dry_run: bool = True) -> dict:
    from modules.mcp.tools import maintenance as _tool_mod
    return _tool_mod.prune_missing_files(dry_run=dry_run)



@mcp.tool(annotations=_RO)
def verify_environment() -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.verify_environment()



@mcp.tool(annotations=_RO)
def get_system_resources() -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_system_resources()



@mcp.tool(annotations=_RO)
def get_thread_dump() -> dict:
    from modules.mcp.tools import diagnostics as _tool_mod
    return _tool_mod.get_thread_dump()



@mcp.tool(annotations=_RO)
def get_runner_status() -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_runner_status()



@mcp.tool(annotations=_RO)
def get_pipeline_stats() -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_pipeline_stats()



@mcp.tool(annotations=_RO)
@_require_db
def get_performance_metrics(days: int = 7) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.get_performance_metrics(days=days)



@mcp.tool(annotations=_RO)
def get_model_status() -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.get_model_status()



@mcp.tool(annotations=_RW)
@_require_db
def run_processing_job(job_type: str, input_path: str, args: dict = None) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.run_processing_job(job_type=job_type, input_path=input_path, args=args)



@mcp.tool(annotations=_RW)
def manage_runners(runner: str, operation: str) -> dict:
    from modules.mcp.tools import jobs as _tool_mod
    return _tool_mod.manage_runners(runner=runner, operation=operation)



# ============================================================
# Configuration & Logs Tools
# ============================================================

@mcp.tool(annotations=_RO)
def get_config() -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.get_config()



@mcp.tool(annotations=_RO)
def validate_config() -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.validate_config()



@mcp.tool(annotations=_RW)
def set_config_value(key: str, value: Any) -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.set_config_value(key=key, value=value)



@mcp.tool(annotations=_RO)
def read_debug_log(lines: int = 100) -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.read_debug_log(lines=lines)



@mcp.tool(annotations=_RO)
def get_server_log_tail(sources: str = "all", lines: int = 100) -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.get_server_log_tail(sources=sources, lines=lines)



@mcp.tool(annotations=_RO)
def search_logs(
    pattern: str,
    sources: str = "all",
    context_lines: int = 2,
    max_lines_scan: int = 25000,
    max_matches_per_file: int = 40,
    case_insensitive: bool = True,
) -> dict:
    from modules.mcp.tools import config_logs as _tool_mod
    return _tool_mod.search_logs(pattern=pattern, sources=sources, context_lines=context_lines, max_lines_scan=max_lines_scan, max_matches_per_file=max_matches_per_file, case_insensitive=case_insensitive)



# ============================================================
# Advanced Search Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def search_similar_images(
    example_path: str | None = None,
    example_image_id: int | None = None,
    limit: int = 20,
    folder_path: str | None = None,
    min_similarity: float | None = None,
    embedding_space: str | None = None,
) -> dict:
    from modules.mcp.tools import similarity as _tool_mod
    return _tool_mod.search_similar_images(example_path=example_path, example_image_id=example_image_id, limit=limit, folder_path=folder_path, min_similarity=min_similarity, embedding_space=embedding_space)



@mcp.tool(annotations=_RO)
@_require_db
def search_images_by_text(
    query: str,
    limit: int = 20,
    folder_path: str | None = None,
    folder_ids: list[int] | None = None,
    min_similarity: float | None = None,
    min_rating: int | None = None,
    color_label: str | None = None,
    keyword: str | None = None,
    captured_date: str | None = None,
    sort_by: str | None = None,
    order: str | None = None,
) -> dict:
    from modules.mcp.tools import similarity as _tool_mod
    return _tool_mod.search_images_by_text(query=query, limit=limit, folder_path=folder_path, folder_ids=folder_ids, min_similarity=min_similarity, min_rating=min_rating, color_label=color_label, keyword=keyword, captured_date=captured_date, sort_by=sort_by, order=order)



@mcp.tool(annotations=_RO)
@_require_db
def find_near_duplicates(
    threshold: float | None = None,
    folder_path: str | None = None,
    limit: int | None = None
) -> dict:
    from modules.mcp.tools import similarity as _tool_mod
    return _tool_mod.find_near_duplicates(threshold=threshold, folder_path=folder_path, limit=limit)



@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False) if MCP_AVAILABLE else None)
@_require_db
def propagate_tags(
    folder_path: str | None = None,
    dry_run: bool = True,
    k: int | None = None,
    min_similarity: float | None = None,
    min_keyword_confidence: float | None = None
) -> dict:
    from modules.mcp.tools import similarity as _tool_mod
    return _tool_mod.propagate_tags(folder_path=folder_path, dry_run=dry_run, k=k, min_similarity=min_similarity, min_keyword_confidence=min_keyword_confidence)



@mcp.tool(annotations=_RO)
@_require_db
def find_outliers(
    folder_path: str = "",
    z_threshold: float | None = None,
    k: int | None = None,
    limit: int | None = None
) -> dict:
    from modules.mcp.tools import similarity as _tool_mod
    return _tool_mod.find_outliers(folder_path=folder_path, z_threshold=z_threshold, k=k, limit=limit)



# ============================================================
# Execute Code (Gradio context - SSE only)
# ============================================================
# SECURITY: This tool uses exec() with user-provided code. It is intended for
# dev/debug use only when connected via SSE to a trusted WebUI. Do not expose
# to untrusted clients. See AGENTS.md for usage guidelines.

@mcp.tool(annotations=_RW_DESTRUCTIVE if MCP_AVAILABLE else None)
def execute_code(code: str) -> dict:
    """Execute Python code in the WebUI process with access to gr, demo, and all Gradio components. Only when Cursor uses SSE (server keys imgscore-py-sse or imgscore-el-sse). Globals: gr, demo, components, runner, tagging_runner, orchestrator, db, config."""
    global _gradio_context
    if not _env_flag("ENABLE_MCP_EXECUTE_CODE", default=False):
        return {
            "error": "execute_code is disabled. Set ENABLE_MCP_EXECUTE_CODE=1 and restart the WebUI to enable it for local debugging."
        }
    if _gradio_context is None:
        return {
            "error": "Gradio context not available. Start the WebUI (run_webui.bat or python webui.py) and connect Cursor MCP (imgscore-py-sse or imgscore-el-sse) to http://127.0.0.1:<port>/mcp/sse (see GET /mcp-status → expected_sse_url)"
        }
    try:
        import gradio as gr
    except ImportError:
        return {"error": "gradio not installed"}

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    result = None

    # Log invocation for audit trail
    logger.warning("execute_code invoked: %s", code[:200] if code else "(empty)")

    exec_globals = {
        "gr": gr,
        "demo": _gradio_context.get("demo"),
        "components": _gradio_context.get("components", {}),
        "main_tabs": _gradio_context.get("main_tabs"),
        "runner": _gradio_context.get("runner"),
        "tagging_runner": _gradio_context.get("tagging_runner"),
        "orchestrator": _gradio_context.get("orchestrator"),
        "indexing_runner": _gradio_context.get("indexing_runner"),
        "metadata_runner": _gradio_context.get("metadata_runner"),
        "db": db,
        "config": config,
    }

    try:
        import builtins as _builtins_mod
        # Blocked dangerous builtins: file I/O, code execution, introspection, subprocess
        dangerous_builtins = {
            "__import__", "open", "eval", "exec", "compile", "globals", "locals",
            "breakpoint", "__loader__", "__spec__", "super", "vars", "dir",
            "getattr", "setattr", "delattr", "hasattr", "type", "isinstance",
        }
        safe_builtins = {k: v for k, v in vars(_builtins_mod).items()
                         if k not in dangerous_builtins}
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_capture, stderr_capture
        try:
            exec_globals["__builtins__"] = safe_builtins
            exec(code, exec_globals)
            if "result" in exec_globals:
                result = exec_globals["result"]
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
    except Exception as e:
        logger.warning("execute_code raised: %s", e)
        return {
            "error": str(e),
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
        }

    out = {
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue(),
    }
    if result is not None:
        try:
            out["result"] = json.dumps(result, default=str)
        except (TypeError, ValueError):
            out["result"] = repr(result)
    return out


# ============================================================
# MCP Resources
# ============================================================

if MCP_AVAILABLE:
    @mcp.resource("config://current")
    def config_resource() -> str:
        """Current application configuration from config.json."""
        return json.dumps(config.load_config(), indent=2)


# ============================================================
# Server Setup & Transport
# ============================================================

def prepare_mcp_embedded(force=False) -> bool:
    """Initialize DB and set _db_available for embedded (SSE) or stdio runs.
    
    If force=True, calls db.init_db() even if _db_available is already True.
    If _db_available is False, always attempts to initialize.
    
    Returns:
        bool: Current database availability status.
    """
    global _db_available, _last_db_error
    
    # If already available and not forced, just return success
    if _db_available and not force:
        return True
        
    try:
        # Note: db.init_db() in modules/db/engine.py has its own _db_initialized flag.
        # We may need to clear it if we want a hard reset, but usually for transient
        # connection issues, just calling it again is sufficient as the internal
        # connector factory will retry the connection.
        db.init_db()
        _db_available = True
        _last_db_error = None
        return True
    except Exception as e:
        _last_db_error = str(e)
        logger.warning("DB init failed (%s). DB tools will return 'Database not available'.", e)
        _db_available = False
        return False


# Loopback + typical Docker/WSL private ranges (Windows host ↔ Docker Desktop ↔ WSL2).
_DEFAULT_MCP_CLIENT_CIDRS = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
)


@lru_cache(maxsize=1)
def _mcp_allowed_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    cidrs = list(_DEFAULT_MCP_CLIENT_CIDRS)
    extra = (os.environ.get("MCP_ALLOWED_CIDRS") or "").strip()
    if extra:
        cidrs.extend(part.strip() for part in extra.split(",") if part.strip())
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid MCP_ALLOWED_CIDRS entry: %s", cidr)
    return tuple(networks)


def get_mcp_client_allowlist_cidrs() -> list[str]:
    """Human-readable CIDR list applied to /mcp HTTP clients (for /mcp-status)."""
    return [str(net) for net in _mcp_allowed_networks()]


def _client_host_from_scope(scope: dict) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    host = (client[0] or "").strip()
    host = host.removeprefix("::ffff:")
    return host or None


def is_mcp_client_ip_allowed(host: str | None) -> bool:
    """True when host is loopback or a private/Docker/WSL-style address."""
    if not host:
        return False
    if (os.environ.get("MCP_DISABLE_CLIENT_ALLOWLIST") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    return any(addr in net for net in _mcp_allowed_networks())


def _expected_mcp_token() -> str | None:
    """Optional bearer token for /mcp SSE (set IMGSCORE_MCP_TOKEN or MCP_TOKEN on the WebUI process)."""
    for key in ("IMGSCORE_MCP_TOKEN", "MCP_TOKEN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return None


def _mcp_token_from_scope(scope: dict) -> str | None:
    raw_headers = scope.get("headers") or []
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw_headers}
    auth = (headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    alt = (headers.get("x-imgscore-mcp-token") or "").strip()
    return alt or None


def wrap_mcp_app_with_security(app):
    """Restrict /mcp HTTP to loopback + private/Docker nets; optional bearer token."""
    expected_token = _expected_mcp_token()
    enforce_token = expected_token is not None
    enforce_allowlist = (os.environ.get("MCP_DISABLE_CLIENT_ALLOWLIST") or "").strip().lower() not in {
        "1", "true", "yes", "on",
    }

    if not enforce_token and not enforce_allowlist:
        return app

    class _MCPSecurityMiddleware:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope.get("type") != "http":
                await self.inner(scope, receive, send)
                return

            from starlette.responses import JSONResponse

            client_host = _client_host_from_scope(scope)
            if enforce_allowlist and not is_mcp_client_ip_allowed(client_host):
                logger.warning("MCP request rejected (client not allowlisted): %s", client_host)
                resp = JSONResponse(
                    {"error": "Forbidden", "detail": "MCP is only available from localhost or private Docker/WSL networks"},
                    status_code=403,
                )
                await resp(scope, receive, send)
                return

            if enforce_token and _mcp_token_from_scope(scope) != expected_token:
                resp = JSONResponse({"error": "Unauthorized"}, status_code=401)
                await resp(scope, receive, send)
                return

            await self.inner(scope, receive, send)

    return _MCPSecurityMiddleware(app)


def get_mcp_sse_profile() -> str:
    """SSE MCP surface: compact (search+dispatch) or full (legacy ~54 tools)."""
    raw = (os.environ.get("MCP_SSE_PROFILE") or "compact").strip().lower()
    if raw in ("full", "legacy"):
        return "full"
    return "compact"


def _install_mcp_sse_route_aliases(app) -> None:
    try:
        from starlette.responses import Response
        from starlette.routing import Mount, Route

        messages_mount = next(
            (
                route for route in getattr(app, "routes", [])
                if isinstance(route, Mount) and getattr(route, "path", "") in {"/messages", "/messages/"}
            ),
            None,
        )
        if messages_mount is not None:
            class _SsePostAlias:
                async def __call__(self, scope, receive, send):
                    # Some MCP clients POST back to /sse instead of /messages/.
                    alias_scope = dict(scope)
                    alias_scope["path"] = messages_mount.path
                    alias_scope["raw_path"] = messages_mount.path.encode("utf-8")
                    await messages_mount.handle(alias_scope, receive, send)

            async def sse_delete_alias(request):
                # Older clients also send DELETE /sse during cleanup.
                return Response(status_code=200)

            app.routes.insert(0, Route("/sse", endpoint=sse_delete_alias, methods=["DELETE"]))
            app.routes.insert(0, Route("/sse", endpoint=_SsePostAlias(), methods=["POST"]))
    except Exception as e:
        logger.warning("Failed to install SSE compatibility aliases: %s", e)


_compact_mcp_sse = None


def _get_compact_mcp_sse():
    """Lazy FastMCP with search+dispatch only (is-be-webui compact SSE)."""
    global _compact_mcp_sse
    if _compact_mcp_sse is None:
        from modules.mcp.names import BE_WEBUI
        from modules.mcp.router_tools import register_compact_tools

        _compact_mcp_sse = FastMCP(BE_WEBUI)
        register_compact_tools(_compact_mcp_sse)
    return _compact_mcp_sse


def _build_mcp_sse_asgi(fast_mcp_instance, mount_path: str):
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK required. Install: pip install mcp")
    prepare_mcp_embedded()
    app = wrap_mcp_app_with_security(fast_mcp_instance.sse_app(mount_path=mount_path))
    _install_mcp_sse_route_aliases(app)
    return app


def create_mcp_compact_sse_app(mount_path: str = "/mcp"):
    """
    SSE app exposing only search + dispatch (same contract as is-be-mcp stdio).
    """
    return _build_mcp_sse_asgi(_get_compact_mcp_sse(), mount_path)


def create_mcp_sse_app(mount_path: str = "/mcp"):
    """
    Create a Starlette ASGI app that exposes MCP over SSE, to be mounted in FastAPI.
    Cursor connects via url e.g. http://localhost:7860/mcp/sse
    """
    return _build_mcp_sse_asgi(mcp, mount_path)


def resolve_mcp_sse_app(mount_path: str = "/"):
    """Return (asgi_app, profile) where profile is compact or full."""
    profile = get_mcp_sse_profile()
    if profile == "full":
        return create_mcp_sse_app(mount_path=mount_path), profile
    return create_mcp_compact_sse_app(mount_path=mount_path), profile


async def run_server():
    """Run the MCP server using stdio transport."""
    if not MCP_AVAILABLE:
        print("Error: MCP SDK not installed. Run: pip install mcp")
        return

    prepare_mcp_embedded()
    await mcp.run_stdio_async()


def start_mcp_server_background():
    """Start MCP server in a background thread (for integration with webui)."""
    import threading

    def run_async():
        asyncio.run(run_server())

    thread = threading.Thread(target=run_async, daemon=True)
    thread.start()
    logger.info("MCP server started in background")
    return thread


_mcp_active_profile: str = "full"


def get_mcp_active_profile() -> str:
    """Active MCP_TOOL_PROFILE after domain filtering (diagnostics, jobs, …)."""
    return _mcp_active_profile


if MCP_AVAILABLE:
    from modules.mcp.profiles import apply_tool_profile

    _mcp_active_profile = apply_tool_profile(mcp)


if __name__ == "__main__":
    # Run standalone - NO print statements allowed! MCP uses stdio for JSON protocol.
    # All output must go to stderr, not stdout.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logger.info("Starting Vexlum Scoring MCP server...")

    # Initialize runners for standalone mode
    try:
        from modules.clustering import ClusteringRunner
        clustering_runner = ClusteringRunner()
        set_runners(None, None, clustering_runner)
        logger.info("Initialized ClusteringRunner for standalone mode")
    except Exception as e:
        logger.warning(f"Failed to initialize clustering runner: {e}")

    asyncio.run(run_server())
