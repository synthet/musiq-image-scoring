#!/usr/bin/env python3
"""Compute checkbox metrics across project TODO files.

Usage:
    python scripts/analysis/todo_metrics.py
"""

from __future__ import annotations

import re
from pathlib import Path

TARGET_FILES = (
    Path("TODO.md"),
    Path("docs/project/TODO.md"),
    Path("docs/features/planned/embeddings/TODO.md"),
    Path("docs/reference/api/TODO.md"),
)

CHECKBOX_PATTERN = re.compile(r"^\s*-\s*\[([ xX])\]", re.MULTILINE)


def count_checkboxes(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    open_count = 0
    done_count = 0

    for match in CHECKBOX_PATTERN.finditer(text):
        marker = match.group(1)
        if marker.lower() == "x":
            done_count += 1
        else:
            open_count += 1

    return open_count, done_count


def main() -> None:
    for target in TARGET_FILES:
        open_count, done_count = count_checkboxes(target)
        total = open_count + done_count
        print(f"{target}: open={open_count}, done={done_count}, total={total}")


if __name__ == "__main__":
    main()
