#!/usr/bin/env python3
"""Agent-assisted cull review CLI (discover-only and dry-run by default)."""

from __future__ import annotations

import argparse
import json
import sys

from modules.agent_cull.apply import apply_agent_remove_candidates
from modules.agent_cull.config import load_agent_cull_config
from modules.agent_cull.discovery_db import discover_eligible_units, load_unit_rows
from modules.agent_cull.repository import get_latest_group_for_unit
from modules.agent_cull.service import run_agent_review_for_unit


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(payload, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent-assisted cull review")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=None)
    parser.add_argument("--apply-candidates", action="store_true")
    parser.add_argument("--stack-id", type=int)
    parser.add_argument("--sub-stack-id", type=int)
    parser.add_argument("--folder-path")
    parser.add_argument("--folder-id", type=int)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--agent")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_out")
    parser.add_argument("--no-thumbnails", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_agent_cull_config()
    if args.no_thumbnails:
        from dataclasses import replace

        cfg = replace(
            cfg,
            agent=replace(cfg.agent, include_thumbnails=False),
        )
    dry_run = cfg.dry_run_default if args.dry_run is None else args.dry_run
    if args.apply_candidates:
        dry_run = False

    if args.stack_id is None and not args.folder_path and args.folder_id is None:
        print("Provide --stack-id, --folder-path, or --folder-id", file=sys.stderr)
        return 2

    if not cfg.enabled and not args.discover_only:
        print("agent_review disabled in config (culling.agent_review.enabled=false)", file=sys.stderr)
        return 2

    try:
        units = discover_eligible_units(
            cfg,
            folder_path=args.folder_path,
            folder_id=args.folder_id,
            stack_id=args.stack_id,
            sub_stack_id=args.sub_stack_id,
            limit=args.limit,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"discovery failed: {exc}", file=sys.stderr)
        return 4

    if args.discover_only:
        payload = {
            "eligible_count": len(units),
            "units": [
                {
                    "review_unit_key": u.review_unit_key,
                    "stack_id": u.stack_id,
                    "sub_stack_id": u.sub_stack_id,
                    "picked": list(u.picked_ids),
                    "rejected": list(u.rejected_ids),
                    "image_count": len(u.image_ids),
                }
                for u in units
            ],
        }
        _emit(payload, as_json=args.json_out)
        return 0

    results = []
    for unit in units:
        if not args.force:
            latest = get_latest_group_for_unit(unit.review_unit_key)
            if latest and latest.get("status") in ("proposed", "validated", "applied"):
                results.append({"review_unit_key": unit.review_unit_key, "skipped": "existing_review"})
                continue
        rows_by_id = load_unit_rows(unit)
        outcome = run_agent_review_for_unit(
            unit,
            rows_by_id,
            cfg,
            dry_run=dry_run,
            provider_override=args.agent,
        )
        if args.apply_candidates and outcome.get("ok") and outcome.get("group_id"):
            apply_result = apply_agent_remove_candidates(int(outcome["group_id"]))
            outcome["apply"] = apply_result
        results.append(outcome)

    _emit({"results": results}, as_json=args.json_out)
    if not results:
        return 1
    return 0 if all(r.get("ok") or r.get("skipped") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
