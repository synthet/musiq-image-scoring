#!/usr/bin/env python3
"""
One-shot local health check for image-scoring-backend.

Run from repo root (prefer WSL + ~/.venvs/tf per docs/DEVELOPMENT.md):

    python scripts/doctor.py
    python scripts/doctor.py --no-gpu
    python scripts/doctor.py --json

Exit code: 0 on PASS or WARN, 1 on FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    root = _repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    os.chdir(root)

    parser = argparse.ArgumentParser(description="Vexlum Scoring backend health check")
    parser.add_argument("--no-gpu", action="store_true", help="Skip torch/CUDA probe")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")
    args = parser.parse_args()

    from modules.doctor_cli import format_report, run_doctor

    result = run_doctor(include_gpu=not args.no_gpu)
    if args.json:
        out = {
            "overall": result["overall"],
            "failures": result["failures"],
            "warnings": result["warnings"],
            "database_engine_info": result.get("database_engine_info"),
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print(format_report(result))

    return 0 if result["overall"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
