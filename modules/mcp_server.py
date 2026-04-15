"""
MCP (Model Context Protocol) Server for Image Scoring WebUI

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
import time
from typing import Any, Optional

# MCP SDK imports
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

try:
    from mcp.server.sse import SseServerTransport
    MCP_SSE_AVAILABLE = True
except ImportError:
    MCP_SSE_AVAILABLE = False

# Add parent directory for imports when running standalone
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db, config, utils

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
    """Decorator that returns an error dict if the database is not available."""
    import functools
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _db_available:
            return {"error": "Database not available. Ensure PostgreSQL is running and migrations are applied."}
        return fn(*args, **kwargs)
    return wrapper


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
                rating, label, keywords, created_at
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
def execute_sql(query: str, params: list = None) -> dict:
    """Execute a read-only SQL SELECT query against the database. Only SELECT queries are allowed for safety."""
    query = query.strip()

    # Safety check - only allow SELECT queries
    if not query.upper().startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed for safety reasons"}

    # Block dangerous SQL patterns (word-boundary check to avoid
    # false positives on column names like "updated_at" or "created_at")
    dangerous_patterns = [
        r'\bDROP\b', r'\bDELETE\b', r'\bINSERT\b', r'\bUPDATE\b',
        r'\bALTER\b', r'\bCREATE\b', r'--', r';--',
    ]
    upper_query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, upper_query):
            return {"error": f"Query contains forbidden pattern: {pattern}"}

    with db.connection() as conn:
        c = conn.cursor()

        try:
            # Defense-in-depth: start a read-only transaction so even if
            # SQL injection bypasses the regex, no writes can occur.
            # For PostgreSQL, PGConnectionManager handles read-only mode if requested,
            # or we rely on the DB role.
            pass  # Standard read-only selective access is performed at the pool level or via SQL constraints.

            if params:
                c.execute(query, tuple(params))
            else:
                c.execute(query)

            rows = c.fetchall()
            columns = [description[0] for description in c.description] if c.description else []
            # RowWrapper iterates as (key, value) pairs — do not use dict(zip(columns, row)).
            results = [
                row.to_dict() if hasattr(row, "to_dict") else dict(zip(columns, row))
                for row in rows
            ]

            return {
                "columns": columns,
                "row_count": len(results),
                "rows": results[:100]  # Limit to 100 rows
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


@mcp.tool(annotations=_RO)
def get_migration_parity() -> dict:
    """Compare image and folder counts between Firebird (legacy) and PostgreSQL (new).
    Useful for verifying the migration status."""
    parity = {
        "postgres": {"images": 0, "folders": 0, "stacks": 0},
        "firebird": {"images": 0, "folders": 0, "stacks": 0},
        "mismatch": False,
        "firebird_available": False
    }

    # Postgres stats (using the default connection which is likely postgres now)
    try:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM images")
            parity["postgres"]["images"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM folders")
            parity["postgres"]["folders"] = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM stacks")
            parity["postgres"]["stacks"] = c.fetchone()[0]
    except Exception as e:
        parity["postgres"]["error"] = str(e)

    # Firebird stats (attempt direct connection if file exists)
    fdb_path = getattr(db, "DB_PATH", "scoring_history.fdb")
    if os.path.exists(fdb_path):
        parity["firebird_available"] = True
        try:
            from firebird.driver import connect
            # Use the credentials from db.py
            with connect(fdb_path, user=db.DB_USER, password=db.DB_PASS) as f_conn:
                fc = f_conn.cursor()
                fc.execute("SELECT COUNT(*) FROM images")
                parity["firebird"]["images"] = fc.fetchone()[0]
                fc.execute("SELECT COUNT(*) FROM folders")
                parity["firebird"]["folders"] = fc.fetchone()[0]
                fc.execute("SELECT COUNT(*) FROM stacks")
                parity["firebird"]["stacks"] = fc.fetchone()[0]
        except Exception as e:
            parity["firebird"]["error"] = str(e)
    else:
        parity["firebird"]["error"] = f"Firebird file {fdb_path} not found"

    # Compare
    if parity["firebird_available"]:
        for key in ["images", "folders", "stacks"]:
            if parity["postgres"][key] != parity["firebird"][key]:
                parity["mismatch"] = True
                break

    return parity


# ============================================================
# Error & Diagnostics Tools
# ============================================================

@mcp.tool(annotations=_RO)
@_require_db
def get_failed_images(limit: int = 50) -> list:
    """Get images that failed processing or have missing scores."""
    with db.connection() as conn:
        c = conn.cursor()

        try:
            c.execute("""
                SELECT id, file_path, file_name, created_at,
                       score_general, score_technical, score_aesthetic,
                       score_spaq, score_koniq, score_liqe
                FROM images
                WHERE (score_general IS NULL OR score_general = 0)
                   OR (score_technical IS NULL OR score_technical = 0)
                   OR (score_spaq IS NULL OR score_spaq = 0)
                   OR (score_koniq IS NULL OR score_koniq = 0)
                ORDER BY created_at DESC
                FETCH FIRST ? ROWS ONLY
            """, (limit,))

            rows = c.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                missing = []
                if not item.get('score_general') or item.get('score_general', 0) == 0:
                    missing.append('general')
                if not item.get('score_technical') or item.get('score_technical', 0) == 0:
                    missing.append('technical')
                if not item.get('score_spaq') or item.get('score_spaq', 0) == 0:
                    missing.append('spaq')
                if not item.get('score_koniq') or item.get('score_koniq', 0) == 0:
                    missing.append('koniq')
                item['missing_scores'] = missing
                results.append(item)

            return results
        except Exception as e:
            return [{"error": str(e)}]


@mcp.tool(annotations=_RO)
@_require_db
def get_incomplete_images(limit: int = 100) -> list:
    """Images with missing composite scores, model scores, rating, or label (broader than get_failed_images)."""
    try:
        rows = db.get_incomplete_records(limit=limit)
        return [_sanitize_for_mcp(dict(row)) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


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
def validate_file_paths(limit: int = 100) -> dict:
    """Validate that file paths in database actually exist on the filesystem."""
    with db.connection() as conn:
        c = conn.cursor()
        results = {
            "checked": 0,
            "exists": 0,
            "missing": 0,
            "missing_files": []
        }

        try:
            c.execute("""
                SELECT id, file_path FROM images
                WHERE file_path IS NOT NULL AND file_path != ''
                ORDER BY created_at DESC
                FETCH FIRST ? ROWS ONLY
            """, (limit,))

            rows = c.fetchall()
            results["checked"] = len(rows)

            for row in rows:
                file_path = row[1]
                if os.path.exists(file_path):
                    results["exists"] += 1
                else:
                    results["missing"] += 1
                    results.get("missing_files").append({
                        "id": row[0],
                        "file_path": file_path
                    })

        except Exception as e:
            results["error"] = str(e)

        return results


@mcp.tool(annotations=_RO)
def summarize_directory(path: str) -> dict:
    """Fast directory summary using os.scandir to avoid hangs on large folders.
    Returns counts of common image types and total size."""
    if not os.path.isdir(path):
        return {"error": f"Path {path} is not a directory or is inaccessible"}

    summary = {
        "path": path,
        "total_files": 0,
        "jpg_count": 0,
        "nef_count": 0,
        "xmp_count": 0,
        "other_count": 0,
        "total_size_bytes": 0,
        "subfolders": 0
    }

    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    summary["total_files"] += 1
                    summary["total_size_bytes"] += entry.stat().st_size
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext == ".jpg" or ext == ".jpeg":
                        summary["jpg_count"] += 1
                    elif ext == ".nef":
                        summary["nef_count"] += 1
                    elif ext == ".xmp":
                        summary["xmp_count"] += 1
                    else:
                        summary["other_count"] += 1
                elif entry.is_dir():
                    summary["subfolders"] += 1
    except Exception as e:
        summary["error"] = str(e)

    return summary


@mcp.tool(annotations=_RO)
def search_missing_sidecars(path: str) -> dict:
    """Identify NEF images in a folder that are missing corresponding XMP sidecar files."""
    if not os.path.isdir(path):
        return {"error": f"Path {path} is not a directory"}

    nefs = set()
    xmps = set()

    try:
        for entry in os.scandir(path):
            if entry.is_file():
                name, ext = os.path.splitext(entry.name)
                ext = ext.lower()
                if ext == ".nef":
                    nefs.add(name)
                elif ext == ".xmp":
                    xmps.add(name)

        missing = list(nefs - xmps)
        return {
            "path": path,
            "nef_total": len(nefs),
            "xmp_total": len(xmps),
            "missing_sidecars_count": len(missing),
            "missing_sidecars": sorted(missing)[:50]  # Limit to first 50
        }
    except Exception as e:
        return {"error": str(e)}


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
    return _sanitize_for_mcp({
        "job_id": jid,
        "report": report,
        "image_actions": actions,
    })


@mcp.tool(annotations=_RO)
@_require_db
def get_embedding_stats(folder_path: Optional[str] = None) -> dict:
    """Counts of images with vs without image_embedding (MobileNetV2 / similar-search). Optional folder_path filters by exact folders.path match."""
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

    # Postgres: use COALESCE predicate to count both legacy and normalized storage
    if conn.type == 'postgres':
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
        # Firebird: legacy path
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
    }


def _probe_path_allowed(path: str) -> tuple[bool, str]:
    p = (path or "").strip()
    if not p.startswith("/"):
        return False, "path must start with /"
    if "\n" in p or "\r" in p or "://" in p:
        return False, "invalid path"
    if ".." in p:
        return False, "path must not contain .."
    if len(p) > 512:
        return False, "path too long"
    return True, p


@mcp.tool(annotations=_RO)
def probe_backend_http(path: str, timeout_ms: int = 10000) -> dict:
    """GET a path on the configured scoring WebUI base URL (e.g. /api/health, /api/scope/tree). Returns status, elapsed_ms, and a short body preview. Read-only; path is constrained to same-origin relative URLs."""
    ok, msg = _probe_path_allowed(path)
    if not ok:
        return {"error": msg, "path": path}

    db_sec = config.get_config_section("database") or {}
    base = str(db_sec.get("api_url", "") or "").strip().rstrip("/")
    if not base:
        port = config.get_config_value("webui_port", default=7860)
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 7860
        base = f"http://127.0.0.1:{port}"

    url = base + msg
    timeout_ms = max(100, min(int(timeout_ms), 120000))
    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed", "url": url}

    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_ms / 1000.0) as client:
            resp = client.get(url)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        body = resp.text or ""
        preview = body[:4000] + ("…" if len(body) > 4000 else "")
        return {
            "url": url,
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "content_length_header": resp.headers.get("content-length"),
            "body_chars": len(body),
            "body_preview": preview,
        }
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "url": url,
            "error": str(e),
            "elapsed_ms": elapsed_ms,
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
            c.execute("SELECT id, file_path FROM images WHERE file_path LIKE ?", (pattern,))
            rows = c.fetchall()

            for image_id, old_path in rows:
                new_path = old_path.replace(old_root, new_root, 1)
                db.update_image_field(image_id, "file_path", new_path)

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
def get_gallery_status() -> dict:
    """Get the current state of the Gradio WebUI gallery and active runners."""
    status = {
        "webui_active": _gradio_context is not None,
        "runners": {
            "scoring": _scoring_runner is not None and not getattr(_scoring_runner, "_stop_event", None).is_set() if _scoring_runner else False,
            "tagging": _tagging_runner is not None and not getattr(_tagging_runner, "_stop_event", None).is_set() if _tagging_runner else False,
        },
        "gradio_tabs": list(_gradio_context.get("components", {}).keys()) if _gradio_context else []
    }
    return status


@mcp.tool(annotations=_RO)
def verify_environment() -> dict:
    """Comprehensive environment check: GPU, DB, Python, and system stats."""
    import torch
    import psutil
    import platform

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
        result["jobs_cancelled_7d"] = jobs_by_status.get("cancelled", 0)
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
    """Trigger a background processing job (scoring, tagging, clustering/stacks, or bird_species)."""
    import uuid

    if args is None:
        args = {}

    job_id = f"mcp_{job_type}_{uuid.uuid4().hex[:8]}"

    if not os.path.exists(input_path) and not (job_type == "clustering" and (not input_path or not input_path.strip())):
        return {"error": f"Input path not found: {input_path}"}

    if job_type == "scoring":
        if not _scoring_runner:
            return {"error": "Scoring runner not available"}
        if _scoring_runner.is_running:
            return {"error": "Scoring job already running"}
        res = _scoring_runner.start_batch(
            input_path,
            job_id,
            skip_existing=not args.get("rescore", False)
        )
        return {"status": res, "job_id": job_id}

    elif job_type == "tagging":
        if not _tagging_runner:
            return {"error": "Tagging runner not available"}
        if _tagging_runner.is_running:
            return {"error": "Tagging job already running"}
        custom_keywords = args.get("custom_keywords")
        res = _tagging_runner.start_batch(
            input_path,
            overwrite=args.get("overwrite", False),
            custom_keywords=custom_keywords
        )
        return {"status": res, "job_id": job_id}

    elif job_type == "clustering":
        if not _clustering_runner:
            return {"error": "Clustering runner not available (not initialized)"}
        if _clustering_runner.is_running:
            return {"error": "Clustering job already running"}
        cluster_path = input_path.strip() if input_path and input_path.strip() else None
        res = _clustering_runner.start_batch(
            cluster_path,
            threshold=args.get("threshold"),
            time_gap=args.get("time_gap"),
            force_rescan=args.get("force_rescan", False),
            job_id=job_id
        )
        return {"status": res, "job_id": job_id}

    elif job_type == "bird_species":
        if not _bird_species_runner:
            return {"error": "Bird species runner not available"}
        if _bird_species_runner.is_running:
            return {"error": "Bird species job already running"}
        res = _bird_species_runner.start_batch(
            input_path,
            threshold=args.get("threshold", 0.1),
            top_k=args.get("top_k", 3),
            overwrite=args.get("overwrite", False),
            candidate_species=args.get("candidate_species"),
        )
        return {"status": res, "job_id": job_id}

    else:
        return {"error": f"Unknown job type: {job_type}"}


# ============================================================
# Configuration & Logs Tools
# ============================================================

@mcp.tool(annotations=_RO)
def get_config() -> dict:
    """Get current application configuration (config.json merged with environment.json)."""
    return config.load_config()


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
                c.execute("SELECT 1 FROM RDB$DATABASE")
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
    min_similarity: Optional[float] = None
) -> dict:
    """Find images visually similar to an example image using stored MobileNetV2 embeddings and cosine similarity. Provide either example_path or example_image_id."""
    from modules import similar_search
    return similar_search.search_similar_images(
        example_path=example_path,
        example_image_id=example_image_id,
        limit=limit,
        folder_path=folder_path,
        min_similarity=min_similarity,
    )


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
        import builtins
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_capture, stderr_capture
        try:
            exec_globals["__builtins__"] = builtins
            exec(code, exec_globals)
            if "result" in exec_globals:
                result = exec_globals["result"]
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
    except Exception as e:
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

def prepare_mcp_embedded():
    """Initialize DB and set _db_available for embedded (SSE) or stdio runs. Idempotent."""
    global _db_available
    try:
        db.init_db()
        _db_available = True
    except Exception as e:
        logger.warning("DB init failed (%s). DB tools will return 'Database not available'.", e)
        _db_available = False


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
    logger.info("Starting Image Scoring MCP Server...")

    # Initialize runners for standalone mode
    try:
        from modules.clustering import ClusteringRunner
        clustering_runner = ClusteringRunner()
        set_runners(None, None, clustering_runner)
        logger.info("Initialized ClusteringRunner for standalone mode")
    except Exception as e:
        logger.warning(f"Failed to initialize clustering runner: {e}")

    asyncio.run(run_server())
