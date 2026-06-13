"""Pick/reject flag distribution (library pick_status and session culling_picks)."""

from __future__ import annotations

from typing import Any

from modules import db
from modules.culling_analytics._common import images_folder_filter


def compute_library_flags(folder_id: int | None) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id)
    conn = db.get_connector()

    total_row = conn.query_one(
        f"SELECT COUNT(*) AS n FROM images i WHERE 1=1{folder_clause}",
        tuple(params),
    )
    total = int((total_row or {}).get("n") or 0)

    status_rows = conn.query(
        f"""
        SELECT i.pick_status, COUNT(*)::int AS cnt
        FROM images i
        WHERE 1=1{folder_clause}
        GROUP BY i.pick_status
        """,
        tuple(params),
    )
    by_pick_status: dict[str, int] = {"pick": 0, "reject": 0, "neutral": 0}
    for r in status_rows:
        ps = int(r.get("pick_status") or 0)
        cnt = int(r["cnt"])
        if ps == 1:
            by_pick_status["pick"] = cnt
        elif ps == -1:
            by_pick_status["reject"] = cnt
        else:
            by_pick_status["neutral"] = cnt

    cull_rows = conn.query(
        f"""
        SELECT COALESCE(NULLIF(TRIM(i.cull_decision), ''), 'unset') AS cd, COUNT(*)::int AS cnt
        FROM images i
        WHERE 1=1{folder_clause}
        GROUP BY cd
        """,
        tuple(params),
    )
    by_cull_decision = {str(r["cd"]): int(r["cnt"]) for r in cull_rows}

    auto_pick = by_cull_decision.get("pick", 0)
    auto_reject = by_cull_decision.get("reject", 0)
    auto_neutral = by_cull_decision.get("neutral", 0)
    auto_unset = by_cull_decision.get("unset", 0)

    stack_rows = conn.query(
        f"""
        SELECT
            i.stack_id,
            COUNT(*) FILTER (WHERE i.pick_status = 1)::int AS picks,
            COUNT(*) FILTER (WHERE i.pick_status = -1)::int AS rejects,
            COUNT(DISTINCT i.pick_status)::int AS distinct_status
        FROM images i
        WHERE i.stack_id IS NOT NULL{folder_clause}
        GROUP BY i.stack_id
        """,
        tuple(params),
    )

    cull_stack_rows = conn.query(
        f"""
        SELECT
            i.stack_id,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
            COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects
        FROM images i
        WHERE i.stack_id IS NOT NULL{folder_clause}
        GROUP BY i.stack_id
        """,
        tuple(params),
    )
    stacks_one_pick = stacks_multi_pick = stacks_no_pick = stacks_all_reject = stacks_mixed_status = 0
    for r in stack_rows:
        picks = int(r.get("picks") or 0)
        rejects = int(r.get("rejects") or 0)
        distinct = int(r.get("distinct_status") or 0)
        if distinct > 1:
            stacks_mixed_status += 1
        if picks == 1:
            stacks_one_pick += 1
        elif picks > 1:
            stacks_multi_pick += 1
        elif picks == 0 and rejects > 0:
            stacks_all_reject += 1
        elif picks == 0:
            stacks_no_pick += 1

    cull_stacks_one_pick = cull_stacks_multi_pick = cull_stacks_over_cap = 0
    for r in cull_stack_rows:
        picks = int(r.get("picks") or 0)
        if picks == 1:
            cull_stacks_one_pick += 1
        elif picks > 1:
            cull_stacks_multi_pick += 1
        if picks > 20:
            cull_stacks_over_cap += 1

    substack_row = conn.query_one(
        f"""
        WITH leaf_sizes AS (
            SELECT ss.id, COUNT(i.id)::int AS image_count,
                   COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks
            FROM sub_stacks ss
            JOIN images i ON i.sub_stack_id = ss.id
            WHERE 1=1{folder_clause}
            GROUP BY ss.id
        )
        SELECT
            COUNT(*)::int AS total_substacks,
            COUNT(*) FILTER (WHERE image_count = 1)::int AS singleton_leaves,
            COUNT(*) FILTER (WHERE picks > 3)::int AS substacks_picks_over_m3,
            COUNT(*) FILTER (WHERE image_count > 50)::int AS giant_leaves
        FROM leaf_sizes
        """,
        tuple(params),
    )
    total_substacks = int((substack_row or {}).get("total_substacks") or 0)
    singleton_leaves = int((substack_row or {}).get("singleton_leaves") or 0)
    substacks_picks_over_m3 = int((substack_row or {}).get("substacks_picks_over_m3") or 0)
    giant_leaves = int((substack_row or {}).get("giant_leaves") or 0)
    singleton_leaf_pct = (
        round(100.0 * singleton_leaves / total_substacks, 1) if total_substacks else 0.0
    )

    disagree = conn.query_one(
        f"""
        SELECT COUNT(*)::int AS n
        FROM images i
        WHERE 1=1{folder_clause}
          AND (
            (i.pick_status = 1 AND LOWER(TRIM(COALESCE(i.cull_decision, ''))) = 'reject')
            OR (i.pick_status = -1 AND LOWER(TRIM(COALESCE(i.cull_decision, ''))) = 'pick')
          )
        """,
        tuple(params),
    )
    pick_reject_disagree = int((disagree or {}).get("n") or 0)

    def _pct(n: int) -> float:
        return round(100.0 * n / total, 2) if total else 0.0

    return {
        "scope": "library",
        "flag_layer": "images.pick_status",
        "total_images": total,
        "pick_count": by_pick_status["pick"],
        "reject_count": by_pick_status["reject"],
        "neutral_count": by_pick_status["neutral"],
        "pick_pct": _pct(by_pick_status["pick"]),
        "reject_pct": _pct(by_pick_status["reject"]),
        "neutral_pct": _pct(by_pick_status["neutral"]),
        "by_cull_decision": by_cull_decision,
        "auto_cull": {
            "flag_layer": "images.cull_decision",
            "pick_count": auto_pick,
            "reject_count": auto_reject,
            "neutral_count": auto_neutral,
            "unset_count": auto_unset,
            "pick_pct": _pct(auto_pick),
            "reject_pct": _pct(auto_reject),
            "neutral_pct": _pct(auto_neutral),
        },
        "auto_cull_stacks": {
            "stacks_with_exactly_one_pick": cull_stacks_one_pick,
            "stacks_with_multiple_picks": cull_stacks_multi_pick,
            "stacks_over_pick_cap_20": cull_stacks_over_cap,
        },
        "auto_cull_substacks": {
            "total_substacks": total_substacks,
            "singleton_leaves": singleton_leaves,
            "singleton_leaf_pct": singleton_leaf_pct,
            "substacks_picks_over_m3": substacks_picks_over_m3,
            "giant_leaves_over_50": giant_leaves,
        },
        "stacks_with_exactly_one_pick": stacks_one_pick,
        "stacks_with_multiple_picks": stacks_multi_pick,
        "stacks_with_no_picks": stacks_no_pick,
        "stacks_all_reject": stacks_all_reject,
        "stacks_mixed_pick_status": stacks_mixed_status,
        "stacks_needing_review": stacks_multi_pick + stacks_mixed_status,
        "pick_status_cull_decision_disagree": pick_reject_disagree,
    }


def compute_session_flags(session_id: int) -> dict[str, Any]:
    conn = db.get_connector()
    total_row = conn.query_one(
        "SELECT COUNT(*) AS n FROM culling_picks WHERE session_id = ?",
        (session_id,),
    )
    total = int((total_row or {}).get("n") or 0)

    dec_rows = conn.query(
        """
        SELECT COALESCE(decision, 'undecided') AS decision, COUNT(*)::int AS cnt
        FROM culling_picks
        WHERE session_id = ?
        GROUP BY COALESCE(decision, 'undecided')
        """,
        (session_id,),
    )
    by_decision: dict[str, int] = {}
    for r in dec_rows:
        by_decision[str(r["decision"])] = int(r["cnt"])

    auto_row = conn.query_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE auto_suggested = 1)::int AS auto_cnt,
            COUNT(*) FILTER (WHERE auto_suggested = 0 OR auto_suggested IS NULL)::int AS manual_cnt
        FROM culling_picks
        WHERE session_id = ? AND decision IS NOT NULL
        """,
        (session_id,),
    )
    auto_cnt = int((auto_row or {}).get("auto_cnt") or 0)
    manual_cnt = int((auto_row or {}).get("manual_cnt") or 0)

    group_rows = conn.query(
        """
        SELECT
            group_id,
            COUNT(*) FILTER (WHERE decision = 'pick')::int AS picks,
            COUNT(DISTINCT decision)::int AS distinct_decisions
        FROM culling_picks
        WHERE session_id = ? AND group_id IS NOT NULL
        GROUP BY group_id
        """,
        (session_id,),
    )
    g_one = g_multi = g_none = 0
    for r in group_rows:
        picks = int(r.get("picks") or 0)
        if picks == 1:
            g_one += 1
        elif picks > 1:
            g_multi += 1
        else:
            g_none += 1

    def _pct(n: int) -> float:
        return round(100.0 * n / total, 2) if total else 0.0

    pick_n = by_decision.get("pick", 0)
    reject_n = by_decision.get("reject", 0)
    undecided_n = by_decision.get("undecided", 0) + by_decision.get("maybe", 0)

    return {
        "scope": "session",
        "flag_layer": "culling_picks.decision",
        "session_id": session_id,
        "total_images": total,
        "pick_count": pick_n,
        "reject_count": reject_n,
        "undecided_count": undecided_n,
        "pick_pct": _pct(pick_n),
        "reject_pct": _pct(reject_n),
        "by_decision": by_decision,
        "auto_suggested_count": auto_cnt,
        "manual_count": manual_cnt,
        "groups_with_exactly_one_pick": g_one,
        "groups_with_multiple_picks": g_multi,
        "groups_with_no_picks": g_none,
        "groups_needing_review": g_multi,
    }
