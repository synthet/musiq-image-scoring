#!/usr/bin/env python3
"""Apply GitHub backlog inventory: epics, labels, obsolete tiers, project stages.

Idempotent where possible. Run from repo root with gh authenticated.

  python scripts/apply_backlog_inventory.py --dry-run
  python scripts/apply_backlog_inventory.py --apply
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

PROJECT_NODE_ID = "PVT_kwHOAFXgIs4BWC3c"
STAGE_FIELD_ID = "PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0"
STAGE_BACKLOG = "83b7a780"
STAGE_DONE = "73062c96"

BACKEND = "synthet/image-scoring-backend"
GALLERY = "synthet/image-scoring-gallery"


def gh_json(*args: str) -> Any:
    res = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}\n{res.stderr}")
    return json.loads(res.stdout or "null")


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


def issue_node_id(repo: str, number: int) -> str:
    owner, name = repo.split("/")
    data = gh_json(
        "api", "graphql", "-f",
        f"query=query {{ repository(owner:\"{owner}\", name:\"{name}\") "
        f"{{ issue(number:{number}) {{ id }} }} }}",
    )
    node = data["data"]["repository"]["issue"]
    if not node:
        raise ValueError(f"Issue #{number} not found in {repo}")
    return node["id"]


def add_sub_issue(parent_repo: str, parent_num: int, child_repo: str, child_num: int, dry_run: bool) -> None:
    if parent_repo != child_repo:
        print(f"  SKIP cross-repo sub-issue: {parent_repo}#{parent_num} <- {child_repo}#{child_num}")
        return
    parent_id = issue_node_id(parent_repo, parent_num)
    child_id = issue_node_id(child_repo, child_num)
    mutation = (
        "mutation($parent:ID!,$child:ID!){"
        "addSubIssue(input:{issueId:$parent,subIssueId:$child})"
        "{issue{id} subIssue{id number}}}"
    )
    if dry_run:
        print(f"  DRY addSubIssue {parent_repo}#{parent_num} <- #{child_num}")
        return
    gh_json(
        "api", "graphql",
        "-f", f"query={mutation}",
        "-f", f"parent={parent_id}",
        "-f", f"child={child_id}",
    )
    time.sleep(0.3)


def create_epic(
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    dry_run: bool,
) -> int | None:
    label_args = [arg for lbl in labels for arg in ("--label", lbl)]
    if dry_run:
        print(f"  DRY create epic [{repo}] {title}")
        return None
    url = gh_run(
        "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        *label_args,
    )
    # gh prints URL last line
    number = int(url.rstrip("/").split("/")[-1])
    gh_run("project", "item-add", "1", "--owner", "synthet", "--url", url)
    time.sleep(0.5)
    return number


def edit_issue(repo: str, number: int, *, labels_add: list[str] | None = None,
               labels_remove: list[str] | None = None, body: str | None = None,
               title: str | None = None, dry_run: bool = True) -> None:
    cmd = ["issue", "edit", str(number), "--repo", repo]
    if title:
        cmd.extend(["--title", title])
    if body is not None:
        cmd.extend(["--body", body])
    for lbl in labels_add or []:
        cmd.extend(["--add-label", lbl])
    for lbl in labels_remove or []:
        cmd.extend(["--remove-label", lbl])
    if dry_run:
        print(f"  DRY edit {repo}#{number}: add={labels_add} remove={labels_remove}")
        return
    gh_run(*cmd)
    time.sleep(0.25)


def close_issue(repo: str, number: int, comment: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  DRY close {repo}#{number}")
        return
    gh_run("issue", "close", str(number), "--repo", repo, "--comment", comment)
    time.sleep(0.3)


def comment_issue(repo: str, number: int, body: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  DRY comment {repo}#{number}")
        return
    gh_run("issue", "comment", str(number), "--repo", repo, "--body", body)
    time.sleep(0.25)


_PROJECT_ITEMS_CACHE: list[dict] | None = None


def _load_project_items() -> list[dict]:
    global _PROJECT_ITEMS_CACHE
    if _PROJECT_ITEMS_CACHE is None:
        data = gh_json(
            "project", "item-list", "1", "--owner", "synthet",
            "--format", "json", "--limit", "300",
        )
        _PROJECT_ITEMS_CACHE = data.get("items", [])
    return _PROJECT_ITEMS_CACHE


def project_item_id(repo: str, number: int) -> str | None:
    short = repo.split("/")[-1]
    for it in _load_project_items():
        c = it.get("content") or {}
        if c.get("number") == number and short in (c.get("repository") or ""):
            return it["id"]
    return None


def set_project_stage(repo: str, number: int, stage_option: str, dry_run: bool) -> None:
    item_id = project_item_id(repo, number)
    if not item_id:
        print(f"  WARN no project item for {repo}#{number}")
        return
    if dry_run:
        print(f"  DRY stage {repo}#{number} -> {stage_option}")
        return
    gh_run(
        "project", "item-edit",
        "--id", item_id,
        "--project-id", PROJECT_NODE_ID,
        "--field-id", STAGE_FIELD_ID,
        "--single-select-option-id", stage_option,
    )
    time.sleep(0.25)


EPIC_BODY_TEMPLATE = """## Goal
{goal}

## Canonical references
{refs}

## Sub-issues
Linked via GitHub sub-issues (same repo) or cross-repo URLs in child bodies.

## Out of scope / obsolete
{obsolete}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Execute changes (default is dry-run)")
    parser.add_argument("--phase", choices=["epics", "labels", "obsolete", "bodies", "all"], default="all")
    args = parser.parse_args()
    dry_run = not args.apply

    print(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'} phase={args.phase}")

    epic_cache: dict[str, int] = {}

    if args.phase in ("epics", "all"):
        print("\n=== Create new epics ===")
        new_epics = [
            (
                BACKEND,
                "Epic: Architecture hardening (post architecture_review)",
                EPIC_BODY_TEMPLATE.format(
                    goal="Harden cross-cutting architecture after architecture_review: docs truth, job lifecycle, gallery contracts, API split, contract drift gates, diagnostics consolidation.",
                    refs="- docs/CANONICAL_SOURCES.md\n- docs/technical/AGENT_COORDINATION.md\n- docs/technical/API_CONTRACT.md",
                    obsolete="Firebird as primary engine; monolithic undocumented API.",
                ),
                ["type:epic", "priority:p1", "area:python", "area:docs", "cross-repo"],
                list(range(169, 176)),
            ),
            (
                BACKEND,
                "Epic: Embedding Atlas UX polish",
                EPIC_BODY_TEMPLATE.format(
                    goal="Polish React Embedding Atlas at `/ui/` (Cosmograph, scope wiring, inspector cross-links).",
                    refs="- frontend/src/features/embedding-atlas/\n- docs/technical/PIPELINE_TERMINOLOGY.md",
                    obsolete="Gradio-only embedding map tab.",
                ),
                ["type:epic", "priority:p2", "area:gradio"],
                list(range(134, 143)),
            ),
            (
                BACKEND,
                "Epic: RAW preview verification (manual QA checklist)",
                EPIC_BODY_TEMPLATE.format(
                    goal="Manual QA checklist for RAW preview via `/api/raw-preview` and operator/React surfaces.",
                    refs="- docs/features/implemented/ (RAW/export)\n- modules/api.py (raw-preview routes)",
                    obsolete="Gradio-only RAW preview assumptions from legacy TODO.",
                ),
                ["type:epic", "priority:p1", "area:python", "type:test"],
                list(range(104, 109)),
            ),
            (
                BACKEND,
                "Epic: AI culling XMP / Lightroom verification",
                EPIC_BODY_TEMPLATE.format(
                    goal="Verify AI culling XMP output (ratings, labels, pick/reject) in Lightroom Cloud/Classic.",
                    refs="- docs/technical/PIPELINE_TERMINOLOGY.md (culling phase)\n- modules/clustering.py / selection",
                    obsolete="N/A",
                ),
                ["type:epic", "priority:p1", "area:python", "type:test"],
                [109, 110],
            ),
            (
                BACKEND,
                "Epic: Run lifecycle, recovery, and phase-status bugs",
                EPIC_BODY_TEMPLATE.format(
                    goal="Fix runner short-circuits, reconciler cancel semantics, missing phase rows, and audit gaps.",
                    refs="- docs/technical/RUNS_QUEUE_AND_RESTART.md\n- modules/pipeline_orchestrator.py",
                    obsolete="N/A — overlaps Architecture #170 for lifecycle centralization.",
                ),
                ["type:epic", "priority:p0", "area:python", "area:db"],
                [156, 157, 161, 163, 164, 165, 166],
            ),
            (
                BACKEND,
                "Epic: Stale codex branch triage (2026-05)",
                EPIC_BODY_TEMPLATE.format(
                    goal="Triage or delete stale `codex/*` remote branches ahead of master.",
                    refs="- scripts/ (branch inventory)",
                    obsolete="N/A",
                ),
                ["type:epic", "priority:p3", "type:chore", "area:python"],
                list(range(192, 198)),
            ),
            (
                GALLERY,
                "Epic: Gallery embeddings and similarity UI",
                EPIC_BODY_TEMPLATE.format(
                    goal="Electron/React surfaces for embeddings map, outliers, smart stack cover, tag propagation.",
                    refs="- docs/features/planned/embeddings/\n- electron/apiService.ts",
                    obsolete="Gradio IPC/WebSocket bridge as primary integration.",
                ),
                ["type:epic", "priority:p1", "area:electron", "cross-repo"],
                list(range(73, 80)),
            ),
            (
                GALLERY,
                "Epic: Cross-repo API and contract hardening",
                EPIC_BODY_TEMPLATE.format(
                    goal="OpenAPI drift gates, generated types, API DB transaction semantics, main-process split.",
                    refs="- docs/CANONICAL_SOURCES.md (backend)\n- npm run contract:check\n- Backend counterpart: #174",
                    obsolete="Hand-maintained apiTypes without OpenAPI sync.",
                ),
                ["type:epic", "priority:p1", "area:electron", "cross-repo"],
                list(range(87, 92)),
            ),
            (
                GALLERY,
                "Epic: Stale codex branch triage (2026-05)",
                EPIC_BODY_TEMPLATE.format(
                    goal="Triage or delete stale `codex/*` remote branches in image-scoring-gallery.",
                    refs="- package.json scripts",
                    obsolete="N/A",
                ),
                ["type:epic", "priority:p3", "type:chore", "area:electron"],
                list(range(103, 107)),
            ),
        ]

        for repo, title, body, labels, children in new_epics:
            key = f"{repo}:{title}"
            num = create_epic(repo, title, body, labels, dry_run)
            if num:
                epic_cache[key] = num
                print(f"  Created {repo}#{num}: {title}")
                for child in children:
                    add_sub_issue(repo, num, repo, child, dry_run)

    if args.phase in ("epics", "all"):
        print("\n=== Formalize existing epics ===")
        existing = [
            (BACKEND, 118, list(range(150, 156))),
            (BACKEND, 143, list(range(144, 150))),
            (BACKEND, 180, list(range(181, 192))),
            (GALLERY, 94, list(range(95, 103))),
        ]
        for repo, parent, children in existing:
            edit_issue(repo, parent, labels_add=["type:epic"], dry_run=dry_run)
            for child in children:
                add_sub_issue(repo, parent, repo, child, dry_run)
        if not dry_run:
            comment_issue(
                BACKEND, 180,
                "Cross-repo epic counterpart: https://github.com/synthet/image-scoring-gallery/issues/94",
                dry_run=False,
            )
            comment_issue(
                GALLERY, 94,
                "Cross-repo epic counterpart: https://github.com/synthet/image-scoring-backend/issues/180",
                dry_run=False,
            )
            comment_issue(
                BACKEND, 143,
                "Cross-repo feature counterpart: https://github.com/synthet/image-scoring-gallery/issues/83",
                dry_run=False,
            )
            comment_issue(
                GALLERY, 83,
                "Cross-repo epic parent: https://github.com/synthet/image-scoring-backend/issues/143",
                dry_run=False,
            )
            # Link gallery contract epic to backend #174
            for key, num in epic_cache.items():
                if "Cross-repo API" in key and num:
                    comment_issue(
                        GALLERY, num,
                        "Backend counterpart: https://github.com/synthet/image-scoring-backend/issues/174",
                        dry_run=False,
                    )

    if args.phase in ("labels", "all"):
        print("\n=== Label hygiene ===")
        arch_labels = {
            169: ["area:docs", "priority:p1", "type:chore"],
            170: ["area:python", "priority:p1", "type:refactor"],
            171: ["area:db", "area:python", "priority:p1", "type:refactor", "cross-repo"],
            172: ["area:db", "area:python", "priority:p1", "type:refactor", "cross-repo"],
            173: ["area:python", "priority:p2", "type:refactor"],
            174: ["area:docs", "area:python", "priority:p2", "type:test", "cross-repo"],
            175: ["area:python", "priority:p2", "type:refactor"],
        }
        for num, labels in arch_labels.items():
            edit_issue(BACKEND, num, labels_add=labels, dry_run=dry_run)

        dup_remove = list(range(134, 141)) + [156, 157, 161, 163, 164, 165, 166]
        for num in dup_remove:
            labels = ["bug"] if num >= 156 else ["enhancement"]
            edit_issue(BACKEND, num, labels_remove=labels, dry_run=dry_run)

        edit_issue(GALLERY, 73, labels_remove=["area:gradio"], dry_run=dry_run)

    if args.phase in ("obsolete", "all"):
        print("\n=== Obsolete tier 1 (close) ===")
        close_issue(
            BACKEND, 145,
            "Closing: Postgres-only policy for new schema work; Firebird DDL not planned. "
            "See docs/planning/models/TECHNICAL_FAILURE_DETECTION_PLAN.md and docs/log.md (2026-05 Firebird marker retirement).",
            dry_run,
        )
        if not dry_run:
            set_project_stage(BACKEND, 145, STAGE_DONE, dry_run=False)

        # Create gallery issues for mis-filed backend #122/#123 then close backend copies
        for backend_num, gallery_title, gallery_body in [
            (
                122,
                "Gallery themes and customization — user-selectable color themes",
                "## Goal\nUser-selectable color themes in Driftara Gallery (Electron/React).\n\n## Canonical references\n- src/ styling\n\n## Supersedes\nBackend #122 (mis-filed under Gradio).",
            ),
            (
                123,
                "Keyboard navigation — full keyboard support for gallery navigation",
                "## Goal\nFull keyboard navigation in Driftara Gallery grid and viewer.\n\n## Canonical references\n- src/components/\n\n## Supersedes\nBackend #123 (mis-filed under Gradio).",
            ),
        ]:
            gnum = create_epic(
                GALLERY,
                gallery_title,
                gallery_body,
                ["area:electron", "priority:p3", "type:feature"],
                dry_run,
            )
            if gnum and not dry_run:
                close_issue(
                    BACKEND, backend_num,
                    f"Closed as mis-filed: gallery UX belongs in image-scoring-gallery. "
                    f"Continued as https://github.com/synthet/image-scoring-gallery/issues/{gnum}",
                    dry_run=False,
                )
                set_project_stage(BACKEND, backend_num, STAGE_DONE, dry_run=False)

        print("\n=== Obsolete tier 2 (status:obsolete) ===")
        tier2_backend = {
            117: "Superseded by React Embedding Atlas (`/ui/`) and REST `/api/similarity/*`.",
            102: "Operator-only Gradio `/app` scope; primary product UI is React `/ui/`. See docs/features/planned/ux-ui-implementation-plan.md.",
            124: "Icebox: video scoring not on current roadmap.",
            125: "Icebox: real-time camera assessment.",
            126: "Icebox: mobile app.",
            127: "Icebox: deployable web service packaging.",
            128: "Icebox: Lightroom Classic plugin.",
            129: "Icebox: Capture One workflow.",
            130: "Icebox: Photo Mechanic integration.",
        }
        for num, reason in tier2_backend.items():
            edit_issue(BACKEND, num, labels_add=["status:obsolete"], dry_run=dry_run)
            if not dry_run:
                set_project_stage(BACKEND, num, STAGE_BACKLOG, dry_run=False)

        edit_issue(GALLERY, 73, labels_add=["status:obsolete"], dry_run=dry_run)
        if not dry_run:
            set_project_stage(GALLERY, 73, STAGE_BACKLOG, dry_run=False)
            comment_issue(
                GALLERY, 73,
                "**Status: obsolete** — Superseded by REST `apiService` + backend `/api/*` integration. "
                "IPC/WebSocket Gradio bridge from legacy plan is no longer the primary path.",
                dry_run=False,
            )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
