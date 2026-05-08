"""
Camera+lens sample definitions for copying from the user's personal library.

Each entry maps a (camera_subdir, local_filename) to the WSL source path
discovered from the image_exif database.  Used by copy_library_samples.py.

These files are NOT redistributable — they stay on disk (.gitignored).
"""

from __future__ import annotations

# (subdir, local_filename, Windows source path)
# One representative NEF per camera body + lens combination.
LIBRARY_SAMPLES: list[tuple[str, str, str]] = [
    # ── D300 ──────────────────────────────────────────────────────────────
    ("D300", "D300_28_70mm_f2_8.NEF",
     r"D:\Photos\D300\28-70mm\2015\2015-09-05\20150905_001.NEF"),
    ("D300", "D300_50mm_f1_4.NEF",
     r"D:\Photos\D300\50mm\2015\2015-09-05\20150905_371.NEF"),

    # ── D90 ───────────────────────────────────────────────────────────────
    ("D90", "D90_10_5mm_f2_8_fisheye.NEF",
     r"D:\Photos\D90\10.5mm\2013\2013-05-01\20130502_0146.NEF"),
    ("D90", "D90_18_55mm_f3_5_5_6.NEF",
     r"D:\Photos\D90\18-55mm\2015\2015-09-08\20150908_0014.NEF"),
    ("D90", "D90_28_70mm_f2_8.NEF",
     r"D:\Photos\D90\28-70mm\2013\2013-05-01\20130502_0074.NEF"),
    ("D90", "D90_28_105mm_f3_5_4_5.NEF",
     r"D:\Photos\D90\28-105mm\2013\2013-06-08\20130609_0241.NEF"),
    ("D90", "D90_35mm_f1_8G.NEF",
     r"D:\Photos\D90\35mm\2013\2013-05-18\20130521_0514.NEF"),
    ("D90", "D90_50mm_f1_4.NEF",
     r"D:\Photos\D90\50mm\2013\2013-05-07\20130507_0347.NEF"),
    ("D90", "D90_50mm_f1_8.NEF",
     r"D:\Photos\D90\50mm\2013\2013-06-30\20130630_1121.NEF"),

    # ── Z6 II ─────────────────────────────────────────────────────────────
    ("Z6II", "Z6II_28mm_f2_8.NEF",
     r"D:\Photos\Z6ii\28mm\2025\2025-06-14\20250614_002.NEF"),
    ("Z6II", "Z6II_28_400mm_f4_8_VR.NEF",
     r"D:\Photos\Z6ii\28-400mm\2025\2025-11-18\DSC_6332.NEF"),
    ("Z6II", "Z6II_40mm_f2.NEF",
     r"D:\Photos\Z6ii\40mm\2025\2025-09-01\DSC_5700.NEF"),
    ("Z6II", "Z6II_MC_105mm_f2_8_VR_S.NEF",
     r"D:\Photos\Z6ii\105mm\2025\2025-06-01\20250601_001.NEF"),

    # ── Z8 ────────────────────────────────────────────────────────────────
    ("Z8", "Z8_28mm_f2_8.NEF",
     r"D:\Photos\Z8\28mm\2025\2025-10-14\DSC_3226.NEF"),
    ("Z8", "Z8_28_400mm_f4_8_VR.NEF",
     r"D:\Photos\Z8\28-400mm\2025\2025-09-21\DSC_0363.NEF"),
    ("Z8", "Z8_180_600mm_f5_6_6_3_VR.NEF",
     r"D:\Photos\Z8\180-600mm\2025\2025-11-16\DSC_5986.NEF"),
    ("Z8", "Z8_MC_105mm_f2_8_VR_S.NEF",
     r"D:\Photos\Z8\105mm\2025\2025-12-17\DSC_6620.NEF"),
]
