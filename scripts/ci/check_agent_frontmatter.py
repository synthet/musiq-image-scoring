#!/usr/bin/env python3
"""Validate frontmatter contracts for agent assets (stdlib only).

Default canonical tree: `.cursor/` (image-scoring-backend). Use `--canonical claude` for
framework-style repos where `.claude/` is canonical.

Contract enforced (see .agent/SKILL_INVENTORY.md):
  Skills   <canonical>/skills/<name>/SKILL.md  frontmatter required; `name` is the FIRST key and
                                             matches the directory name; non-empty `description`;
                                             names unique across the tree.
  Agents   <canonical>/agents/<name>.md      frontmatter required; `name` matches the file stem;
                                             non-empty `description`; names unique.
  Rules    <canonical>/rules/*               frontmatter required; non-empty `description`.
  Commands <canonical>/commands/<name>.md    an H1 of the form `# /<name> ...` must be present
                                             (frontmatter optional).

All files: no exotic YAML tags (`!!`) in frontmatter — plain scalar keys only.

Exit code 0 when clean, 1 when any violation is found.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(.*)$")


def parse_frontmatter(text: str) -> list[tuple[str, str]] | None:
    """Return ordered (key, value) pairs from a leading YAML frontmatter block, or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    pairs: list[tuple[str, str]] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return pairs
        if not line.strip() or line.startswith((" ", "\t", "-", "#")):
            continue
        m = _KEY_RE.match(line)
        if m:
            pairs.append((m.group(1), m.group(2).strip().strip("\"'")))
    return None


def _value(pairs: list[tuple[str, str]], key: str) -> str | None:
    for k, v in pairs:
        if k == key:
            return v
    return None


def check_no_exotic_yaml(text: str, rel: str, errors: list[str]) -> None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return
    for line in lines[1:]:
        if line.strip() == "---":
            return
        if "!!" in line:
            errors.append(f"{rel}: exotic YAML tag in frontmatter ({line.strip()!r})")


def check_skills(tree: Path, root: Path, errors: list[str]) -> None:
    skills_dir = tree / "skills"
    if not skills_dir.is_dir():
        return
    seen: dict[str, str] = {}
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        rel = skill_md.relative_to(root).as_posix()
        if not skill_md.is_file():
            errors.append(f"{skill_dir.relative_to(root).as_posix()}: missing SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        check_no_exotic_yaml(text, rel, errors)
        pairs = parse_frontmatter(text)
        if pairs is None:
            errors.append(f"{rel}: missing or unterminated YAML frontmatter")
            continue
        if not pairs or pairs[0][0] != "name":
            errors.append(f"{rel}: `name` must be the first frontmatter key")
        name = _value(pairs, "name")
        if name and name != skill_dir.name:
            errors.append(f"{rel}: name {name!r} does not match directory {skill_dir.name!r}")
        if not _value(pairs, "description"):
            errors.append(f"{rel}: missing or empty `description`")
        if name:
            if name in seen:
                errors.append(f"{rel}: duplicate skill name {name!r} (also in {seen[name]})")
            seen[name] = rel


def check_agents(tree: Path, root: Path, errors: list[str]) -> None:
    agents_dir = tree / "agents"
    if not agents_dir.is_dir():
        return
    seen: dict[str, str] = {}
    for md in sorted(agents_dir.glob("*.md")):
        rel = md.relative_to(root).as_posix()
        text = md.read_text(encoding="utf-8")
        check_no_exotic_yaml(text, rel, errors)
        pairs = parse_frontmatter(text)
        if pairs is None:
            errors.append(f"{rel}: missing or unterminated YAML frontmatter")
            continue
        name = _value(pairs, "name")
        if not name:
            errors.append(f"{rel}: missing `name` in frontmatter")
        elif name != md.stem:
            errors.append(f"{rel}: name {name!r} does not match file stem {md.stem!r}")
        if not _value(pairs, "description"):
            errors.append(f"{rel}: missing or empty `description`")
        if name:
            if name in seen:
                errors.append(f"{rel}: duplicate agent name {name!r} (also in {seen[name]})")
            seen[name] = rel


def check_rules(tree: Path, root: Path, errors: list[str], rule_suffix: str) -> None:
    rules_dir = tree / "rules"
    if not rules_dir.is_dir():
        return
    for md in sorted(rules_dir.glob(f"*{rule_suffix}")):
        rel = md.relative_to(root).as_posix()
        text = md.read_text(encoding="utf-8")
        check_no_exotic_yaml(text, rel, errors)
        pairs = parse_frontmatter(text)
        if pairs is None:
            errors.append(f"{rel}: missing or unterminated YAML frontmatter")
            continue
        if not _value(pairs, "description"):
            errors.append(f"{rel}: missing or empty `description`")


def check_commands(tree: Path, root: Path, errors: list[str]) -> None:
    commands_dir = tree / "commands"
    if not commands_dir.is_dir():
        return
    for md in sorted(commands_dir.glob("*.md")):
        rel = md.relative_to(root).as_posix()
        text = md.read_text(encoding="utf-8")
        check_no_exotic_yaml(text, rel, errors)
        expected = f"# /{md.stem}"
        for line in text.splitlines():
            if line.startswith(expected) and (
                len(line) == len(expected) or not line[len(expected)].isalnum()
            ):
                break
        else:
            errors.append(f"{rel}: missing H1 heading starting with {expected!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate agent-asset frontmatter")
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT, help="Repo root (default: this repo)"
    )
    parser.add_argument(
        "--canonical",
        choices=("cursor", "claude"),
        default="cursor",
        help="Which assistant tree is canonical (default: cursor)",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    tree = root / (".cursor" if args.canonical == "cursor" else ".claude")
    rule_suffix = ".mdc" if args.canonical == "cursor" else ".md"

    errors: list[str] = []
    check_skills(tree, root, errors)
    check_agents(tree, root, errors)
    check_rules(tree, root, errors, rule_suffix)
    check_commands(tree, root, errors)

    if errors:
        print(f"Agent frontmatter check FAILED ({len(errors)} problem(s)) on {tree.name}/:")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"Agent frontmatter check passed ({tree.name}/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
