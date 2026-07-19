#!/usr/bin/env python3
"""Compiled /pr-ready hygiene harness.

Deterministic merge-readiness scans the agent used to rediscover every time:
  - dirty-tree forbidden paths
  - secret-ish patterns in staged/unstaged diff
  - optional fast lint/test gate
  - PR template skeleton fill from git metadata

Narrative Summary / Motivation remain LLM-shaped. Commit/push/PR create stay
human-gated.

Usage:
  python scripts/agent_skills/pr_ready_checks.py scan
  python scripts/agent_skills/pr_ready_checks.py scan --run-tests
  python scripts/agent_skills/pr_ready_checks.py skeleton --issue 123 -o .agent/scratch/pr.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / ".github" / "pull_request_template.md"

FORBIDDEN_PATH_GLOBS = (
    re.compile(r"(^|/|\\)tmp(/|\\|$)", re.I),
    re.compile(r"(^|/|\\)__pycache__(/|\\|$)", re.I),
    re.compile(r"(^|/|\\)\.env$", re.I),
    re.compile(r"secrets\.json$", re.I),
    re.compile(r"(^|/|\\)test_[^/\\]+\.py$", re.I),  # root scratch tests
)

SECRET_DIFF_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}"),
    re.compile(r"(?i)(aws_secret|private_key|begin rsa private key)"),
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]+"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)

FAST_TEST_CMD = (
    'python -m pytest -m "not gpu and not db and not ml" '
    "--ignore=tests/test_probe.py -q"
)
FAST_LINT_CMD = "ruff check"


@dataclass
class Finding:
    severity: str
    code: str
    detail: str


@dataclass
class ScanResult:
    ok: bool
    branch: str
    findings: list[Finding] = field(default_factory=list)
    status_paths: list[str] = field(default_factory=list)
    checks: dict[str, dict] = field(default_factory=dict)
    next_actions: list[str] = field(default_factory=list)


def _run(cmd: list[str] | str, shell: bool = False) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        shell=shell,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    # rstrip only — strip() would eat the leading space on git porcelain's first line
    out = ((proc.stdout or "") + (proc.stderr or "")).rstrip()
    return proc.returncode, out


def _git(args: list[str]) -> str:
    code, out = _run(["git", *args])
    if code != 0:
        return ""
    return out


def scan(run_tests: bool, run_lint: bool) -> ScanResult:
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "(unknown)"
    status = _git(["status", "--porcelain"])
    paths = []
    findings: list[Finding] = []
    for line in status.splitlines():
        # Porcelain v1: exactly two status chars, space, then path
        m = re.match(r"^(.{2}) (.+)$", line)
        path = m.group(2) if m else line.strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
        # Only flag root-level test_*.py as scratch, not tests/
        if re.search(r"(^|/|\\)test_[^/\\]+\.py$", path) and not path.replace(
            "\\", "/"
        ).startswith("tests/"):
            findings.append(
                Finding("error", "scratch_test", f"Unwanted root test file: {path}")
            )
        for rx in FORBIDDEN_PATH_GLOBS:
            if rx.pattern.endswith(r"test_[^/\\]+\.py$"):
                continue
            if rx.search(path.replace("\\", "/")):
                findings.append(
                    Finding("error", "forbidden_path", f"Matches forbid pattern: {path}")
                )

    diff = _git(["diff"]) + "\n" + _git(["diff", "--cached"])
    for rx in SECRET_DIFF_PATTERNS:
        if rx.search(diff):
            findings.append(
                Finding(
                    "error",
                    "secret_pattern",
                    f"Diff matches {rx.pattern[:40]}… — inspect before PR",
                )
            )

    checks: dict[str, dict] = {}
    if run_lint:
        code, out = _run(FAST_LINT_CMD, shell=True)
        checks["ruff"] = {
            "exit": code,
            "ok": code == 0,
            "tail": "\n".join(out.splitlines()[-15:]),
        }
        if code != 0:
            findings.append(
                Finding("warn", "lint", "ruff check failed (pre-existing warnings may exist)")
            )

    if run_tests:
        code, out = _run(FAST_TEST_CMD, shell=True)
        checks["pytest_fast"] = {
            "exit": code,
            "ok": code == 0,
            "tail": "\n".join(out.splitlines()[-20:]),
        }
        if code != 0:
            findings.append(Finding("error", "tests", "Fast pytest subset failed"))

    errors = [f for f in findings if f.severity == "error"]
    result = ScanResult(
        ok=not errors,
        branch=branch,
        findings=findings,
        status_paths=paths,
        checks=checks,
        next_actions=[
            "Run validate-implementation when a spec with ACs exists",
            "Fill PR Summary/Motivation (LLM judgment)",
            "Ensure board card Stage=Review and Closes #<n>",
            "Do not create/push PR unless the user asked",
        ],
    )
    return result


def skeleton(issue: int | None, summary: str, testing: str) -> str:
    base = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else ""
    if issue is not None:
        base = re.sub(r"Closes #\s*", f"Closes #{issue}", base, count=1)
    if summary:
        base = base.replace(
            "**What changed:**\n",
            f"**What changed:**\n\n{summary.strip()}\n",
            1,
        )
    if testing:
        # Insert after How to test heading block
        base = base.replace(
            "**Risk / testing notes:**\n",
            f"{testing.strip()}\n\n**Risk / testing notes:**\n",
            1,
        )
    return base


def cmd_scan(args: argparse.Namespace) -> int:
    result = scan(run_tests=args.run_tests, run_lint=args.run_lint)
    payload = asdict(result)
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 1


def cmd_skeleton(args: argparse.Namespace) -> int:
    text = skeleton(args.issue, args.summary or "", args.testing or "")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="Hygiene + optional lint/tests")
    s.add_argument("--run-tests", action="store_true")
    s.add_argument("--run-lint", action="store_true")
    s.set_defaults(func=cmd_scan)

    k = sub.add_parser("skeleton", help="Fill PR template skeleton")
    k.add_argument("--issue", type=int, default=None)
    k.add_argument("--summary", default="")
    k.add_argument("--testing", default="")
    k.add_argument("-o", "--output", type=Path, default=None)
    k.set_defaults(func=cmd_skeleton)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
