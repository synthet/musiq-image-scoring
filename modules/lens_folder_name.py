"""
Canonical lens model → backup/sync folder name.

**Keep in sync with** ``image-scoring-gallery/electron/lensFolderName.ts``
(same rules; mirror test cases in ``test_lens_folder_name.py`` / ``lensFolderName.test.ts``).

Used by maintenance/backup scripts and mirrored in the Electron gallery for Backup/Sync paths.
"""

from __future__ import annotations

import re

# Match focal length patterns: 105mm, 180-600mm, 24-70mm, 10.5mm
_FOCAL_MM_PATTERN = re.compile(r"(\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?mm)", re.IGNORECASE)

# Nikon EXIF quad: min focal, max focal, max aperture @ min, max aperture @ max (no "mm")
_NIKON_LENS_QUAD_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)$"
)

_INVALID_LENS_TOKENS = frozenset({"0mm"})

UNKNOWN_LENS_FOLDER = "_unknown_lens"


def _fmt_focal(value: float) -> str:
    """Strip unnecessary .0 decimals (parity with fix_backup_structure._fmt_focal)."""
    return str(int(value)) if value == int(value) else str(value)


def _parse_nikon_lens_quad(trimmed: str) -> str | None:
    m = _NIKON_LENS_QUAD_PATTERN.match(trimmed)
    if not m:
        return None
    try:
        min_f = float(m.group(1))
        max_f = float(m.group(2))
    except ValueError:
        return None
    if min_f <= 0 or max_f <= 0:
        return None
    if min_f == max_f:
        token = f"{_fmt_focal(min_f)}mm"
    else:
        token = f"{_fmt_focal(min_f)}-{_fmt_focal(max_f)}mm"
    if token.lower() in _INVALID_LENS_TOKENS:
        return None
    return token


def _is_degenerate_lens_spec(trimmed: str) -> bool:
    """
    True when the lens data is recognisably *invalid* rather than merely unrecognised.

    Distinguishes "EXIF reports no usable lens" (``0mm``, ``0 0 0 0``) — where the image has
    no real lens and must fall to :data:`UNKNOWN_LENS_FOLDER` so sync/backup skips it — from
    an unrecognised *marketing* name, which is still meaningful once sanitized.

    Without this, ``0 0 0 0`` and ``0mm f/0`` get sanitized into literal folder names; both
    were observed on a live backup destination.
    """
    m = _FOCAL_MM_PATTERN.search(trimmed)
    if m and m.group(1).lower() in _INVALID_LENS_TOKENS:
        return True

    quad = _NIKON_LENS_QUAD_PATTERN.match(trimmed)
    if quad:
        try:
            min_f = float(quad.group(1))
            max_f = float(quad.group(2))
        except ValueError:
            return False
        return min_f <= 0 or max_f <= 0

    return False


def _sanitize_lens_name(raw: str) -> str:
    if not raw.strip():
        return UNKNOWN_LENS_FOLDER
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", raw.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80]


def lens_folder_from_exif_model(lens_model: str | None) -> str:
    """
    Derive a single path segment from EXIF lens model / lens tag.

    Examples: ``NIKKOR 35mm f/1.8`` → ``35mm``; ``35 35 1.8 1.8`` → ``35mm``;
    ``28 105 3.5 4.5`` → ``28-105mm``.
    """
    if not lens_model or not lens_model.strip():
        return UNKNOWN_LENS_FOLDER

    trimmed = lens_model.strip()
    m = _FOCAL_MM_PATTERN.search(trimmed)
    if m:
        token = m.group(1).lower()
        if token not in _INVALID_LENS_TOKENS:
            return token

    quad = _parse_nikon_lens_quad(trimmed)
    if quad:
        return quad

    if _is_degenerate_lens_spec(trimmed):
        return UNKNOWN_LENS_FOLDER

    return _sanitize_lens_name(trimmed)


def extract_lens_token_from_model(lens_model: str | None) -> str | None:
    """
    Extract canonical lens token from EXIF model string, or None if unparseable.

    Returns None for missing values and strings that are not marketing ``mm`` or Nikon quad specs.
    """
    if not lens_model or not lens_model.strip():
        return None

    trimmed = lens_model.strip()
    m = _FOCAL_MM_PATTERN.search(trimmed)
    if m:
        token = m.group(1).lower()
        if token not in _INVALID_LENS_TOKENS:
            return token

    quad = _parse_nikon_lens_quad(trimmed)
    if quad:
        return quad

    return None


def extract_lens_token_from_path_segment(segment: str | None) -> str | None:
    """Canonicalize a lens folder segment (``35mm`` or ``35 35 1.8 1.8``) to ``…mm`` token."""
    if not segment or not segment.strip():
        return None
    return extract_lens_token_from_model(segment.strip())
