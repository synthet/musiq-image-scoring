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
import json
import logging
import os
import re
import sys
from typing import Any, Optional

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

from modules import db, config, db_postgres

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
    """Get comprehensive database statistics including image counts, score distributions, and job summaries."""
    with db.connection() as conn:
        c = conn.cursor()
        stats = {}

        try:
            c.execute("SELECT COUNT(*) FROM images")
            stats["total_images"] = c.fetchone()[0]

            c.execute("""
                SELECT rating, COUNT(*) as cnt
                FROM images
                GROUP BY rating
                ORDER BY rating
            """)
            stats["by_rating"] = {str(row[0]): row[1] for row in c.fetchall()}

            c.execute("""
                SELECT COALESCE(label, 'None') as lbl, COUNT(*) as cnt
                FROM images
                GROUP BY label
                ORDER BY cnt DESC
            """)
            stats["by_label"] = {row[0]: row[1] for row in c.fetchall()}

            c.execute("""
                SELECT
                    CASE
                        WHEN score_general < 0.2 THEN '0.0-0.2'
                        WHEN score_general < 0.4 THEN '0.2-0.4'
                        WHEN score_general < 0.6 THEN '0.4-0.6'
                        WHEN score_general < 0.8 THEN '0.6-0.8'
                        ELSE '0.8-1.0'
                    END as range,
                    COUNT(*) as cnt
                FROM images
                WHERE score_general IS NOT NULL
                GROUP BY range
                ORDER BY range
            """)
            stats["score_distribution"] = {row[0]: row[1] for row in c.fetchall()}

            c.execute("""
                SELECT
                    AVG(score_general) as avg_general,
                    AVG(score_technical) as avg_technical,
                    AVG(score_aesthetic) as avg_aesthetic,
                    AVG(score_spaq) as avg_spaq,
                    AVG(score_koniq) as avg_koniq,
                    AVG(score_liqe) as avg_liqe
                FROM images
                WHERE score_general IS NOT NULL
            """)
            row = c.fetchone()
            stats["average_scores"] = {
                "general": round(row[0] or 0, 4),
                "technical": round(row[1] or 0, 4),
                "aesthetic": round(row[2] or 0, 4),
                "spaq": round(row[3] or 0, 4),
                "koniq": round(row[4] or 0, 4),
                "liqe": round(row[5] or 0, 4)
            }

            c.execute("SELECT COUNT(*) FROM folders")
            stats["total_folders"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM stacks")
            stats["total_stacks"] = c.fetchone()[0]

            c.execute("""
                SELECT status, COUNT(*) as cnt
                FROM jobs
                GROUP BY status
            """)
            stats["jobs_by_status"] = {row[0]: row[1] for row in c.fetchall()}

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE CAST(created_at AS DATE) = CURRENT_DATE
            """)
            stats["images_today"] = c.fetchone()[0]

        except Exception as e:
            stats["error"] = str(e)

        return stats


@mcp.tool(annotations=_RO)
@_require_db
def query_images(
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc",
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    rating: Optional[int] = None,
    label: Optional[str] = None,
    keyword: Optional[str] = None,
    folder_path: Optional[str] = None
) -> list:
    """Query images with flexible filtering and pagination. Supports filtering by score range, rating, label, keywords, and folder."""
    with db.connection() as conn:
        c = conn.cursor()

        query = """
            SELECT
                id, file_path, file_name, file_type,
                score_general, score_technical, score_aesthetic,
                score_spaq, score_koniq, score_liqe,
                rating, label, keywords, image_hash, created_at
            FROM images
        """

        conditions = []
        params = []

        if min_score is not None:
            conditions.append("score_general >= ?")
            params.append(min_score)

        if max_score is not None:
            conditions.append("score_general <= ?")
            params.append(max_score)

        if rating is not None:
            conditions.append("rating = ?")
            params.append(rating)

        if label:
            if label.lower() == "none":
                conditions.append("(label IS NULL OR label = '')")
            else:
                conditions.append("label = ?")
                params.append(label)

        if keyword:
            db._add_keyword_filter(conditions, params, keyword)

        if folder_path:
            folder_id = db.get_or_create_folder(folder_path)
            if folder_id:
                conditions.append("folder_id = ?")
                params.append(folder_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        valid_columns = ["id", "created_at", "score_general", "score_technical",
                         "score_aesthetic", "rating", "file_name"]
        if sort_by not in valid_columns:
            sort_by = "created_at"

        order = "DESC" if order.lower() == "desc" else "ASC"
        query += f" ORDER BY {sort_by} {order} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, limit])

        try:
            c.execute(query, tuple(params))
            rows = c.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            return [{"error": str(e)}]


@mcp.tool(annotations=_RO)
@_require_db
def get_image_details(file_path: str) -> dict:
    """Get full details for a specific image by file path."""
    return db.get_image_details(file_path)


@mcp.tool(annotations=_RO)
@_require_db
def search_images_by_hash(image_hash: str, hash_version: Optional[int] = None) -> dict:
    """Find an image by content hash (image_hash column, typically SHA-256). Returns file_paths when found."""
    h = (image_hash or "").strip()
    if not h:
        return {"error": "image_hash is required"}
    row = db.get_image_by_hash(h, hash_version=hash_version)
    if not row:
        return {"found": False, "image": None}
    return {"found": True, "image": _sanitize_for_mcp(row)}


@mcp.tool(annotations=_RO)
@_require_db
def get_db_schema(
    table_name_prefix: Optional[str] = None,
    max_tables: int = 200,
    max_column_rows: int = 8000,
) -> dict:
    """List ``public`` tables and columns (data type, nullability) for writing ``execute_sql`` queries. PostgreSQL only."""
    if config.get_database_engine() != "postgres":
        return {
            "error": "get_db_schema is supported when database.engine is postgres.",
            "database_engine": config.get_database_engine(),
        }
    prefix = (table_name_prefix or "").strip().lower()
    max_tables = max(1, min(int(max_tables), 500))
    max_column_rows = max(100, min(int(max_column_rows), 50_000))
    conn = db.get_connector()
    try:
        if prefix:
            rows = conn.query(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND LOWER(table_name) LIKE LOWER(?)
                ORDER BY table_name, ordinal_position
                FETCH FIRST ? ROWS ONLY
                """,
                (f"{prefix}%", max_column_rows),
            )
        else:
            rows = conn.query(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                FETCH FIRST ? ROWS ONLY
                """,
                (max_column_rows,),
            )
    except Exception as e:
        return {"error": str(e)}

    tables: dict[str, list[dict]] = {}
    for r in rows or []:
        tname = str(r.get("table_name") or "")
        if not tname:
            continue
        tables.setdefault(tname, []).append(
            {
                "column": r.get("column_name"),
                "data_type": r.get("data_type"),
                "is_nullable": r.get("is_nullable"),
            }
        )

    names_sorted = sorted(tables.keys())
    truncated_tables = len(names_sorted) > max_tables
    names_sorted = names_sorted[:max_tables]
    out_tables = {n: tables[n] for n in names_sorted}

    return _sanitize_for_mcp(
        {
            "database_engine": "postgres",
            "table_count": len(out_tables),
            "tables": out_tables,
            "truncated_tables": truncated_tables,
            "table_name_prefix": prefix or None,
        }
    )


@mcp.tool(annotations=_RO)
@_require_db
def execute_sql(query: str, params: list = None) -> dict:
    """Execute a read-only SQL SELECT (or WITH … SELECT) query. Uses the same ``?`` placeholder dialect as the app; translated on PostgreSQL. Discover tables/columns with ``get_db_schema`` first."""
    normalized = _strip_sql_comments_for_mcp(query)
    if not normalized:
        return {"error": "Empty query"}

    if not _is_mcp_read_only_sql(normalized):
        return {"error": "Only read-only SELECT queries are allowed (must start with SELECT or WITH after comments)."}

    ok_stmt, stmt_err = _mcp_sql_single_statement(normalized)
    if not ok_stmt:
        return {"error": stmt_err}

    dangerous_patterns = [
        r"\bDROP\b",
        r"\bDELETE\b",
        r"\bINSERT\b",
        r"\bUPDATE\b",
        r"\bALTER\b",
        r"\bCREATE\b",
        r"\bTRUNCATE\b",
        r"\bMERGE\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
    ]
    upper_query = normalized.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, upper_query):
            return {"error": f"Query contains forbidden pattern: {pattern}"}

    tparams = tuple(params) if params else None

    try:
        if config.get_database_engine() == "postgres":
            from modules import db_postgres
            from modules.db import _escape_pct_in_string_literals, _translate_fb_to_pg

            pg_sql = _escape_pct_in_string_literals(_translate_fb_to_pg(normalized))
            rows_raw = db_postgres.execute_select(pg_sql, tparams)
            results = [_sanitize_for_mcp(dict(r)) for r in rows_raw[:100]]
            columns = list(results[0].keys()) if results else []
            return {
                "columns": columns,
                "row_count": len(rows_raw),
                "rows": results,
                "truncated": len(rows_raw) > 100,
            }

        with db.connection() as conn:
            c = conn.cursor()
            if tparams:
                c.execute(normalized, tparams)
            else:
                c.execute(normalized)

            rows = c.fetchall()
            columns = [description[0] for description in c.description] if c.description else []
            results = [
                _sanitize_for_mcp(row.to_dict() if hasattr(row, "to_dict") else dict(zip(columns, row)))
                for row in rows
            ]

            return {
                "columns": columns,
                "row_count": len(rows),
                "rows": results[:100],
                "truncated": len(rows) > 100,
            }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=_RO)
@_require_db
def get_folder_tree(root_path: Optional[str] = None) -> list:
    """Get folder tree structure from database with image counts."""
    with db.connection() as conn:
        c = conn.cursor()
        try:
            if root_path:
                root_path = os.path.normpath(root_path)
                c.execute("""
                    SELECT f.path, COUNT(i.id) as image_count
                    FROM folders f
                    LEFT JOIN images i ON f.id = i.folder_id
                    WHERE f.path LIKE ? || '%'
                    GROUP BY f.path
                    ORDER BY f.path
                """, (root_path, root_path))
            else:
                c.execute("""
                    SELECT f.path, COUNT(i.id) as image_count
                    FROM folders f
                    LEFT JOIN images i ON f.id = i.folder_id
                    GROUP BY f.path
                    ORDER BY f.path
                """)
            return [
                {"path": row[0], "name": os.path.basename(row[0]) or row[0], "image_count": row[1]}
                for row in c.fetchall()
            ]
        except Exception as e:
            return [{"error": str(e)}]


@mcp.tool(annotations=_RO)
@_require_db
def get_newly_imported_folders(days: int = 7, min_images: int = 1, path_pattern: Optional[str] = None) -> list[dict]:
    """
    Find folders created in the last N days with at least min_images.
    Useful for identifying newly imported media that might need processing.
    """
    try:
        rows = db.get_newly_imported_folders(days=days, min_images=min_images, path_pattern=path_pattern)
        return [
            {
                "id": row["id"],
                "path": row["path"],
                "image_count": row["image_count"],
                "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], 'isoformat') else str(row["created_at"]),
                "is_fully_scored": bool(row["is_fully_scored"]),
                "is_keywords_processed": bool(row["is_keywords_processed"]),
                "phase_agg_dirty": bool(row["phase_agg_dirty"]),
                "needs_processing": not bool(row["is_fully_scored"]) or not bool(row["is_keywords_processed"])
            }
            for row in rows
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool(annotations=_RW)
@_require_db
def process_newly_imported_folders(days: int = 7, job_type: str = "scoring", path_pattern: Optional[str] = None) -> dict:
    """
    Trigger background processing jobs for newly imported folders that haven't been completed yet.
    job_type can be 'scoring', 'tagging', 'clustering', or 'bird_species'.
    """
    try:
        folders = db.get_newly_imported_folders(days=days, min_images=1, path_pattern=path_pattern)
        triggered = []
        skipped = []
        errors = []
        
        for f in folders:
            path = f["path"]
            needs_work = False
            if job_type == "scoring" and not f["is_fully_scored"]:
                needs_work = True
            elif job_type == "tagging" and not f["is_keywords_processed"]:
                needs_work = True
            elif job_type in ("clustering", "bird_species"):
                needs_work = True # Always check these if requested for recent folders
                
            if needs_work:
                # Reuse the run_processing_job logic or trigger directly if runners are available
                res = run_processing_job(job_type, path)
                if "error" in res:
                    errors.append({"path": path, "error": res["error"]})
                else:
                    triggered.append(path)
            else:
                skipped.append(path)
        
        return {
            "status": "success" if not errors else "partial_success",
            "triggered_count": len(triggered),
            "triggered_folders": triggered,
            "skipped_count": len(skipped),
            "skipped_folders": skipped,
            "errors": errors
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=_RO)
@_require_db
def get_stacks_summary(folder_path: Optional[str] = None) -> dict:
    """Get summary of image stacks/clusters including size distribution and largest stacks."""
    with db.connection() as conn:
        c = conn.cursor()
        summary = {}

        try:
            c.execute("SELECT COUNT(*) FROM stacks")
            summary["total_stacks"] = c.fetchone()[0]

            c.execute("""
                SELECT
                    CASE
                        WHEN cnt = 1 THEN 'single'
                        WHEN cnt BETWEEN 2 AND 5 THEN '2-5'
                        WHEN cnt BETWEEN 6 AND 10 THEN '6-10'
                        ELSE '10+'
                    END as size_range,
                    COUNT(*) as stack_count
                FROM (
                    SELECT stack_id, COUNT(*) as cnt
                    FROM images
                    WHERE stack_id IS NOT NULL
                    GROUP BY stack_id
                )
                GROUP BY size_range
            """)
            summary["stacks_by_size"] = {row[0]: row[1] for row in c.fetchall()}

            c.execute("SELECT COUNT(*) FROM images WHERE stack_id IS NULL")
            summary["unstacked_images"] = c.fetchone()[0]

            c.execute("""
                SELECT s.id, s.name, COUNT(i.id) as image_count,
                       MAX(i.score_general) as best_score
                FROM stacks s
                JOIN images i ON s.id = i.stack_id
                GROUP BY s.id
                ORDER BY image_count DESC
                FETCH FIRST 10 ROWS ONLY
            """)
            summary["largest_stacks"] = [
                {"id": row[0], "name": row[1], "count": row[2], "best_score": row[3]}
                for row in c.fetchall()
            ]

        except Exception as e:
            summary["error"] = str(e)

        return summary




# ============================================================
# Error & Diagnostics Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_incomplete_images(limit: int = 100) -> list:
    """Images with missing composite scores, model scores, rating, or label (broader than get_failed_images)."""
    try:
        rows = db.get_incomplete_records(limit=limit)
        return [_sanitize_for_mcp(dict(row)) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


_SCORE_FAIL_COLUMNS = (
    ("score_general", "general"),
    ("score_technical", "technical"),
    ("score_spaq", "spaq"),
    ("score_koniq", "koniq"),
    ("score_ava", "ava"),
    ("score_paq2piq", "paq2piq"),
    ("score_liqe", "liqe"),
)


@mcp.tool(annotations=_RO)
@_require_db
def get_failed_images(limit: int = 50, offset: int = 0) -> dict:
    """Images missing key quality scores (NULL or <= 0): general, technical, spaq, koniq, ava, paq2piq, liqe.

    Narrower than ``get_incomplete_images`` (no rating/label requirement). See also ``get_error_summary`` for counts.
    """
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    or_parts = [f"(i.{col} IS NULL OR i.{col} <= 0)" for col, _ in _SCORE_FAIL_COLUMNS]
    where_sql = "(" + " OR ".join(or_parts) + ")"
    conn = db.get_connector()
    try:
        count_row = conn.query_one(f"SELECT COUNT(*) AS c FROM images i WHERE {where_sql}", ())
        total = int((count_row or {}).get("c") or 0)
        rows = conn.query(
            f"""
            SELECT i.id, i.file_path, i.score_general, i.score_technical, i.score_spaq, i.score_koniq,
                   i.score_ava, i.score_paq2piq, i.score_liqe, i.created_at
            FROM images i
            WHERE {where_sql}
            ORDER BY i.created_at DESC NULLS LAST, i.id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            (off, lim),
        )
    except Exception as e:
        return {"error": str(e), "items": [], "total": 0}

    items = []
    for r in rows or []:
        d = dict(r)
        missing = []
        for col, label in _SCORE_FAIL_COLUMNS:
            v = d.get(col)
            if v is None or (isinstance(v, (int, float)) and v <= 0):
                missing.append(label)
        d["missing_scores"] = missing
        items.append(_sanitize_for_mcp(d))

    return {"total": total, "offset": off, "limit": lim, "items": items}


@mcp.tool(annotations=_RO)
@_require_db
def get_error_summary() -> dict:
    """Get summary of errors and issues in the database including failed jobs and missing scores."""
    with db.connection() as conn:
        c = conn.cursor()
        summary = {}

        try:
            c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'failed'")
            summary["failed_jobs"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE score_general IS NULL OR score_general = 0
            """)
            summary["images_missing_general_score"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE score_technical IS NULL OR score_technical = 0
            """)
            summary["images_missing_technical_score"] = c.fetchone()[0]

            models = ['spaq', 'koniq', 'ava', 'paq2piq', 'liqe']
            for model in models:
                col = f"score_{model}"
                c.execute(f"""
                    SELECT COUNT(*) FROM images
                    WHERE {col} IS NULL OR {col} = 0
                """)
                summary[f"images_missing_{model}"] = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM images WHERE folder_id IS NULL")
            summary["orphaned_images"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images WHERE file_path IS NULL OR file_path = ''
            """)
            summary["images_with_empty_paths"] = c.fetchone()[0]

            c.execute("""
                SELECT id, input_path, status, log, created_at
                FROM jobs
                WHERE status = 'failed'
                ORDER BY created_at DESC
                FETCH FIRST 10 ROWS ONLY
            """)
            summary["recent_failed_jobs"] = [dict(row) for row in c.fetchall()]

        except Exception as e:
            summary["error"] = str(e)

        try:
            stale = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=1)
            summary["stale_running_count"] = int(stale.get("count_estimate") or 0)
        except Exception:
            summary["stale_running_count"] = None

        return summary


@mcp.tool(annotations=_RO)
@_require_db
def check_database_health() -> dict:
    """Check database for inconsistencies, orphaned records, and data integrity issues."""
    with db.connection() as conn:
        c = conn.cursor()
        health = {
            "status": "healthy",
            "issues": [],
            "warnings": []
        }

        try:
            c.execute("""
                SELECT COUNT(*) FROM images i
                LEFT JOIN folders f ON i.folder_id = f.id
                WHERE i.folder_id IS NOT NULL AND f.id IS NULL
            """)
            orphaned_count = c.fetchone()[0]
            if orphaned_count > 0:
                health["issues"].append(f"{orphaned_count} images with invalid folder_id")
                health["status"] = "unhealthy"

            c.execute("""
                SELECT COUNT(*) FROM images i
                LEFT JOIN stacks s ON i.stack_id = s.id
                WHERE i.stack_id IS NOT NULL AND s.id IS NULL
            """)
            orphaned_stacks = c.fetchone()[0]
            if orphaned_stacks > 0:
                health["issues"].append(f"{orphaned_stacks} images with invalid stack_id")
                health["status"] = "unhealthy"

            c.execute("""
                SELECT file_path, COUNT(*) as cnt
                FROM images
                WHERE file_path IS NOT NULL
                GROUP BY file_path
                HAVING COUNT(*) > 1
            """)
            duplicates = c.fetchall()
            if duplicates:
                health["warnings"].append(f"{len(duplicates)} duplicate file paths found")

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE image_hash IS NOT NULL AND (file_path IS NULL OR file_path = '')
            """)
            hash_no_path = c.fetchone()[0]
            if hash_no_path > 0:
                health["warnings"].append(f"{hash_no_path} images with hash but no path")

            c.execute("""
                SELECT COUNT(*) FROM folders f
                LEFT JOIN images i ON f.id = i.folder_id
                WHERE i.id IS NULL
            """)
            empty_folders = c.fetchone()[0]
            if empty_folders > 0:
                health["warnings"].append(f"{empty_folders} folders with no images")

            c.execute("""
                SELECT COUNT(*) FROM stacks s
                LEFT JOIN images i ON s.id = i.stack_id
                WHERE i.id IS NULL
            """)
            empty_stacks = c.fetchone()[0]
            if empty_stacks > 0:
                health["warnings"].append(f"{empty_stacks} stacks with no images")

            try:
                stale_ph = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=1)
                n_stale = int(stale_ph.get("count_estimate") or 0)
                if n_stale > 0:
                    health["warnings"].append(
                        f"{n_stale} image_phase_status row(s) stuck in running >3600s "
                        "(folder phase badges may drift; MCP tool get_stale_running_phase_status)"
                    )
            except Exception:
                pass

            health["summary"] = {
                "total_issues": len(health["issues"]),
                "total_warnings": len(health["warnings"])
            }

        except Exception as e:
            health["status"] = "error"
            health["error"] = str(e)

        return health


@mcp.tool(annotations=_RO)
@_require_db
def validate_file_paths(
    limit: int = 100,
    folder_path: Optional[str] = None,
    missing_only: bool = False,
) -> dict:
    """Validate that image ``file_path`` values exist on disk. Optional ``folder_path`` restricts to images under that folder path (exact ``folders.path`` match or descendants). When ``missing_only`` is true, only missing files are listed (scans up to ``limit`` missing rows, expanding the DB fetch window)."""
    lim = max(1, min(int(limit), 5000))
    fetch_cap = lim if not missing_only else min(20_000, max(lim * 20, lim))
    conn = db.get_connector()
    results: dict[str, Any] = {
        "checked": 0,
        "exists": 0,
        "missing": 0,
        "missing_files": [],
        "folder_path": os.path.normpath(folder_path.strip()) if folder_path and str(folder_path).strip() else None,
        "missing_only": bool(missing_only),
    }

    try:
        if results["folder_path"]:
            norm = results["folder_path"]
            plike_u = norm + "/%"
            plike_w = norm + "\\%"
            rows = conn.query(
                """
                SELECT i.id, i.file_path FROM images i
                INNER JOIN folders f ON f.id = i.folder_id
                WHERE i.file_path IS NOT NULL AND TRIM(i.file_path) != ''
                  AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)
                ORDER BY i.created_at DESC NULLS LAST, i.id DESC
                FETCH FIRST ? ROWS ONLY
                """,
                (norm, plike_u, plike_w, fetch_cap),
            )
        else:
            rows = conn.query(
                """
                SELECT id, file_path FROM images
                WHERE file_path IS NOT NULL AND TRIM(file_path) != ''
                ORDER BY created_at DESC NULLS LAST, id DESC
                FETCH FIRST ? ROWS ONLY
                """,
                (fetch_cap,),
            )
    except Exception as e:
        results["error"] = str(e)
        return results

    examined = 0
    for row in rows or []:
        rid = row.get("id")
        file_path = row.get("file_path")
        if not file_path:
            continue
        examined += 1
        if os.path.exists(file_path):
            results["exists"] += 1
            if missing_only:
                continue
        else:
            results["missing"] += 1
            results["missing_files"].append({"id": rid, "file_path": file_path})
        if missing_only:
            if results["missing"] >= lim:
                break
        elif examined >= lim:
            break

    results["checked"] = examined
    return results


@mcp.tool(annotations=_RO)
@_require_db
def diagnose_phase_consistency(image_id: int, folder_path: Optional[str] = None) -> dict:
    """Diagnose folder vs per-image phase status mismatch (e.g. folder shows 69/69 KEYWORDS done but image shows Pending).
    Returns image info, folder info, phase statuses, and whether the image is in the folder's phase aggregate set."""
    result = {"image_id": image_id, "image": None, "folder": None, "phase_statuses": None, "in_folder_set": None}
    try:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, file_path, file_name, folder_id FROM images WHERE id = ?",
                (image_id,)
            )
            row = c.fetchone()
            if not row:
                result["error"] = f"Image {image_id} not found"
                return result

            result["image"] = {
                "id": row[0],
                "file_path": row[1],
                "file_name": row[2],
                "folder_id": row[3],
            }

            folder_id = row[3]
            if folder_id:
                c.execute("SELECT id, path FROM folders WHERE id = ?", (folder_id,))
                frow = c.fetchone()
                if frow:
                    result["folder"] = {"id": frow[0], "path": frow[1]}

            result["phase_statuses"] = db.get_image_phase_statuses(image_id)

            target_path = folder_path or (result.get("folder") or {}).get("path")
            if target_path:
                from modules import utils
                wsl_path = utils.convert_path_to_wsl(target_path) if hasattr(utils, "convert_path_to_wsl") else target_path
                path_like_unix = wsl_path + "/%"
                path_like_win = wsl_path + "\\%"
                c.execute(
                    """
                    SELECT COUNT(*) FROM images
                    WHERE folder_id IN (
                        SELECT id FROM folders
                        WHERE path = ? OR path LIKE ? OR path LIKE ?
                    )
                    """,
                    (wsl_path, path_like_unix, path_like_win),
                )
                folder_image_count = c.fetchone()[0]
                c.execute(
                    """
                    SELECT 1 FROM images i
                    JOIN folders f ON f.id = i.folder_id
                    WHERE i.id = ? AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)
                    """,
                    (image_id, wsl_path, path_like_unix, path_like_win),
                )
                in_set = c.fetchone() is not None
                result["folder_aggregate"] = {
                    "folder_path_used": target_path,
                    "image_count_in_folder": folder_image_count,
                    "image_in_folder_set": in_set,
                }
    except Exception as e:
        result["error"] = str(e)
    return result


@mcp.tool(annotations=_RO)
@_require_db
def get_stale_running_phase_status(min_age_seconds: int = 3600, limit: int = 50) -> dict:
    """Find image_phase_status rows stuck in ``running`` longer than ``min_age_seconds`` (folder rollup drift).

    Use after crashes or forced stops when folder badges still show ``running`` but jobs are terminal.
    """
    return db.list_stale_running_image_phase_rows(
        min_age_seconds=min_age_seconds,
        limit=limit,
    )


# ============================================================
# Monitoring & Jobs Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_recent_jobs(limit: int = 10) -> list:
    """Get recent scoring/tagging jobs with their status."""
    rows = db.get_jobs(limit=limit)
    return [dict(row) for row in rows]


def _normalize_job_payload_for_mcp(job: dict) -> dict:
    """Copy job row to JSON-safe dict; parse queue_payload JSON and trim very long logs."""
    out = _sanitize_for_mcp(dict(job))
    qp = out.get("queue_payload")
    if isinstance(qp, str) and qp.strip():
        try:
            out["queue_payload_parsed"] = json.loads(qp)
        except (json.JSONDecodeError, TypeError, ValueError):
            out["queue_payload_parsed"] = None
    log = out.get("log")
    if isinstance(log, str) and len(log) > 8000:
        out["log"] = log[-8000:]
        out["log_truncated"] = True
    return out


@mcp.tool(annotations=_RO)
@_require_db
def get_job_details(job_id: int) -> dict:
    """Get one job/run by id (jobs.id): status, paths, timestamps, queue_payload summary, log tail. Same id as workflow run_id in the API."""
    row = db.get_job(int(job_id))
    if not row:
        return {"error": "Job not found", "job_id": int(job_id)}
    return _normalize_job_payload_for_mcp(row)


@mcp.tool(annotations=_RO)
@_require_db
def get_job_phases(job_id: int) -> dict:
    """List phase rows (order, code, state, timestamps, errors) for a job/run id."""
    jid = int(job_id)
    phases = db.get_job_phases(jid)
    return {"job_id": jid, "count": len(phases), "phases": _sanitize_for_mcp(phases)}


@mcp.tool(annotations=_RO)
@_require_db
def get_job_stage_images(
    job_id: int,
    phase_code: str,
    limit: int = 50,
    offset: int = 0,
    include_steps: bool = False,
) -> dict:
    """Paginate per-image phase status for a job+phase (image_phase_status). Optional include_steps adds job_steps telemetry for that phase."""
    jid = int(job_id)
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    data = db.get_job_stage_images(jid, phase_code, offset=off, limit=lim)
    out = {
        "job_id": jid,
        "phase_code": phase_code,
        "offset": off,
        "limit": lim,
        "total": data.get("total", 0),
        "items": data.get("items", []),
    }
    if include_steps:
        out["steps"] = db.get_job_steps(jid, phase_code)
    return _sanitize_for_mcp(out)


@mcp.tool(annotations=_RO)
@_require_db
def get_run_diagnostics(run_id: int) -> dict:
    """Post-run audit snapshot from queue_payload plus per-phase image_phase_status counts for this job/run id."""
    jid = int(run_id)
    data = db.get_run_diagnostics(jid)
    return _sanitize_for_mcp(data)


@mcp.tool(annotations=_RO)
@_require_db
def get_job_execution_report(run_id: int, phase_code: Optional[str] = None, action: Optional[str] = None, offset: int = 0, limit: int = 20) -> dict:
    """Structured execution report for a job: what the run did to each image.

    Returns report_json summary (per-phase stats, before/after aggregates) and
    paginated per-image action log with before/after score snapshots.
    Filter with phase_code (scoring, metadata, indexing) and action (processed, skipped, failed).
    """
    jid = int(run_id)
    report = db.get_job_report(jid)
    actions = db.get_job_image_actions(jid, phase_code, action, offset, limit)
    summary: dict[str, Any] = {"action_counts": {}}
    try:
        conn = db.get_connector()
        act_rows = conn.query(
            """
            SELECT LOWER(TRIM(COALESCE(action, ''))) AS act, COUNT(*) AS c
            FROM job_image_actions
            WHERE job_id = ?
            GROUP BY LOWER(TRIM(COALESCE(action, '')))
            """,
            (jid,),
        )
        for r in act_rows or []:
            act = (r.get("act") or "").strip() or "unknown"
            summary["action_counts"][act] = int(r.get("c") or 0)
    except Exception as e:
        summary["error"] = str(e)

    return _sanitize_for_mcp({
        "job_id": jid,
        "report": report,
        "image_actions": actions,
        "summary": summary,
    })


@mcp.tool(annotations=_RO)
@_require_db
def get_image_pipeline_failures(
    image_id: Optional[int] = None,
    file_path: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Recent ``job_image_actions`` rows with action ``failed`` for one image (by ``image_id`` or ``file_path``).

    Joins ``jobs`` for terminal status and log snippet. Use after locating an image via ``query_images`` / ``get_image_details``.
    """
    if not image_id and not (file_path and str(file_path).strip()):
        return {"error": "Provide image_id or file_path", "items": []}

    conn = db.get_connector()
    iid: int | None = int(image_id) if image_id is not None else None
    if iid is None and file_path:
        fp = os.path.normpath(str(file_path).strip())
        row = conn.query_one("SELECT id FROM images WHERE file_path = ?", (fp,))
        if not row:
            return {"error": "image_not_found", "file_path": fp, "items": []}
        iid = int(row["id"])

    lim = max(1, min(int(limit), 200))
    try:
        rows = conn.query(
            """
            SELECT jia.id, jia.job_id, jia.phase_code, jia.action, jia.reason,
                   jia.before_snapshot, jia.after_snapshot, jia.created_at,
                   j.status AS job_status, j.log AS job_log
            FROM job_image_actions jia
            LEFT JOIN jobs j ON j.id = jia.job_id
            WHERE jia.image_id = ?
              AND LOWER(TRIM(jia.action)) = 'failed'
            ORDER BY jia.created_at DESC NULLS LAST, jia.id DESC
            FETCH FIRST ? ROWS ONLY
            """,
            (iid, lim),
        )
    except Exception as e:
        return {"error": str(e), "image_id": iid, "items": []}

    items = []
    for r in rows or []:
        d = dict(r)
        for k in ("before_snapshot", "after_snapshot", "job_log"):
            v = d.get(k)
            if isinstance(v, str) and len(v) > 2000:
                d[k] = v[:2000] + "…"
        items.append(_sanitize_for_mcp(d))

    return {"image_id": iid, "items": items}


@mcp.tool(annotations=_RO)
@_require_db
def get_location_stats() -> dict:
    """Summarize GPS and geocode coverage in ``image_exif`` (PostgreSQL; requires migration 0013 columns)."""
    if config.get_database_engine() != "postgres":
        return {"error": "get_location_stats is supported on PostgreSQL only.", "database_engine": config.get_database_engine()}
    conn = db.get_connector()
    try:
        row = conn.query_one(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(*) FILTER (WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL) AS with_gps,
                COUNT(*) FILTER (WHERE geocoded_at IS NOT NULL) AS geocoded,
                COUNT(*) FILTER (
                    WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL AND geocoded_at IS NULL
                ) AS gps_not_geocoded
            FROM image_exif
            """,
            (),
        )
    except Exception as e:
        return {"error": str(e), "note": "Ensure image_exif GPS/geocode columns exist (Alembic 0013)."}

    return _sanitize_for_mcp(dict(row) if row else {})


@mcp.tool(annotations=_RO)
def export_debug_bundle(output_path: Optional[str] = None) -> dict:
    """Write a redacted support zip (config, environment, doctor JSON, log tails). Same content as ``scripts/export_debug_bundle.py``."""
    from pathlib import Path

    from modules.debug_bundle_export import write_redacted_debug_bundle

    op = Path(os.path.expanduser(output_path)).resolve() if output_path and str(output_path).strip() else None
    if op is not None:
        if op.suffix.lower() != ".zip":
            return {"error": "output_path must end with .zip", "success": False}
        op.parent.mkdir(parents=True, exist_ok=True)

    return write_redacted_debug_bundle(output_zip=op)


@mcp.tool(annotations=_RO)
@_require_db
def get_embedding_stats(
    folder_path: Optional[str] = None,
    embedding_space: Optional[str] = None,
) -> dict:
    """Counts of images with vs without a stored image embedding.

    By default reports coverage for the MobileNetV2 default space and a
    per-space breakdown of every row in ``embedding_spaces``. Pass
    ``embedding_space`` to get coverage counts for that specific space. Optional
    ``folder_path`` filters by exact ``folders.path`` match.
    """
    try:
        from modules.similar_search import EMBEDDING_DIM
        expected_dim = EMBEDDING_DIM
    except Exception:
        expected_dim = None

    conn = db.get_connector()
    folder_id = None
    if folder_path and str(folder_path).strip():
        norm = os.path.normpath(str(folder_path).strip())
        frow = conn.query_one("SELECT id FROM folders WHERE path = ?", (norm,))
        if not frow:
            return {"error": "folder_not_found", "folder_path": norm}
        folder_id = frow["id"]

    def _per_space_counts(is_postgres: bool) -> list[dict]:
        if not is_postgres:
            return []
        try:
            rows = db_postgres.execute_select(
                "SELECT id, code, dim FROM embedding_spaces WHERE COALESCE(active, 1) = 1 ORDER BY id"
            )
        except Exception:
            return []
        per_space: list[dict] = []
        for r in rows:
            dim = int(r.get("dim") or 0)
            try:
                table = db._pg_embedding_table_for_dim(dim)
            except ValueError:
                per_space.append({
                    "code": r.get("code"),
                    "dim": dim,
                    "error": "no fact table for dim",
                })
                continue
            params: list = [int(r.get("id"))]
            folder_clause = ""
            if folder_id is not None:
                folder_clause = (
                    " AND EXISTS ("
                    "  SELECT 1 FROM images i WHERE i.id = e.image_id AND i.folder_id = %s"
                    " )"
                )
                params.append(folder_id)
            try:
                row = db_postgres.execute_select_one(
                    f"SELECT COUNT(*) AS c FROM {table} e WHERE e.embedding_space_id = %s{folder_clause}",
                    tuple(params),
                )
                count = int((row or {}).get("c") or 0)
            except Exception as exc:  # noqa: BLE001
                per_space.append({
                    "code": r.get("code"),
                    "dim": dim,
                    "error": f"count failed: {exc}",
                })
                continue
            per_space.append({
                "code": r.get("code"),
                "dim": dim,
                "table": table,
                "count": count,
            })
        return per_space

    is_postgres = conn.type == 'postgres'

    # Per-space lookup for a specific embedding_space argument.
    if embedding_space:
        if not is_postgres:
            return {
                "error": "embedding_space queries require PostgreSQL (pgvector).",
                "embedding_space": embedding_space,
            }
        try:
            from modules.embedding_spaces import SPACE_DIMS, get_embedding_space_id

            dim = SPACE_DIMS.get(embedding_space)
            if dim is None:
                row = db_postgres.execute_select_one(
                    "SELECT dim FROM embedding_spaces WHERE code = %s",
                    (embedding_space,),
                )
                if not row:
                    return {"error": "unknown embedding_space", "embedding_space": embedding_space}
                dim = int(row["dim"])
            table = db._pg_embedding_table_for_dim(int(dim))
            space_id = get_embedding_space_id(embedding_space)
            if space_id is None:
                return {"error": "embedding_space not registered", "embedding_space": embedding_space}
        except ValueError as exc:
            return {"error": str(exc), "embedding_space": embedding_space}

        params_total: list = []
        total_clause = ""
        if folder_id is not None:
            total_clause = " WHERE folder_id = %s"
            params_total.append(folder_id)
        total_row = db_postgres.execute_select_one(
            f"SELECT COUNT(*) AS c FROM images{total_clause}",
            tuple(params_total) if params_total else None,
        )
        params_with: list = [space_id]
        with_clause = " WHERE e.embedding_space_id = %s"
        if folder_id is not None:
            with_clause += " AND EXISTS (SELECT 1 FROM images i WHERE i.id = e.image_id AND i.folder_id = %s)"
            params_with.append(folder_id)
        with_row = db_postgres.execute_select_one(
            f"SELECT COUNT(*) AS c FROM {table} e{with_clause}",
            tuple(params_with),
        )
        total = int((total_row or {}).get("c") or 0)
        with_emb = int((with_row or {}).get("c") or 0)
        return {
            "folder_path": os.path.normpath(folder_path) if folder_path and str(folder_path).strip() else None,
            "embedding_space": embedding_space,
            "embedding_dim": int(dim),
            "table": table,
            "total_images": total,
            "with_embedding": with_emb,
            "missing_embedding": max(0, total - with_emb),
        }

    # Default: MobileNet coverage + per-space summary.
    if is_postgres:
        sub = db._pg_default_embedding_space_subquery_sql()
        has_e = db._postgres_has_default_embedding_sql("i")
        if folder_id is not None:
            base = "i.folder_id = ?"
            params_t = (folder_id,)
            total_row = conn.query_one(
                f"SELECT COUNT(*) AS c FROM images i WHERE {base}",
                params_t
            )
            with_row = conn.query_one(
                f"""SELECT COUNT(*) AS c FROM images i
                   LEFT JOIN image_embeddings ie ON ie.image_id = i.id AND ie.embedding_space_id = {sub}
                   WHERE {base} AND {has_e}""",
                params_t,
            )
        else:
            total_row = conn.query_one("SELECT COUNT(*) AS c FROM images i", ())
            with_row = conn.query_one(
                f"""SELECT COUNT(*) AS c FROM images i
                   LEFT JOIN image_embeddings ie ON ie.image_id = i.id AND ie.embedding_space_id = {sub}
                   WHERE {has_e}""",
                (),
            )
    else:
        if folder_id is not None:
            base = "folder_id = ?"
            params_t = (folder_id,)
            total_row = conn.query_one(f"SELECT COUNT(*) AS c FROM images WHERE {base}", params_t)
            with_row = conn.query_one(
                f"SELECT COUNT(*) AS c FROM images WHERE {base} AND image_embedding IS NOT NULL",
                params_t,
            )
        else:
            total_row = conn.query_one("SELECT COUNT(*) AS c FROM images", ())
            with_row = conn.query_one(
                "SELECT COUNT(*) AS c FROM images WHERE image_embedding IS NOT NULL",
                (),
            )

    total = int((total_row or {}).get("c") or 0)
    with_emb = int((with_row or {}).get("c") or 0)
    missing = max(0, total - with_emb)
    return {
        "folder_path": os.path.normpath(folder_path) if folder_path and str(folder_path).strip() else None,
        "total_images": total,
        "with_embedding": with_emb,
        "missing_embedding": missing,
        "expected_embedding_dim": expected_dim,
        "per_space": _per_space_counts(is_postgres),
    }


@mcp.tool(annotations=_RO)
def get_database_engine_info() -> dict:
    """Summarize database.engine, connector mode, non-secret connection targets, and whether a simple query succeeds. Complements validate_config."""
    engine = config.get_database_engine()
    out: dict[str, Any] = {
        "database_engine_config": engine,
        "mcp_db_initialized": bool(_db_available),
        "connector_type": None,
        "targets": {},
        "ping_ok": None,
        "ping_error": None,
    }
    try:
        conn = db.get_connector()
        out["connector_type"] = getattr(conn, "type", type(conn).__name__)
    except Exception as e:
        out["connector_error"] = str(e)
        return out

    db_sec = config.get_config_section("database") or {}
    if engine == "api" or out.get("connector_type") == "api":
        out["targets"]["api_url"] = str(db_sec.get("api_url", "http://localhost:7860")).strip()
    if engine in ("postgres", "firebird") or out.get("connector_type") == "postgres":
        try:
            from modules import db_postgres as _dpg
            pg = _dpg.get_pg_config()
            out["targets"]["postgres"] = {
                "host": pg.get("host"),
                "port": pg.get("port"),
                "dbname": pg.get("dbname"),
                "user": pg.get("user"),
                "password_configured": bool(pg.get("password")),
            }
        except Exception as e:
            out["targets"]["postgres_error"] = str(e)

    if _db_available:
        try:
            db.get_connector().query_one("SELECT 1 AS ok FROM images FETCH FIRST 1 ROWS ONLY")
            out["ping_ok"] = True
        except Exception as e:
            out["ping_ok"] = False
            out["ping_error"] = str(e)
    else:
        out["ping_ok"] = None
        out["ping_note"] = "Database not initialized in this MCP process."

    return out


@mcp.tool(annotations=_RO)
@_require_db
def check_stack_invariants(limit: int = 20) -> dict:
    """Detect common stack data issues: single-image stacks, images pointing at missing stacks, stacks with no images. Returns counts and small samples."""
    lim = max(1, min(int(limit), 200))
    conn = db.get_connector()

    singleton = conn.query_one(
        """
        SELECT COUNT(*) AS c FROM (
            SELECT stack_id FROM images WHERE stack_id IS NOT NULL
            GROUP BY stack_id
            HAVING COUNT(*) = 1
        ) AS singletons
        """
    )
    orphan_img = conn.query_one(
        """
        SELECT COUNT(*) AS c FROM images i
        WHERE i.stack_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM stacks s WHERE s.id = i.stack_id)
        """
    )
    empty_stacks = conn.query_one(
        """
        SELECT COUNT(*) AS c FROM stacks s
        WHERE NOT EXISTS (SELECT 1 FROM images i WHERE i.stack_id = s.id)
        """
    )

    sample_singletons = conn.query(
        """
        SELECT stack_id, COUNT(*) AS cnt FROM images
        WHERE stack_id IS NOT NULL
        GROUP BY stack_id
        HAVING COUNT(*) = 1
        ORDER BY stack_id
        FETCH FIRST ? ROWS ONLY
        """,
        (lim,),
    )
    sample_orphans = conn.query(
        """
        SELECT i.id AS image_id, i.stack_id, i.file_path FROM images i
        WHERE i.stack_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM stacks s WHERE s.id = i.stack_id)
        ORDER BY i.id
        FETCH FIRST ? ROWS ONLY
        """,
        (lim,),
    )

    return {
        "singleton_stack_count": int((singleton or {}).get("c") or 0),
        "images_orphan_stack_id_count": int((orphan_img or {}).get("c") or 0),
        "empty_stacks_count": int((empty_stacks or {}).get("c") or 0),
        "sample_singleton_stack_ids": [r.get("stack_id") for r in (sample_singletons or [])],
        "sample_orphan_stack_images": _sanitize_for_mcp(sample_orphans or []),
    }


# ============================================================
# Maintenance & Mutation Tools (Write Access)
# ============================================================

@mcp.tool(annotations=_RW_DESTRUCTIVE)
@_require_db
def rebase_file_paths(old_root: str, new_root: str, dry_run: bool = True) -> dict:
    """Batch update image file paths by replacing a root prefix.
    Example: rebase D:\\Photos to Z:\\Archive."""
    old_root = os.path.normpath(old_root)
    new_root = os.path.normpath(new_root)

    with db.connection() as conn:
        c = conn.cursor()
        try:
            # First find how many would be affected
            pattern = old_root + "%"
            c.execute("SELECT COUNT(*) FROM images WHERE file_path LIKE ?", (pattern,))
            count = c.fetchone()[0]

            if dry_run:
                return {
                    "dry_run": True,
                    "affected_count": count,
                    "message": f"Would update {count} paths from {old_root} to {new_root}"
                }

            if count == 0:
                return {"success": True, "count": 0, "message": "No matching paths found"}

            # Update paths - using a simple replace logic
            # This is complex in SQL depending on the DB engine, so we'll do it in a transaction
            c.execute("SELECT id, file_path, folder_id FROM images WHERE file_path LIKE ?", (pattern,))
            rows = c.fetchall()

            folder_cache = {}
            affected_folders = set()

            for image_id, old_path, old_fid in rows:
                new_path = old_path.replace(old_root, new_root, 1)
                db.update_image_field(image_id, "file_path", new_path)
                
                # Update folder_id to match the new path
                new_dir = os.path.normpath(os.path.dirname(new_path))
                if new_dir not in folder_cache:
                    folder_cache[new_dir] = db.get_or_create_folder(new_dir)
                new_fid = folder_cache[new_dir]
                
                if new_fid != old_fid:
                    db.update_image_field(image_id, "folder_id", new_fid)
                    if old_fid:
                        affected_folders.add(old_fid)
                    if new_fid:
                        affected_folders.add(new_fid)

            # Invalidate aggregates for all affected folders
            for fid in affected_folders:
                try:
                    db.invalidate_folder_phase_aggregates(folder_id=fid)
                except Exception:
                    pass

            conn.commit()
            return {"success": True, "updated_count": count}
        except Exception as e:
            return {"error": str(e)}


@mcp.tool(annotations=_RW)
@_require_db
def set_image_metadata(file_path: str, rating: Optional[int] = None, label: Optional[str] = None) -> dict:
    """Update metadata for a specific image in the database.
    Optionally updates sidecar files if background runners are active."""
    details = db.get_image_details(file_path)
    if not details:
        return {"error": f"Image {file_path} not found in database"}

    image_id = details["id"]
    updates = {}
    if rating is not None:
        updates["rating"] = rating
    if label is not None:
        updates["label"] = label

    if not updates:
        return {"message": "No updates specified"}

    try:
        for field, value in updates.items():
            db.update_image_field(image_id, field, value)

        # Notify gallery if context exists
        if _gradio_context:
            msg = f"Updated {file_path}: {updates}"
            logger.info(f"MCP metadata update: {msg}")

        return {"success": True, "image_id": image_id, "updates": updates}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=_RW_DESTRUCTIVE)
@_require_db
def prune_missing_files(dry_run: bool = True) -> dict:
    """Remove database records for images whose files no longer exist on disk."""
    from modules import utils
    try:
        rows = db.get_connector().query("SELECT id, file_path FROM images")
        to_prune = []  # List of (id, path)

        for row in rows:
            # Robust row access: handle both dict and RowWrapper (which might iterate as tuples)
            if hasattr(row, 'get'):
                image_id = row.get("id")
                file_path = row.get("file_path")
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                # Fallback for raw tuples
                image_id, file_path = row[0], row[1]
            else:
                try:
                    image_id = row["id"]
                    file_path = row["file_path"]
                except Exception:
                    continue

            if not file_path:
                to_prune.append((image_id, file_path))
                continue
            
            # Ensure file_path is a string (defensive)
            if isinstance(file_path, (list, tuple)) and len(file_path) > 0:
                file_path = file_path[0]
            
            # Use resolve_file_path for consistent resolution across the app
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                to_prune.append((image_id, file_path))

        if dry_run:
            return {
                "dry_run": True,
                "to_prune_count": len(to_prune),
                "examples": [p for _, p in to_prune][:10]
            }

        if not to_prune:
            return {"success": True, "pruned_count": 0}

        # Batch delete using the existing delete_image which handles relations
        count = 0
        for mid, mpath in to_prune:
            if mpath:
                db.delete_image(mpath)
            else:
                # If path is null, delete by ID directly
                db.get_connector().execute("DELETE FROM images WHERE id = ?", (mid,))
            count += 1

        return {"success": True, "pruned_count": count}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=_RO)
def verify_environment() -> dict:
    """Comprehensive environment check: GPU, DB, Python, and system stats."""
    import torch
    import psutil
    import platform

    # Try to refresh DB status if it's currently marked as unavailable
    global _db_available
    if not _db_available:
        prepare_mcp_embedded()

    status = {
        "os": platform.system(),
        "python_version": sys.version,
        "gpu": {
            "available": torch.cuda.is_available(),
            "count": torch.cuda.device_count(),
            "names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else []
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024**3), 2)
        },
        "database": {
            "engine": db._get_db_engine(),
            "available": _db_available
        }
    }
    return status


@mcp.tool(annotations=_RO)
def get_system_resources() -> dict:
    """CPU and RAM snapshot plus optional ``nvidia-smi`` GPU rows. Does not require database access."""
    out: dict[str, Any] = {"cpu_percent": None, "memory": {}, "gpu": {}}
    try:
        import psutil

        out["cpu_percent"] = round(psutil.cpu_percent(interval=0.1), 2)
        vm = psutil.virtual_memory()
        out["memory"] = {
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "percent_used": vm.percent,
        }
    except Exception as e:
        out["memory_error"] = str(e)

    try:
        import subprocess

        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        gpus: list[dict[str, str]] = []
        if proc.returncode == 0 and proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append(
                        {
                            "name": parts[0],
                            "memory_used_mb": parts[1],
                            "memory_total_mb": parts[2],
                            "utilization_gpu_pct": parts[3],
                        }
                    )
        out["gpu"]["nvidia_smi"] = gpus
    except Exception as e:
        out["gpu"]["error"] = str(e)

    return out


@mcp.tool(annotations=_RO)
def get_thread_dump() -> dict:
    """Capture a full Python thread dump for backend diagnostic and stall debugging."""
    try:
        from modules.pipeline_diagnostics import get_thread_dump as _get_thread_dump
        return {"success": True, "thread_dump": _get_thread_dump()}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool(annotations=_RO)
def get_runner_status() -> dict:
    """Get current status of scoring and tagging background runners including progress and recent logs."""
    status = {
        "scoring": {"available": False},
        "tagging": {"available": False},
        "clustering": {"available": False},
        "selection": {"available": False},
        "indexing": {"available": False},
        "metadata": {"available": False}
    }

    if _scoring_runner:
        try:
            result = _scoring_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["scoring"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["scoring"]["error"] = str(e)

    if _tagging_runner:
        try:
            result = _tagging_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["tagging"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["tagging"]["error"] = str(e)

    if _clustering_runner:
        try:
            result = _clustering_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["clustering"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["clustering"]["error"] = str(e)

    if _selection_runner:
        try:
            result = _selection_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["selection"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["selection"]["error"] = str(e)

    if _indexing_runner:
        try:
            result = _indexing_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["indexing"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["indexing"]["error"] = str(e)

    if _metadata_runner:
        try:
            result = _metadata_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["metadata"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["metadata"]["error"] = str(e)

    if _maintenance_runner:
        try:
            if hasattr(_maintenance_runner, "get_status"):
                result = _maintenance_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["maintenance"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "recent_log": log[-2000:] if log else "",
                }
            else:
                running = bool(getattr(_maintenance_runner, "is_running", False))
                status["maintenance"] = {
                    "available": True,
                    "is_running": running,
                    "status_message": "Running maintenance job" if running else "Idle",
                    "progress": {"current": 0, "total": 0},
                    "recent_log": "",
                }
        except Exception as e:
            status["maintenance"] = {"available": True, "error": str(e)}
    else:
        status["maintenance"] = {"available": False}

    if _bird_species_runner:
        try:
            result = _bird_species_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["bird_species"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["bird_species"] = {"available": True, "error": str(e)}
    else:
        status["bird_species"] = {"available": False}

    return status


@mcp.tool(annotations=_RO)
def get_pipeline_stats() -> dict:
    """Get statistics about the processing pipeline and active jobs. Runner status, queue sizes, dispatcher state, and active job info."""
    result = {
        "runners": get_runner_status(),
        "dispatcher": {"dispatcher_available": False},
        "queue_config": {}
    }

    # Dispatcher state (only when WebUI is running and api module has job_dispatcher)
    try:
        from modules import api
        dispatcher = getattr(api, "_job_dispatcher", None)
        if dispatcher is not None:
            state = dispatcher.get_state()
            result["dispatcher"] = {
                "dispatcher_available": True,
                "is_dispatcher_running": state.get("is_dispatcher_running", False),
                "active_runner": state.get("active_runner"),
                "queue_size": state.get("queue_size", 0),
                "queue": state.get("queue", [])
            }
    except ImportError:
        pass
    except Exception as e:
        result["dispatcher"]["error"] = str(e)

    # Queue config from config.json
    try:
        proc = config.get_config_section("processing") or {}
        result["queue_config"] = {
            "prep_queue_size": proc.get("prep_queue_size"),
            "scoring_queue_size": proc.get("scoring_queue_size"),
            "result_queue_size": proc.get("result_queue_size"),
            "clustering_batch_size": proc.get("clustering_batch_size"),
        }
    except Exception:
        pass

    return result


@mcp.tool(annotations=_RO)
@_require_db
def get_performance_metrics(days: int = 7) -> dict:
    """Get performance metrics from recent jobs: avg job duration, jobs completed/failed, success rate, jobs by status."""
    import datetime
    result = {
        "avg_job_duration_seconds": None,
        "jobs_completed_7d": 0,
        "jobs_failed_7d": 0,
        "jobs_cancelled_7d": 0,
        "jobs_interrupted_7d": 0,
        "success_rate": None,
        "jobs_by_status": {},
        "total_jobs_7d": 0,
        "images_processed_7d": None,
    }
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        with db.connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT status, started_at, finished_at, completed_at
                FROM jobs
                WHERE created_at >= ?
                """,
                (cutoff,),
            )
            rows = c.fetchall()

        jobs_by_status = {}
        durations = []
        for row in rows:
            status = (row[0] or "unknown").strip().lower()
            jobs_by_status[status] = jobs_by_status.get(status, 0) + 1
            started = row[1]
            finished = row[2] or row[3]
            if started and finished:
                try:
                    delta = (finished - started).total_seconds()
                    if delta >= 0:
                        durations.append(delta)
                except (TypeError, AttributeError):
                    pass

        result["jobs_by_status"] = jobs_by_status
        result["total_jobs_7d"] = len(rows)
        result["jobs_completed_7d"] = jobs_by_status.get("completed", 0)
        result["jobs_failed_7d"] = jobs_by_status.get("failed", 0)
        result["jobs_cancelled_7d"] = jobs_by_status.get("cancelled", 0) + jobs_by_status.get("canceled", 0)
        result["jobs_interrupted_7d"] = jobs_by_status.get("interrupted", 0)

        if durations:
            result["avg_job_duration_seconds"] = round(sum(durations) / len(durations), 1)

        terminal = result["jobs_completed_7d"] + result["jobs_failed_7d"] + result["jobs_cancelled_7d"] + result["jobs_interrupted_7d"]
        if terminal > 0:
            result["success_rate"] = round(100.0 * result["jobs_completed_7d"] / terminal, 1)

        result["period_days"] = days
    except Exception as e:
        result["error"] = str(e)
    return result


@mcp.tool(annotations=_RO)
def get_model_status() -> dict:
    """Get status of loaded models, GPU availability, and CUDA/PyTorch/TensorFlow configuration."""
    status = {
        "models": {},
        "gpu": {},
        "scorer_available": False
    }

    try:
        if _scoring_runner and _scoring_runner.shared_scorer:
            status["scorer_available"] = True
            scorer = _scoring_runner.shared_scorer

            try:
                status["models"]["version"] = getattr(scorer, 'VERSION', 'unknown')
            except Exception:
                pass

            model_names = ['spaq', 'ava', 'koniq', 'paq2piq']
            for model_name in model_names:
                try:
                    model_attr = getattr(scorer, f'{model_name}_model', None)
                    status["models"][model_name] = {"loaded": model_attr is not None}
                except Exception:
                    status["models"][model_name] = {"loaded": False}
        else:
            status["models"]["note"] = "Scorer not initialized"

        try:
            import tensorflow as tf
            gpus = tf.config.list_physical_devices('GPU')
            status["gpu"]["tensorflow_available"] = True
            status["gpu"]["physical_gpus"] = len(gpus)
            status["gpu"]["cuda_built"] = tf.test.is_built_with_cuda()
            if gpus:
                status["gpu"]["gpu_names"] = [str(gpu) for gpu in gpus]
        except ImportError:
            status["gpu"]["tensorflow_available"] = False
        except Exception as e:
            status["gpu"]["error"] = str(e)

        try:
            import torch
            status["gpu"]["pytorch_available"] = True
            status["gpu"]["pytorch_cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                status["gpu"]["pytorch_device_count"] = torch.cuda.device_count()
                status["gpu"]["pytorch_device_name"] = torch.cuda.get_device_name(0)
        except ImportError:
            status["gpu"]["pytorch_available"] = False
        except Exception as e:
            status["gpu"]["pytorch_error"] = str(e)

        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                status["gpu"]["nvidia_driver"] = "available"
                lines = result.stdout.strip().split('\n')
                status["gpu"]["gpu_info"] = lines
            else:
                status["gpu"]["nvidia_driver"] = "not_available"
        except (OSError, Exception):
            status["gpu"]["nvidia_driver"] = "not_checked"

    except Exception as e:
        status["error"] = str(e)

    return status


@mcp.tool(annotations=_RW)
@_require_db
def run_processing_job(job_type: str, input_path: str, args: dict = None) -> dict:
    """Trigger a background processing job (scoring, tagging, clustering/stacks, or bird_species).

    Creates a ``jobs`` row and returns integer ``job_id`` / ``jobs_id`` (same value) for use with
    ``get_job_details``, ``get_run_diagnostics``, and ``get_job_execution_report``.
    """
    if args is None:
        args = {}

    if not os.path.exists(input_path) and not (job_type == "clustering" and (not input_path or not input_path.strip())):
        return {"error": f"Input path not found: {input_path}"}

    def _ok_payload(res: str, jid: int) -> dict:
        return {"status": res, "job_id": jid, "jobs_id": jid}

    if job_type == "scoring":
        if not _scoring_runner:
            return {"error": "Scoring runner not available"}
        if _scoring_runner.is_running:
            return {"error": "Scoring job already running"}
        jid = db.create_job(input_path, phase_code="scoring")
        db.create_job_phases(jid, ["scoring"])
        res = _scoring_runner.start_batch(
            input_path,
            jid,
            skip_existing=not args.get("rescore", False),
        )
        return _ok_payload(res, jid)

    if job_type == "tagging":
        if not _tagging_runner:
            return {"error": "Tagging runner not available"}
        if _tagging_runner.is_running:
            return {"error": "Tagging job already running"}
        jid = db.create_job(input_path, phase_code="keywords")
        db.create_job_phases(jid, ["keywords"])
        custom_keywords = args.get("custom_keywords")
        generate_captions = config.get_config_section("tagging").get("captions_default", True)
        res = _tagging_runner.start_batch(
            input_path,
            jid,
            custom_keywords=custom_keywords,
            overwrite=args.get("overwrite", False),
            generate_captions=generate_captions,
        )
        return _ok_payload(res, jid)

    if job_type == "clustering":
        culling_runner = _selection_runner or _clustering_runner
        if not culling_runner:
            return {"error": "Clustering/selection runner not available (not initialized)"}
        if culling_runner.is_running:
            return {"error": "Clustering job already running"}
        cluster_path = input_path.strip() if input_path and input_path.strip() else None
        store_path = cluster_path or "CLUSTERING"
        jid = db.create_job(store_path, phase_code="culling")
        db.create_job_phases(jid, ["culling"])
        if _selection_runner and culling_runner is _selection_runner:
            res = _selection_runner.start_batch(
                input_path or "",
                job_id=jid,
                force_rescan=args.get("force_rescan", False),
            )
        else:
            res = _clustering_runner.start_batch(
                cluster_path,
                threshold=args.get("threshold"),
                time_gap=args.get("time_gap"),
                force_rescan=args.get("force_rescan", False),
                job_id=jid,
            )
        return _ok_payload(res, jid)

    if job_type == "bird_species":
        if not _bird_species_runner:
            return {"error": "Bird species runner not available"}
        if _bird_species_runner.is_running:
            return {"error": "Bird species job already running"}
        jid = db.create_job(input_path or "BIRD_SPECIES", phase_code="bird_species")
        db.create_job_phases(jid, ["bird_species"])
        res = _bird_species_runner.start_batch(
            input_path,
            job_id=jid,
            threshold=args.get("threshold", 0.1),
            top_k=args.get("top_k", 3),
            overwrite=args.get("overwrite", False),
            candidate_species=args.get("candidate_species"),
        )
        return _ok_payload(res, jid)

    return {"error": f"Unknown job type: {job_type}"}


@mcp.tool(annotations=_RW)
def manage_runners(runner: str, operation: str) -> dict:
    """Request ``stop`` or read ``status`` for an in-process background runner (WebUI / SSE context). Starting jobs is not supported here — use ``run_processing_job`` or the UI."""
    r = (runner or "").strip().lower()
    op = (operation or "").strip().lower()
    if op == "start":
        return {
            "success": False,
            "error": "Starting jobs is not supported via manage_runners; use run_processing_job or the Web UI.",
        }
    if op not in ("stop", "status"):
        return {"success": False, "error": "operation must be 'stop' or 'status' (or 'start', which is rejected)."}

    mapping: dict[str, Any] = {
        "scoring": _scoring_runner,
        "tagging": _tagging_runner,
        "clustering": _clustering_runner,
        "selection": _selection_runner,
        "indexing": _indexing_runner,
        "metadata": _metadata_runner,
        "bird_species": _bird_species_runner,
        "maintenance": _maintenance_runner,
    }
    if r not in mapping:
        return {"success": False, "error": f"Unknown runner '{runner}'.", "known": sorted(mapping.keys())}

    obj = mapping[r]
    if obj is None:
        return {"success": False, "error": f"Runner '{r}' is not wired in this process."}

    if op == "status":
        is_running = bool(getattr(obj, "is_running", False))
        msg = str(getattr(obj, "status_message", "") or "")[:500]
        return {"success": True, "runner": r, "is_running": is_running, "status_message": msg}

    stop_fn = getattr(obj, "stop", None)
    if not callable(stop_fn):
        return {"success": False, "error": f"Runner '{r}' has no stop() method."}
    try:
        stop_fn()
        return {"success": True, "runner": r, "message": "stop() invoked"}
    except Exception as e:
        return {"success": False, "runner": r, "error": str(e)}


# ============================================================
# Configuration & Logs Tools
# ============================================================

@mcp.tool(annotations=_RO)
def get_config() -> dict:
    """Get current application configuration (config.json merged with environment.json). Sensitive keys are redacted."""
    from modules.redact_sensitive import redact_json_obj

    cfg = redact_json_obj(config.load_config())
    if not isinstance(cfg, dict):
        cfg = {"_raw": cfg}
    cfg = dict(cfg)
    cfg["_mcp_status"] = {
        "db_available": _db_available,
        "last_db_error": _last_db_error,
        "version": "1.0.1-resilient",
    }
    return cfg


@mcp.tool(annotations=_RO)
def validate_config() -> dict:
    """Validate config structure and referenced paths; optionally ping the database when available."""
    out = dict(config.validate_config())
    out["config_path"] = str(config.CONFIG_FILE)
    out["environment_path"] = str(config.ENVIRONMENT_FILE)
    if _db_available:
        try:
            with db.connection() as conn:
                c = conn.cursor()
                c.execute("SELECT 1")
                c.fetchone()
            out["database_reachable"] = True
        except Exception as e:
            out["database_reachable"] = False
            out["database_error"] = str(e)
    else:
        out["database_reachable"] = None
        out["database_note"] = "Database not initialized; structural checks only."
    return out


@mcp.tool(annotations=_RW)
def set_config_value(key: str, value: Any) -> dict:
    """Set a configuration value in config.json."""
    try:
        config.save_config_value(key, value)
        return {"success": True, "key": key, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool(annotations=_RO)
def read_debug_log(lines: int = 100) -> dict:
    """Read recent entries from debug.log (JSON lines); falls back to raw line in entries."""
    from modules.ui import log_views

    n = log_views.clamp_tail_lines(lines)
    path = log_views.resolve_debug_log_path()
    tail = log_views.read_log_tail(path, n)
    if not tail["exists"]:
        return {"error": "Debug log file not found", "path": tail["path"]}
    if tail.get("error"):
        return {"error": tail["error"], "path": tail["path"]}

    entries = []
    for line in tail["lines"]:
        try:
            entries.append(json.loads(line.strip()))
        except (json.JSONDecodeError, ValueError):
            entries.append({"raw": line.strip()})

    return {
        "path": tail["path"],
        "total_lines": tail["total_lines"],
        "returned_lines": len(entries),
        "entries": entries,
    }


@mcp.tool(annotations=_RO)
def get_server_log_tail(sources: str = "all", lines: int = 100) -> dict:
    """Tail webui.log and/or debug.log (same paths and caps as GET /api/status/log-tails)."""
    from modules.ui import log_views

    try:
        return log_views.build_log_tails_payload(sources, lines)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool(annotations=_RO)
def search_logs(
    pattern: str,
    sources: str = "all",
    context_lines: int = 2,
    max_lines_scan: int = 25000,
    max_matches_per_file: int = 40,
    case_insensitive: bool = True,
) -> dict:
    """Search the tail of ``webui.log`` / ``debug.log`` for a regex ``pattern``; returns matching lines with optional context."""
    from modules.ui import log_views

    spec = (sources or "all").strip().lower()
    if spec in ("all", "*", ""):
        file_ids = ("webui", "debug")
    elif spec in ("webui", "debug"):
        file_ids = (spec,)
    else:
        return {"error": "sources must be 'all', 'webui', or 'debug'"}

    ctx = max(0, min(int(context_lines), 50))
    max_scan = max(100, min(int(max_lines_scan), 100_000))
    cap = max(1, min(int(max_matches_per_file), 200))
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return {"error": f"invalid_regex: {e}"}

    out: dict[str, Any] = {"pattern": pattern, "matches": []}

    for sid in file_ids:
        path = log_views.resolve_webui_log_path() if sid == "webui" else log_views.resolve_debug_log_path()
        tail = log_views.read_log_tail(path, max_scan)
        lines = tail.get("lines") or []
        total = tail.get("total_lines")
        if not lines:
            continue
        base = int(total or len(lines)) - len(lines)
        n_matches = 0
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            lo = max(0, i - ctx)
            hi = min(len(lines), i + ctx + 1)
            out["matches"].append(
                {
                    "source": sid,
                    "path": tail.get("path"),
                    "line_number": base + i + 1,
                    "line": line[:4000],
                    "context_before": lines[lo:i],
                    "context_after": lines[i + 1 : hi],
                }
            )
            n_matches += 1
            if n_matches >= cap:
                break

    return out


# ============================================================
# Advanced Search Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def search_similar_images(
    example_path: Optional[str] = None,
    example_image_id: Optional[int] = None,
    limit: int = 20,
    folder_path: Optional[str] = None,
    min_similarity: Optional[float] = None,
    embedding_space: Optional[str] = None,
) -> dict:
    """Find images visually similar to an example image using stored embeddings and cosine similarity.

    Provide either ``example_path`` or ``example_image_id``. By default this uses
    the MobileNetV2 ``mobilenet_v2_imagenet_gap`` space. Pass ``embedding_space``
    (e.g. ``clip_vit_b32_image``, ``bioclip_2_image``, ``blip_vit_b16_image``) to
    search a different per-dim table; non-default spaces are Postgres-only.
    """
    from modules import similar_search
    return similar_search.search_similar_images(
        example_path=example_path,
        example_image_id=example_image_id,
        limit=limit,
        folder_path=folder_path,
        min_similarity=min_similarity,
        embedding_space=embedding_space,
    )


@mcp.tool(annotations=_RO)
@_require_db
def search_images_by_text(
    query: str,
    limit: int = 20,
    folder_path: Optional[str] = None,
    min_similarity: Optional[float] = None,
) -> dict:
    """Search images by free-text query using CLIP text-to-image similarity.

    Encodes the query with the CLIP ViT-B/32 text tower and searches against
    stored ``clip_vit_b32_image`` embeddings via pgvector cosine distance.
    Requires PostgreSQL and images with CLIP embeddings (produced during tagging).

    Examples: ``"sunset over mountains"``, ``"a bird on a branch"``,
    ``"portrait with dramatic lighting"``.
    """
    from modules import similar_search
    result = similar_search.search_by_text(
        query=query,
        limit=limit,
        folder_path=folder_path,
        min_similarity=min_similarity,
    )
    if isinstance(result, dict) and "error" in result:
        return result
    return {
        "query": query,
        "results": result,
        "count": len(result),
        "embedding_space": "clip_vit_b32_image",
    }


@mcp.tool(annotations=_RO)
@_require_db
def find_near_duplicates(
    threshold: Optional[float] = None,
    folder_path: Optional[str] = None,
    limit: Optional[int] = None
) -> dict:
    """Detect visually duplicate or near-duplicate images even when file hashes differ. Returns a list of near-duplicate image pairs."""
    from modules import similar_search
    return similar_search.find_near_duplicates(
        threshold=threshold,
        folder_path=folder_path,
        limit=limit
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False) if MCP_AVAILABLE else None)
@_require_db
def propagate_tags(
    folder_path: Optional[str] = None,
    dry_run: bool = True,
    k: Optional[int] = None,
    min_similarity: Optional[float] = None,
    min_keyword_confidence: Optional[float] = None
) -> dict:
    """Propagate keywords from tagged images to untagged neighbors using embedding cosine similarity. Uses weighted voting with configurable thresholds. Defaults to dry_run=true for safe preview."""
    from modules.tagging import propagate_tags as _propagate_tags
    return _propagate_tags(
        folder_path=folder_path,
        dry_run=dry_run,
        k=k,
        min_similarity=min_similarity,
        min_keyword_confidence=min_keyword_confidence,
    )


@mcp.tool(annotations=_RO)
@_require_db
def find_outliers(
    folder_path: str = "",
    z_threshold: Optional[float] = None,
    k: Optional[int] = None,
    limit: Optional[int] = None
) -> dict:
    """Identify visually atypical images in a folder using embedding similarity analysis. Computes top-K mean cosine similarity per image and flags statistical outliers via z-score. Returns flagged images with explainability (nearest neighbors, folder stats)."""
    from modules import similar_search
    return similar_search.find_outliers(
        folder_path=folder_path,
        z_threshold=z_threshold,
        k=k,
        limit=limit,
    )


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


def create_mcp_sse_app(mount_path: str = "/mcp"):
    """
    Create a Starlette ASGI app that exposes MCP over SSE, to be mounted in FastAPI.
    Cursor connects via url e.g. http://localhost:7860/mcp/sse
    """
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK required. Install: pip install mcp")

    prepare_mcp_embedded()
    app = mcp.sse_app(mount_path=mount_path)
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

    return app


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
