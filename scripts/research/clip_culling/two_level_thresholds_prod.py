#!/usr/bin/env python3
"""Sweep the level2 sub-stacking distance threshold against the PRODUCTION library.

Unlike ``two_level_thresholds`` (which reads the small E2E corpus, folders
62/44/45/676), this reads every multi-image stack in production ``image_scoring``
@5432 and the full ``openclip_l14_laion2b_image`` embedding set, then reports the
within-stack leaf sub-stack distribution per threshold. Pure CPU (numpy + the
agglomerative pass in ``compute_leaf_substacks``) — no GPU/WSL; run from the host
venv.

Goal: pick a ``culling.two_level.level2.distance_threshold`` that splits genuine
within-stack variants without (a) collapsing a whole stack to one leaf (caps an
N-frame stack at picks_per_substack) or (b) shattering near-identical frames.

Usage (host)::

    .venv/Scripts/python.exe -m scripts.research.clip_culling.two_level_thresholds_prod \
        --thresholds 0.03,0.05,0.06,0.08,0.10,0.12
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.two_level_culling import compute_leaf_substacks  # noqa: E402

SPACE = "openclip_l14_laion2b_image"
TABLE = "image_embeddings_768"


def _connect():
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "image_scoring"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", "postgres"),
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _parse_vec(v) -> np.ndarray | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lstrip("[").rstrip("]")
        return np.array([float(x) for x in s.split(",")], dtype=np.float32) if s else None
    if isinstance(v, (bytes, bytearray, memoryview)):
        return np.frombuffer(bytes(v), dtype=np.float32).copy()
    return np.asarray(v, dtype=np.float32)


def load_prod(conn) -> tuple[dict[int, list[int]], dict[int, bytes]]:
    import psycopg2.extras

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM embedding_spaces WHERE code=%s", (SPACE,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"space {SPACE!r} not registered in production")
    sid = int(row["id"])

    cur.execute("SELECT stack_id, id FROM images WHERE stack_id IS NOT NULL")
    stack_map: dict[int, list[int]] = {}
    for r in cur.fetchall():
        stack_map.setdefault(int(r["stack_id"]), []).append(int(r["id"]))

    cur.execute(
        f"SELECT e.image_id, e.embedding FROM {TABLE} e "
        f"JOIN images i ON i.id = e.image_id "
        f"WHERE e.embedding_space_id = %s AND i.stack_id IS NOT NULL",
        (sid,),
    )
    emb: dict[int, bytes] = {}
    for r in cur.fetchall():
        vec = _parse_vec(r["embedding"])
        if vec is not None:
            emb[int(r["image_id"])] = vec.astype(np.float32).tobytes()
    return stack_map, emb


def sweep(stack_map, emb, thresholds) -> dict:
    multi = {sid: ids for sid, ids in stack_map.items() if len(ids) >= 2}
    grid = []
    for t in thresholds:
        leaf_counts, frac_split, singletons_made = [], [], 0
        for ids in multi.values():
            group = [{"id": i} for i in ids]
            leaves = compute_leaf_substacks(group, emb, t)
            n = len(leaves)
            leaf_counts.append(n)
            frac_split.append(1.0 if n > 1 else 0.0)
            singletons_made += sum(1 for lf in leaves if len(lf) == 1)
        arr = np.array(leaf_counts, dtype=float) if leaf_counts else np.array([0.0])
        grid.append(
            {
                "threshold": t,
                "mean_leaf_substacks": round(float(arr.mean()), 3),
                "median_leaf_substacks": float(np.median(arr)),
                "max_leaf_substacks": int(arr.max()),
                "pct_stacks_split": round(100.0 * float(np.mean(frac_split)), 1),
                "singleton_leaves": singletons_made,
            }
        )
    return {
        "space": SPACE,
        "multi_image_stacks": len(multi),
        "embeddings_loaded": len(emb),
        "grid": grid,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--thresholds", default="0.03,0.05,0.06,0.08,0.10,0.12")
    ap.add_argument("--output", type=Path, default=Path("reports/clip-culling/two_level_thresholds_prod.json"))
    args = ap.parse_args()
    thr = [float(x) for x in args.thresholds.split(",") if x.strip()]

    conn = _connect()
    stack_map, emb = load_prod(conn)
    payload = sweep(stack_map, emb, thr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"space={payload['space']}  multi_image_stacks={payload['multi_image_stacks']}  "
          f"embeddings={payload['embeddings_loaded']}")
    print(f"{'thr':>6} {'mean_leaves':>12} {'median':>7} {'max':>5} {'%split':>7} {'singletons':>11}")
    for g in payload["grid"]:
        print(f"{g['threshold']:>6} {g['mean_leaf_substacks']:>12} {g['median_leaf_substacks']:>7} "
              f"{g['max_leaf_substacks']:>5} {g['pct_stacks_split']:>7} {g['singleton_leaves']:>11}")
    print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
