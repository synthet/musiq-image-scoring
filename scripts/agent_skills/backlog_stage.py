#!/usr/bin/env python3
"""Compiled backlog claim / Stage transition harness.

Deterministic gh Project board steps from /task-claim and backlog-queue:
  - verify issue is claimable
  - assign @me
  - resolve project item id
  - set Stage (Claimed / In Progress / Blocked / Review / Done)

Picking which Ready card and writing Blocked comment bodies stay LLM-shaped.
Backlog→Ready promotion stays human-gated.

Usage:
  python scripts/agent_skills/backlog_stage.py claim 123
  python scripts/agent_skills/backlog_stage.py claim 45 --repo gallery
  python scripts/agent_skills/backlog_stage.py set-stage 123 --stage in_progress
  python scripts/agent_skills/backlog_stage.py set-stage 123 --stage blocked --comment "Blocked: …"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

PROJECT_NODE_ID = "PVT_kwHOAFXgIs4BWC3c"
STAGE_FIELD_ID = "PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0"
PROJECT_NUMBER = "1"
OWNER = "synthet"

REPOS = {
    "backend": "synthet/image-scoring-backend",
    "gallery": "synthet/image-scoring-gallery",
}

STAGE_OPTIONS = {
    "backlog": "83b7a780",
    "ready": "ddaf7773",
    "claimed": "1cc70f0b",
    "in_progress": "8b22e18e",
    "blocked": "4bbe5dd0",
    "review": "cb723acb",
    "done": "73062c96",
}


@dataclass
class ActionResult:
    ok: bool
    action: str
    repo: str
    number: int
    title: str = ""
    url: str = ""
    item_id: str = ""
    stage: str = ""
    message: str = ""
    reminder: str = ""


def gh_run(*args: str) -> str:
    res = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        raise RuntimeError(f"gh {' '.join(args)}\n{err}")
    return (res.stdout or "").strip()


def gh_json(*args: str) -> Any:
    return json.loads(gh_run(*args) or "null")


def resolve_repo(alias: str) -> str:
    key = (alias or "backend").lower().strip()
    if key in ("backend", "be", "image-scoring-backend"):
        return REPOS["backend"]
    if key in ("gallery", "ui", "image-scoring-gallery"):
        return REPOS["gallery"]
    if "/" in key:
        return key
    raise SystemExit(f"Unknown repo alias: {alias!r} (use backend|gallery)")


def short_repo(full: str) -> str:
    return full.split("/")[-1]


def view_issue(repo: str, number: int) -> dict:
    return gh_json(
        "issue",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        "number,state,assignees,title,url",
    )


def current_login() -> str | None:
    try:
        data = gh_json("api", "user")
        login = data.get("login")
        return str(login) if login else None
    except RuntimeError:
        return None


def project_item_for(repo: str, number: int) -> str | None:
    short = short_repo(repo)
    data = gh_json(
        "project",
        "item-list",
        PROJECT_NUMBER,
        "--owner",
        OWNER,
        "--format",
        "json",
        "--limit",
        "300",
    )
    for item in data.get("items", []) or []:
        content = item.get("content") or {}
        if content.get("number") != number:
            continue
        repo_field = content.get("repository") or ""
        if str(repo_field).endswith(short):
            return str(item.get("id") or "")
    return None


def set_stage(item_id: str, stage_key: str) -> None:
    option = STAGE_OPTIONS[stage_key]
    gh_run(
        "project",
        "item-edit",
        "--id",
        item_id,
        "--project-id",
        PROJECT_NODE_ID,
        "--field-id",
        STAGE_FIELD_ID,
        "--single-select-option-id",
        option,
    )
    time.sleep(0.2)


def claim_issue(number: int, repo_alias: str, *, dry_run: bool = False) -> ActionResult:
    repo = resolve_repo(repo_alias)
    data = view_issue(repo, number)
    title = str(data.get("title") or "")
    url = str(data.get("url") or f"https://github.com/{repo}/issues/{number}")
    state = str(data.get("state") or "").upper()
    assignees = [a.get("login") for a in (data.get("assignees") or []) if a.get("login")]
    me = current_login()

    if state == "CLOSED":
        return ActionResult(
            ok=False,
            action="claim",
            repo=repo,
            number=number,
            title=title,
            url=url,
            message="issue is closed",
        )

    if assignees and me and me not in assignees:
        return ActionResult(
            ok=False,
            action="claim",
            repo=repo,
            number=number,
            title=title,
            url=url,
            message=f"already assigned to: {', '.join(assignees)}",
        )

    item_id = project_item_for(repo, number)
    if not item_id:
        return ActionResult(
            ok=False,
            action="claim",
            repo=repo,
            number=number,
            title=title,
            url=url,
            message=(
                f"issue #{number} is not on the Project board "
                f"(https://github.com/users/{OWNER}/projects/1)"
            ),
        )

    if dry_run:
        return ActionResult(
            ok=True,
            action="claim",
            repo=repo,
            number=number,
            title=title,
            url=url,
            item_id=item_id,
            stage="claimed",
            message="dry_run: would assign @me and set Stage=Claimed",
            reminder=(
                f"Claimed. Move to Stage=In Progress on first commit. "
                f"PR description must include Closes #{number}."
            ),
        )

    if not assignees or (me and me not in assignees):
        gh_run("issue", "edit", str(number), "--repo", repo, "--add-assignee", "@me")
        time.sleep(0.25)

    set_stage(item_id, "claimed")
    return ActionResult(
        ok=True,
        action="claim",
        repo=repo,
        number=number,
        title=title,
        url=url,
        item_id=item_id,
        stage="claimed",
        message="Claimed",
        reminder=(
            f"Move to Stage=In Progress (option id {STAGE_OPTIONS['in_progress']}) "
            f"on your first commit. PR description must include Closes #{number}."
        ),
    )


def set_issue_stage(
    number: int,
    repo_alias: str,
    stage_key: str,
    *,
    comment: str | None = None,
    dry_run: bool = False,
) -> ActionResult:
    stage_key = stage_key.lower().replace("-", "_").replace(" ", "_")
    if stage_key not in STAGE_OPTIONS:
        raise SystemExit(
            f"Unknown stage {stage_key!r}; choose from: {', '.join(STAGE_OPTIONS)}"
        )
    repo = resolve_repo(repo_alias)
    data = view_issue(repo, number)
    title = str(data.get("title") or "")
    url = str(data.get("url") or f"https://github.com/{repo}/issues/{number}")
    item_id = project_item_for(repo, number)
    if not item_id:
        return ActionResult(
            ok=False,
            action="set-stage",
            repo=repo,
            number=number,
            title=title,
            url=url,
            stage=stage_key,
            message="issue not on Project board",
        )

    if stage_key == "blocked" and not (comment or "").strip():
        return ActionResult(
            ok=False,
            action="set-stage",
            repo=repo,
            number=number,
            title=title,
            url=url,
            item_id=item_id,
            stage=stage_key,
            message="Blocked requires --comment with reason + unblock condition",
        )

    if dry_run:
        return ActionResult(
            ok=True,
            action="set-stage",
            repo=repo,
            number=number,
            title=title,
            url=url,
            item_id=item_id,
            stage=stage_key,
            message=f"dry_run: would set Stage={stage_key}",
        )

    set_stage(item_id, stage_key)
    if stage_key == "blocked" and comment:
        gh_run(
            "issue",
            "comment",
            str(number),
            "--repo",
            repo,
            "--body",
            comment.strip(),
        )
        time.sleep(0.2)

    return ActionResult(
        ok=True,
        action="set-stage",
        repo=repo,
        number=number,
        title=title,
        url=url,
        item_id=item_id,
        stage=stage_key,
        message=f"Stage={stage_key}",
    )


def cmd_claim(args: argparse.Namespace) -> int:
    result = claim_issue(args.number, args.repo, dry_run=args.dry_run)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def cmd_set_stage(args: argparse.Namespace) -> int:
    result = set_issue_stage(
        args.number,
        args.repo,
        args.stage,
        comment=args.comment,
        dry_run=args.dry_run,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("claim", help="Assign @me and set Stage=Claimed")
    c.add_argument("number", type=int)
    c.add_argument("--repo", default="backend", help="backend|gallery")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_claim)

    s = sub.add_parser("set-stage", help="Move Project Stage for an issue")
    s.add_argument("number", type=int)
    s.add_argument(
        "--stage",
        required=True,
        choices=sorted(STAGE_OPTIONS.keys()),
    )
    s.add_argument("--repo", default="backend")
    s.add_argument("--comment", default=None, help="Required when --stage blocked")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_set_stage)

    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
