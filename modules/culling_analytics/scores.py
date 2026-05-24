"""Model score distribution summaries."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.culling_analytics._common import (
    histogram,
    images_folder_filter,
    safe_float,
    summarize_numeric,
)

AGGREGATE_SCORE_FIELDS = (
    "score_general",
    "score_technical",
    "score_aesthetic",
)

# Per-model scores live in ``image_model_scores`` (migration 0016 → drop
# migration). They are reported under the legacy ``score_<name>`` field names
# for stable consumer compatibility but sourced from the model row.
PER_MODEL_LEGACY_FIELDS: tuple[tuple[str, str], ...] = (
    ("score_spaq", "spaq"),
    ("score_ava", "ava"),
    ("score_koniq", "koniq"),
    ("score_paq2piq", "paq2piq"),
    ("score_liqe", "liqe"),
)

# Preserved for backwards-compatible callers that iterate field names.
SCORE_FIELDS = AGGREGATE_SCORE_FIELDS + tuple(name for name, _ in PER_MODEL_LEGACY_FIELDS)


def compute_library_scores(
    folder_id: int | None,
    *,
    per_stack_limit: int = 50,
    per_stack_offset: int = 0,
) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id)
    conn = db.get_connector()
    by_field: dict[str, Any] = {}
    total_images = max(1, _image_count(conn, folder_clause, params))

    for field in AGGREGATE_SCORE_FIELDS:
        rows = conn.query(
            f"""
            SELECT {field} AS v
            FROM images i
            WHERE {field} IS NOT NULL{folder_clause}
            """,
            tuple(params),
        )
        vals = [safe_float(r["v"]) for r in rows]
        vals = [v for v in vals if v is not None]
        summary = summarize_numeric(vals)
        summary["histogram"] = histogram(vals)
        summary["coverage_pct"] = round(100.0 * summary["count"] / total_images, 2)
        by_field[field] = summary

    for field, model_name in PER_MODEL_LEGACY_FIELDS:
        rows = conn.query(
            f"""
            SELECT COALESCE(ims.normalized, ims.raw_score) AS v
            FROM image_model_scores ims
            JOIN images i ON i.id = ims.image_id
            WHERE ims.model_name = ?
              AND ims.status = 'success'
              AND ims.is_shadow = FALSE
              AND COALESCE(ims.normalized, ims.raw_score) IS NOT NULL{folder_clause}
            """,
            (model_name, *params),
        )
        vals = [safe_float(r["v"]) for r in rows]
        vals = [v for v in vals if v is not None]
        summary = summarize_numeric(vals)
        summary["histogram"] = histogram(vals)
        summary["coverage_pct"] = round(100.0 * summary["count"] / total_images, 2)
        by_field[field] = summary

    stack_summaries = _per_stack_score_summaries(
        conn, folder_clause, params, per_stack_limit, per_stack_offset
    )
    return {"by_field": by_field, "per_stack_summary": stack_summaries}


def _image_count(conn, folder_clause: str, params: list) -> int:
    row = conn.query_one(f"SELECT COUNT(*) AS n FROM images i WHERE 1=1{folder_clause}", tuple(params))
    return int((row or {}).get("n") or 0)


def _per_stack_score_summaries(
    conn,
    folder_clause: str,
    params: list,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    folder_clause_sc = folder_clause.replace("i.", "sc.") if folder_clause else ""
    rows = conn.query(
        f"""
        SELECT
            sc.stack_id,
            sc.image_count AS stack_size,
            sc.min_score_general AS min_sg,
            sc.max_score_general AS max_sg,
            (sc.max_score_general - sc.min_score_general) AS spread
        FROM stack_cache sc
        WHERE sc.stack_id IS NOT NULL
          AND sc.image_count > 0{folder_clause_sc}
        ORDER BY sc.image_count DESC, sc.stack_id
        LIMIT ? OFFSET ?
        """,
        tuple(params) + (limit, offset),
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        stack_id = int(r["stack_id"])
        mn, mx = safe_float(r.get("min_sg")), safe_float(r.get("max_sg"))
        spread = safe_float(r.get("spread"))
        if spread is None and mn is not None and mx is not None:
            spread = mx - mn

        top_row = conn.query_one(
            """
            SELECT score_general, pick_status
            FROM images
            WHERE stack_id = ? AND score_general IS NOT NULL
            ORDER BY score_general DESC, id
            LIMIT 1
            """,
            (stack_id,),
        )
        second_row = conn.query_one(
            """
            SELECT score_general
            FROM images
            WHERE stack_id = ? AND score_general IS NOT NULL
            ORDER BY score_general DESC, id
            OFFSET 1 ROWS FETCH NEXT 1 ROWS ONLY
            """,
            (stack_id,),
        )
        top = safe_float(top_row.get("score_general")) if top_row else mx
        second = safe_float(second_row.get("score_general")) if second_row else None
        gap = (top - second) if top is not None and second is not None else None
        top_ps = int(top_row.get("pick_status") or 0) if top_row else 0

        std_row = conn.query_one(
            "SELECT STDDEV_POP(score_general) AS std_sg FROM images WHERE stack_id = ?",
            (stack_id,),
        )
        std_sg = safe_float((std_row or {}).get("std_sg"))
        mean_sg = (mn + mx) / 2.0 if mn is not None and mx is not None else None
        cv = (std_sg / mean_sg) if std_sg and mean_sg and mean_sg > 0 else None

        out.append({
            "stack_id": stack_id,
            "stack_size": int(r.get("stack_size") or 0),
            "top_score": top,
            "second_score": second,
            "score_gap_top_two": gap,
            "score_spread": spread,
            "score_std": std_sg,
            "score_coefficient_of_variation": cv,
            "pick_agrees_with_top_score": top_ps == 1,
        })
    return out


def compute_stack_scores(stack_id: int) -> dict[str, Any]:
    conn = db.get_connector()
    by_field: dict[str, Any] = {}
    for field in AGGREGATE_SCORE_FIELDS:
        rows = conn.query(
            f"SELECT {field} AS v FROM images WHERE stack_id = ? AND {field} IS NOT NULL",
            (stack_id,),
        )
        vals = [safe_float(r["v"]) for r in rows if safe_float(r["v"]) is not None]
        summary = summarize_numeric(vals)
        summary["histogram"] = histogram(vals)
        by_field[field] = summary

    for field, model_name in PER_MODEL_LEGACY_FIELDS:
        rows = conn.query(
            """
            SELECT COALESCE(ims.normalized, ims.raw_score) AS v
            FROM image_model_scores ims
            JOIN images i ON i.id = ims.image_id
            WHERE i.stack_id = ?
              AND ims.model_name = ?
              AND ims.status = 'success'
              AND ims.is_shadow = FALSE
              AND COALESCE(ims.normalized, ims.raw_score) IS NOT NULL
            """,
            (stack_id, model_name),
        )
        vals = [safe_float(r["v"]) for r in rows if safe_float(r["v"]) is not None]
        summary = summarize_numeric(vals)
        summary["histogram"] = histogram(vals)
        by_field[field] = summary

    ranked = conn.query(
        """
        SELECT id, score_general, pick_status
        FROM images
        WHERE stack_id = ?
        ORDER BY score_general DESC NULLS LAST, id
        LIMIT 5
        """,
        (stack_id,),
    )
    top = safe_float(ranked[0]["score_general"]) if ranked else None
    second = safe_float(ranked[1]["score_general"]) if len(ranked) > 1 else None
    gap = (top - second) if top is not None and second is not None else None
    top_ps = int(ranked[0]["pick_status"] or 0) if ranked else 0

    return {
        "by_field": by_field,
        "top_score": top,
        "second_score": second,
        "score_gap_top_two": gap,
        "pick_agrees_with_top_score": top_ps == 1,
        "ranked_top_images": [
            {
                "image_id": int(r["id"]),
                "score_general": safe_float(r.get("score_general")),
                "pick_status": int(r.get("pick_status") or 0),
            }
            for r in ranked
        ],
    }
