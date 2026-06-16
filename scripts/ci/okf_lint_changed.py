#!/usr/bin/env python3
"""CI helper: OKF-lint docs/**/*.md changed between two git refs."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from okf_lint import lint_bundle, print_text_report  # noqa: E402


def git_changed_docs(repo_root: Path, base: str, head: str) -> list[str]:
    cmd = ["git", "diff", "--name-only", f"{base}...{head}", "--", "docs"]
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git diff failed: {' '.join(cmd)}")

    rel_paths: list[str] = []
    for line in result.stdout.splitlines():
        path = line.strip().replace("\\", "/")
        if not path.endswith(".md") or not path.startswith("docs/"):
            continue
        rel_paths.append(path.removeprefix("docs/"))
    return sorted(set(rel_paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OKF-lint changed docs/ markdown files")
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Git base ref for diff (default: origin/main)",
    )
    parser.add_argument("--head", default="HEAD", help="Git head ref (default: HEAD)")
    parser.add_argument(
        "--profile",
        choices=("minimal", "vexlum"),
        default="vexlum",
        help="OKF profile (default: vexlum)",
    )
    parser.add_argument(
        "--exclude-prefix",
        action="append",
        default=["archive/"],
        dest="exclude_prefixes",
        help="Skip frontmatter checks under prefix (repeatable)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning", "info"),
        default="error",
        help="Exit non-zero when findings at or above this severity exist",
    )
    args = parser.parse_args(argv)

    docs_root = _REPO_ROOT / "docs"
    changed = git_changed_docs(_REPO_ROOT, args.base, args.head)
    exclude = tuple(args.exclude_prefixes or ())
    changed = [
        p
        for p in changed
        if p != "log.md" and not any(p.startswith(prefix) for prefix in exclude)
    ]

    if not changed:
        print("No changed living docs; skipping backend OKF lint")
        return 0

    print(f"OKF lint changed docs ({len(changed)} file(s)) vs {args.base}...{args.head}")
    report = lint_bundle(
        docs_root,
        profile=args.profile,
        bundle_name="docs",
        exclude_prefixes=exclude,
        only_paths=frozenset(changed),
    )
    print_text_report(report)

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    threshold = severity_rank[args.fail_on]
    for finding in report.findings:
        if severity_rank[finding.severity] <= threshold:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
