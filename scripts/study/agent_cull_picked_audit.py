#!/usr/bin/env python3
"""Run pass-2 picked-only advisory audit for a stack (study harness)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent cull picked-only audit pass")
    parser.add_argument("--stack-id", type=int, required=True)
    parser.add_argument("--sub-stack-id", type=int)
    parser.add_argument("--mode-profile", default="technical_focus_strict_picks")
    parser.add_argument("--provider", default="antigravity")
    parser.add_argument(
        "--picked-quality-hints",
        action="store_true",
        help="Include picked_quality_hints in pass-1 packet shape (hints apply to full packet only)",
    )
    args = parser.parse_args(argv)

    from dataclasses import replace

    from modules.agent_cull.config import load_agent_cull_config
    from modules.agent_cull.discovery_db import inspect_review_unit_for_run, load_unit_rows
    from modules.agent_cull.mode_profiles import apply_mode_profile
    from modules.agent_cull.picked_audit import run_picked_audit_pass

    cfg = apply_mode_profile(load_agent_cull_config(), args.mode_profile)
    if args.picked_quality_hints:
        cfg = replace(cfg, picked_quality_hints=True)
    unit = inspect_review_unit_for_run(cfg, stack_id=args.stack_id, sub_stack_id=args.sub_stack_id)
    if unit is None:
        print(json.dumps({"ok": False, "error": "no_unit"}, indent=2))
        return 2
    rows = load_unit_rows(unit)
    result = run_picked_audit_pass(unit, rows, cfg, provider_override=args.provider)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
