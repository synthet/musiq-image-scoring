#!/usr/bin/env python3
"""Enforce Ruff lint ratchet for modules/ (stdlib only).

1. F821 (undefined names) must be zero — hard gate (see lint-f821.yml history).
2. Total Ruff findings must not exceed the committed baseline (ratchet).

Exit 0 when clean, 1 on violation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = Path(__file__).with_name("ruff_modules_baseline.json")
FOUND_RE = re.compile(r"Found (\d+) errors?")


def _run_ruff(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ruff", "check", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def count_findings(scope: str) -> int:
    proc = _run_ruff([scope, "--output-format", "concise"])
    # ruff exits 1 when findings exist
    combined = (proc.stdout or "") + (proc.stderr or "")
    m = FOUND_RE.search(combined)
    if m:
        return int(m.group(1))
    if proc.returncode == 0:
        return 0
    print(combined, file=sys.stderr)
    raise SystemExit(f"ruff check failed without parseable count (exit {proc.returncode})")


def check_f821(scope: str) -> None:
    proc = _run_ruff(["--select", "F821", "--output-format", "concise", scope])
    if proc.returncode != 0:
        print(proc.stdout or proc.stderr, file=sys.stderr)
        raise SystemExit("F821 (undefined names) must be zero in modules/")


def load_baseline(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    total_max = data.get("total_max")
    if not isinstance(total_max, int) or total_max < 0:
        raise SystemExit(f"{path}: invalid or missing total_max")
    return total_max


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="JSON file with total_max ceiling",
    )
    parser.add_argument(
        "--scope",
        default="modules/",
        help="Path passed to ruff check (default: modules/)",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Print current total for updating the baseline file (does not write)",
    )
    args = parser.parse_args()

    current = count_findings(args.scope)
    if args.write_baseline:
        print(current)
        return

    check_f821(args.scope)
    ceiling = load_baseline(args.baseline)

    if current > ceiling:
        print(
            f"Ruff findings in {args.scope}: {current} (baseline max {ceiling}).\n"
            "Fix new violations or run `ruff check modules/ --fix` and lower the baseline "
            "in a dedicated PR.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"OK: {current} ruff findings in {args.scope} (baseline max {ceiling}); F821 clean")


if __name__ == "__main__":
    main()
