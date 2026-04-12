"""
Canonical camera model → backup/sync folder name.

**Keep in sync with** ``image-scoring-gallery/electron/cameraFolderName.ts`` (same rules and test cases).

Used by maintenance/backup scripts and mirrored in the Electron gallery for Backup/Sync paths.
"""

from __future__ import annotations

import re

# Explicit model → folder overrides (keys lowercased, stripped model strings).
# E.g. some Z6 II bodies report "NIKON Z 6" without " II".
_MODEL_OVERRIDES: dict[str, str] = {
    "nikon z 6": "Z6ii",
    "nikon z6": "Z6ii",
}


def _sanitize_fs(s: str) -> str:
    """Sanitize string for filesystem: remove unsafe chars, collapse spaces."""
    s = re.sub(r'[<>:"/\\|?*]', "", str(s).strip())
    return re.sub(r"\s+", "", s) or "unknown"


def camera_folder_from_exif_model(model: str | None) -> str:
    """
    Derive a single path segment from camera EXIF Model.

    Examples: ``Nikon Z 8`` → ``Z8``, ``NIKON D300`` → ``D300``, ``Canon EOS R5`` → ``R5``.
    Returns ``unknown`` when the model is missing or unparseable.
    """
    if not model or model.lower() == "unknown":
        return "unknown"
    m = model.strip()

    override = _MODEL_OVERRIDES.get(m.lower())
    if override:
        return override

    # Nikon Z series — "Nikon Z 6 II", "NIKON Z 6_2", "Z8"
    nikon_z = re.search(r"Z\s*(\d+)(\s*(?:_2|II|ii))?", m, re.I)
    if nikon_z:
        gen2 = nikon_z.group(2) or ""
        suffix = "ii" if re.search(r"_2|II|ii", gen2, re.I) else ""
        return f"Z{nikon_z.group(1)}{suffix}"

    # Nikon D series — "NIKON D90", "Nikon D300", "NIKOND90", optional S/X/H suffix
    nikon_d = re.search(r"(?:NIKON\s*)?D(\d+)(\s*(?:S|X|H))?", m, re.I)
    if nikon_d:
        suffix = nikon_d.group(2).strip().upper() if nikon_d.group(2) else ""
        return f"D{nikon_d.group(1)}{suffix}"

    # Canon EOS R series
    canon_r = re.search(r"EOS\s*R\s*(\d+)", m, re.I)
    if canon_r:
        return f"R{canon_r.group(1)}"

    # Fallback: remove common brands from start, take last 2 tokens
    m_clean = re.sub(r"^(Nikon|Canon|Camera|Sony)\s+", "", m, flags=re.I)
    tokens = re.findall(r"[A-Za-z0-9]+", m_clean)
    if len(tokens) >= 1:
        return "".join(tokens[-2:]) if len(tokens) >= 2 else tokens[0]
    return _sanitize_fs(m)
