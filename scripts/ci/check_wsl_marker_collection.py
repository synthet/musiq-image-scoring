#!/usr/bin/env python3
"""Guard: ensure WSL-marked tests are still discoverable by pytest.

This script intentionally uses `pytest -m wsl --collect-only` and fails when
that command yields zero collected tests.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _wsl_marked_test_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "pytest.mark.wsl" in text:
            files.append(path.as_posix())
    return files


def main() -> int:
    test_files = _wsl_marked_test_files(Path("tests"))
    if not test_files:
        print("[error] No files contain pytest.mark.wsl under tests/.")
        return 1

    cmd = [sys.executable, "-m", "pytest", "-m", "wsl", "--collect-only", "-q", *test_files]
    print(f"[run] {' '.join(cmd)}")
    proc = subprocess.run(cmd, text=True, capture_output=True)

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)

    collected = 0
    combined = f"{proc.stdout}\n{proc.stderr}"
    match = re.search(r"(\d+)\s+tests?\s+collected", combined)
    if match:
        collected = int(match.group(1))
    elif "no tests collected" in combined.lower():
        collected = 0

    if collected == 0:
        print("[error] pytest -m wsl --collect-only discovered zero tests.")
        return 1

    print(f"[ok] pytest collected {collected} wsl-marked tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
