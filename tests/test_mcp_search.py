"""Tests for MCP action search."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from modules.mcp.actions.search import search_actions

EVAL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mcp_search_eval.yaml"


@pytest.mark.parametrize(
    "query,expected_in_top",
    [
        ("why did scoring fail", "diagnostics.get_error_summary"),
        ("run doctor without gpu", "diagnostics.run_doctor"),
        ("database health", "diagnostics.check_database_health"),
        ("images without embeddings", "data.get_embedding_stats"),
        ("search logs for error", "logs.search_logs"),
        ("export debug bundle", "support.export_debug_bundle"),
        ("runner status", "jobs.get_runner_status"),
        ("recent jobs", "jobs.get_recent_jobs"),
        ("query images in folder", "data.query_images"),
        ("image details by path", "data.get_image_details"),
    ],
)
def test_search_finds_expected_action(query, expected_in_top):
    result = search_actions(query, limit=8)
    ids = [r["action_id"] for r in result.get("results") or []]
    assert expected_in_top in ids[:3], f"query={query!r} got {ids}"


def test_search_low_confidence_on_nonsense():
    result = search_actions("xyzzy plugh completely unrelated gibberish")
    assert result.get("low_confidence") is True or result.get("count", 0) == 0


def test_search_read_only_only():
    result = search_actions("config", limit=20, read_only_only=True)
    for row in result.get("results") or []:
        assert row.get("side_effect_level") == "read_only"


def _load_eval_cases() -> list[dict]:
    if yaml is None:
        pytest.skip("PyYAML not installed")
    if not EVAL_FIXTURE.exists():
        pytest.skip(f"missing fixture: {EVAL_FIXTURE}")
    data = yaml.safe_load(EVAL_FIXTURE.read_text(encoding="utf-8")) or []
    return [c for c in data if isinstance(c, dict)]


def test_search_eval_fixture_top1_accuracy():
    cases = _load_eval_cases()
    ranked = [c for c in cases if c.get("expected_top1") and not c.get("expect_low_confidence")]
    if not ranked:
        pytest.skip("no top-1 cases in fixture")

    hits = 0
    failures: list[str] = []
    for case in ranked:
        query = case["query"]
        expected = case["expected_top1"]
        result = search_actions(query, limit=8)
        ids = [r["action_id"] for r in result.get("results") or []]
        if ids and ids[0] == expected:
            hits += 1
        else:
            failures.append(f"{query!r} -> {ids[:5]} (want top-1 {expected})")

    rate = hits / len(ranked)
    assert rate >= 0.8, f"top-1 accuracy {rate:.0%} ({hits}/{len(ranked)}): " + "; ".join(failures)


def test_search_eval_fixture_top3_recall():
    cases = _load_eval_cases()
    recall_cases = [
        c
        for c in cases
        if not c.get("expect_low_confidence")
        and (c.get("expected_top1") or c.get("expected_top3"))
    ]
    if not recall_cases:
        pytest.skip("no recall cases in fixture")

    hits = 0
    failures: list[str] = []
    for case in recall_cases:
        query = case["query"]
        acceptable = {case["expected_top1"]} if case.get("expected_top1") else set()
        acceptable |= set(case.get("expected_top3") or [])
        result = search_actions(query, limit=8)
        ids = [r["action_id"] for r in result.get("results") or []][:3]
        if acceptable & set(ids):
            hits += 1
        else:
            failures.append(f"{query!r} -> {ids} (want one of {sorted(acceptable)})")

    rate = hits / len(recall_cases)
    assert rate >= 0.95, f"top-3 recall {rate:.0%} ({hits}/{len(recall_cases)}): " + "; ".join(failures)


@pytest.mark.parametrize("query", [
    "rebuild embeddings for this folder",
    "start thumbnail generation",
])
def test_search_unsupported_queries_low_confidence(query: str):
    result = search_actions(query, limit=8)
    assert result.get("low_confidence") is True, f"query={query!r} results={result.get('results')}"
