#!/usr/bin/env python
"""Read-only audit: sub-stack leaf sizes, hierarchy tiers, embedding coverage, agent-cull skips.

Usage (WSL + ~/.venvs/tf)::

    python -m scripts.study.substack_split_audit
    python -m scripts.study.substack_split_audit --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from modules import db
from modules.agent_cull.config import AgentCullConfig, load_agent_cull_config
from modules.agent_cull.discovery import (
    discover_review_units_from_stack_rows,
    default_is_usable,
)
from modules.culling_analytics._common import require_postgres
from modules.culling_analytics.flags import compute_library_flags
from modules.culling_analytics.hierarchy import compute_library_hierarchy
from modules.embedding_spaces import OPENCLIP_L14_IMAGE_SPACE_CODE


def _leaf_size_histogram() -> dict[str, int]:
    rows = db.get_connector().query(
        """
        SELECT
            CASE
                WHEN cnt = 1 THEN '1'
                WHEN cnt BETWEEN 2 AND 3 THEN '2-3'
                WHEN cnt BETWEEN 4 AND 9 THEN '4-9'
                WHEN cnt BETWEEN 10 AND 20 THEN '10-20'
                WHEN cnt BETWEEN 21 AND 50 THEN '21-50'
                ELSE '51+'
            END AS bucket,
            COUNT(*)::int AS substacks
        FROM (
            SELECT sub_stack_id, COUNT(*)::int AS cnt
            FROM images
            WHERE sub_stack_id IS NOT NULL
            GROUP BY sub_stack_id
        ) s
        GROUP BY 1
        ORDER BY 1
        """
    ) or []
    return {str(r["bucket"]): int(r["substacks"]) for r in rows}


def _openclip_coverage() -> dict[str, int | float]:
    rows = db.get_connector().query(
        """
        SELECT
            COUNT(*)::int AS stacked_images,
            COUNT(ie.image_id)::int AS with_openclip
        FROM images i
        LEFT JOIN embedding_spaces es ON es.code = ?
        LEFT JOIN image_embeddings_768 ie
          ON ie.image_id = i.id AND ie.embedding_space_id = es.id
        WHERE i.stack_id IS NOT NULL
        """,
        (OPENCLIP_L14_IMAGE_SPACE_CODE,),
    ) or [{}]
    row = rows[0]
    stacked = int(row.get("stacked_images") or 0)
    with_emb = int(row.get("with_openclip") or 0)
    pct = round(100.0 * with_emb / stacked, 2) if stacked else 0.0
    return {
        "stacked_images": stacked,
        "with_openclip_l14": with_emb,
        "coverage_pct": pct,
    }


def _group_too_large_skips(cfg: AgentCullConfig, *, sample_limit: int = 5000) -> dict[str, int]:
    rows = db.get_connector().query(
        """
        SELECT
            i.id, i.stack_id, i.sub_stack_id, i.pick_status, i.cull_decision,
            i.file_path, i.thumbnail_path, i.thumbnail_path_win
        FROM images i
        WHERE i.stack_id IS NOT NULL
        ORDER BY i.stack_id, i.sub_stack_id NULLS FIRST, i.id
        LIMIT ?
        """,
        (sample_limit * 50,),
    ) or []
    by_stack: dict[int, list[dict]] = {}
    for row in rows:
        sid = int(row["stack_id"])
        by_stack.setdefault(sid, []).append(dict(row))

    too_large = 0
    eligible = 0
    other_skip: dict[str, int] = {}
    for sid, stack_rows in by_stack.items():
        substack_ids = {r.get("sub_stack_id") for r in stack_rows if r.get("sub_stack_id")}
        leaf_count = len(substack_ids)
        with_sub = sum(1 for r in stack_rows if r.get("sub_stack_id"))
        units = discover_review_units_from_stack_rows(
            sid,
            stack_rows,
            cfg,
            leaf_count=leaf_count,
            images_with_substack=with_sub,
            is_usable_fn=default_is_usable,
        )
        for unit in units:
            if unit.skip_reason is None:
                eligible += 1
            elif unit.skip_reason in ("group_too_large", "group_exceeds_safety_ceiling"):
                too_large += 1
            else:
                other_skip[unit.skip_reason] = other_skip.get(unit.skip_reason, 0) + 1
            if eligible + too_large + sum(other_skip.values()) >= sample_limit:
                break
        if eligible + too_large + sum(other_skip.values()) >= sample_limit:
            break

    return {
        "eligible_units": eligible,
        "skipped_group_too_large": too_large,
        "other_skips": other_skip,
        "stacks_scanned": len(by_stack),
    }


def build_audit_report() -> dict:
    require_postgres()
    cfg = load_agent_cull_config()
    hierarchy = compute_library_hierarchy(None)
    flags = compute_library_flags(None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_review_config": {
            "max_group_size": cfg.max_group_size,
            "review_batch_size": cfg.review_batch_size,
        },
        "hierarchy": hierarchy,
        "flags": flags,
        "leaf_size_histogram": _leaf_size_histogram(),
        "openclip_coverage": _openclip_coverage(),
        "agent_cull_skips": _group_too_large_skips(cfg),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sub-stack split + agent-cull eligibility audit")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args(argv)
    report = build_audit_report()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    h = report["hierarchy"]
    print("Sub-stack split audit")
    print(f"  single_leaf_stacks: {h.get('single_leaf_stacks')}")
    print(f"  flat_stacks: {h.get('flat_stacks')}")
    print(f"  populated_multi_leaf: {h.get('populated_multi_leaf_stacks')}")
    print(f"  giant_leaves_over_50: {report['flags']['auto_cull_substacks']['giant_leaves_over_50']}")
    print(f"  openclip coverage: {report['openclip_coverage']}")
    print(f"  leaf histogram: {report['leaf_size_histogram']}")
    print(f"  agent skips: {report['agent_cull_skips']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
