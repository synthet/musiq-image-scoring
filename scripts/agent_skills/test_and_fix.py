#!/usr/bin/env python3
"""Compiled /test-and-fix harness (Token Shrinker style).

Deterministic steps agents used to rediscover every time:
  - run the canonical fast pytest subset
  - parse failures into nodeid + message fingerprint
  - optional re-run of failed nodeids only
  - emit a Markdown/JSON report skeleton

Root-cause analysis and code/test repairs stay LLM-shaped.
Weakening assertions / skipping tests stays human-gated.

Usage:
  python scripts/agent_skills/test_and_fix.py run
  python scripts/agent_skills/test_and_fix.py run --failed-only
  python scripts/agent_skills/test_and_fix.py run --wsl
  python scripts/agent_skills/test_and_fix.py report -o .agent/scratch/test-fix.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / ".agent" / "scratch" / "test_and_fix_last.json"

FAST_PYTEST_ARGS = [
    "-m",
    "not gpu and not db and not ml",
    "--ignore=tests/test_probe.py",
    "-q",
    "--tb=short",
]

# FAILED tests/path/test_x.py::TestClass::test_name - AssertionError: ...
FAILED_LINE_RE = re.compile(
    r"^(FAILED|ERROR)\s+(\S+?)(?:\s+-\s+(.*))?$"
)
# short traceback last meaningful line
ASSERT_RE = re.compile(r"(AssertionError|Error|Exception|Failed):\s*(.+)$")


@dataclass
class Failure:
    outcome: str
    nodeid: str
    message: str
    fingerprint: str


@dataclass
class RunResult:
    ok: bool
    exit_code: int
    mode: str
    failures: list[Failure] = field(default_factory=list)
    summary_line: str = ""
    tail: str = ""
    next_actions: list[str] = field(default_factory=list)


def fingerprint(nodeid: str, message: str) -> str:
    raw = f"{nodeid}|{message.strip()[:200]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def parse_pytest_output(text: str) -> list[Failure]:
    failures: list[Failure] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = FAILED_LINE_RE.match(line.strip())
        if not m:
            continue
        outcome, nodeid, message = m.group(1), m.group(2), (m.group(3) or "").strip()
        if not message:
            am = ASSERT_RE.search(line)
            if am:
                message = am.group(0)
        fp = fingerprint(nodeid, message)
        if nodeid in seen:
            continue
        seen.add(nodeid)
        failures.append(
            Failure(
                outcome=outcome.lower(),
                nodeid=nodeid,
                message=message,
                fingerprint=fp,
            )
        )
    return failures


def _summary_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        s = line.strip()
        if re.search(r"\d+\s+(passed|failed|error|skipped)", s, re.I):
            return s
    return ""


def _wsl_project_path() -> str:
    # D:\Projects\... → /mnt/d/Projects/...
    drive = ROOT.drive.rstrip(":").lower()
    rest = ROOT.as_posix()
    if ":" in rest:
        rest = rest.split(":", 1)[1]
    return f"/mnt/{drive}{rest}"


def _build_cmd(
    *,
    failed_only: bool,
    nodeids: list[str],
    use_wsl: bool,
    extra: list[str],
) -> list[str]:
    pytest_args = ["python", "-m", "pytest", *FAST_PYTEST_ARGS, *extra]
    if failed_only and nodeids:
        pytest_args.extend(nodeids)
    elif failed_only:
        pytest_args.append("--lf")

    if not use_wsl:
        return pytest_args

    wsl_root = _wsl_project_path()
    inner = (
        f"cd {wsl_root} && "
        f"source ~/.venvs/tf/bin/activate && "
        + " ".join(_shell_quote(a) for a in pytest_args)
    )
    return ["wsl", "-e", "bash", "-lc", inner]


def _shell_quote(arg: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:=+@%,-]+", arg):
        return arg
    return "'" + arg.replace("'", "'\"'\"'") + "'"


def run_tests(
    *,
    failed_only: bool = False,
    use_wsl: bool = False,
    extra: list[str] | None = None,
    prior_nodeids: list[str] | None = None,
) -> RunResult:
    extra = list(extra or [])
    nodeids = list(prior_nodeids or [])
    if failed_only and not nodeids and STATE_PATH.is_file():
        try:
            prior = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            nodeids = [f["nodeid"] for f in prior.get("failures", []) if f.get("nodeid")]
        except (OSError, json.JSONDecodeError, TypeError):
            nodeids = []

    cmd = _build_cmd(
        failed_only=failed_only,
        nodeids=nodeids,
        use_wsl=use_wsl,
        extra=extra,
    )
    env = os.environ.copy()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).rstrip()
    failures = parse_pytest_output(out)
    mode = "failed_only" if failed_only else "full_fast"
    if use_wsl:
        mode += "+wsl"
    result = RunResult(
        ok=proc.returncode == 0 and not failures,
        exit_code=proc.returncode,
        mode=mode,
        failures=failures,
        summary_line=_summary_line(out),
        tail="\n".join(out.splitlines()[-40:]),
        next_actions=[
            "For each failure: locate root cause and apply a minimal fix (LLM)",
            "Re-run: python scripts/agent_skills/test_and_fix.py run --failed-only",
            "If blocked (env/data/flaky): document owner + unblock condition",
            "Do not weaken assertions without explicit user approval",
        ],
    )
    return result


def save_state(result: RunResult) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(asdict(result), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def render_report(result: RunResult) -> str:
    lines = [
        "# Test-and-fix report",
        "",
        f"- ok: `{result.ok}`",
        f"- exit_code: `{result.exit_code}`",
        f"- mode: `{result.mode}`",
        f"- summary: {result.summary_line or '(none)'}",
        "",
        "## Failures",
        "",
    ]
    if not result.failures:
        lines.append("_None._")
    else:
        lines.extend(
            [
                "| Outcome | Nodeid | Fingerprint | Message |",
                "|---------|--------|-------------|---------|",
            ]
        )
        for f in result.failures:
            msg = (f.message or "").replace("|", "\\|")[:120]
            lines.append(
                f"| {f.outcome} | `{f.nodeid}` | `{f.fingerprint}` | {msg} |"
            )
    lines.extend(["", "## Next actions", ""])
    for a in result.next_actions:
        lines.append(f"- {a}")
    lines.extend(["", "## Tail", "", "```", result.tail or "(empty)", "```", ""])
    return "\n".join(lines)


def _normalize_extra(extra: list[str] | None) -> list[str]:
    args = list(extra or [])
    if args and args[0] == "--":
        args = args[1:]
    return args


def cmd_run(args: argparse.Namespace) -> int:
    result = run_tests(
        failed_only=args.failed_only,
        use_wsl=args.wsl,
        extra=_normalize_extra(args.extra),
    )
    save_state(result)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def cmd_report(args: argparse.Namespace) -> int:
    if args.from_state and STATE_PATH.is_file():
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        result = RunResult(
            ok=bool(data.get("ok")),
            exit_code=int(data.get("exit_code", 1)),
            mode=str(data.get("mode", "")),
            failures=[Failure(**f) for f in data.get("failures", [])],
            summary_line=str(data.get("summary_line", "")),
            tail=str(data.get("tail", "")),
            next_actions=list(data.get("next_actions") or []),
        )
    else:
        result = run_tests(failed_only=args.failed_only, use_wsl=args.wsl)
        save_state(result)
    text = render_report(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {args.output}")
    else:
        print(text)
    return 0 if result.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run fast pytest subset (or last failures)")
    r.add_argument("--failed-only", action="store_true")
    r.add_argument("--wsl", action="store_true", help="Run via WSL + ~/.venvs/tf")
    r.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        default=[],
        help="Extra pytest args; use -- before flags (e.g. run -- tests/foo.py -q)",
    )
    r.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="Markdown report from run or saved state")
    p.add_argument("--failed-only", action="store_true")
    p.add_argument("--wsl", action="store_true")
    p.add_argument(
        "--from-state",
        action="store_true",
        help=f"Read {STATE_PATH.relative_to(ROOT)} instead of re-running",
    )
    p.add_argument("-o", "--output", type=Path, default=None)
    p.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
