"""Library-wide re-cluster driver (throwaway rollout tool).

Re-clusters every folder with force_rescan using the validated single-folder
path (capture-time batching + burst_uuid clear). Checkpointed so it resumes if
interrupted. Run detached; tail the log for progress.
"""
from __future__ import annotations

import json
import os
import sys
import time

from modules import db, clustering

CKPT = os.path.join("reports", "clip-culling", "rollout_recluster.checkpoint.json")


def load_done():
    if os.path.exists(CKPT):
        try:
            return set(json.load(open(CKPT))["done"])
        except Exception:
            return set()
    return set()


def save_done(done):
    os.makedirs(os.path.dirname(CKPT), exist_ok=True)
    json.dump({"done": sorted(done)}, open(CKPT, "w"))


def main():
    engine = clustering.ClusteringEngine()
    folders = list(db.get_all_folders() or [])
    done = load_done()
    todo = [f for f in folders if f not in done]
    t0 = time.time()
    print(f"START folders_total={len(folders)} done={len(done)} todo={len(todo)}", flush=True)
    for i, folder in enumerate(todo):
        try:
            last = None
            for status in engine.cluster_images(target_folder=folder, force_rescan=True):
                last = status
            done.add(folder)
            save_done(done)
            msg = last[0] if isinstance(last, tuple) else last
            rate = (i + 1) / max(1e-6, (time.time() - t0))
            eta_min = (len(todo) - (i + 1)) / max(1e-6, rate) / 60
            print(f"[{i+1}/{len(todo)}] OK {folder} :: {msg} | eta~{eta_min:.0f}min", flush=True)
        except Exception as e:
            print(f"[{i+1}/{len(todo)}] ERR {folder}: {e}", flush=True)
    print(f"ROLLOUT_RECLUSTER_DONE folders={len(done)} elapsed_min={(time.time()-t0)/60:.1f}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
