#!/usr/bin/env python3
"""Compiled harness for commit-and-push (image-scoring-backend).

Inspect status/diff, flag secret paths, optionally run agent-infra verify.
Defaults to dry-run. Commit/push only with --execute plus explicit flags,
and only when the user requested shipping.

Usage (repo root):
  python scripts/agent_skills/commit_and_push.py --json
  python scripts/agent_skills/commit_and_push.py --release --run-verify --json
  python scripts/agent_skills/commit_and_push.py --execute --commit -m "msg" --json
  python scripts/agent_skills/commit_and_push.py --execute --push --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SECRET_PATH_PATTERNS = [
    re.compile(r"(?i)(^|/|\\)\.env(\.|$)"),
    re.compile(r"(?i)secrets\.json$"),
    re.compile(r"(?i)\.pem$"),
    re.compile(r"(?i)id_rsa"),
    re.compile(r"(?i)\.p12$"),
]

VERIFY_COMMANDS = [
    ("sync_check", "python scripts/sync_assistant_trees.py --check"),
    ("frontmatter", "python scripts/ci/check_agent_frontmatter.py"),
    ("cli_hub", "python scripts/validate_cli_hub_skills.py"),
]


def is_secret_path(path: str | Path) -> bool:
    text = str(path).replace("\\", "/")
    return any(p.search(text) for p in SECRET_PATH_PATTERNS)


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


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
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--run-verify", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("-m", "--message", default=None)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    status = _git("status", "--short")
    branch = _git("status", "-sb")
    recent = _git("log", "-5", "--oneline")
    paths = [line[3:].strip() for line in status.splitlines() if line.strip()]
    secret_hits = [p for p in paths if is_secret_path(p)]

    result: dict = {
        "repo": str(ROOT),
        "branch_status": branch,
        "status_short": status,
        "recent_commits": recent.splitlines(),
        "paths": paths,
        "secret_paths": secret_hits,
        "verify_commands": (
            [{"id": i, "command": c} for i, c in VERIFY_COMMANDS] if args.release else []
        ),
        "verify_runs": [],
        "committed": False,
        "pushed": False,
        "notes": [
            "LLM slot: draft Conventional Commit subject/body.",
            "Human: do not --execute/--commit/--push unless the user explicitly asked to ship.",
            "Default is dry-run inspect only.",
        ],
    }

    if secret_hits:
        result["notes"].append(
            f"Blocked secret-looking paths: {secret_hits}. Exclude before staging."
        )

    if args.release and args.run_verify:
        for cid, cmd in VERIFY_COMMANDS:
            proc = subprocess.run(
                cmd, shell=True, cwd=ROOT, capture_output=True, text=True
            )
            result["verify_runs"].append(
                {
                    "id": cid,
                    "command": cmd,
                    "exit_code": proc.returncode,
                    "ok": proc.returncode == 0,
                }
            )
        if any(not r["ok"] for r in result["verify_runs"]):
            result["notes"].append("Verify failed; refusing commit/push.")
            _emit(result, as_json=args.json)
            return 1

    if args.commit or args.push:
        if not args.execute:
            result["notes"].append(
                "Refusing mutate: pass --execute only after explicit user request."
            )
            _emit(result, as_json=args.json)
            return 1
        if secret_hits:
            _emit(result, as_json=args.json)
            return 1

    if args.commit:
        if not args.message:
            result["notes"].append("Commit requires -m/--message.")
            _emit(result, as_json=args.json)
            return 1
        add = subprocess.run(
            ["git", "add", "-A"], cwd=ROOT, capture_output=True, text=True
        )
        if add.returncode != 0:
            result["notes"].append(add.stderr)
            _emit(result, as_json=args.json)
            return 1
        staged = _git("diff", "--cached", "--name-only")
        staged_secrets = [p for p in staged.splitlines() if is_secret_path(p)]
        if staged_secrets:
            subprocess.run(["git", "reset", "HEAD"], cwd=ROOT, capture_output=True)
            result["secret_paths"] = staged_secrets
            result["notes"].append("Reset staging: secret paths present.")
            _emit(result, as_json=args.json)
            return 1
        commit = subprocess.run(
            ["git", "commit", "-m", args.message],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        result["committed"] = commit.returncode == 0
        if commit.returncode != 0:
            result["notes"].append(commit.stderr or commit.stdout)
            _emit(result, as_json=args.json)
            return 1

    if args.push:
        push = subprocess.run(
            ["git", "push"], cwd=ROOT, capture_output=True, text=True
        )
        result["pushed"] = push.returncode == 0
        if push.returncode != 0:
            result["notes"].append(push.stderr or push.stdout)
            _emit(result, as_json=args.json)
            return 1

    _emit(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
