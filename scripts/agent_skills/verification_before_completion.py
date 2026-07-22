#!/usr/bin/env python3
"""Compiled harness for verification-before-completion (image-scoring-backend).

Claim→proof catalog and optional command runner. Interpreting whether output
supports a claim is an LLM judgment slot.

Usage (repo root):
  python scripts/agent_skills/verification_before_completion.py --json
  python scripts/agent_skills/verification_before_completion.py --claim assets_synced --run --json
  python scripts/agent_skills/verification_before_completion.py --suite --run --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CLAIM_PROOF_CATALOG: dict[str, dict[str, str]] = {
    "tests_pass": {
        "claim": "Fast unit tests pass",
        "proof": 'python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py -q',
        "not_enough": "Previous run or narrow subset for a broad claim",
    },
    "lint_clean": {
        "claim": "Ruff check clean on touched scope (or default)",
        "proof": "python -m ruff check scripts/agent_skills .cursor/skills --quiet",
        "not_enough": "Formatting only",
    },
    "assets_synced": {
        "claim": "Generated assistant trees in sync",
        "proof": "python scripts/sync_assistant_trees.py --check",
        "not_enough": "Manual copy or assumed sync",
    },
    "frontmatter_ok": {
        "claim": "Agent frontmatter valid",
        "proof": "python scripts/ci/check_agent_frontmatter.py",
        "not_enough": "Spot-check of one file",
    },
    "cli_hub_ok": {
        "claim": "CLI hub skills valid",
        "proof": "python scripts/validate_cli_hub_skills.py",
        "not_enough": "Skipped hub validation",
    },
    "ready_to_commit": {
        "claim": "Ready to commit",
        "proof": "git status --short && git diff --check",
        "not_enough": "Memory of earlier status",
    },
}

SUITE_ORDER = [
    "assets_synced",
    "frontmatter_ok",
    "cli_hub_ok",
]


def _run(cmd: str, cwd: Path, timeout: int = 600) -> dict:
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": cmd,
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": cmd,
            "exit_code": -1,
            "stdout_tail": "",
            "stderr_tail": "timeout",
            "ok": False,
        }


def _emit(data: dict, as_json: bool) -> None:
    if as_json:
        json.dump(data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            print(f"{key}:")
            print(json.dumps(value, indent=2, sort_keys=True))
        else:
            print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", action="append", default=[])
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--suite",
        action="store_true",
        help="Select agent-infra verify claims (sync, frontmatter, cli hub)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result: dict = {
        "repo": str(ROOT),
        "catalog": CLAIM_PROOF_CATALOG,
        "selected": [],
        "runs": [],
        "report": "",
        "notes": [
            "LLM slot: name the claim, read exit code/output, report only supported claims.",
            "Never claim pass from stale runs.",
        ],
    }

    if args.suite:
        ids = list(SUITE_ORDER)
    elif args.claim:
        ids = list(args.claim)
    else:
        result["notes"].append("Pass --claim <id> and/or --suite; use --run to execute proofs.")
        _emit(result, as_json=args.json)
        return 0

    selected = []
    for cid in ids:
        if cid not in CLAIM_PROOF_CATALOG:
            print(f"unknown claim id {cid!r}", file=sys.stderr)
            print(f"known: {', '.join(sorted(CLAIM_PROOF_CATALOG))}", file=sys.stderr)
            return 1
        entry = dict(CLAIM_PROOF_CATALOG[cid])
        entry["id"] = cid
        selected.append(entry)

    result["selected"] = selected

    if args.run:
        for entry in selected:
            result["runs"].append(_run(entry["proof"], ROOT))

    lines = ["## Verification"]
    if result["runs"]:
        for entry, run in zip(selected, result["runs"]):
            mark = "PASS" if run["ok"] else "FAIL"
            lines.append(
                f"- {mark} `{run['command']}` — {entry.get('claim', entry['id'])} "
                f"(exit {run['exit_code']})"
            )
    else:
        for entry in selected:
            lines.append(f"- (not run) `{entry['proof']}` — {entry['claim']}")
    result["report"] = "\n".join(lines)

    _emit(result, as_json=args.json)
    if args.run and any(not r["ok"] for r in result["runs"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
