#!/usr/bin/env python3
"""Validate consolidated CLI hub skills under .cursor/skills/."""

from __future__ import annotations

import re
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
    "install-tiers.md",
    "agent-environment.md",
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

DESTRUCTIVE_PATTERNS = re.compile(
    r"(?i)(git reset --hard|git clean -fd|git push --force|rm -rf|docker system prune)",
)


def _legacy_skills_dir_problem() -> str | None:
    if not LEGACY_ROOT.is_dir():
        return None
    legacy_md = list(LEGACY_ROOT.glob("*.md"))
    if legacy_md:
        return f"repo-root skills/*.md still exists ({LEGACY_ROOT}) — migrate to .cursor/skills/"
    return None


def _check_destructive_patterns(rel: str, text: str, errors: list[str]) -> None:
    confirm_idx = text.lower().find("## commands requiring confirmation")
    for match in DESTRUCTIVE_PATTERNS.finditer(text):
        pos = match.start()
        if confirm_idx == -1 or pos < confirm_idx:
            snippet = text[max(0, pos - 40) : pos + 40].replace("\n", " ")
            if "confirmation" not in snippet.lower() and "confirm" not in snippet.lower():
                errors.append(
                    f"{rel}: destructive pattern {match.group()!r} outside confirmation context"
                )


def _check_platform_install(rel: str, text: str, errors: list[str]) -> None:
    lower = text.lower()
    if "## install" not in lower:
        errors.append(f"{rel}: missing '## Install' section")
        return
    install_idx = lower.find("## install")
    install_block = text[install_idx : install_idx + 800].lower()
    has_windows = "windows" in install_block or "winget" in install_block
    has_wsl = "wsl" in install_block or "install-blocks" in install_block
    if not (has_windows and has_wsl):
        errors.append(
            f"{rel}: Install section should cover Windows and WSL (or link install-blocks.md)"
        )


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

    tiers = refs_dir / "install-tiers.md"
    if tiers.is_file():
        tiers_text = tiers.read_text(encoding="utf-8")
        if "Human provisioning" not in tiers_text:
            errors.append(f"{tiers.relative_to(ROOT).as_posix()}: missing Human provisioning section")

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
            _check_destructive_patterns(rel, text, errors)
            if name == "agent-platform-tooling":
                _check_platform_install(rel, text, errors)

    if errors:
        print("CLI hub skills validation FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"OK: {len(HUB_SKILLS)} CLI hub skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
