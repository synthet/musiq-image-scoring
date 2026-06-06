#!/usr/bin/env python3
"""Warn on stale MCP vocabulary in agent-facing docs (PR2 hygiene)."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_GLOBS = (
    ".agent",
    ".claude",
    ".cursor",
    "docs",
    "AGENTS.md",
    "CLAUDE.md",
)

SKIP_GLOBS = (
    "CHANGELOG.md",
    "docs/archive/**",
    "notebooklm_docs.md",
    "docs/technical/MCP_SEARCH_DISPATCH_PR1_SUMMARY.md",
)

STALE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("imgscore-py-*", re.compile(r"imgscore-py[-_]")),
    ("imgscore-el-gallery", re.compile(r"imgscore-el-gallery")),
    ("image-scoring-backend-stdio", re.compile(r"image-scoring-backend-(stdio|webui|postgres)")),
    ("is-ga-*", re.compile(r"\bis-ga-")),
    ("ga_find", re.compile(r"\bga_find\b")),
    ("mcp__imgscore-py", re.compile(r"mcp__imgscore-py")),
    ("router-first primary (deprecated phrase)", re.compile(r"Router-first \(all agents\)", re.I)),
]


def _should_skip(path: Path) -> bool:
    rel = path.as_posix()
    for pat in SKIP_GLOBS:
        if pat.endswith("/**"):
            if rel.startswith(pat[:-3]):
                return True
        elif rel == pat or rel.endswith("/" + pat):
            return True
    return False


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for name in DEFAULT_GLOBS:
        p = ROOT / name
        if p.is_file():
            if not _should_skip(p.relative_to(ROOT)):
                out.append(p)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in {".md", ".mdc", ".json"}:
                    rel = f.relative_to(ROOT)
                    if not _should_skip(rel):
                        out.append(f)
    return sorted(set(out))


def lint_paths(paths: list[Path], *, warn_only: bool = True) -> int:
    hits: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for label, pattern in STALE_PATTERNS:
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line}: {label} ({m.group(0)!r})")

    if hits:
        prefix = "WARN" if warn_only else "ERROR"
        for h in hits:
            print(f"{prefix}: {h}")
        return 0 if warn_only else 1
    print("OK: no stale MCP vocabulary found")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--error", action="store_true", help="Exit 1 when stale terms found")
    args = parser.parse_args()
    return lint_paths(_iter_files(), warn_only=not args.error)


if __name__ == "__main__":
    sys.exit(main())
