"""
Canonical list of (subdir, filename, source_url) for scripted Nikon NEF test downloads.

Used by download_nef_testing_samples.py and nef_testing_manifest.py.
"""

from __future__ import annotations

# (subdir under tests/fixtures/testing_samples root, local filename, URL)
SAMPLES: list[tuple[str, str, str]] = [
    # D300 — rawsamples + raw.pixls.us
    ("D300", "RAW_NIKON_D300.NEF", "http://www.rawsamples.ch/raws/nikon/d300/RAW_NIKON_D300.NEF"),
    ("D300", "D300_MMC_2821.NEF", "https://raw.pixls.us/data/Nikon/D300/MMC_2821.NEF"),
    ("D300", "D300_MMC_2822.NEF", "https://raw.pixls.us/data/Nikon/D300/MMC_2822.NEF"),
    ("D300", "D300_MMC_2824.NEF", "https://raw.pixls.us/data/Nikon/D300/MMC_2824.NEF"),
    # D90
    ("D90", "RAW_NIKON_D90.NEF", "http://www.rawsamples.ch/raws/nikon/d90/RAW_NIKON_D90.NEF"),
    ("D90", "D90_00001_pixls.NEF", "https://raw.pixls.us/data/Nikon/D90/00001.NEF"),
    # Z6 II — raw.pixls.us (folder name is "Z 6_2")
    ("Z6II", "Z6II_CZP_0299.NEF", "https://raw.pixls.us/data/Nikon/Z%206_2/CZP_0299.NEF"),
    ("Z6II", "Z6II_CZP_0300.NEF", "https://raw.pixls.us/data/Nikon/Z%206_2/CZP_0300.NEF"),
    ("Z6II", "Z6II_CZP_0301.NEF", "https://raw.pixls.us/data/Nikon/Z%206_2/CZP_0301.NEF"),
    ("Z6II", "Z6II_CZP_0302.NEF", "https://raw.pixls.us/data/Nikon/Z%206_2/CZP_0302.NEF"),
    # Z8 — HE + lossless variants on raw.pixls.us
    ("Z8", "Z8_high_efficiency_low.NEF", "https://raw.pixls.us/data/Nikon/Z%208/Nikon_Z8_high_efficiency_low.NEF"),
    ("Z8", "Z8_14bit_lossless_compression.NEF", "https://raw.pixls.us/data/Nikon/Z%208/Nikon_Z8_raw_14_bit_lossless_compression.NEF"),
    ("Z8", "Z8_high_efficiency_high.NEF", "https://raw.pixls.us/data/Nikon/Z%208/Nikon_Z8_raw_high_efficiency_hight.NEF"),
]


def source_url_by_relpath() -> dict[str, str]:
    """Maps 'public/D300/RAW_NIKON_D300.NEF' -> url."""
    return {f"public/{sub}/{name}": url for sub, name, url in SAMPLES}
