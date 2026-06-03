"""Unit tests for model score quality report helpers (no DB)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analysis" / "model_score_quality_report.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("model_score_quality_report", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


def test_histogram_bucket_boundaries():
    series = pd.Series([0.0, 0.05, 0.15, 0.95, 1.0])
    buckets = mod.histogram(series, bins=10)
    assert len(buckets) == 10
    assert buckets[0]["bucket_start"] == 0.0
    assert buckets[-1]["bucket_end"] == 1.0
    assert sum(b["count"] for b in buckets) == 5


def test_correlation_matrices_known_fixture():
    n = 100
    x = np.linspace(0, 1, n)
    df = pd.DataFrame(
        {
            "perfect": x,
            "copy": x * 0.8 + 0.1,
            "noise": np.random.default_rng(0).random(n),
            "inverse": 1.0 - x,
        }
    )
    corr = mod.correlation_matrices(df)
    pearson = corr["pearson"]
    labels = pearson["labels"]
    matrix = pearson["matrix"]
    i_p, i_c = labels.index("perfect"), labels.index("copy")
    i_n = labels.index("noise")
    assert matrix[i_p][i_c] == pytest.approx(1.0, abs=0.01)
    assert abs(matrix[i_p][i_n]) < 0.3
    assert matrix[i_p][labels.index("inverse")] == pytest.approx(-1.0, abs=0.01)


def test_build_report_schema_keys():
    df = pd.DataFrame(
        {
            "liqe": [0.2, 0.5, 0.8, 0.9],
            "ava": [0.3, 0.35, 0.4, 0.45],
            "general": [0.25, 0.45, 0.65, 0.75],
        }
    )
    meta = [
        {"name": "liqe", "source": "legacy_column", "is_composite": False},
        {"name": "ava", "source": "legacy_column", "is_composite": False},
        {"name": "general", "source": "legacy_column", "is_composite": True},
    ]
    report = mod.build_report(
        df,
        meta,
        bins=4,
        filters={"sample": 0},
        total_images=len(df),
    )
    assert report["report_version"] == "1.0"
    assert "models" in report and "correlation" in report and "diversity" in report
    assert "liqe" in report["models"]
    assert report["models"]["liqe"]["histogram"]
    assert report["correlation"]["pearson"]["labels"]


def test_render_html_contains_chart_and_models():
    report = {
        "report_version": "1.0",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "filters": {"folder_path": None, "sample": 0},
        "corpus": {"total_images": 2, "scored_images_by_model": {"liqe": 2}},
        "models": {
            "liqe": {
                "count": 2,
                "stats": {"effective_range": 0.5, "std": 0.1},
                "histogram": [
                    {"bucket_start": 0.0, "bucket_end": 0.5, "count": 1},
                    {"bucket_start": 0.5, "bucket_end": 1.0, "count": 1},
                ],
            }
        },
        "correlation": {
            "pearson": {"labels": ["liqe"], "matrix": [[1.0]], "pairwise_n": [[2]]},
            "spearman": {"labels": ["liqe"], "matrix": [[1.0]], "pairwise_n": [[2]]},
        },
        "diversity": {
            "discrimination_rank": [{"model": "liqe", "effective_range": 0.5, "std": 0.1}],
            "redundant_pairs": [],
            "orthogonal_pairs": [],
            "rank_delta_vs_general": {},
            "anchor_drift": {},
        },
    }
    html = mod.render_html(report)
    assert "chart.js" in html.lower()
    assert "hist-liqe" in html
    assert "Model Score Quality Report" in html
