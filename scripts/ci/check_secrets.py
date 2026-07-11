#!/usr/bin/env python3
"""Scan tracked files for committed secrets (stdlib only).

Detects common credential shapes:
  - Provider tokens (AWS access keys, GitHub PATs, Slack tokens, OpenAI/Anthropic keys, JWTs)
  - Private key blocks (PEM)
  - Credentialed connection strings (scheme://user:password@host)
  - Suspicious assignments (api_key/token/password/secret = long literal)

Skips placeholders and documented examples: `${VAR}`, `{{ var }}`, `TODO(...)`, `<angle-bracket>`
values, obvious example/dummy words, and `env.example` / lockfile / binary paths.

Exit code 0 when clean, 1 when potential secrets are found. CI complement to .agent/SAFETY.md.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key id", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    (
        "Credentialed URL",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@\"']+:[^\s:/@\"']+@[^\s\"']+"),
    ),
    (
        "Suspicious assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|auth[_-]?token|access[_-]?token|client[_-]?secret|password|passwd)\b"
            r"\s*[:=]\s*[\"']([A-Za-z0-9+/_=-]{16,})[\"']"
        ),
    ),
]

ALLOW_LINE_RE = re.compile(
    r"\$\{[A-Z0-9_]+\}"
    r"|\{\{[^}]*\}\}"
    r"|TODO\("
    r"|<[A-Za-z][A-Za-z0-9 _-]*>"
    r"|(?i:\b(example|placeholder|dummy|sample|fake|redacted|changeme|your[_-]))"
    r"|x{6,}|\*{4,}|\.{3}"
    r"|sk-abcdefghijklmnopqrstuvwxyz",  # deliberate fixture in secret-detector unit tests
)

SKIP_NAME_PARTS = {"env.example", ".env.example", "secrets.json.example"}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".woff", ".woff2",
    ".lock", ".svg",
}
SKIP_PATH_PREFIXES = ("scripts/ci/check_secrets.py",)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return [root / line for line in result.stdout.splitlines() if line.strip()]


def scan_file(path: Path, rel: str, findings: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_LINE_RE.search(line):
            continue
        for label, pattern in TOKEN_PATTERNS:
            if pattern.search(line):
                findings.append(f"{rel}:{lineno}: possible {label}")
                break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan tracked files for committed secrets")
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT, help="Repo root (default: this repo)"
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    findings: list[str] = []
    for path in tracked_files(root):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(SKIP_PATH_PREFIXES):
            continue
        if path.name.lower() in SKIP_NAME_PARTS or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        scan_file(path, rel, findings)

    if findings:
        print(f"Secrets check FAILED ({len(findings)} potential secret(s)):")
        for f in findings:
            print(f"  {f}")
        print("If these are placeholders/examples, mark them clearly (e.g. ${VAR}, <value>, 'example').")
        return 1
    print("Secrets check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
