#!/usr/bin/env python3
"""Lint README/docs setup files for dependency version literals that diverge from canonical requirements.

This intentionally checks only quick-start/setup docs where stale literals cause copy/paste install drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_REQUIREMENTS = [
    REPO_ROOT / "requirements" / "requirements_wsl_gpu.txt",
    REPO_ROOT / "requirements.txt",
    REPO_ROOT / "requirements" / "requirements_simple.txt",
]

TARGET_FILES = [
    REPO_ROOT / "README.md",
    *sorted((REPO_ROOT / "docs" / "setup").glob("*.md")),
]

REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(==|~=|>=|<=|>|<)\s*([^\s#;]+)")
DOC_SPEC_RE = re.compile(r"\b([A-Za-z0-9_.-]+)\s*(==|~=|>=|<=|>|<)\s*([0-9][A-Za-z0-9_.-]*)\b")


def normalize_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def load_canonical_specs() -> dict[str, set[str]]:
    specs: dict[str, set[str]] = {}
    for req_file in CANONICAL_REQUIREMENTS:
        if not req_file.exists():
            continue
        for raw_line in req_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = REQ_RE.match(line)
            if not m:
                continue
            pkg, op, ver = m.groups()
            specs.setdefault(normalize_name(pkg), set()).add(f"{op}{ver}")
    return specs


def main() -> int:
    canonical = load_canonical_specs()
    errors: list[str] = []

    for target in TARGET_FILES:
        rel = target.relative_to(REPO_ROOT)
        for line_no, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for pkg, op, ver in DOC_SPEC_RE.findall(line):
                pkg_norm = normalize_name(pkg)
                spec = f"{op}{ver}"
                known_specs = canonical.get(pkg_norm)
                if not known_specs:
                    continue
                if spec not in known_specs:
                    allowed = ", ".join(sorted(known_specs))
                    errors.append(
                        f"{rel}:{line_no}: {pkg}{spec} diverges from canonical requirements ({allowed})"
                    )

    if errors:
        print("Dependency version lint failed:\n")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Dependency version lint passed for README/docs setup files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
