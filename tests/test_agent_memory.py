"""Unit tests for agent memory consolidation (no gpu/db/ml)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.agent_memory import consolidate, secrets
from scripts.agent_memory.consolidate import (
    merge_sections,
    normalize_text,
    parse_memory_markdown,
    promote_dream,
    run_dream,
)
from scripts.agent_memory.paths import load_config
from scripts.agent_memory.schema import parse_candidate_flag

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent_memory"
PYTHON = sys.executable


@pytest.fixture
def memory_home(tmp_path: Path) -> Path:
    """Minimal .agent-memory tree for isolated tests."""
    base = tmp_path / ".agent-memory"
    (base / "raw-sessions").mkdir(parents=True)
    (base / "dreams").mkdir(parents=True)
    shutil.copy(FIXTURES / "memory_seed.md", base / "memory.md")
    config = {
        "max_sessions": 10,
        "max_session_bytes": 65536,
        "max_items_per_section": 40,
        "max_context_chars": 500,
        "raw_session_retention_days": 0,
    }
    (base / "config.json").write_text(json.dumps(config), encoding="utf-8")
    shutil.copy(FIXTURES / "session1.yaml", base / "raw-sessions" / "session1.yaml")
    return tmp_path


def test_secret_detector_blocks_api_key():
    with pytest.raises(ValueError, match="secret"):
        secrets.assert_no_secrets("key sk-abcdefghijklmnopqrstuvwxyz1234567890")


def test_parse_candidate_flag():
    cand = parse_candidate_flag("Do X|working_rule|high")
    assert cand["text"] == "Do X"
    assert cand["category"] == "working_rule"


def test_normalize_dedupe_key():
    assert normalize_text("Hello-World!") == normalize_text("hello world")


def test_merge_adds_new_candidate(memory_home: Path):
    base = parse_memory_markdown((memory_home / ".agent-memory" / "memory.md").read_text())
    sessions = consolidate.load_sessions(
        memory_home / ".agent-memory" / "raw-sessions",
        max_sessions=5,
        max_bytes=65536,
    )
    merged, changelog = merge_sections(base, sessions, max_per_section=40)
    texts = [i.text for i in merged["Working Rules"]]
    assert "New working rule from session" in texts
    assert any("New working rule" in e for e in changelog["added"])


def test_dream_does_not_overwrite_memory(memory_home: Path):
    memory_path = memory_home / ".agent-memory" / "memory.md"
    before = memory_path.read_text(encoding="utf-8")
    run_dream(memory_home)
    after = memory_path.read_text(encoding="utf-8")
    assert before == after
    dreams = list((memory_home / ".agent-memory" / "dreams").glob("*.md"))
    assert any("changelog" not in p.name for p in dreams)


def test_cross_section_conflict_open_question(memory_home: Path):
    shutil.copy(
        FIXTURES / "session_conflict.yaml",
        memory_home / ".agent-memory" / "raw-sessions" / "session_conflict.yaml",
    )
    base = parse_memory_markdown((memory_home / ".agent-memory" / "memory.md").read_text())
    sessions = consolidate.load_sessions(
        memory_home / ".agent-memory" / "raw-sessions",
        max_sessions=10,
        max_bytes=65536,
    )
    merged, changelog = merge_sections(base, sessions, max_per_section=40)
    oq = [i.text for i in merged["Open Questions"]]
    assert any("Resolve:" in t for t in oq) or changelog["uncertain"]


def test_promote_dream_updates_memory(memory_home: Path):
    dream_path, changelog_path = run_dream(memory_home)
    assert changelog_path.is_file()
    promote_dream(memory_home, dream_path)
    content = (memory_home / ".agent-memory" / "memory.md").read_text(encoding="utf-8")
    assert "New working rule from session" in content
    archives = list((memory_home / ".agent-memory" / "dreams" / "archive").glob("memory-*.md"))
    assert len(archives) >= 1


def test_context_truncation(memory_home: Path):
    config = load_config(memory_home)
    config["max_context_chars"] = 80
    (memory_home / ".agent-memory" / "config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    result = subprocess.run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts" / "agent-memory" / "context.py"),
            "--repo-root",
            str(memory_home),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "truncated" in result.stdout or len(result.stdout) <= 120


def test_log_session_cli_rejects_secret(memory_home: Path):
    payload = {
        "timestamp": "2026-06-03T12:00:00+00:00",
        "task_summary": "bad",
        "memory_candidates": [],
    }
    payload["task_summary"] = "uses sk-abcdefghijklmnopqrstuvwxyz1234567890"
    proc = subprocess.run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts" / "agent-memory" / "log_session.py"),
            "--repo-root",
            str(memory_home),
            "--stdin",
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "secret" in proc.stderr.lower() or "secret" in proc.stdout.lower()


def test_log_session_cli_writes_file(memory_home: Path):
    proc = subprocess.run(
        [
            PYTHON,
            str(REPO_ROOT / "scripts" / "agent-memory" / "log_session.py"),
            "--repo-root",
            str(memory_home),
            "--summary",
            "CLI test",
            "--outcome",
            "ok",
            "--candidate",
            "CLI rule|working_rule|high",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(proc.stdout.strip())
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["task_summary"] == "CLI test"
