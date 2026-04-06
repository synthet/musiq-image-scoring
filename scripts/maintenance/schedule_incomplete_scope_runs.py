#!/usr/bin/env python3
"""
Schedule scoring runs for incomplete scope folders.

Fetches the folder tree from GET /api/scope/tree, computes dominant phase
status using the same precedence as the React sidebar (running → failed →
partial → all-done → null), selects leaf folders whose status is null
(no dot) or partial (yellow dot), and submits POST /api/runs/submit for each.

Requirements: requests  (pip install requests)

Examples:
  # Dry-run — list which folders would be submitted:
  python scripts/maintenance/schedule_incomplete_scope_runs.py --dry-run

  # Submit up to 20 folders under a specific prefix:
  python scripts/maintenance/schedule_incomplete_scope_runs.py \\
      --prefix /mnt/d/Photos/Z8 --max-runs 20

  # Include failed folders and full re-run (skip_done=false, force_rerun=true — same as modal "Force re-run"):
  python scripts/maintenance/schedule_incomplete_scope_runs.py \\
      --include-failed --force-rerun

  # Match modal "Fix non-completed stages" (incomplete images only for scoring):
  python scripts/maintenance/schedule_incomplete_scope_runs.py --fix-incomplete

  # Only run specific stages with a delay between submissions:
  python scripts/maintenance/schedule_incomplete_scope_runs.py \\
      --stages indexing scoring --delay-seconds 2.0

  # Match the SPA default checkbox set (discovery through bird ID):
  # indexing, metadata, scoring, culling, keywords, bird_species — this is
  # now the script default. For API-default stages only (no culling/tagging/bird):
  python scripts/maintenance/schedule_incomplete_scope_runs.py --minimal-stages
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

# Same order as ALL_STAGES in frontend/src/components/scope/ScopeSelector.tsx
FULL_WORKFLOW_STAGES: List[str] = [
    "indexing",
    "metadata",
    "scoring",
    "culling",
    "keywords",
    "bird_species",
]


# ---------------------------------------------------------------------------
# Dominant-status logic — mirrors getDominantStatus() in Sidebar.tsx
# Precedence: running > failed > partial > all-done > null
# ---------------------------------------------------------------------------

def dominant_status(phase_statuses: Optional[Dict[str, str]]) -> Optional[str]:
    """Return the dominant status for a folder node, or None if unscored."""
    if not phase_statuses:
        return None
    vals = list(phase_statuses.values())
    if "running" in vals:
        return "running"
    if "failed" in vals:
        return "failed"
    if any(v == "partial" for v in vals):
        return "partial"
    if all(v == "done" for v in vals):
        return "done"
    return None


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------

def collect_leaves(
    nodes: List[Dict[str, Any]],
    *,
    target_statuses: set[Optional[str]],
    prefix: Optional[str],
) -> List[Dict[str, Any]]:
    """Walk the scope tree and return leaf nodes whose dominant status is in *target_statuses*.

    A leaf is a node with no children (or an empty children list).
    If *prefix* is given, only nodes whose path starts with it are considered.
    """
    results: List[Dict[str, Any]] = []

    def _walk(node_list: List[Dict[str, Any]]) -> None:
        for node in node_list:
            children = node.get("children") or []
            path: str = node.get("path", "")

            if children:
                _walk(children)
                continue

            # Leaf node
            if prefix and not path.startswith(prefix):
                continue

            status = dominant_status(node.get("phase_statuses"))
            if status in target_statuses:
                results.append({"path": path, "status": status})

    _walk(nodes)
    return results


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_scope_tree(base_url: str) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/scope/tree"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def submit_run(
    base_url: str,
    path: str,
    *,
    stages: Optional[List[str]] = None,
    skip_done: bool = True,
    force_rerun: bool = False,
    fix_incomplete_stages: bool = False,
) -> dict:
    url = f"{base_url.rstrip('/')}/api/runs/submit"
    payload: Dict[str, Any] = {
        "scope_type": "folder_recursive",
        "scope_paths": [path],
        "skip_done": skip_done,
        "force_rerun": force_rerun,
        "fix_incomplete_stages": fix_incomplete_stages,
    }
    if stages:
        payload["stages"] = stages
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Find incomplete scope folders (no-dot or yellow-dot in the sidebar) "
            "and submit scoring runs via the backend API."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Notes:\n"
            "  - The tree only includes folders known to the DB; purely on-disk\n"
            "    folders not yet indexed will not appear.\n"
            "  - Paths must match the style stored in the DB (e.g. /mnt/d/... on\n"
            "    WSL, D:\\\\... on Windows).\n"
            "  - Use --prefix to narrow scope to a subtree.\n"
        ),
    )
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:7860",
        help="Backend API base URL (default: %(default)s)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected paths without submitting runs",
    )
    p.add_argument(
        "--prefix",
        default=None,
        help="Only consider folders whose path starts with this prefix",
    )
    p.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Maximum number of runs to submit",
    )
    p.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Seconds to sleep between submissions (default: 0)",
    )
    p.add_argument(
        "--include-failed",
        action="store_true",
        help="Also target folders with dominant status 'failed'",
    )
    run_mode = p.add_mutually_exclusive_group()
    run_mode.add_argument(
        "--force-rerun",
        action="store_true",
        help=(
            "Full re-run: skip_done=false and force_rerun=true (matches New Run → Force re-run all stages). "
            "Mutually exclusive with --fix-incomplete."
        ),
    )
    run_mode.add_argument(
        "--fix-incomplete",
        action="store_true",
        help=(
            "Fix incomplete images under each folder for scoring (fix_incomplete_stages=true; matches New Run → "
            "Fix non-completed stages). Mutually exclusive with --force-rerun."
        ),
    )
    p.add_argument(
        "--minimal-stages",
        action="store_true",
        help=(
            "Omit explicit stages in the API request so the server runs only its "
            "default slice (indexing, metadata, scoring) — no culling, keywords, or bird_species."
        ),
    )
    p.add_argument(
        "--stages",
        nargs="+",
        default=None,
        help=(
            "Explicit pipeline stages in order (overrides default). "
            f"Default when not set: {' '.join(FULL_WORKFLOW_STAGES)}."
        ),
    )
    return p


def resolve_stages(args: argparse.Namespace) -> Optional[List[str]]:
    """Stages list for the submit payload, or None to use server defaults."""
    if args.stages is not None:
        return list(args.stages)
    if args.minimal_stages:
        return None
    return list(FULL_WORKFLOW_STAGES)


def resolve_run_flags(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    """(skip_done, force_rerun, fix_incomplete_stages) — aligned with ScopeSelector radio modes."""
    if args.force_rerun:
        return False, True, False
    if args.fix_incomplete:
        return True, False, True
    return True, False, False


def main() -> None:
    args = build_parser().parse_args()
    stages_for_submit = resolve_stages(args)
    skip_done, force_rerun, fix_incomplete = resolve_run_flags(args)

    # Determine which statuses to target
    target: set[Optional[str]] = {None, "partial"}
    if args.include_failed:
        target.add("failed")

    # 1. Fetch tree
    print(f"Fetching scope tree from {args.base_url} ...")
    try:
        tree = fetch_scope_tree(args.base_url)
    except requests.RequestException as e:
        print(f"Error fetching scope tree: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Collect matching leaves
    leaves = collect_leaves(tree, target_statuses=target, prefix=args.prefix)
    leaves.sort(key=lambda x: x["path"])

    if not leaves:
        print("No incomplete leaf folders found.")
        return

    # Apply max-runs cap
    if args.max_runs is not None:
        leaves = leaves[: args.max_runs]

    status_label = {None: "null (no dot)", "partial": "partial (yellow)", "failed": "failed (red)"}

    # 3. Dry-run or submit
    if args.dry_run:
        print(f"\n{'DRY RUN':=^60}")
        if stages_for_submit is None:
            print("Stages: (API default — indexing, metadata, scoring only)\n")
        else:
            print(f"Stages: {' '.join(stages_for_submit)}\n")
        if fix_incomplete:
            mode = "fix_incomplete (fix_incomplete_stages=true)"
        elif force_rerun:
            mode = "force_rerun (skip_done=false, force_rerun=true)"
        else:
            mode = "incremental (skip_done=true, force_rerun=false)"
        print(f"Run mode: {mode}\n")
        print(f"Would submit {len(leaves)} run(s):\n")
        for entry in leaves:
            label = status_label.get(entry["status"], entry["status"])
            print(f"  [{label}]  {entry['path']}")
        return

    if stages_for_submit is None:
        print(f"\nSubmitting {len(leaves)} run(s) (API default stages) ...")
    else:
        print(f"\nSubmitting {len(leaves)} run(s) stages={' '.join(stages_for_submit)} ...")
    if fix_incomplete:
        print("Run mode: fix_incomplete (fix_incomplete_stages=true)")
    elif force_rerun:
        print("Run mode: force_rerun (skip_done=false, force_rerun=true)")
    else:
        print("Run mode: incremental (skip_done=true)")
    submitted = 0
    for i, entry in enumerate(leaves):
        label = status_label.get(entry["status"], entry["status"])
        path = entry["path"]
        try:
            result = submit_run(
                args.base_url,
                path,
                stages=stages_for_submit,
                skip_done=skip_done,
                force_rerun=force_rerun,
                fix_incomplete_stages=fix_incomplete,
            )
            submitted += 1
            run_id = result.get("run_id", "?")
            print(f"  [{submitted}/{len(leaves)}] [{label}] {path}  -> run_id={run_id}")
        except requests.RequestException as e:
            print(f"  [ERROR] {path}: {e}", file=sys.stderr)

        if args.delay_seconds > 0 and i < len(leaves) - 1:
            time.sleep(args.delay_seconds)

    print(f"\nDone. Submitted {submitted}/{len(leaves)} run(s).")


if __name__ == "__main__":
    main()
