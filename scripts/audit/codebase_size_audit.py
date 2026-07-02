#!/usr/bin/env python3
"""Scan a repo for large source files and long functions/methods.

Read-only audit — no code changes. Defaults match the Batch 1 codebase size audit:
  --file-min 1000   files at or above this line count
  --fn-min 150      functions/methods at or above this body line count

Usage:
  python scripts/audit/codebase_size_audit.py
  python scripts/audit/codebase_size_audit.py --root /path/to/image-scoring-gallery
  python scripts/audit/codebase_size_audit.py --format json -o /tmp/audit.json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

DEFAULT_FILE_MIN = 1000
DEFAULT_FN_MIN = 150

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    ".venv_wsl",
    ".venv-wsl-tests",
    "venv",
    "site-packages",
    "node_modules",
    "__pycache__",
    "dist",
    "dist-electron",
    "build",
    "release-builds",
    "static",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "FirebirdLinux",
    "backups",
    "thumbnails",
    "mcp-server/node_modules",
    "frontend/node_modules",
}

SKIP_FILE_PARTS = {
    ".min.js",
    ".generated.ts",
    "api.generated.ts",
}


@dataclass(frozen=True)
class LargeFile:
    path: str
    lines: int
    language: str


@dataclass(frozen=True)
class LargeFunction:
    path: str
    name: str
    start_line: int
    end_line: int
    lines: int
    kind: str  # function | method | arrow | async


def _should_skip_dir(parts: tuple[str, ...]) -> bool:
    return any(p in SKIP_DIR_NAMES for p in parts)


def _should_skip_file(path: Path) -> bool:
    name = path.name
    if name.endswith(".pyc"):
        return True
    return any(part in name for part in SKIP_FILE_PARTS)


def iter_source_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel_dir = Path(dirpath).relative_to(root)
        parts = rel_dir.parts
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        if parts and any(p in SKIP_DIR_NAMES for p in parts):
            dirnames.clear()
            continue
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if _should_skip_file(path):
                continue
            yield path


def count_lines(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def _py_functions(path: Path, text: str, fn_min: int) -> list[LargeFunction]:
    rel = str(path).replace("\\", "/")
    out: list[LargeFunction] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            return out

    def walk_class(node: ast.ClassDef, prefix: str = "") -> None:
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (child.end_lineno or child.lineno) - child.lineno + 1
                if span >= fn_min:
                    out.append(
                        LargeFunction(
                            path=rel,
                            name=f"{prefix}{node.name}.{child.name}",
                            start_line=child.lineno,
                            end_line=child.end_lineno or child.lineno,
                            lines=span,
                            kind="method",
                        )
                    )
            elif isinstance(child, ast.ClassDef):
                walk_class(child, prefix=f"{prefix}{node.name}.")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            if span >= fn_min:
                out.append(
                    LargeFunction(
                        path=rel,
                        name=node.name,
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        lines=span,
                        kind="async" if isinstance(node, ast.AsyncFunctionDef) else "function",
                    )
                )
        elif isinstance(node, ast.ClassDef):
            walk_class(node)

    return out


_TS_FN_START = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)",
)
_TS_METHOD = re.compile(r"^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*[\w<>,\s\[\]|&?.]+)?\s*\{")
_TS_ARROW = re.compile(r"^(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?\s*=>")
_TS_ARROW_BARE = re.compile(r"^(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?[^=]+=>\s*\{")


def _brace_block_end(lines: list[str], start_idx: int) -> int:
    """Return 0-based index of closing line for a block opening at start_idx."""
    depth = 0
    started = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return i
    return len(lines) - 1


def _ts_functions(path: Path, text: str, fn_min: int) -> list[LargeFunction]:
    rel = str(path).replace("\\", "/")
    lines = text.splitlines()
    out: list[LargeFunction] = []
    in_class = False
    class_name = ""

    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if re.match(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", stripped):
            m = re.match(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", stripped)
            in_class = True
            class_name = m.group(1) if m else ""
            continue
        if in_class and stripped.startswith("}") and not stripped.strip().startswith("});"):
            # naive class end — good enough for audit
            if stripped == "}":
                in_class = False
                class_name = ""

        name = None
        kind = "function"
        if m := _TS_FN_START.match(stripped):
            name, kind = m.group(1), "function"
        elif m := _TS_ARROW.match(stripped) or _TS_ARROW_BARE.match(stripped):
            name, kind = m.group(1), "arrow"
        elif in_class and (m := _TS_METHOD.match(line)):
            name, kind = f"{class_name}.{m.group(1)}", "method"
        else:
            continue

        if "{" not in stripped:
            # opening brace on next lines — find first {
            j = i
            while j < len(lines) and "{" not in lines[j]:
                j += 1
            if j >= len(lines):
                continue
            end = _brace_block_end(lines, j)
        else:
            end = _brace_block_end(lines, i)

        span = end - i + 1
        if span >= fn_min:
            out.append(
                LargeFunction(
                    path=rel,
                    name=name,
                    start_line=i + 1,
                    end_line=end + 1,
                    lines=span,
                    kind=kind,
                )
            )
    return out


def scan_root(root: Path, file_min: int, fn_min: int) -> tuple[list[LargeFile], list[LargeFunction]]:
    large_files: list[LargeFile] = []
    large_fns: list[LargeFunction] = []

    for path in iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root)
        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        if line_count >= file_min:
            large_files.append(
                LargeFile(
                    path=str(rel).replace("\\", "/"),
                    lines=line_count,
                    language=path.suffix.lstrip("."),
                )
            )
        if path.suffix == ".py":
            large_fns.extend(_py_functions(rel, text, fn_min))
        elif path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            large_fns.extend(_ts_functions(rel, text, fn_min))

    large_files.sort(key=lambda x: (-x.lines, x.path))
    large_fns.sort(key=lambda x: (-x.lines, x.path, x.start_line))
    return large_files, large_fns


def format_markdown(
    root: Path,
    large_files: list[LargeFile],
    large_fns: list[LargeFunction],
    file_min: int,
    fn_min: int,
) -> str:
    lines = [
        f"# Codebase size audit — `{root}`",
        "",
        f"Thresholds: **files ≥ {file_min} LoC**, **functions/methods ≥ {fn_min} LoC**.",
        "",
        "## Large files",
        "",
        "| Lines | Language | Path |",
        "|------:|----------|------|",
    ]
    if not large_files:
        lines.append(f"| — | — | *(none ≥ {file_min})* |")
    else:
        for f in large_files:
            lines.append(f"| {f.lines:,} | {f.language} | `{f.path}` |")

    lines.extend(["", "## Large functions / methods", ""])
    lines.append("| Lines | Kind | Path | Symbol | Range |")
    lines.append("|------:|------|------|--------|-------|")
    if not large_fns:
        lines.append(f"| — | — | — | *(none ≥ {fn_min})* | — |")
    else:
        for fn in large_fns[:80]:
            lines.append(
                f"| {fn.lines:,} | {fn.kind} | `{fn.path}` | `{fn.name}` | L{fn.start_line}–{fn.end_line} |"
            )
        if len(large_fns) > 80:
            lines.append(f"| … | | | *({len(large_fns) - 80} more)* | |")

    lines.extend(["", "## Suggested refactor priority", ""])
    if large_files:
        top = large_files[0]
        lines.append(
            f"1. **Largest file:** `{top.path}` ({top.lines:,} LoC) — prefer mechanical extraction (helpers, domain modules) before logic edits."
        )
    if large_fns:
        top_fn = large_fns[0]
        lines.append(
            f"2. **Largest symbol:** `{top_fn.name}` in `{top_fn.path}` ({top_fn.lines:,} LoC) — split by responsibility or extract nested helpers."
        )
    lines.append(
        "3. Cross-repo: run the same script on sibling **image-scoring-gallery** with `--root`."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit large files and long functions.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root to scan (default: image-scoring-backend root)",
    )
    parser.add_argument("--file-min", type=int, default=DEFAULT_FILE_MIN)
    parser.add_argument("--fn-min", type=int, default=DEFAULT_FN_MIN)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("-o", "--output", type=Path, help="Write report to file instead of stdout")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    large_files, large_fns = scan_root(root, args.file_min, args.fn_min)

    if args.format == "json":
        payload = {
            "root": str(root),
            "file_min": args.file_min,
            "fn_min": args.fn_min,
            "large_files": [asdict(x) for x in large_files],
            "large_functions": [asdict(x) for x in large_fns],
        }
        text = json.dumps(payload, indent=2)
    else:
        text = format_markdown(root, large_files, large_fns, args.file_min, args.fn_min)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
