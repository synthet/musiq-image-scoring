#!/usr/bin/env python3
"""Compiled validate-implementation harness.

Parses numbered acceptance criteria from a spec markdown file, optionally runs
evidence commands, and emits the validation report skeleton. Verdict assignment
(Verified/Failed/Unknown) remains an LLM/operator judgment step — this script
owns parsing, scaffolding, and command capture.

Usage:
  python scripts/agent_skills/validate_implementation.py parse path/to/spec.md
  python scripts/agent_skills/validate_implementation.py report path/to/spec.md \\
      --name "feature" -o .agent/scratch/validation-report.md
  python scripts/agent_skills/validate_implementation.py report path/to/spec.md \\
      --evidence "AC-1=pytest tests/test_x.py::test_y"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# AC-1, AC-1:, **AC-1**, `AC-1`
AC_RE = re.compile(
    r"(?m)^(?:\s*[-*]\s+|\s*\d+\.\s+|\s*)?(?:\*\*)?(?:AC[-_ ]?)(\d+)(?:\*\*)?\s*[:.)\-–—]\s*(.+)$"
)
AC_INLINE_RE = re.compile(
    r"(?m)^(?:\s*[-*]\s+)(?:\*\*)?AC[-_ ]?(\d+)(?:\*\*)?\s+(.+)$"
)


@dataclass
class Criterion:
    id: str
    text: str
    verdict: str = "Unknown"
    evidence: str = "not checked yet"


def parse_criteria(text: str) -> list[Criterion]:
    found: dict[str, Criterion] = {}
    for rx in (AC_RE, AC_INLINE_RE):
        for m in rx.finditer(text):
            acid = f"AC-{int(m.group(1))}"
            body = m.group(2).strip().rstrip("*").strip()
            if acid not in found:
                found[acid] = Criterion(id=acid, text=body)
    # Stable numeric order
    return [found[k] for k in sorted(found.keys(), key=lambda x: int(x.split("-")[1]))]


def render_report(name: str, criteria: list[Criterion]) -> str:
    lines = [
        f"## Validation report — {name}",
        "",
        "| AC | Criterion (short) | Verdict | Evidence |",
        "|----|-------------------|---------|----------|",
    ]
    for c in criteria:
        short = c.text.replace("|", "\\|")
        if len(short) > 80:
            short = short[:77] + "…"
        evid = c.evidence.replace("|", "\\|")
        lines.append(f"| {c.id} | {short} | {c.verdict} | {evid} |")

    verified = sum(1 for c in criteria if c.verdict == "Verified")
    failed = sum(1 for c in criteria if c.verdict == "Failed")
    unknown = sum(1 for c in criteria if c.verdict == "Unknown")
    lines.append("")
    lines.append(
        f"Overall: {verified} verified / {failed} failed / {unknown} unknown."
    )
    if failed or unknown:
        lines.append(
            "Blockers: resolve Failed items; Unknowns are not implicit passes."
        )
    else:
        lines.append("Spec satisfied: every AC is Verified.")
    lines.append("")
    return "\n".join(lines)


def _run_cmd(cmd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return 124, "timeout after 600s"
    out = (proc.stdout or "") + (proc.stderr or "")
    # Bound evidence size for the report
    if len(out) > 2000:
        out = out[:1800] + "\n…(truncated)…"
    return proc.returncode, out.strip() or "(no output)"


def apply_evidence(criteria: list[Criterion], specs: list[str]) -> None:
    """specs like AC-1=pytest … or AC-1:pass:manual check OK"""
    by_id = {c.id: c for c in criteria}
    for spec in specs:
        if "=" in spec:
            acid, cmd = spec.split("=", 1)
            acid = acid.strip().upper().replace("AC_", "AC-")
            if not acid.startswith("AC-"):
                acid = f"AC-{acid}" if acid.isdigit() else acid
            code, out = _run_cmd(cmd.strip())
            c = by_id.get(acid)
            if not c:
                continue
            c.evidence = f"`{cmd.strip()}` → exit {code}"
            if code == 0:
                c.verdict = "Verified"
            else:
                c.verdict = "Failed"
                c.evidence += f"; {out.splitlines()[-1] if out else 'failed'}"
        elif ":" in spec:
            parts = spec.split(":", 2)
            if len(parts) < 3:
                continue
            acid, verdict, evid = parts[0].strip(), parts[1].strip(), parts[2].strip()
            acid = acid.upper().replace("AC_", "AC-")
            c = by_id.get(acid)
            if not c:
                continue
            if verdict not in ("Verified", "Failed", "Unknown"):
                raise SystemExit(f"Bad verdict in --evidence: {verdict}")
            c.verdict = verdict
            c.evidence = evid


def cmd_parse(args: argparse.Namespace) -> int:
    text = Path(args.spec).read_text(encoding="utf-8")
    criteria = parse_criteria(text)
    print(
        json.dumps(
            {
                "spec": str(args.spec),
                "count": len(criteria),
                "criteria": [asdict(c) for c in criteria],
            },
            indent=2,
        )
    )
    if not criteria:
        print(
            "# warning: no AC-n criteria found — reconstruct with the user",
            flush=True,
        )
        return 2
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    text = Path(args.spec).read_text(encoding="utf-8")
    criteria = parse_criteria(text)
    if not criteria:
        raise SystemExit("No AC-n criteria found in spec")
    if args.evidence:
        apply_evidence(criteria, args.evidence)
    name = args.name or Path(args.spec).stem
    report = render_report(name, criteria)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8", newline="\n")
        print(f"Wrote {out}")
    print(report)
    failed = sum(1 for c in criteria if c.verdict == "Failed")
    unknown = sum(1 for c in criteria if c.verdict == "Unknown")
    return 1 if failed else (2 if unknown else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("parse", help="List AC-n criteria as JSON")
    p.add_argument("spec", type=Path)
    p.set_defaults(func=cmd_parse)

    r = sub.add_parser("report", help="Emit validation report markdown")
    r.add_argument("spec", type=Path)
    r.add_argument("--name", default=None)
    r.add_argument("-o", "--output", type=Path, default=None)
    r.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="AC-1=cmd   or   AC-1:Verified:manual note",
    )
    r.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
