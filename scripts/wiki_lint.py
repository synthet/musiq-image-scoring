#!/usr/bin/env python3
"""Combined wiki lint: structural scan (orphans, links) + OKF metadata."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent


def build_parser() -> argparse.ArgumentParser:
    default_docs = _REPO_ROOT / "docs"
    parser = argparse.ArgumentParser(description="Lint docs/ structure and OKF metadata")
    parser.add_argument(
        "bundle_roots",
        nargs="*",
        type=Path,
        help=f"Bundle roots to scan (default: {default_docs})",
    )
    parser.add_argument(
        "--profile",
        choices=("minimal", "vexlum"),
        default="vexlum",
        help="OKF profile for metadata checks (default: vexlum)",
    )
    parser.add_argument(
        "--exclude-prefix",
        action="append",
        default=["archive/"],
        dest="exclude_prefixes",
        help="Skip OKF frontmatter checks under this prefix (repeatable)",
    )
    parser.add_argument("--json", action="store_true", help="OKF lint JSON output")
    parser.add_argument(
        "--skip-okf",
        action="store_true",
        help="Run structural scan only",
    )
    parser.add_argument(
        "--skip-structural",
        action="store_true",
        help="Run OKF metadata scan only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    roots = args.bundle_roots or [_REPO_ROOT / "docs"]
    exit_code = 0

    if not args.skip_structural:
        from wiki_lint_scan import lint_docs

        for root in roots:
            root = Path(root)
            result = lint_docs(root)
            print(f"=== structural: {root} ===")
            print(
                f"md={result['total']} hubs={result['hubs']} indexed_refs={result['indexed_refs']} "
                f"orphans={len(result['orphans'])} missing={len(result['missing'])} "
                f"broken_docs={len(result['broken_docs'])} broken_code={len(result['broken_code'])}"
            )
            for cls, items in sorted(result["orphan_by_class"].items()):
                print(f"  orphans[{cls}]: {len(items)}")
            if result["missing"]:
                print("MISSING:")
                for item in result["missing"]:
                    print(f"  {item}")
            if result["isolated_active"]:
                print("ISOLATED_ACTIVE (no inbound):")
                for item in result["isolated_active"][:25]:
                    print(f"  {item}")
            print()

    if not args.skip_okf:
        okf_cmd = [
            sys.executable,
            str(_SCRIPTS_DIR / "okf_lint.py"),
            "--profile",
            args.profile,
            "--bundle-name",
            "docs",
            "--fail-on",
            "error",
        ]
        for prefix in args.exclude_prefixes or []:
            okf_cmd.extend(["--exclude-prefix", prefix])
        if args.json:
            okf_cmd.append("--json")
        okf_cmd.extend(str(Path(r)) for r in roots)
        completed = subprocess.run(okf_cmd, check=False)
        exit_code = max(exit_code, completed.returncode)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
