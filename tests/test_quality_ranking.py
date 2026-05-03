"""Unit tests for modules.quality_ranking."""

import pytest

from modules.quality_ranking import (
    parse_exposure_seconds,
    quality_tiebreak_order_sql,
    quality_tiebreak_sort_key_best_first,
)


class TestParseExposureSeconds:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1/250", 1.0 / 250.0),
            ("0.005", 0.005),
            ("1", 1.0),
            (0.25, 0.25),
            (None, None),
            ("", None),
            ("not-a-number", None),
            ("1/0", None),
        ],
    )
    def test_parse(self, raw, expected):
        got = parse_exposure_seconds(raw)
        if expected is None:
            assert got is None
        else:
            assert got == pytest.approx(expected)


class TestQualityTiebreakSortKey:
    def test_lower_iso_wins(self):
        a = {"id": 1, "iso": 400, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        b = {"id": 2, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        assert quality_tiebreak_sort_key_best_first(b) < quality_tiebreak_sort_key_best_first(a)

    def test_shorter_exposure_wins_when_iso_equal(self):
        a = {"id": 1, "iso": 100, "exposure_time": "1/60", "date_time_original": "2020-01-02"}
        b = {"id": 2, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        assert quality_tiebreak_sort_key_best_first(b) < quality_tiebreak_sort_key_best_first(a)

    def test_earlier_date_wins_when_iso_and_exposure_equal(self):
        a = {"id": 1, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-03"}
        b = {"id": 2, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        assert quality_tiebreak_sort_key_best_first(b) < quality_tiebreak_sort_key_best_first(a)

    def test_lower_id_wins_when_exif_equal(self):
        a = {"id": 10, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        b = {"id": 5, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        assert quality_tiebreak_sort_key_best_first(b) < quality_tiebreak_sort_key_best_first(a)

    def test_missing_exif_sorts_after_present(self):
        full = {"id": 1, "iso": 100, "exposure_time": "1/250", "date_time_original": "2020-01-02"}
        empty = {"id": 2, "iso": None, "exposure_time": None, "date_time_original": None}
        assert quality_tiebreak_sort_key_best_first(full) < quality_tiebreak_sort_key_best_first(empty)


def test_quality_tiebreak_order_sql_aliases():
    sql = quality_tiebreak_order_sql(exif_alias="ex", images_alias="img")
    assert "ex.iso ASC" in sql
    assert "ex.exposure_time" in sql
    assert "ex.date_time_original ASC" in sql
    assert "img.id ASC" in sql
