#!/usr/bin/env python3
"""Audit folders for pipeline-order gaps (a later phase done while an earlier required phase is not_started).

Read-only diagnostic. Surfaces the "index + tags, no score" inconsistency that arose
when the legacy single-phase ``/api/tagging/start`` and ``/api/clustering/start``
endpoints enqueued ``keywords`` / ``culling`` without their dependency prefix, driving
those phases to ``done`` while ``metadata`` / ``scoring`` stayed ``not_started``.

A folder is flagged when a *required* earlier phase (indexing -> metadata -> scoring)
is ``not_started`` for the folder while some *later* phase has any images ``done``.
These folders self-heal once auto-drive re-buckets them as ``awaiting_<earlier phase>``,
or via a one-off ``/runs/submit`` covering the full prefix. This script writes nothing.

Usage (WSL, project root):
  source ~/.venvs/tf/bin/activate
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/.../lib

  python scripts/maintenance/audit_pipeline_gaps.py --report
  python scripts/maintenance/audit_pipeline_gaps.py --report --limit 50
  python scripts/maintenance/audit_pipeline_gaps.py --report --all-folders   # include ancestors
  python scripts/maintenance/audit_pipeline_gaps.py --json                   # machine-readable
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Phases whose absence should block downstream work. Optional phases (culling, keywords,
# bird_species) are never treated as the "missing earlier" stage — they are the *later*
# stages that should not have run ahead.
REQUIRED_EARLIER = ("indexing", "metadata", "scoring")


def _leaf_folders(paths: list[str]) -> list[str]:
    """Return only folders with no descendant folder (the data-bearing leaves).

    ``get_folder_phase_summary`` aggregates descendants, so reporting ancestors too
    would duplicate every child gap. Leaves give one row per real date folder.
    """
    norm = [p for p in paths if p]
    out: list[str] = []
    for p in norm:
        prefix_unix = p.rstrip("/\\") + "/"
        prefix_win = p.rstrip("/\\") + "\\"
        if any(o != p and (o.startswith(prefix_unix) or o.startswith(prefix_win)) for o in norm):
            continue
        out.append(p)
    return out


def _find_gap(summary: list[dict]) -> dict | None:
    """Given a folder phase summary, return gap info or None.

    Gap = earliest REQUIRED_EARLIER phase that is ``not_started`` (with images present)
    while any later phase (higher sort_order) has ``done_count > 0``.
    """
    by_code = {(r.get("code") or "").strip(): r for r in summary or []}
    for code in REQUIRED_EARLIER:
        row = by_code.get(code)
        if not row:
            continue
        if (row.get("status") or "") != "not_started":
            continue
        if int(row.get("total_count") or 0) <= 0:
            continue
        sort_order = row.get("sort_order")
        later_done = [
            (r.get("code") or "").strip()
            for r in summary or []
            if r.get("sort_order") is not None
            and sort_order is not None
            and r.get("sort_order") > sort_order
            and int(r.get("done_count") or 0) > 0
        ]
        if later_done:
            return {"gap_phase": code, "later_done": later_done}
    return None


def audit(*, include_ancestors: bool = False, limit: int | None = None) -> list[dict]:
    from modules import db

    folders = db.get_all_folders()
    if not include_ancestors:
        folders = _leaf_folders(folders)
    folders = sorted(folders)

    findings: list[dict] = []
    for path in folders:
        try:
            summary = db.get_folder_phase_summary(path, force_refresh=False)
        except Exception:
            logger.exception("audit_pipeline_gaps: summary failed for %s", path)
            continue
        gap = _find_gap(summary)
        if gap:
            findings.append({"folder": path, **gap})
            if limit and len(findings) >= limit:
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true", help="Print a human-readable gap table (default).")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    parser.add_argument(
        "--all-folders",
        action="store_true",
        help="Include ancestor folders (default: data-bearing leaves only).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Stop after N flagged folders.")
    args = parser.parse_args()

    findings = audit(include_ancestors=args.all_folders, limit=args.limit)

    if args.json:
        print(json.dumps(findings, indent=2))
        return 0

    if not findings:
        logger.info("No pipeline-order gaps found.")
        return 0

    width = max(len(f["folder"]) for f in findings)
    logger.info("Found %d folder(s) with a pipeline-order gap:", len(findings))
    logger.info("%-*s  %-12s  %s", width, "folder", "gap (earlier)", "later done")
    for f in findings:
        logger.info("%-*s  %-12s  %s", width, f["folder"], f["gap_phase"], ", ".join(f["later_done"]))
    logger.info(
        "These self-heal once auto-drive re-buckets them as awaiting_<gap phase>, "
        "or run /runs/submit with the full prefix on each."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
