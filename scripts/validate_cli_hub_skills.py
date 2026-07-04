#!/usr/bin/env python3
"""Validate consolidated CLI hub skills under .cursor/skills/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".cursor" / "skills"
LEGACY_ROOT = ROOT / "skills"

HUB_SKILLS = [
    "agent-cli-hub",
    "agent-search",
    "agent-git-workflows",
    "agent-data-config",
    "agent-dev-tooling",
    "agent-platform-tooling",
    "mcp-code-intelligence",
]

HUB_REFERENCES = [
    "install-blocks.md",
    "bounded-output-patterns.md",
    "commands-requiring-confirmation.md",
    "windows-wsl-split.md",
]

TOPIC_HEADINGS = [
    "## Purpose",
    "## When to use",
    "## Required tools",
    "## Common commands",
    "## Agent-safe patterns",
    "## Verification checklist",
]

SEARCH_EXTRA = [
    SKILLS / "agent-search" / "references" / "tool-selection.md",
]


def _legacy_skills_dir_problem() -> str | None:
    if not LEGACY_ROOT.is_dir():
        return None
    legacy_md = list(LEGACY_ROOT.glob("*.md"))
    if legacy_md:
        return f"repo-root skills/*.md still exists ({LEGACY_ROOT}) — migrate to .cursor/skills/"
    return None


def main() -> int:
    errors: list[str] = []
    legacy = _legacy_skills_dir_problem()
    if legacy:
        errors.append(legacy)

    refs_dir = SKILLS / "agent-cli-hub" / "references"
    for name in HUB_REFERENCES:
        p = refs_dir / name
        if not p.is_file():
            errors.append(f"missing {p.relative_to(ROOT).as_posix()}")

    for extra in SEARCH_EXTRA:
        if not extra.is_file():
            errors.append(f"missing {extra.relative_to(ROOT).as_posix()}")

    for name in HUB_SKILLS:
        skill_md = SKILLS / name / "SKILL.md"
        rel = skill_md.relative_to(ROOT).as_posix()
        if not skill_md.is_file():
            errors.append(f"missing {rel}")
            continue
        text = skill_md.read_text(encoding="utf-8")
        if name != "agent-cli-hub":
            headings = list(TOPIC_HEADINGS)
            if name == "mcp-code-intelligence":
                headings = [h for h in headings if h != "## Common commands"]
                if "## Recommended tiers" not in text:
                    errors.append(f"{rel}: missing '## Recommended tiers'")
            for heading in headings:
                if heading.lower() not in text.lower():
                    errors.append(f"{rel}: missing heading like {heading!r}")

    if errors:
        print("CLI hub skills validation FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"OK: {len(HUB_SKILLS)} CLI hub skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
