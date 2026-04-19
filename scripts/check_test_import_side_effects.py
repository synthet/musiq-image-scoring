#!/usr/bin/env python3
"""Fail if non-allowlisted tests/test_*.py files run code at import time."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / "scripts" / "check_test_import_side_effects.allowlist"


def _load_allowlist() -> set[Path]:
    entries: set[Path] = set()
    if not ALLOWLIST_PATH.exists():
        return entries
    for raw in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(REPO_ROOT / line)
    return entries


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if not isinstance(test.left, ast.Name) or test.left.id != "__name__":
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    if len(test.comparators) != 1:
        return False
    comp = test.comparators[0]
    return isinstance(comp, ast.Constant) and comp.value == "__main__"


def _has_call(node: ast.AST | None) -> bool:
    if node is None:
        return False
    return any(isinstance(child, ast.Call) for child in ast.walk(node))


def _import_time_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue  # module docstring
            if _has_call(node.value):
                violations.append(f"L{node.lineno}: top-level call expression")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = node.value if hasattr(node, "value") else None
            if _has_call(value):
                violations.append(f"L{node.lineno}: top-level assignment invokes call")
        elif isinstance(node, ast.If):
            if _is_main_guard(node):
                continue
            if _has_call(node):
                violations.append(f"L{node.lineno}: top-level if block invokes call")
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
            violations.append(f"L{node.lineno}: top-level executable block")

    return violations


def main() -> int:
    allowlist = _load_allowlist()
    offenders: list[tuple[Path, list[str]]] = []

    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        if path in allowlist:
            continue
        violations = _import_time_violations(path)
        if violations:
            offenders.append((path, violations))

    if offenders:
        print("Import-time side effects detected in automated tests:\n")
        for path, violations in offenders:
            rel = path.relative_to(REPO_ROOT)
            print(f"- {rel}")
            for issue in violations:
                print(f"  - {issue}")
        print("\nFix the files above, or move manual scripts to manual-checks/.")
        return 1

    print("OK: no import-time side effects found in non-allowlisted tests/test_*.py files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
