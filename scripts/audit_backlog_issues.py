#!/usr/bin/env python3
"""Read-only backlog inventory report (labels, epics, obsolete candidates).

  python scripts/audit_backlog_issues.py
  python scripts/audit_backlog_issues.py --json reports/backlog-audit.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict

REPOS = ("synthet/image-scoring-backend", "synthet/image-scoring-gallery")


def gh_issues(repo: str) -> list[dict]:
    out = subprocess.run(
        [
            "gh", "issue", "list", "--repo", repo, "--state", "open",
            "--limit", "200", "--json", "number,title,labels,body",
        ],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return json.loads(out.stdout)


def label_names(issue: dict) -> list[str]:
    return [l["name"] for l in issue.get("labels", [])]


def audit_repo(repo: str) -> dict:
    issues = gh_issues(repo)
    missing_area = []
    missing_priority = []
    missing_type = []
    obsolete = []
    epics = []
    dup_github = []

    for i in issues:
        labels = label_names(i)
        n = i["number"]
        if not any(l.startswith("area:") for l in labels):
            missing_area.append(n)
        if not any(l.startswith("priority:") for l in labels):
            missing_priority.append(n)
        if not any(l.startswith("type:") for l in labels):
            missing_type.append(n)
        if "status:obsolete" in labels:
            obsolete.append(n)
        if "type:epic" in labels:
            epics.append(n)
        if ("bug" in labels or "enhancement" in labels) and any(
            l.startswith("type:") for l in labels
        ):
            dup_github.append(n)

    return {
        "repo": repo,
        "open_count": len(issues),
        "missing_area": missing_area,
        "missing_priority": missing_priority,
        "missing_type": missing_type,
        "status_obsolete": obsolete,
        "type_epic": epics,
        "duplicate_github_defaults": dup_github,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", metavar="PATH", help="Write JSON report to path")
    args = parser.parse_args()

    reports = [audit_repo(r) for r in REPOS]
    for r in reports:
        print(f"\n{r['repo']}: {r['open_count']} open")
        for key in ("missing_area", "missing_priority", "missing_type", "duplicate_github_defaults"):
            if r[key]:
                print(f"  {key}: {r[key]}")
        print(f"  type_epic: {r['type_epic']}")
        print(f"  status_obsolete: {r['status_obsolete']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2)
        print(f"\nWrote {args.json}")

    bad = sum(len(r["missing_area"]) + len(r["missing_priority"]) + len(r["missing_type"]) for r in reports)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
