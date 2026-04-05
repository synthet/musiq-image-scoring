"""Unit tests for photos_top_segment_prune (no DB)."""

from __future__ import annotations

import re

import pytest

from modules.photos_top_segment_prune import (
    DEFAULT_ALLOW_PATTERN,
    first_segment_raw_under_logical_roots,
    first_segment_under_logical_roots,
    top_segment_allowed,
)


def test_first_segment_longest_root():
    roots_mixed = frozenset({"/mnt/d/photos", "d:/photos"})
    fp = "/mnt/d/photos/D850/2024/a.nef"
    assert first_segment_raw_under_logical_roots(fp, roots_mixed) == "D850"
    assert first_segment_under_logical_roots(fp, roots_mixed) == "d850"

    roots_wsl = frozenset({"/mnt/d/photos"})
    assert first_segment_raw_under_logical_roots(fp, roots_wsl) == "D850"

    assert first_segment_raw_under_logical_roots("/mnt/d/photos", roots_wsl) is None
    assert first_segment_raw_under_logical_roots("/mnt/d/other/x.jpg", roots_wsl) is None


@pytest.mark.parametrize(
    "name,ok",
    [
        ("D850", True),
        ("d7500", True),
        ("Z6", True),
        ("Z30", True),
        ("Zf", True),
        ("Zfc", True),
        ("Z6 III", True),
        ("Lightroom", False),
        ("Downloads", False),
        ("Z", False),
        ("D", False),
    ],
)
def test_default_allow_pattern(name: str, ok: bool):
    r = re.compile(DEFAULT_ALLOW_PATTERN, re.IGNORECASE)
    assert bool(r.fullmatch(name)) is ok


@pytest.mark.parametrize(
    "seg,on_wl,expect",
    [
        ("D850", frozenset(), True),
        ("Lightroom", frozenset(), False),
        ("TestingSamples", frozenset({"testingsamples"}), True),
        ("testingSamples", frozenset({"testingsamples"}), True),
        ("Lightroom", frozenset({"d850"}), False),
    ],
)
def test_top_segment_allowed_union_regex(seg: str, on_wl: frozenset[str], expect: bool):
    allow_re = re.compile(DEFAULT_ALLOW_PATTERN, re.IGNORECASE)
    assert top_segment_allowed(seg, whitelist_lower=on_wl, allow_re=allow_re) is expect
