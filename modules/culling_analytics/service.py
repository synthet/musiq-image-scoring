"""Orchestration for culling / stack analytics API."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.culling_analytics import (
    composite,
    embeddings,
    exposure,
    flags,
    gps,
    keywords,
    labels,
    scores,
    stack_size,
)
from modules.culling_analytics._common import require_postgres, resolve_folder_id, utc_now_iso


def get_library_analytics(
    *,
    folder_path: str | None = None,
    folder_id: int | None = None,
    per_stack_limit: int = 50,
    per_stack_offset: int = 0,
) -> dict[str, Any]:
    require_postgres()
    fid, fpath = resolve_folder_id(folder_path, folder_id)
    if folder_path and fid is None:
        return {
            "scope": "library",
            "error": "folder_not_found",
            "folder_path": folder_path,
            "generated_at": utc_now_iso(),
        }

    warnings: list[str] = []
    ss = stack_size.compute_stack_size_stats(fid)
    fl = flags.compute_library_flags(fid)
    sc = scores.compute_library_scores(fid, per_stack_limit=per_stack_limit, per_stack_offset=per_stack_offset)
    ex = exposure.compute_library_exposure(fid)
    lb = labels.compute_library_labels(fid)
    gp = gps.compute_library_gps(fid)
    kw = keywords.compute_library_keywords(fid)
    em = embeddings.compute_library_embeddings(fid)

    if fl.get("pick_status_cull_decision_disagree", 0) > 0:
        warnings.append(f"pick_status_cull_decision_disagree:{fl['pick_status_cull_decision_disagree']}")

    comp = composite.build_composite(
        flags=fl,
        stack_size=ss,
        embeddings=em,
        exposure=ex,
    )

    return {
        "scope": "library",
        "folder_id": fid,
        "folder_path": fpath,
        "generated_at": utc_now_iso(),
        "stack_size": ss,
        "flags": fl,
        "scores": sc,
        "exposure": ex,
        "labels": lb,
        "gps": gp,
        "keywords": kw,
        "embeddings": em,
        "composite": comp,
        "warnings": warnings,
    }


def get_session_analytics(session_id: int) -> dict[str, Any]:
    require_postgres()
    row = db.get_connector().query_one("SELECT id, folder_path, status FROM culling_sessions WHERE id = ?", (session_id,))
    if not row:
        return {"scope": "session", "error": "session_not_found", "session_id": session_id}

    fl = flags.compute_session_flags(session_id)
    try:
        base_stats = db.get_session_stats(session_id)
    except AttributeError:
        base_stats = {}

    return {
        "scope": "session",
        "session_id": session_id,
        "folder_path": row.get("folder_path"),
        "session_status": row.get("status"),
        "generated_at": utc_now_iso(),
        "session_counters": base_stats,
        "flags": fl,
        "warnings": [],
    }


def get_stack_analytics(stack_id: int) -> dict[str, Any]:
    require_postgres()
    row = db.get_connector().query_one(
        "SELECT id, name, best_image_id FROM stacks WHERE id = ?",
        (stack_id,),
    )
    if not row:
        return {"scope": "stack", "error": "stack_not_found", "stack_id": stack_id}

    sc = scores.compute_stack_scores(stack_id)
    ex = exposure.compute_stack_exposure(stack_id)
    lb = labels.compute_stack_labels(stack_id)
    gp = gps.compute_stack_gps(stack_id)
    kw = keywords.compute_stack_keywords(stack_id)
    em = embeddings.compute_stack_embeddings(stack_id)
    comp = composite.build_stack_composite(
        flags=lb,
        embeddings=em,
        exposure=ex,
        scores=sc,
    )

    warnings: list[str] = []
    if lb.get("mixed_labels"):
        warnings.append("mixed_color_labels")
    if em.get("visually_mixed"):
        warnings.append("visually_mixed_stack")
    for w in ex.get("warnings") or []:
        warnings.append(str(w))

    cnt_row = db.get_connector().query_one(
        "SELECT COUNT(*)::int AS n FROM images WHERE stack_id = ?",
        (stack_id,),
    )
    member_count = int((cnt_row or {}).get("n") or 0)

    return {
        "scope": "stack",
        "stack_id": stack_id,
        "stack_name": row.get("name"),
        "best_image_id": row.get("best_image_id"),
        "member_count": member_count,
        "generated_at": utc_now_iso(),
        "scores": sc,
        "exposure": ex,
        "labels": lb,
        "gps": gp,
        "keywords": kw,
        "embeddings": em,
        "composite": comp,
        "warnings": warnings,
    }
