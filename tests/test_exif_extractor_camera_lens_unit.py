"""Unit tests for EXIF merge / camera+lens predicates (no DB)."""

from __future__ import annotations

import pytest

from modules.exif_extractor import _exif_row_has_camera_and_lens, _merge_exif_for_upsert


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"model": "Z8", "lens_model": "180-600mm f/5.6-6.3"}, True),
        ({"make": "NIKON CORPORATION", "lens_model": "35mm"}, True),
        ({"model": "Z8"}, False),
        ({}, False),
        (None, False),
    ],
)
def test_exif_row_has_camera_and_lens(row, expected: bool) -> None:
    assert _exif_row_has_camera_and_lens(row) is expected


def test_merge_exif_for_upsert_preserves_existing_columns() -> None:
    existing = {
        "date_time_original": "2020:01:01 12:00:00",
        "model": None,
        "iso": 400,
    }
    fresh = {"model": "NIKON Z 6_2", "lens_model": "28-400mm f/2.8-5.6"}
    merged = _merge_exif_for_upsert(existing, fresh)
    assert merged["date_time_original"] == "2020:01:01 12:00:00"
    assert merged["iso"] == 400
    assert merged["model"] == "NIKON Z 6_2"
    assert merged["lens_model"] == "28-400mm f/2.8-5.6"
