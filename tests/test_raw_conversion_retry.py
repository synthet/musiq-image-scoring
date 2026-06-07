"""Transient-failure handling for embedded-preview RAW conversion.

Regression for the loop-wedge RCA: a slow/failed ``exiftool`` spawn under concurrent
load used to be misreported as a permanent "RAW Conversion Failed" on otherwise-valid
RAW files (e.g. Nikon Z8 HE*), which left the image's scoring phase terminally
``failed`` and wedged its whole folder in auto-drive. The extractor now retries
transient subprocess failures before giving up, while still treating a genuinely-absent
embedded tag as terminal.

Marked ``ml`` because ``scripts.python.run_all_musiq_models`` imports TensorFlow / rawpy
at module load; the logic under test is pure subprocess handling.
"""
from __future__ import annotations

import subprocess

import pytest

pytestmark = pytest.mark.ml


@pytest.fixture
def converter():
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    # Bypass the heavy __init__ (model loading); we only exercise the exiftool extractor.
    return object.__new__(MultiModelMUSIQ)


def _patch_common(converter, monkeypatch, *, transient_retries):
    import scripts.python.run_all_musiq_models as m

    monkeypatch.setattr(
        converter,
        "_get_raw_conversion_config",
        lambda: {"exiftool_timeout_s": 1.0, "transient_retries": transient_retries},
    )
    monkeypatch.setattr(m.shutil, "which", lambda _n: "/usr/bin/exiftool")
    monkeypatch.setattr(m.time, "sleep", lambda *_a, **_k: None)
    return m


def test_exiftool_extract_retries_transient_timeout(converter, monkeypatch):
    """A transient exiftool timeout is retried, not misreported as permanent failure."""
    m = _patch_common(converter, monkeypatch, transient_retries=2)
    calls = {"n": 0}
    jpeg = b"\xff\xd8\xff" + b"\x00" * 1000

    def fake_run(cmd, capture_output=True, text=False, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd, timeout)
        return subprocess.CompletedProcess(cmd, 0, stdout=jpeg, stderr=b"")

    monkeypatch.setattr(m.subprocess, "run", fake_run)

    result = converter._exiftool_extract_preview_bytes("/x/DSC_6280.NEF")

    assert result is not None
    tag, data = result
    assert tag == "JpgFromRaw"
    assert data.startswith(b"\xff\xd8")
    assert calls["n"] == 2  # first attempt timed out, retry succeeded


def test_exiftool_extract_gives_up_after_exhausting_retries(converter, monkeypatch):
    """All attempts time out -> returns None (caller treats terminal), retries bounded."""
    m = _patch_common(converter, monkeypatch, transient_retries=1)
    calls = {"n": 0}

    def fake_run(cmd, capture_output=True, text=False, timeout=None):
        calls["n"] += 1
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(m.subprocess, "run", fake_run)

    result = converter._exiftool_extract_preview_bytes("/x/DSC_6280.NEF")

    assert result is None
    # 4 candidate tags x (1 + transient_retries) attempts each = bounded 8 calls.
    assert calls["n"] == 4 * 2


def test_exiftool_extract_absent_tag_not_retried(converter, monkeypatch):
    """A genuinely-absent tag (rc!=0 / short output) is terminal for that tag, not retried."""
    m = _patch_common(converter, monkeypatch, transient_retries=3)
    calls = {"n": 0}

    def fake_run(cmd, capture_output=True, text=False, timeout=None):
        calls["n"] += 1
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"")

    monkeypatch.setattr(m.subprocess, "run", fake_run)

    result = converter._exiftool_extract_preview_bytes("/x/DSC_6280.NEF")

    assert result is None
    assert calls["n"] == 4  # exactly one call per tag, no retries on absent tags
