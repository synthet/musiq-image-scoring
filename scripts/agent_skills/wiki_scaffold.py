#!/usr/bin/env python3
"""Compiled wiki ingest scaffolding harness.

Deterministic glue for /wiki-ingest and docs-wiki:
  - OKF frontmatter stub
  - INDEX.md row append
  - docs/log.md append (## [YYYY-MM-DD] verb | Title)
  - okf_lint wrapper

Source summary, page body, placement judgment, and cross-links stay LLM-shaped.
Human reviews before treating ingest as done.

Usage:
  python scripts/agent_skills/wiki_scaffold.py frontmatter --type Report --title "…" --resource reports/FOO.md
  python scripts/agent_skills/wiki_scaffold.py append-index docs/reports/INDEX.md --link FOO.md --desc "…"
  python scripts/agent_skills/wiki_scaffold.py append-log --verb ingest --title "…"
  python scripts/agent_skills/wiki_scaffold.py lint
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LOG_PATH = DOCS / "log.md"
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@dataclass
class ScaffoldResult:
    ok: bool
    action: str
    path: str = ""
    detail: str = ""


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def render_frontmatter(
    *,
    doc_type: str,
    title: str,
    description: str,
    resource: str,
    tags: list[str],
) -> str:
    tag_list = ", ".join(tags) if tags else "docs"
    lines = [
        "---",
        f"type: {doc_type}",
        f"title: {title}",
        f"description: {description or title}",
        f"resource: {resource}",
        f"tags: [{tag_list}]",
        f"timestamp: {utc_timestamp()}",
        "okf_version: 0.1",
        "---",
        "",
    ]
    return "\n".join(lines)


def append_index_row(index_path: Path, link: str, description: str) -> ScaffoldResult:
    if not index_path.is_file():
        return ScaffoldResult(
            ok=False,
            action="append-index",
            path=str(index_path),
            detail="INDEX.md not found",
        )
    text = index_path.read_text(encoding="utf-8")
    # Avoid duplicate link targets
    link_norm = link.replace("\\", "/")
    if f"]({link_norm})" in text or f"](./{link_norm})" in text:
        return ScaffoldResult(
            ok=True,
            action="append-index",
            path=str(index_path),
            detail="link already present; no change",
        )

    name = Path(link_norm).stem
    display = name.replace("_", " ")
    row = f"| [{display}]({link_norm}) | {description} |"

    # Prefer appending to the last markdown table
    lines = text.splitlines()
    table_end = None
    in_table = False
    for i, line in enumerate(lines):
        if re.match(r"^\|", line):
            in_table = True
            table_end = i
        elif in_table and not line.strip():
            in_table = False
    if table_end is not None:
        lines.insert(table_end + 1, row)
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    else:
        block = (
            "\n\n| Document | Description |\n"
            "|----------|-------------|\n"
            f"{row}\n"
        )
        new_text = text.rstrip() + block
    index_path.write_text(new_text, encoding="utf-8", newline="\n")
    return ScaffoldResult(
        ok=True,
        action="append-index",
        path=str(index_path),
        detail=f"appended row for {link_norm}",
    )


def append_log(verb: str, title: str, body: str = "") -> ScaffoldResult:
    if not LOG_PATH.is_file():
        return ScaffoldResult(
            ok=False,
            action="append-log",
            path=str(LOG_PATH),
            detail="docs/log.md not found",
        )
    today = date.today().isoformat()
    header = f"## [{today}] {verb} | {title}"
    existing = LOG_PATH.read_text(encoding="utf-8")
    if header in existing:
        return ScaffoldResult(
            ok=True,
            action="append-log",
            path=str(LOG_PATH),
            detail="identical header already present; no change",
        )
    # Insert after the first `---` following the intro (top of chronological log)
    entry_lines = [header, ""]
    if body.strip():
        entry_lines.append(body.strip())
        entry_lines.append("")
    entry = "\n".join(entry_lines) + "\n"

    marker = "\n---\n\n"
    idx = existing.find(marker)
    if idx != -1:
        insert_at = idx + len(marker)
        new_text = existing[:insert_at] + entry + existing[insert_at:]
    else:
        new_text = existing.rstrip() + "\n\n" + entry
    LOG_PATH.write_text(new_text, encoding="utf-8", newline="\n")
    return ScaffoldResult(
        ok=True,
        action="append-log",
        path=str(LOG_PATH),
        detail=f"appended {header}",
    )


def run_lint(exclude_prefix: str = "archive/") -> ScaffoldResult:
    cmd = [
        sys.executable,
        str(SCRIPTS / "okf_lint.py"),
        "--profile",
        "vexlum",
        "--exclude-prefix",
        exclude_prefix,
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).rstrip()
    return ScaffoldResult(
        ok=proc.returncode == 0,
        action="lint",
        path=str(DOCS),
        detail=out[-2000:] if out else f"exit {proc.returncode}",
    )


def cmd_frontmatter(args: argparse.Namespace) -> int:
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    text = render_frontmatter(
        doc_type=args.type,
        title=args.title,
        description=args.description or "",
        resource=args.resource,
        tags=tags,
    )
    if args.output:
        out = args.output
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        body = args.body or f"# {args.title}\n\n"
        out.write_text(text + body, encoding="utf-8", newline="\n")
        result = ScaffoldResult(
            ok=True, action="frontmatter", path=str(out), detail="wrote stub page"
        )
        print(json.dumps(asdict(result), indent=2))
    else:
        print(text, end="")
    return 0


def cmd_append_index(args: argparse.Namespace) -> int:
    path = args.index if args.index.is_absolute() else ROOT / args.index
    result = append_index_row(path, args.link, args.desc)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def cmd_append_log(args: argparse.Namespace) -> int:
    result = append_log(args.verb, args.title, args.body or "")
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def cmd_lint(args: argparse.Namespace) -> int:
    result = run_lint(args.exclude_prefix)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("frontmatter", help="Print or write OKF frontmatter stub")
    f.add_argument("--type", required=True)
    f.add_argument("--title", required=True)
    f.add_argument("--resource", required=True, help="Repo-relative resource path")
    f.add_argument("--description", default="")
    f.add_argument("--tags", default="docs", help="Comma-separated tags")
    f.add_argument("-o", "--output", type=Path, default=None)
    f.add_argument("--body", default=None, help="Markdown body when using -o")
    f.set_defaults(func=cmd_frontmatter)

    i = sub.add_parser("append-index", help="Append a row to an INDEX.md table")
    i.add_argument("index", type=Path)
    i.add_argument("--link", required=True)
    i.add_argument("--desc", required=True)
    i.set_defaults(func=cmd_append_index)

    lg = sub.add_parser("append-log", help="Append docs/log.md entry")
    lg.add_argument("--verb", default="ingest", help="ingest|edit|created|…")
    lg.add_argument("--title", required=True)
    lg.add_argument("--body", default="")
    lg.set_defaults(func=cmd_append_log)

    lint = sub.add_parser("lint", help="Run okf_lint vexlum profile")
    lint.add_argument("--exclude-prefix", default="archive/")
    lint.set_defaults(func=cmd_lint)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
