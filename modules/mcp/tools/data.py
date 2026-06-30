"""MCP tool implementations — data (extracted from modules.mcp_server)."""

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
                    AVG(score_aesthetic) as avg_aesthetic
                FROM images
                WHERE score_general IS NOT NULL
            """)
            row = c.fetchone()
            avg_per_model: dict[str, float] = {}
            try:
                c.execute(
                    "SELECT model_name, AVG(COALESCE(normalized, raw_score)) AS avg_v "
                    "FROM image_model_scores "
                    "WHERE model_name IN ('spaq', 'koniq', 'liqe') "
                    "AND is_shadow = FALSE AND status = 'success' "
                    "GROUP BY model_name"
                )
                for m_row in c.fetchall():
                    name = m_row[0]
                    val = m_row[1]
                    avg_per_model[name] = round(float(val), 4) if val is not None else 0.0
            except Exception:
                avg_per_model = {}
            stats["average_scores"] = {
                "general": round(row[0] or 0, 4),
                "technical": round(row[1] or 0, 4),
                "aesthetic": round(row[2] or 0, 4),
                "spaq": avg_per_model.get("spaq", 0.0),
                "koniq": avg_per_model.get("koniq", 0.0),
                "liqe": avg_per_model.get("liqe", 0.0),
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

            try:
                parity = db.get_scores_json_parity_report()
                if parity and "error" not in parity:
                    stats["scores_json_parity"] = parity
            except Exception:
                pass

        except Exception as e:
            stats["error"] = str(e)

        return stats


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

        query = f"""
            SELECT
                i.id, i.file_path, i.file_name, i.file_type,
                i.score_general, i.score_technical, i.score_aesthetic,
                ims.score_spaq, ims.score_koniq, ims.score_liqe,
                i.rating, i.label, i.keywords, i.image_hash, i.created_at
            FROM images i
            LEFT JOIN ({ts.IMS_OVERLAY_SUBQUERY}) ims ON ims.image_id = i.id
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


def get_image_details(file_path: str) -> dict:
    """Get full details for a specific image by file path."""
    return db.get_image_details(file_path)


def search_images_by_hash(image_hash: str, hash_version: Optional[int] = None) -> dict:
    """Find an image by content hash (image_hash column, typically SHA-256). Returns file_paths when found."""
    h = (image_hash or "").strip()
    if not h:
        return {"error": "image_hash is required"}
    row = db.get_image_by_hash(h, hash_version=hash_version)
    if not row:
        return {"found": False, "image": None}
    return {"found": True, "image": ts.sanitize_for_mcp(row)}


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

    return ts.sanitize_for_mcp(
        {
            "database_engine": "postgres",
            "table_count": len(out_tables),
            "tables": out_tables,
            "truncated_tables": truncated_tables,
            "table_name_prefix": prefix or None,
        }
    )


def execute_sql(query: str, params: list = None) -> dict:
    """Execute a read-only SQL SELECT (or WITH … SELECT) query. Uses the same ``?`` placeholder dialect as the app; translated on PostgreSQL. Discover tables/columns with ``get_db_schema`` first."""
    normalized = ts.strip_sql_comments_for_mcp(query)
    if not normalized:
        return {"error": "Empty query"}

    if not ts.is_mcp_read_only_sql(normalized):
        return {"error": "Only read-only SELECT queries are allowed (must start with SELECT or WITH after comments)."}

    ok_stmt, stmt_err = ts.mcp_sql_single_statement(normalized)
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
            results = [ts.sanitize_for_mcp(dict(r)) for r in rows_raw[:100]]
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
                ts.sanitize_for_mcp(row.to_dict() if hasattr(row, "to_dict") else dict(zip(columns, row)))
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

