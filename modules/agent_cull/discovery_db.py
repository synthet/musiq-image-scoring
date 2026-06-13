"""Postgres-backed discovery for agent cull review units."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.discovery import ReviewUnit, discover_eligible_units_from_stack_rows, default_is_usable
from modules.culling_analytics._common import images_folder_filter, require_postgres, resolve_folder_id


def _stack_member_query(folder_id: int | None) -> tuple[str, list[Any]]:
    folder_sql, folder_params = images_folder_filter(folder_id)
    sql = f"""
        SELECT
            i.id,
            i.stack_id,
            i.sub_stack_id,
            i.pick_status,
            i.cull_decision,
            i.file_path,
            i.file_name,
            i.file_type,
            i.thumbnail_path,
            i.thumbnail_path_win,
            i.score_general,
            i.score_technical,
            i.score_aesthetic,
            i.score,
            COALESCE(
                (SELECT string_agg(kd.keyword_display, ', ' ORDER BY kd.keyword_display)
                 FROM image_keywords ik
                 JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                 WHERE ik.image_id = i.id),
                i.keywords,
                ''
            ) AS keywords
        FROM images i
        WHERE i.stack_id IS NOT NULL
        {folder_sql}
        ORDER BY i.stack_id, i.sub_stack_id NULLS FIRST, i.id
    """
    return sql, folder_params


def _leaf_stats(rows: list[dict[str, Any]]) -> tuple[int, int]:
    substack_ids = {r.get("sub_stack_id") for r in rows if r.get("sub_stack_id") is not None}
    leaf_count = len(substack_ids)
    with_sub = sum(1 for r in rows if r.get("sub_stack_id") is not None)
    return leaf_count, with_sub


def discover_eligible_units(
    cfg: AgentCullConfig,
    *,
    folder_path: str | None = None,
    folder_id: int | None = None,
    stack_id: int | None = None,
    sub_stack_id: int | None = None,
    limit: int = 50,
) -> list[ReviewUnit]:
    require_postgres()
    fid, _ = resolve_folder_id(folder_path, folder_id)
    sql, params = _stack_member_query(fid)
    if stack_id is not None:
        sql = sql.replace("ORDER BY", " AND i.stack_id = ? ORDER BY")
        params = list(params) + [int(stack_id)]
    rows = db.get_connector().query(sql, tuple(params)) or []

    by_stack: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        sid = int(row["stack_id"])
        by_stack.setdefault(sid, []).append(dict(row))

    units: list[ReviewUnit] = []
    for sid, stack_rows in sorted(by_stack.items()):
        if sub_stack_id is not None:
            stack_rows = [r for r in stack_rows if int(r.get("sub_stack_id") or 0) == int(sub_stack_id)]
            if not stack_rows:
                continue
        leaf_count, with_sub = _leaf_stats(stack_rows)
        found = discover_eligible_units_from_stack_rows(
            sid,
            stack_rows,
            cfg,
            leaf_count=leaf_count,
            images_with_substack=with_sub,
            is_usable_fn=default_is_usable,
        )
        for unit in found:
            if sub_stack_id is not None and unit.sub_stack_id != int(sub_stack_id):
                continue
            units.append(unit)
            if len(units) >= limit:
                return units
    return units


def load_unit_rows(unit: ReviewUnit, folder_id: int | None = None) -> dict[int, dict[str, Any]]:
    require_postgres()
    folder_sql, folder_params = images_folder_filter(folder_id, alias="i")
    if unit.sub_stack_id is None:
        sub_sql = " AND i.sub_stack_id IS NULL"
        sub_params: list[Any] = []
    else:
        sub_sql = " AND i.sub_stack_id = ?"
        sub_params = [unit.sub_stack_id]
    sql = f"""
        SELECT
            i.id, i.pick_status, i.cull_decision, i.file_path, i.file_name, i.file_type,
            i.thumbnail_path, i.thumbnail_path_win,
            i.score_general, i.score_technical, i.score_aesthetic, i.score,
            COALESCE(
                (SELECT string_agg(kd.keyword_display, ', ' ORDER BY kd.keyword_display)
                 FROM image_keywords ik
                 JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                 WHERE ik.image_id = i.id),
                i.keywords,
                ''
            ) AS keywords
        FROM images i
        WHERE i.stack_id = ?
        {sub_sql}
        {folder_sql}
    """
    params: list[Any] = [unit.stack_id, *sub_params, *folder_params]
    rows = db.get_connector().query(sql, tuple(params)) or []
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        rec = dict(row)
        rec["usable"] = default_is_usable(rec)
        out[int(rec["id"])] = rec
    return out
