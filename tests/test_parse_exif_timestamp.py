"""Tests for _parse_exif_timestamp — covers the truncation bug fix.

The original code used s[:len(fmt)] to truncate the input string before
parsing, but len(fmt) is the length of the *format string* (e.g. 17 for
"%Y:%m:%d %H:%M:%S") — not the length of the *date string* it represents
(19 for "2025:11:18 12:54:57").  This caused every standard EXIF timestamp
to silently fail parsing and return None.

The fix uses s[:min_len] instead, where min_len is the expected date string
length (19 for datetime, 10 for date-only).
"""

import datetime

from modules.db import _parse_exif_timestamp


# ---------------------------------------------------------------------------
# Standard EXIF formats (the bug caused all of these to return None)
# ---------------------------------------------------------------------------

def test_exif_colon_format():
    """Standard exiftool output: YYYY:MM:DD HH:MM:SS"""
    result = _parse_exif_timestamp("2025:11:18 12:54:57")
    assert result == datetime.datetime(2025, 11, 18, 12, 54, 57)


def test_iso_format():
    """ISO 8601 without timezone: YYYY-MM-DDTHH:MM:SS"""
    result = _parse_exif_timestamp("2025-11-18T12:54:57")
    assert result == datetime.datetime(2025, 11, 18, 12, 54, 57)


def test_space_separated_format():
    """YYYY-MM-DD HH:MM:SS"""
    result = _parse_exif_timestamp("2025-11-18 12:54:57")
    assert result == datetime.datetime(2025, 11, 18, 12, 54, 57)


# ---------------------------------------------------------------------------
# Timestamps with trailing data (subseconds, timezone) — truncated to min_len
# ---------------------------------------------------------------------------

def test_exif_with_subseconds():
    """Exiftool sometimes returns subsecond precision: YYYY:MM:DD HH:MM:SS.ss"""
    result = _parse_exif_timestamp("2025:11:18 12:54:57.20")
    assert result == datetime.datetime(2025, 11, 18, 12, 54, 57)


def test_iso_with_timezone_offset():
    """ISO with timezone: YYYY-MM-DDTHH:MM:SS+05:00"""
    result = _parse_exif_timestamp("2025-11-18T12:54:57+05:00")
    assert result == datetime.datetime(2025, 11, 18, 12, 54, 57)


# ---------------------------------------------------------------------------
# Date-only formats
# ---------------------------------------------------------------------------

def test_date_only_colon():
    """YYYY:MM:DD (no time)"""
    result = _parse_exif_timestamp("2025:11:18")
    assert result == datetime.datetime(2025, 11, 18, 0, 0, 0)


def test_date_only_dash():
    """YYYY-MM-DD (no time)"""
    result = _parse_exif_timestamp("2025-11-18")
    assert result == datetime.datetime(2025, 11, 18, 0, 0, 0)


# ---------------------------------------------------------------------------
# Edge cases / passthrough
# ---------------------------------------------------------------------------

def test_none_returns_none():
    assert _parse_exif_timestamp(None) is None


def test_empty_string_returns_none():
    assert _parse_exif_timestamp("") is None


def test_whitespace_returns_none():
    assert _parse_exif_timestamp("   ") is None


def test_datetime_passthrough():
    """Already a datetime object — returned as-is."""
    dt = datetime.datetime(2025, 1, 1, 0, 0, 0)
    assert _parse_exif_timestamp(dt) is dt


def test_garbage_returns_none():
    assert _parse_exif_timestamp("not a date") is None


def test_partial_date_returns_none():
    """A string too short for any format should return None."""
    assert _parse_exif_timestamp("2025:1") is None
