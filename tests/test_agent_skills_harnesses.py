#!/usr/bin/env python3
"""Unit tests for compiled agent_skills harnesses (no network / no gh)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "agent_skills"


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def test_and_fix():
    return _load("test_and_fix")


@pytest.fixture(scope="module")
def wiki_scaffold():
    return _load("wiki_scaffold")


@pytest.fixture(scope="module")
def backlog_stage():
    return _load("backlog_stage")


def test_parse_pytest_failures(test_and_fix):
    sample = """
=========================== short test summary info ============================
FAILED tests/test_foo.py::test_a - AssertionError: expected 1
ERROR tests/test_bar.py::test_b - RuntimeError: boom
========================= 1 failed, 1 error in 0.12s ===========================
"""
    fails = test_and_fix.parse_pytest_output(sample)
    assert len(fails) == 2
    assert fails[0].nodeid == "tests/test_foo.py::test_a"
    assert fails[0].outcome == "failed"
    assert "AssertionError" in fails[0].message
    assert fails[1].nodeid == "tests/test_bar.py::test_b"
    assert fails[1].fingerprint
    assert test_and_fix.fingerprint("a", "m") == test_and_fix.fingerprint("a", "m")


def test_render_report_empty(test_and_fix):
    result = test_and_fix.RunResult(
        ok=True, exit_code=0, mode="full_fast", summary_line="1 passed"
    )
    md = test_and_fix.render_report(result)
    assert "# Test-and-fix report" in md
    assert "_None._" in md


def test_frontmatter_contains_okf_fields(wiki_scaffold):
    text = wiki_scaffold.render_frontmatter(
        doc_type="Report",
        title="Example",
        description="Desc",
        resource="reports/EXAMPLE.md",
        tags=["docs", "audit"],
    )
    assert text.startswith("---\n")
    assert "type: Report" in text
    assert "okf_version: 0.1" in text
    assert "resource: reports/EXAMPLE.md" in text
    assert "tags: [docs, audit]" in text


def test_append_index_and_dedupe(wiki_scaffold, tmp_path: Path):
    index = tmp_path / "INDEX.md"
    index.write_text(
        "# Index\n\n| Document | Description |\n|----------|-------------|\n| [Old](old.md) | Prior |\n",
        encoding="utf-8",
    )
    r1 = wiki_scaffold.append_index_row(index, "new.md", "New page")
    assert r1.ok
    text = index.read_text(encoding="utf-8")
    assert "new.md" in text
    assert "New page" in text
    r2 = wiki_scaffold.append_index_row(index, "new.md", "dup")
    assert r2.ok
    assert "already present" in r2.detail
    assert text.count("new.md") == index.read_text(encoding="utf-8").count("new.md")


def test_append_log_inserts_after_rule(wiki_scaffold, tmp_path: Path, monkeypatch):
    log = tmp_path / "log.md"
    log.write_text(
        "# Wiki Log\n\nIntro\n\n---\n\n## [2020-01-01] edit | Old\n\nBody\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(wiki_scaffold, "LOG_PATH", log)
    r = wiki_scaffold.append_log("ingest", "Fresh Title", "Details here.")
    assert r.ok
    text = log.read_text(encoding="utf-8")
    assert text.index("Fresh Title") < text.index("2020-01-01")
    assert "ingest | Fresh Title" in text


def test_resolve_repo_aliases(backlog_stage):
    assert backlog_stage.resolve_repo("backend").endswith("image-scoring-backend")
    assert backlog_stage.resolve_repo("gallery").endswith("image-scoring-gallery")
    with pytest.raises(SystemExit):
        backlog_stage.resolve_repo("unknown-place")


def test_stage_options_complete(backlog_stage):
    expected = {
        "backlog",
        "ready",
        "claimed",
        "in_progress",
        "blocked",
        "review",
        "done",
    }
    assert set(backlog_stage.STAGE_OPTIONS) == expected
