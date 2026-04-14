"""Unit tests for indexing hash reuse helpers (no DB)."""

from __future__ import annotations

import os
import tempfile

from modules.indexing_runner import (
    _INDEXING_CONTENT_FP_KEY,
    _attach_indexing_content_fp,
    _content_fp_matches_file,
    _parse_metadata_dict,
)


def test_parse_metadata_dict():
    assert _parse_metadata_dict(None) == {}
    assert _parse_metadata_dict({}) == {}
    assert _parse_metadata_dict({"a": 1}) == {"a": 1}
    assert _parse_metadata_dict('{"x": 2}') == {"x": 2}
    assert _parse_metadata_dict("not-json") == {}


def test_content_fp_matches_file():
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        os.write(fd, b"hello")
        os.close(fd)
        fd = -1
        st = os.stat(path)
        fp = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
        assert _content_fp_matches_file(fp, path) is True
        assert _content_fp_matches_file({"size": st.st_size - 1, "mtime_ns": st.st_mtime_ns}, path) is False
        assert _content_fp_matches_file({}, path) is False
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(path)
        except OSError:
            pass


def test_attach_indexing_content_fp():
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        os.write(fd, b"abc")
        os.close(fd)
        fd = -1
        out = _attach_indexing_content_fp({"keep": True}, path)
        assert out["keep"] is True
        assert _INDEXING_CONTENT_FP_KEY in out
        assert "size" in out[_INDEXING_CONTENT_FP_KEY]
        assert "mtime_ns" in out[_INDEXING_CONTENT_FP_KEY]
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(path)
        except OSError:
            pass
