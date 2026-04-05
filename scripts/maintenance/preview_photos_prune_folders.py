"""
Print which sample top-level folder names under ``photos_prune_root`` would be kept
(whitelist union regex), using merged config — no DB writes.

  python scripts/maintenance/preview_photos_prune_folders.py
"""

from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.photos_top_segment_prune import (  # noqa: E402
    photos_prune_allow_regex_from_config,
    photos_prune_whitelist_from_config,
    top_segment_allowed,
)


def main() -> None:
    pat = photos_prune_allow_regex_from_config(None)
    wl = photos_prune_whitelist_from_config()
    allow_re = re.compile(pat, re.IGNORECASE)

    samples = [
        "D850",
        "D7500",
        "D300",
        "D90",
        "D4S",
        "d500",
        "Z6",
        "Z6 II",
        "Z6III",
        "Z30",
        "Z9",
        "Zf",
        "Zfc",
        "Z6II",
        "Lightroom",
        "Lightroom Classic",
        "TestingSamples",
        "Exports",
        "Archive",
        "Downloads",
        "DCIM",
        "2024",
        "Misc",
        "Z",
        "D",
        "SonyA7",
        "Canon",
    ]

    print("effective_regex:", pat)
    print("whitelist (from config):", sorted(wl) if wl else "(empty)")
    print()
    hdr = f"{'folder_name':<22} {'allowed':<8} reason"
    print(hdr)
    print("-" * len(hdr))
    for name in samples:
        ok = top_segment_allowed(name, whitelist_lower=wl, allow_re=allow_re)
        if name.lower() in wl:
            why = "whitelist"
        elif allow_re.fullmatch(name):
            why = "regex"
        else:
            why = "-"
        print(f"{name:<22} {str(ok):<8} {why}")


if __name__ == "__main__":
    main()
