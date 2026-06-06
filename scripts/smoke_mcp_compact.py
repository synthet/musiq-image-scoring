#!/usr/bin/env python3
"""Smoke test for is-be-mcp search + dispatch (mirrors Cursor manual checks)."""
from __future__ import annotations

import sys


def main() -> int:
    from modules.mcp.actions.dispatch import dispatch_action
    from modules.mcp.actions.search import search_actions
    from modules.mcp.router_tools import register_compact_tools

    # Compact profile exposes exactly search + dispatch
    tool_names: list[str] = []

    class _FakeMcp:
        def tool(self, *args, **kwargs):
            def deco(fn):
                tool_names.append(fn.__name__)
                return fn

            return deco

    register_compact_tools(_FakeMcp())
    expected = {"search", "dispatch"}
    if set(tool_names) != expected:
        print(f"FAIL compact tools: {tool_names!r} expected {expected!r}", file=sys.stderr)
        return 1

    r1 = search_actions("why did scoring fail", limit=8)
    ids = [x["action_id"] for x in r1.get("results") or []]
    print("SEARCH top3:", ids[:3])
    print("SEARCH low_confidence:", r1.get("low_confidence"))
    if "diagnostics.get_error_summary" not in ids[:3]:
        print(f"FAIL search ranking: {ids}", file=sys.stderr)
        return 1

    r2 = dispatch_action("diagnostics.get_error_summary", {})
    print("DISPATCH get_error_summary status:", r2.get("status"))
    if r2.get("action_id") != "diagnostics.get_error_summary":
        print(f"FAIL dispatch envelope: {r2!r}", file=sys.stderr)
        return 1

    r3 = dispatch_action("diagnostics.run_doctor", {"no_gpu": True})
    print("DISPATCH run_doctor status:", r3.get("status"))
    if r3.get("status") not in ("success", "error"):
        print(f"FAIL run_doctor: {r3!r}", file=sys.stderr)
        return 1

    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
