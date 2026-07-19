#!/usr/bin/env python3
"""Profile skill/command usage across Cursor agent transcripts.

Feeds the Token Shrinker compilation loop: which workflows actually recur.

Usage:
  python scripts/agent_skills/profile_skill_usage.py
  python scripts/agent_skills/profile_skill_usage.py --transcripts-dir PATH
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

DEFAULT_PATTERNS: dict[str, str] = {
    "skill:backup-db": r"Skill Name:\s*backup-db|/backup-db|skills/backup-db",
    "cmd:release": r"Cursor Command:.*release|/release —|commands/release",
    "cmd:test-and-fix": r"test-and-fix",
    "skill:docs-wiki": r"Skill Name:\s*docs-wiki|skills/docs-wiki|/wiki-",
    "skill:backlog-queue": r"Skill Name:\s*backlog-queue|skills/backlog-queue|/task-claim",
    "skill:subagent-review": r"subagent-review|/run-codex-review|/run-gemini-review",
    "cmd:pr-ready": r"Cursor Command:.*pr-ready|/pr-ready|commands/pr-ready",
    "skill:imgscore-mcp-debug": r"imgscore-mcp-debug",
    "skill:wsl-tf-python-runner": r"wsl-tf-python-runner",
    "skill:critical-commit-audit": r"critical-commit-audit",
    "skill:agent-memory": (
        r"Skill Name:\s*agent-memory|skills/agent-memory|"
        r"/log-session|/dream-memory|/import-transcripts"
    ),
    "skill:codebase-size-audit": r"codebase-size-audit",
    "skill:release-bump": r"Skill Name:\s*release-bump|skills/release-bump",
    "skill:backlog-housekeeping": r"backlog-housekeeping|/backlog-housekeeping",
    "skill:windows-keep-awake": r"windows-keep-awake|Keep-Awake",
    "skill:validate-implementation": r"validate-implementation",
    "cmd:implement": r"Cursor Command:.*implement|/implement —|commands/implement",
    "skill:eval": r"Skill Name:\s*eval|skills/eval/",
}


def default_transcripts_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".")
    return (
        home
        / ".cursor"
        / "projects"
        / "d-Projects-image-scoring-backend"
        / "agent-transcripts"
    )


def profile(root: Path) -> dict:
    counts: Counter[str] = Counter()
    files = list(root.rglob("*.jsonl")) if root.is_dir() else []
    compiled = {k: re.compile(v) for k, v in DEFAULT_PATTERNS.items()}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, rx in compiled.items():
            if rx.search(text):
                counts[name] += 1
    ranked = [{"workflow": k, "transcripts": v} for k, v in counts.most_common()]
    return {
        "transcripts_dir": str(root),
        "transcript_files": len(files),
        "ranked": ranked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=None,
        help="Cursor agent-transcripts directory",
    )
    args = parser.parse_args()
    root = args.transcripts_dir or default_transcripts_dir()
    result = profile(root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
