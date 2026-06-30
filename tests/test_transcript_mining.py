"""Tests for Cursor transcript mining (no gpu/db/ml)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.agent_memory.transcripts import (
    dedupe_transcripts,
    extract_heuristic_candidates,
    extract_user_queries,
    filter_candidates_for_repo,
    is_duplicate_lesson,
    parse_jsonl,
    score_repos_in_text,
    TranscriptRecord,
)


def test_extract_user_query():
    text = "Hello <user_query>Fix pytest marker</user_query> world"
    assert extract_user_queries(text) == ["Fix pytest marker"]


def test_parse_jsonl_minimal(tmp_path: Path):
    jsonl = tmp_path / "chat.jsonl"
    rows = [
        {
            "role": "user",
            "message": {
                "content": [{"type": "text", "text": "<user_query>Run tests</user_query>"}]
            },
        },
        {
            "role": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Shell",
                        "input": {"command": "python -m pytest -m unit"},
                    }
                ]
            },
        },
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    turns = parse_jsonl(jsonl)
    assert len(turns) == 2
    assert turns[1].commands == ["python -m pytest -m unit"]


def test_dedupe_prefers_newer_mtime():
    entries = [
        ("ws-a", Path("a/u/u.jsonl"), 100.0),
        ("ws-b", Path("b/u/u.jsonl"), 200.0),
    ]
    out = dedupe_transcripts(entries)
    assert out["u"][0] == "ws-b"


def test_score_repos_in_text():
    text = "Edit D:/Projects/image-scoring-backend/modules/api.py"
    scores = score_repos_in_text(text, {"image-scoring-backend", "image-scoring-gallery"})
    assert scores["image-scoring-backend"] >= 2


def test_heuristic_candidates_wsl():
    rec = TranscriptRecord(
        uuid="abc",
        workspace="d-Projects-image-scoring-backend",
        path=Path("x.jsonl"),
        mtime=0.0,
        user_queries=["run script in wsl with ~/.venvs/tf"],
        relevance=0.5,
    )
    rec.repo_scores = {"image-scoring-backend": 3}
    cands = extract_heuristic_candidates(rec)
    assert any("~/.venvs/tf" in c["text"] for c in cands)


def test_duplicate_detection():
    authority = "Python app/scripts importing modules should run in WSL with ~/.venvs/tf."
    assert is_duplicate_lesson(
        "Python app/scripts importing modules should run in WSL with ~/.venvs/tf unless documented otherwise.",
        authority,
    )


def test_filter_candidates_skips_secrets():
    cands = [
        {
            "text": "key sk-abcdefghijklmnopqrstuvwxyz1234567890",
            "category": "working_rule",
            "confidence": "high",
        }
    ]
    assert filter_candidates_for_repo(cands, "") == []
