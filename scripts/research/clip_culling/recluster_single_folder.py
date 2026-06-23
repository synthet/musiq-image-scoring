"""Re-cluster one folder with force_rescan (capture-time batching + burst_uuid clear)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from modules import clustering, db  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Force re-cluster one folder.")
    parser.add_argument("folder", help="Folder path (WSL), e.g. /mnt/d/Photos/...")
    args = parser.parse_args()

    db.init_db()
    engine = clustering.ClusteringEngine()
    last = None
    for status in engine.cluster_images(target_folder=args.folder, force_rescan=True):
        last = status
        if isinstance(status, dict):
            msg = status.get("message") or status.get("status")
            if msg:
                print(msg)
    print("CLUSTERING_DONE", last)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
