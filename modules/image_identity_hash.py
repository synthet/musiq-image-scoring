"""
Content-aware image identity hashing for indexing and deduplication.

``hash_version``:
  1 — SHA-256 of the entire file (legacy / fallback).
  2 — SHA-256 of the **largest** embedded JPEG preview bytes discovered from TIFF-based
      RAW (see discovery order below), or largest in-file JPEG segment when needed.

Controlled by ``indexing.hash_mode`` in config: ``full_file`` | ``content_preview``.

Version 2 discovery (merged candidates; digest = SHA-256 of the longest JPEG blob ≥ 64 B):
  A — JPEG-compressed TIFF strips/pages via ``tifffile`` (all pages, not only one).
  B — Nikon MakerNote tag 0x0011 → preview IFD → tags 0x0201 / 0x0202 (offset/length),
      when present (Nikon NEF/NRW-oriented).
  C — Largest ``FFD8``…``FFD9`` segment via mmap scan (container-agnostic fallback).

For ``.nrw``, mmap (C) runs before ``tifffile`` (A) to avoid noisy failed TIFF opens;
the **largest** blob across A ∪ B ∪ C is still chosen.
"""

from __future__ import annotations

import hashlib
import logging
import mmap
import os
import struct
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Stored in images.hash_version
HASH_VERSION_FULL_FILE = 1
HASH_VERSION_CONTENT_PREVIEW = 2

# Extensions where we attempt TIFF IFD / JPEG extraction before full-file fallback.
_TIFF_RAW_EXTENSIONS = frozenset(
    {
        ".nef",
        ".nrw",
        ".arw",
        ".cr2",
        ".cr3",
        ".dng",
        ".tif",
        ".tiff",
    }
)

_NIKON_MAKERNOTE_EXTENSIONS = frozenset({".nef", ".nrw"})

# Read enough of the file for EXIF + MakerNote + typical preview JPEG headers.
_METADATA_READ_CAP = 48 * 1024 * 1024


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tiff_type_size(t: int) -> int:
    return {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 1, 9: 4, 10: 8, 11: 4, 12: 8}.get(t, 0)


def _u16(data: bytes, off: int, endian: str) -> int:
    return struct.unpack_from(endian + "H", data, off)[0]


def _u32(data: bytes, off: int, endian: str) -> int:
    return struct.unpack_from(endian + "I", data, off)[0]


def _ifd_entry_value(
    data: bytes, entry_off: int, endian: str
) -> Optional[Tuple[int, int, int, bytes]]:
    """Return (tag, typ, count, value_bytes) for a 12-byte IFD entry."""
    if entry_off + 12 > len(data):
        return None
    tag = _u16(data, entry_off, endian)
    typ = _u16(data, entry_off + 2, endian)
    cnt = _u32(data, entry_off + 4, endian)
    tsz = _tiff_type_size(typ)
    if tsz <= 0:
        return None
    vsz = tsz * cnt
    raw4 = data[entry_off + 8 : entry_off + 12]
    if vsz <= 4:
        return (tag, typ, cnt, raw4[:vsz])
    voff = _u32(data, entry_off + 8, endian)
    if voff < 0 or voff + vsz > len(data):
        return None
    return (tag, typ, cnt, data[voff : voff + vsz])


def _iter_ifd_entries(data: bytes, ifd_off: int, endian: str) -> List[int]:
    if ifd_off + 2 > len(data):
        return []
    n = _u16(data, ifd_off, endian)
    if n > 4096:
        return []
    entries: List[int] = []
    for i in range(n):
        e = ifd_off + 2 + 12 * i
        if e + 12 <= len(data):
            entries.append(e)
    return entries


def _find_tag_in_ifd(data: bytes, ifd_off: int, endian: str, want: int) -> Optional[bytes]:
    for e in _iter_ifd_entries(data, ifd_off, endian):
        parsed = _ifd_entry_value(data, e, endian)
        if not parsed:
            continue
        tag, _typ, _cnt, val = parsed
        if tag == want:
            return val
    return None


def _exif_pointer_to_ifd(data: bytes, ifd0_off: int, endian: str) -> Optional[int]:
    """IFD0 tag 0x8769 (Exif IFD pointer) → offset of Exif SubIFD."""
    v = _find_tag_in_ifd(data, ifd0_off, endian, 0x8769)
    if not v or len(v) < 4:
        return None
    return _u32(v, 0, endian)


def _makernote_entry(data: bytes, exif_ifd_off: int, endian: str) -> Optional[Tuple[int, bytes]]:
    """Exif tag 0x927C (MakerNote): return (value_start_offset_in_file, raw maker bytes)."""
    for e in _iter_ifd_entries(data, exif_ifd_off, endian):
        parsed = _ifd_entry_value(data, e, endian)
        if not parsed:
            continue
        tag, typ, cnt, _val = parsed
        if tag != 0x927C:
            continue
        tsz = _tiff_type_size(typ)
        if tsz <= 0:
            continue
        vsz = tsz * cnt
        if vsz <= 4:
            continue
        voff = _u32(data, e + 8, endian)
        if voff < 0 or voff + vsz > len(data):
            continue
        return (voff, data[voff : voff + vsz])
    return None


def _find_tag_in_nikon_makernote(mk: bytes, endian_ifd: str, want: int) -> Optional[bytes]:
    """Nikon MakerNote IFD usually starts at byte offset 8 (after ``Nikon\\0`` + type)."""
    if len(mk) < 10:
        return None
    if mk[:5] != b"Nikon" or mk[5] != 0:
        return None
    if 8 + 2 > len(mk):
        return None
    return _find_tag_in_ifd(mk, 8, endian_ifd, want)


def _parse_u32_candidates(raw: bytes) -> List[int]:
    if not raw:
        return []
    out: List[int] = []
    if len(raw) >= 4:
        out.append(struct.unpack(">I", raw[:4])[0])
        out.append(struct.unpack("<I", raw[:4])[0])
    return out


def _preview_jpeg_from_preview_ifd(
    data: bytes,
    preview_ifd_off: int,
    endian: str,
) -> Optional[Tuple[int, int]]:
    """Return (jpeg_start, jpeg_len) from a Preview IFD using 0x0201 / 0x0202."""
    if preview_ifd_off + 2 > len(data) or preview_ifd_off < 0:
        return None
    joff_b = _find_tag_in_ifd(data, preview_ifd_off, endian, 0x0201)
    jlen_b = _find_tag_in_ifd(data, preview_ifd_off, endian, 0x0202)
    if not joff_b or not jlen_b or len(joff_b) < 4 or len(jlen_b) < 4:
        return None
    joff = _u32(joff_b, 0, endian)
    jlen = _u32(jlen_b, 0, endian)
    if jlen < 64 or joff < 0:
        return None
    return (joff, jlen)


def _read_jpeg_span(path: str, joff: int, jlen: int, head: bytes) -> Optional[bytes]:
    end = joff + jlen
    if end <= len(head):
        blob = head[joff:end]
    else:
        try:
            with open(path, "rb") as f:
                f.seek(joff)
                blob = f.read(jlen)
        except OSError:
            return None
    if len(blob) < 64 or not blob.startswith(b"\xff\xd8"):
        return None
    return blob


def _nikon_makernote_preview_jpeg(path: str, head: bytes) -> Optional[bytes]:
    """
    Nikon MakerNote tag 0x0011 → Preview IFD → JPEG offset/length (0x0201 / 0x0202).
    Preview IFD offsets are usually relative to the TIFF header (byte 0 of the file).
    """
    if len(head) < 8:
        return None
    sig = head[0:2]
    if sig not in (b"II", b"MM"):
        return None
    endian = "<" if sig == b"II" else ">"
    if _u16(head, 2, endian) != 42:
        return None
    ifd0 = _u32(head, 4, endian)
    exif_ifd = _exif_pointer_to_ifd(head, ifd0, endian)
    if exif_ifd is None or exif_ifd + 6 > len(head):
        return None
    mk_ent = _makernote_entry(head, exif_ifd, endian)
    if not mk_ent:
        return None
    mk_off, mk = mk_ent
    if len(mk) < 8:
        return None
    if mk[:5] != b"Nikon" or mk[5] != 0:
        return None

    ptr_raw: Optional[bytes] = None
    for endian_mk in (">", "<"):
        ptr_raw = _find_tag_in_nikon_makernote(mk, endian_mk, 0x0011)
        if ptr_raw:
            break
    if not ptr_raw or len(ptr_raw) < 4:
        return None

    best: Optional[bytes] = None
    ptrs: set[int] = set()
    for u in _parse_u32_candidates(ptr_raw):
        ptrs.add(u)
        ptrs.add(mk_off + u)
        ptrs.add(mk_off + 8 + u)

    for ptr in ptrs:
        if ptr < 0 or ptr + 6 > len(head):
            continue
        for p_endian in (endian, ">", "<"):
            span = _preview_jpeg_from_preview_ifd(head, ptr, p_endian)
            if not span:
                continue
            joff, jlen = span
            blob = _read_jpeg_span(path, joff, jlen, head)
            if blob and (best is None or len(blob) > len(best)):
                best = blob
    return best


def _load_head(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read(_METADATA_READ_CAP)
    except OSError:
        return b""


def _largest_jpeg_in_buffer(buf: bytes | mmap.mmap) -> Optional[bytes]:
    """Return the largest valid JPEG blob (FFD8 .. FFD9) in *buf*."""
    if not buf or len(buf) < 4:
        return None
    best = b""
    i = 0
    n = len(buf)
    while i < n - 1:
        j = buf.find(b"\xff\xd8", i)
        if j < 0:
            break
        k = buf.find(b"\xff\xd9", j + 2)
        if k < 0:
            i = j + 2
            continue
        seg = buf[j : k + 2]
        if len(seg) > len(best):
            best = seg
        i = j + 2
    return best if len(best) >= 64 else None


def _largest_jpeg_mmap_path(path: str, max_bytes: int = 512 * 1024 * 1024) -> Optional[bytes]:
    """Memory-map file and find largest embedded JPEG (caps read size for safety)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    to_read = min(size, max_bytes)
    try:
        with open(path, "rb") as f:
            with mmap.mmap(f.fileno(), to_read, access=mmap.ACCESS_READ) as mm:
                return _largest_jpeg_in_buffer(mm)
    except OSError as e:
        logger.debug("JPEG mmap scan failed for %s: %s", path, e)
        return None


def _embedded_jpegs_from_tiff(path: str) -> List[bytes]:
    """Use tifffile to read JPEG-compressed strips for every qualifying page (each blob is one candidate)."""
    try:
        import tifffile
    except ImportError:
        return []
    out: List[bytes] = []
    try:
        with tifffile.TiffFile(path) as tf, open(path, "rb") as rawf:
            for page in tf.pages:
                comp = page.compression
                if comp is None:
                    continue
                try:
                    cv = int(comp) if not hasattr(comp, "value") else int(comp.value)
                except (TypeError, ValueError, AttributeError):
                    try:
                        cv = int(comp)
                    except (TypeError, ValueError):
                        continue
                if cv not in (7, 33003, 33004, 33005, 34712):
                    continue
                try:
                    offsets = page.dataoffsets
                    counts = page.databytecounts
                except Exception:
                    continue
                chunks: List[bytes] = []
                for off, cnt in zip(offsets, counts):
                    try:
                        rawf.seek(int(off))
                        chunks.append(rawf.read(int(cnt)))
                    except Exception:
                        chunks = []
                        break
                blob = b"".join(chunks)
                if len(blob) >= 64:
                    out.append(blob)
    except Exception as e:
        logger.debug("tifffile JPEG extraction failed for %s: %s", path, e)
        return []
    return out


def _merge_jpeg_candidates(candidates: List[bytes]) -> Optional[bytes]:
    valid = [c for c in candidates if c and len(c) >= 64]
    if not valid:
        return None
    return max(valid, key=len)


def _content_preview_payload(path: str, ext: str) -> Optional[bytes]:
    ext_l = ext.lower()
    if ext_l not in _TIFF_RAW_EXTENSIONS:
        return None

    head = _load_head(path)
    candidates: List[bytes] = []

    is_nrw = ext_l == ".nrw"
    nikon_mk = ext_l in _NIKON_MAKERNOTE_EXTENSIONS

    if is_nrw:
        mmap_blob = _largest_jpeg_mmap_path(path)
        if mmap_blob:
            candidates.append(mmap_blob)
        if nikon_mk:
            mk_blob = _nikon_makernote_preview_jpeg(path, head)
            if mk_blob:
                candidates.append(mk_blob)
        candidates.extend(_embedded_jpegs_from_tiff(path))
    else:
        candidates.extend(_embedded_jpegs_from_tiff(path))
        if nikon_mk:
            mk_blob = _nikon_makernote_preview_jpeg(path, head)
            if mk_blob:
                candidates.append(mk_blob)
        mmap_blob = _largest_jpeg_mmap_path(path)
        if mmap_blob:
            candidates.append(mmap_blob)

    return _merge_jpeg_candidates(candidates)


def compute_image_identity_hash(file_path: str) -> Optional[Tuple[str, int]]:
    """
    Compute (hex digest, hash_version). Returns None if the file is missing or unreadable.

    Respects ``indexing.hash_mode``:
      - ``full_file``: SHA-256 of entire file, version 1.
      - ``content_preview``: for TIFF-based RAW, hash largest discovered embedded JPEG when found (version 2);
        otherwise full-file SHA-256 (version 1).
    """
    from modules import utils
    from modules.config import get_config_value

    resolved = utils.resolve_file_path(file_path)
    if resolved:
        file_path = resolved
    elif not os.path.exists(file_path):
        return None

    mode = (get_config_value("indexing.hash_mode", "content_preview") or "content_preview").strip().lower()
    if mode not in ("full_file", "content_preview"):
        mode = "content_preview"

    ext = os.path.splitext(file_path)[1]

    if mode == "full_file":
        h = utils.compute_file_hash(file_path)
        if not h:
            return None
        return (h, HASH_VERSION_FULL_FILE)

    # content_preview
    payload = _content_preview_payload(file_path, ext)
    if payload:
        return (_sha256_hex(payload), HASH_VERSION_CONTENT_PREVIEW)

    h = utils.compute_file_hash(file_path)
    if not h:
        return None
    if mode == "content_preview":
        log_fb = get_config_value("indexing.log_hash_fallback", False)
        if log_fb:
            logger.info(
                "hash_fallback: content_preview using full-file SHA-256 (v1) for %s",
                file_path,
            )
    return (h, HASH_VERSION_FULL_FILE)


def expected_hash_version_for_config_mode() -> int:
    """Version we expect when reusing a stored hash without recomputing (best-effort)."""
    from modules.config import get_config_value

    mode = (get_config_value("indexing.hash_mode", "content_preview") or "content_preview").strip().lower()
    if mode == "full_file":
        return HASH_VERSION_FULL_FILE
    # content_preview may still fall back to v1 per file; indexing_runner uses metadata mode match.
    return HASH_VERSION_CONTENT_PREVIEW
