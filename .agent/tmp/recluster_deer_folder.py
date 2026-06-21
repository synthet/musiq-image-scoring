#!/usr/bin/env python
"""One-off: re-cluster deer pilot folder with force_rescan."""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from modules import clustering, db  # noqa: E402

FOLDER = "/mnt/d/Photos/Z8/180-600mm/2026/2026-06-14"


def main() -> int:
    db.init_db()
    engine = clustering.ClusteringEngine()
    last = None
    for status in engine.cluster_images(target_folder=FOLDER, force_rescan=True):
        last = status
        if isinstance(status, dict):
            msg = status.get("message") or status.get("status")
            if msg:
                print(msg)
    print("CLUSTERING_DONE", last)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
