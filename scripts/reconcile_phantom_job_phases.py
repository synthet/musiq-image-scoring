#!/usr/bin/env python3
"""Demote phantom job_phases rows stuck in running without a busy runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _busy_runner_keys_from_api(base_url: str = "http://127.0.0.1:7860") -> set[str]:
    """Read active runner from the live WebUI when available."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/tasks/active",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return set()
    active = (data.get("dispatcher") or {}).get("active_runner")
    return {str(active).strip().lower()} if active else set()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grace-sec",
        type=int,
        default=None,
        help="Override dispatcher.stale_phase_grace_sec (default from config).",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:7860",
        help="WebUI base URL for detecting busy runners (default: %(default)s).",
    )
    parser.add_argument(
        "--busy-runner",
        action="append",
        default=[],
        help="Treat runner family as busy (indexing, metadata, scoring, tagging, ...).",
    )
    parser.add_argument("--dry-run", action="store_true", help="List candidates only.")
    args = parser.parse_args()

    from modules import db
    from modules.config import get_config_value

    grace = args.grace_sec
    if grace is None:
        try:
            grace = int(get_config_value("dispatcher.stale_phase_grace_sec", default=120))
        except (TypeError, ValueError):
            grace = 120

    busy = {str(r).strip().lower() for r in args.busy_runner if str(r).strip()}
    busy |= _busy_runner_keys_from_api(args.base_url)

    if args.dry_run:
        rows = db.list_phantom_running_job_phases(busy_runner_keys=busy, grace_seconds=grace)
        print(json.dumps({"grace_seconds": grace, "busy_runner_keys": sorted(busy), "candidates": rows}, indent=2))
        return 0

    demoted = db.reconcile_phantom_running_job_phases(busy_runner_keys=busy, grace_seconds=grace)
    print(json.dumps({"grace_seconds": grace, "demoted": demoted}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
