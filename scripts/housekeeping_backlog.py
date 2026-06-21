#!/usr/bin/env python3
"""Backlog housekeeping: project Stage sync, label hygiene, tier-1 closes.

Requires `gh` authenticated (run from Windows host where gh is installed).

  python scripts/housekeeping_backlog.py
  python scripts/housekeeping_backlog.py --apply
  python scripts/housekeeping_backlog.py --apply --phase stages
  python scripts/audit_backlog_issues.py

Config: scripts/backlog_housekeeping_config.json (promote_ready, tier1_closes).
Skill: .cursor/skills/backlog-housekeeping/SKILL.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_NODE_ID = "PVT_kwHOAFXgIs4BWC3c"
STAGE_FIELD_ID = "PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0"
STAGE_BACKLOG = "83b7a780"
STAGE_READY = "ddaf7773"
STAGE_DONE = "73062c96"

BACKEND = "synthet/image-scoring-backend"
GALLERY = "synthet/image-scoring-gallery"
REPOS = (BACKEND, GALLERY)

CONFIG_PATH = Path(__file__).resolve().parent / "backlog_housekeeping_config.json"


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {"promote_ready": {}, "tier1_closes": []}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def gh_run(*args: str) -> str:
    res = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}\n{res.stderr}")
    return (res.stdout or "").strip()


def gh_json(*args: str):
    return json.loads(gh_run(*args) or "null")


def issue_state(repo: str, number: int) -> tuple[str, list[str]]:
    data = gh_json(
        "issue", "view", str(number), "--repo", repo,
        "--json", "state,labels",
    )
    labels = [l["name"] for l in data.get("labels", [])]
    return data["state"], labels


def list_open_issues(repo: str) -> list[dict]:
    out = gh_json(
        "issue", "list", "--repo", repo, "--state", "open",
        "--limit", "200", "--json", "number,title,labels",
    )
    return out


def label_names(issue: dict) -> list[str]:
    return [l["name"] for l in issue.get("labels", [])]


def default_area(repo: str, labels: list[str], title: str) -> str | None:
    if any(l.startswith("area:") for l in labels):
        return None
    if "image-scoring-gallery" in repo:
        if any(l.startswith("area:") for l in labels):
            return None
        return "area:electron"
    if "security" in title.lower() or "type:bug" in labels:
        return "area:python"
    if any(l.startswith("type:") for l in labels) or "enhancement" in labels:
        return "area:python"
    return None


def set_project_stage(item_id: str, stage_option: str, dry_run: bool) -> None:
    if dry_run:
        return
    gh_run(
        "project", "item-edit",
        "--id", item_id,
        "--project-id", PROJECT_NODE_ID,
        "--field-id", STAGE_FIELD_ID,
        "--single-select-option-id", stage_option,
    )
    time.sleep(0.2)


def edit_labels(repo: str, number: int, add: list[str], remove: list[str], dry_run: bool) -> None:
    if not add and not remove:
        return
    cmd = ["issue", "edit", str(number), "--repo", repo]
    for lbl in add:
        cmd.extend(["--add-label", lbl])
    for lbl in remove:
        cmd.extend(["--remove-label", lbl])
    if dry_run:
        print(f"  DRY labels {repo}#{number}: +{add} -{remove}")
        return
    gh_run(*cmd)
    time.sleep(0.25)


def close_issue(repo: str, number: int, comment: str, dry_run: bool) -> bool:
    state, _ = issue_state(repo, number)
    if state == "CLOSED":
        print(f"  SKIP close {repo}#{number} (already closed)")
        return False
    if dry_run:
        print(f"  DRY close {repo}#{number}: {comment[:80]}...")
        return True
    gh_run("issue", "close", str(number), "--repo", repo, "--comment", comment)
    time.sleep(0.3)
    return True


def project_item_for(repo: str, number: int) -> str | None:
    short = repo.split("/")[-1]
    data = gh_json("project", "item-list", "1", "--owner", "synthet", "--format", "json", "--limit", "300")
    for item in data.get("items", []):
        content = item.get("content") or {}
        if content.get("number") == number and short in (content.get("repository") or ""):
            return item["id"]
    return None


def promote_ready_numbers(config: dict) -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    for repo, numbers in (config.get("promote_ready") or {}).items():
        for n in numbers:
            out.add((repo, int(n)))
    return out


def sync_unstaged_items(dry_run: bool, ready: set[tuple[str, int]]) -> int:
    data = gh_json("project", "item-list", "1", "--owner", "synthet", "--format", "json", "--limit", "300")
    count = 0
    for item in data.get("items", []):
        if item.get("stage"):
            continue
        content = item.get("content") or {}
        number = content.get("number")
        repo_url = content.get("repository") or item.get("repository") or ""
        if repo_url.startswith("http"):
            repo = repo_url.replace("https://github.com/", "")
        elif "/" in repo_url:
            repo = repo_url
        else:
            continue
        if not number:
            continue
        state, _ = issue_state(repo, number)
        if state == "CLOSED":
            stage = STAGE_DONE
            label = "Done"
        elif (repo, number) in ready:
            stage = STAGE_READY
            label = "Ready"
        else:
            stage = STAGE_BACKLOG
            label = "Backlog"
        print(f"  stage {repo.split('/')[-1]}#{number} -> {label} ({state})")
        set_project_stage(item["id"], stage, dry_run)
        count += 1
    return count


def sync_review_stage(dry_run: bool) -> int:
    data = gh_json("project", "item-list", "1", "--owner", "synthet", "--format", "json", "--limit", "300")
    count = 0
    for item in data.get("items", []):
        if item.get("stage") != "Review":
            continue
        content = item.get("content") or {}
        number = content.get("number")
        repo = (content.get("repository") or "").replace("https://github.com/", "")
        if not number or not repo:
            continue
        state, _ = issue_state(repo, number)
        if state == "CLOSED":
            print(f"  Review->Done {repo.split('/')[-1]}#{number}")
            set_project_stage(item["id"], STAGE_DONE, dry_run)
        else:
            print(f"  Review->Backlog {repo.split('/')[-1]}#{number} (still open)")
            set_project_stage(item["id"], STAGE_BACKLOG, dry_run)
        count += 1
    return count


def auto_label_hygiene(dry_run: bool) -> int:
    print("\n=== Label hygiene (auto) ===")
    count = 0
    for repo in REPOS:
        for issue in list_open_issues(repo):
            n = issue["number"]
            labels = label_names(issue)
            add: list[str] = []
            remove: list[str] = []
            area = default_area(repo, labels, issue.get("title", ""))
            if area:
                add.append(area)
            if "bug" in labels and any(l.startswith("type:") for l in labels):
                remove.append("bug")
            if "enhancement" in labels:
                if any(l.startswith("type:") for l in labels):
                    remove.append("enhancement")
                elif "type:feature" not in labels:
                    add.append("type:feature")
                    remove.append("enhancement")
            if add or remove:
                edit_labels(repo, n, add, remove, dry_run)
                count += 1
    return count


def tier1_closes(config: dict, dry_run: bool) -> int:
    print("\n=== Close superseded (tier 1, config) ===")
    count = 0
    for entry in config.get("tier1_closes") or []:
        repo = entry["repo"]
        number = int(entry["number"])
        comment = entry["comment"]
        if close_issue(repo, number, comment, dry_run):
            count += 1
            if not dry_run:
                item_id = project_item_for(repo, number)
                if item_id:
                    set_project_stage(item_id, STAGE_DONE, dry_run=False)
    return count


def run_audit() -> int:
    script = Path(__file__).resolve().parent / "audit_backlog_issues.py"
    res = subprocess.run([sys.executable, str(script)], check=False)
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub backlog housekeeping")
    parser.add_argument("--apply", action="store_true", help="Execute changes (default dry-run)")
    parser.add_argument(
        "--phase",
        choices=["stages", "labels", "closes", "audit", "all"],
        default="all",
        help="Run one phase only",
    )
    args = parser.parse_args()
    dry_run = not args.apply
    config = load_config()
    ready = promote_ready_numbers(config)

    print(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'} phase={args.phase}")
    print(f"Config: {CONFIG_PATH.name}")

    if args.phase in ("audit", "all"):
        print("\n=== Audit (read-only) ===")
        rc = run_audit()
        if args.phase == "audit":
            return rc

    if args.phase in ("stages", "all"):
        print("\n=== Sync unstaged project items ===")
        n1 = sync_unstaged_items(dry_run, ready)
        print(f"  touched {n1} items")
        print("\n=== Reconcile Review stage ===")
        n2 = sync_review_stage(dry_run)
        print(f"  touched {n2} items")

    if args.phase in ("labels", "all"):
        n3 = auto_label_hygiene(dry_run)
        print(f"  touched {n3} issues")

    if args.phase in ("closes", "all"):
        n4 = tier1_closes(config, dry_run)
        print(f"  closed {n4} issues")

    if args.phase == "all" and not dry_run:
        print("\n=== Post-apply audit ===")
        run_audit()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
