#!/usr/bin/env python3
"""Sync assistant trees between `.cursor/` and `.claude/`.

image-scoring-backend uses **`.cursor/` as canonical** (default direction: cursor-to-claude).
synthet-code-framework uses `.claude/` as canonical (direction: claude-to-cursor).

Mappings (cursor-to-claude):
  .cursor/commands/*.md        -> .claude/commands/*.md       (verbatim)
  .cursor/skills/<n>/**        -> .claude/skills/<n>/**       (verbatim, whole dir)
  .cursor/agents/*.md          -> .claude/agents/*.md         (verbatim)
  .cursor/rules/<n>.mdc        -> .claude/rules/<n>.md          (extension change; content kept)

Only rules in MIRROR_RULES are synced cursor-to-claude (partial mirror policy).

Hand-authored files (mcp.example.json, Cursor-only skills) are left untouched.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Rules mirrored to Claude per .agent/AGENT_INFRA_INVENTORY.md
MIRROR_RULES = {
    "agent-canonical-sources",
    "agent-memory",
    "backlog-queue",
    "documentation",
    "external-cli-subagents",
    "image-scoring-mcp",
    "pytest-e2e-vocabulary",
    "python-wsl-webapp-env",
    "safety-and-secrets",
    "sdlc-core",
}

SUBDIRS = [
    ("commands", "commands", "files"),
    ("skills", "skills", "tree"),
    ("agents", "agents", "files"),
    ("rules", "rules", "rules"),
]


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_tree(src: Path, dst: Path) -> None:
    for child in sorted(src.iterdir()):
        if child.is_dir():
            shutil.copytree(child, dst / child.name)
        else:
            shutil.copy2(child, dst / child.name)


def sync_cursor_to_claude(check: bool = False) -> int:
    changes: list[str] = []
    src_root = ROOT / ".cursor"
    dst_root = ROOT / ".claude"

    for src_name, dst_name, mode in SUBDIRS:
        src = src_root / src_name
        dst = dst_root / dst_name
        if not src.is_dir():
            continue

        if mode == "rules":
            if check:
                for mdc in sorted(src.glob("*.mdc")):
                    if mdc.stem not in MIRROR_RULES:
                        continue
                    target = dst / f"{mdc.stem}.md"
                    if not target.exists():
                        changes.append(f"missing in .claude: rules/{target.name}")
                    elif target.read_text(encoding="utf-8") != mdc.read_text(encoding="utf-8"):
                        changes.append(f"differs: rules/{target.name}")
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for mdc in sorted(src.glob("*.mdc")):
                if mdc.stem not in MIRROR_RULES:
                    continue
                (dst / f"{mdc.stem}.md").write_text(
                    mdc.read_text(encoding="utf-8"), encoding="utf-8"
                )
            print(f"synced rules ({len(MIRROR_RULES)} mirrored) -> .claude/rules")
            continue

        if check:
            changes.extend(_diff(src, dst, mode, dst_name))
            continue

        _reset_dir(dst)
        if mode == "tree":
            _copy_tree(src, dst)
        else:
            for md in sorted(src.glob("*.md")):
                shutil.copy2(md, dst / md.name)
        print(f"synced {src_name} -> .claude/{dst_name}")

    if check:
        if changes:
            print("OUT OF SYNC (.cursor/ canonical vs .claude/ mirror):")
            for c in changes:
                print(f"  {c}")
            return 1
        print("assistant trees in sync")
        return 0
    return 0


def sync_claude_to_cursor(check: bool = False) -> int:
    """Framework-original direction: .claude/ -> .cursor/."""
    changes: list[str] = []
    src_root = ROOT / ".claude"
    dst_root = ROOT / ".cursor"

    for src_name, dst_name, mode in SUBDIRS:
        src = src_root / src_name
        dst = dst_root / dst_name
        if not src.is_dir():
            continue

        if mode == "rules":
            if check:
                for md in sorted(src.glob("*.md")):
                    target = dst / f"{md.stem}.mdc"
                    if not target.exists():
                        changes.append(f"missing in .cursor: rules/{target.name}")
                    elif target.read_text(encoding="utf-8") != md.read_text(encoding="utf-8"):
                        changes.append(f"differs: rules/{target.name}")
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for md in sorted(src.glob("*.md")):
                (dst / f"{md.stem}.mdc").write_text(
                    md.read_text(encoding="utf-8"), encoding="utf-8"
                )
            print(f"synced rules -> .cursor/rules")
            continue

        if check:
            changes.extend(_diff(src, dst, mode, dst_name, rules_ext=".mdc"))
            continue

        _reset_dir(dst)
        if mode == "tree":
            _copy_tree(src, dst)
        else:
            for md in sorted(src.glob("*.md")):
                shutil.copy2(md, dst / md.name)
        print(f"synced {src_name} -> .cursor/{dst_name}")

    if check:
        if changes:
            print("OUT OF SYNC:")
            for c in changes:
                print(f"  {c}")
            return 1
        print("in sync")
    return 0


def _expected_name(p: Path, mode: str, rules_ext: str = ".md") -> str:
    if mode == "rules":
        return f"{p.stem}{rules_ext}"
    return p.name


def _diff(src: Path, dst: Path, mode: str, dst_label: str, rules_ext: str = ".md") -> list[str]:
    out: list[str] = []
    if mode == "tree":
        src_names = {c.name for c in src.iterdir()}
        dst_names = {c.name for c in dst.iterdir()} if dst.is_dir() else set()
        for name in sorted(src_names - dst_names):
            out.append(f"missing in mirror: {dst_label}/{name}")
        for name in sorted(dst_names - src_names):
            out.append(f"stale in mirror: {dst_label}/{name}")
        for name in sorted(src_names & dst_names):
            s = src / name
            d = dst / name
            if s.is_dir() and d.is_dir():
                for sub in sorted(s.rglob("*")):
                    if sub.is_file():
                        rel = sub.relative_to(s)
                        mirror = d / rel
                        if not mirror.exists():
                            out.append(f"missing in mirror: {dst_label}/{name}/{rel}")
                        elif mirror.read_text(encoding="utf-8") != sub.read_text(encoding="utf-8"):
                            out.append(f"differs: {dst_label}/{name}/{rel}")
        return out
    pat = "*.md"
    for f in sorted(src.glob(pat)):
        target = dst / _expected_name(f, mode, rules_ext)
        if not target.exists():
            out.append(f"missing in mirror: {dst_label}/{target.name}")
        elif target.read_text(encoding="utf-8") != f.read_text(encoding="utf-8"):
            out.append(f"differs: {dst_label}/{target.name}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync .cursor/ and .claude/ assistant trees")
    ap.add_argument(
        "--direction",
        choices=("cursor-to-claude", "claude-to-cursor"),
        default="cursor-to-claude",
        help="Sync direction (default: cursor-to-claude for this repo)",
    )
    ap.add_argument("--check", action="store_true", help="Report drift without writing (CI gate)")
    args = ap.parse_args()

    if args.direction == "cursor-to-claude":
        return sync_cursor_to_claude(check=args.check)
    return sync_claude_to_cursor(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
