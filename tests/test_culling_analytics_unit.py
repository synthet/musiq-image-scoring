"""Unit tests for culling analytics helpers (no database)."""

from modules.culling_analytics._common import histogram, percentile_from_sorted, summarize_numeric
from modules.culling_analytics.exposure import _exposure_similarity_score, _parse_exposure_time, _parse_f_number
from modules.culling_analytics.gps import haversine_m


def test_haversine_zero_distance():
    assert haversine_m(48.0, 2.0, 48.0, 2.0) == 0.0


def test_haversine_positive():
    d = haversine_m(48.8566, 2.3522, 51.5074, -0.1278)
    assert 300_000 < d < 400_000


def test_histogram_empty():
    buckets = histogram([])
    assert len(buckets) == 10
    assert sum(b["count"] for b in buckets) == 0


def test_summarize_numeric():
    s = summarize_numeric([0.1, 0.5, 0.9])
    assert s["count"] == 3
    assert s["min"] == 0.1
    assert s["max"] == 0.9
    assert s["median"] == 0.5


def test_percentile():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_from_sorted(vals, 0.5) == 3.0


def test_parse_exposure_time_fraction():
    assert abs(_parse_exposure_time("1/100") - 0.01) < 1e-6


def test_parse_f_number():
    assert _parse_f_number("f/2.8") == 2.8


def test_exposure_similarity_identical():
    rows = [{"make": "Nikon", "lens_model": "24-70", "iso": 400, "f_number": "2.8"}] * 3
    assert _exposure_similarity_score(rows) >= 0.8
