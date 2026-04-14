"""Unit tests for modules/image_identity_hash.py (no GPU, no DB)."""

from __future__ import annotations

import logging
import os
import struct
import tempfile

from modules.image_identity_hash import (
    HASH_VERSION_CONTENT_PREVIEW,
    HASH_VERSION_FULL_FILE,
    _largest_jpeg_in_buffer,
    _merge_jpeg_candidates,
    _nikon_makernote_preview_jpeg,
)


def test_largest_jpeg_in_buffer_prefers_bigger_segment():
    small = b"\xff\xd8\xff\xe0\x00\x10" + b"x" * 50 + b"\xff\xd9"
    big = b"\xff\xd8\xff\xe0\x00\x10" + b"y" * 200 + b"\xff\xd9"
    buf = b"pre" + small + b"mid" + big + b"trail"
    out = _largest_jpeg_in_buffer(buf)
    assert out == big


def test_largest_jpeg_in_buffer_none_when_too_small():
    buf = b"\xff\xd8\x00\x00\xff\xd9"
    assert _largest_jpeg_in_buffer(buf) is None


def test_hash_version_constants():
    assert HASH_VERSION_FULL_FILE == 1
    assert HASH_VERSION_CONTENT_PREVIEW == 2


def test_merge_jpeg_candidates_picks_largest():
    small = b"\xff\xd8" + b"a" * 62 + b"\xff\xd9"
    big = b"\xff\xd8" + b"b" * 200 + b"\xff\xd9"
    assert _merge_jpeg_candidates([small, big]) == big


def test_nikon_makernote_preview_jpeg_synthetic(tmp_path):
    """Minimal LE TIFF + Nikon MakerNote tag 0x11 → preview IFD → 0x0201/0x0202."""
    jpeg = b"\xff\xd8\xff\xe0\x00\x10" + b"c" * 180 + b"\xff\xd9"
    assert len(jpeg) >= 64
    jlen = len(jpeg)
    joff = 600

    def le_ifd_entry(tag: int, typ: int, cnt: int, val: int) -> bytes:
        return struct.pack("<HHII", tag, typ, cnt, val)

    def be_ifd_entry(tag: int, typ: int, cnt: int, val: int) -> bytes:
        return struct.pack(">HHII", tag, typ, cnt, val)

    mk_base = 200
    preview_ifd = 400
    mk_len = 48

    buf = bytearray(2048)
    buf[0:2] = b"II"
    buf[2:4] = struct.pack("<H", 42)
    struct.pack_into("<I", buf, 4, 8)
    # IFD0 @8: Exif pointer -> 100
    buf[8:10] = struct.pack("<H", 1)
    buf[10:22] = le_ifd_entry(0x8769, 4, 1, 100)
    buf[22:26] = struct.pack("<I", 0)
    # Exif IFD @100
    buf[100:102] = struct.pack("<H", 1)
    buf[102:114] = le_ifd_entry(0x927C, 7, mk_len, mk_base)
    buf[114:118] = struct.pack("<I", 0)
    # MakerNote @200: header + BE IFD @208
    buf[mk_base : mk_base + 6] = b"Nikon\x00"
    buf[mk_base + 6 : mk_base + 8] = b"\x02\x00"
    o = mk_base + 8
    buf[o : o + 2] = struct.pack(">H", 1)
    buf[o + 2 : o + 14] = be_ifd_entry(0x0011, 4, 1, preview_ifd)
    buf[o + 14 : o + 18] = struct.pack(">I", 0)
    # Preview IFD @400 (LE, same as container)
    buf[400:402] = struct.pack("<H", 2)
    buf[402:414] = le_ifd_entry(0x0201, 4, 1, joff)
    buf[414:426] = le_ifd_entry(0x0202, 4, 1, jlen)
    buf[426:430] = struct.pack("<I", 0)
    buf[joff : joff + jlen] = jpeg

    total = joff + jlen
    blob = bytes(buf[:total])
    p = tmp_path / "nikon_synthetic.nef"
    p.write_bytes(blob)

    out = _nikon_makernote_preview_jpeg(str(p), blob)
    assert out == jpeg


def test_compute_full_file_mode(monkeypatch):
    from modules import image_identity_hash as mod
    from modules import utils

    fd, path = tempfile.mkstemp(suffix=".jpg")
    try:
        os.write(fd, b"not-a-jpeg-but-bytes")
        os.close(fd)

        def _cfg(key, default=None):
            if key == "indexing.hash_mode":
                return "full_file"
            return default

        monkeypatch.setattr("modules.config.get_config_value", _cfg)
        monkeypatch.setattr("modules.utils.resolve_file_path", lambda p: p)

        h = utils.compute_file_hash(path)
        out = mod.compute_image_identity_hash(path)
        assert out is not None
        assert out[0] == h
        assert out[1] == HASH_VERSION_FULL_FILE
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_nrw_probe_order_mmap_before_tifffile(tmp_path, monkeypatch):
    """``.nrw`` runs mmap + MakerNote before ``tifffile`` strip extraction."""
    from modules import image_identity_hash as mod

    order: list[str] = []

    def mmap_spy(path: str):
        order.append("mmap")
        return None

    def mk_spy(path: str, head: bytes):
        order.append("makernote")
        return None

    def tiff_spy(path: str):
        order.append("tifffile")
        return []

    monkeypatch.setattr(mod, "_largest_jpeg_mmap_path", mmap_spy)
    monkeypatch.setattr(mod, "_nikon_makernote_preview_jpeg", mk_spy)
    monkeypatch.setattr(mod, "_embedded_jpegs_from_tiff", tiff_spy)
    monkeypatch.setattr(mod, "_load_head", lambda p: b"")

    p = tmp_path / "probe.nrw"
    p.write_bytes(b"not-tiff")
    mod._content_preview_payload(str(p), ".nrw")
    assert order == ["mmap", "makernote", "tifffile"]


def test_content_preview_same_jpeg_different_prefix_same_digest(tmp_path, monkeypatch):
    """Largest embedded JPEG segment matches across files that differ only outside that segment."""
    from modules import image_identity_hash as mod

    jpeg = b"\xff\xd8\xff\xe0\x00\x10" + b"z" * 120 + b"\xff\xd9"
    p1 = tmp_path / "a.nef"
    p2 = tmp_path / "b.nef"
    p1.write_bytes(b"A" * 2000 + jpeg + b"tail1")
    p2.write_bytes(b"B" * 3000 + jpeg + b"tail2")
    monkeypatch.setattr(mod, "_embedded_jpegs_from_tiff", lambda path: [])

    def _cfg(key, default=None):
        if key == "indexing.hash_mode":
            return "content_preview"
        return default

    monkeypatch.setattr("modules.config.get_config_value", _cfg)
    monkeypatch.setattr("modules.utils.resolve_file_path", lambda p: str(p))

    r1 = mod.compute_image_identity_hash(str(p1))
    r2 = mod.compute_image_identity_hash(str(p2))
    assert r1 is not None and r2 is not None
    assert r1[1] == HASH_VERSION_CONTENT_PREVIEW
    assert r1[0] == r2[0]


def test_log_hash_fallback_emits_info(caplog, tmp_path, monkeypatch):
    from modules import image_identity_hash as mod

    p = tmp_path / "nojpeg.nef"
    p.write_bytes(b"no-jpeg-markers-here-at-all" * 50)

    def _cfg(key, default=None):
        if key == "indexing.log_hash_fallback":
            return True
        if key == "indexing.hash_mode":
            return "content_preview"
        return default

    monkeypatch.setattr("modules.config.get_config_value", _cfg)
    monkeypatch.setattr("modules.utils.resolve_file_path", lambda x: str(x))
    caplog.set_level(logging.INFO)

    out = mod.compute_image_identity_hash(str(p))
    assert out is not None
    assert out[1] == HASH_VERSION_FULL_FILE
    assert any("hash_fallback" in r.message for r in caplog.records)

