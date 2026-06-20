"""Offline stack-hierarchy tuning harness (throwaway research tool).

Replicates the production two-level clustering *exactly* using the already
persisted embeddings, so we can sweep L1 (mobilenet, time-gap) and L2
(openclip_l14) thresholds in-memory without re-running the heavy pipeline.

Production parity:
  * L1: per-folder, sort by capture time, split into time batches when the
        consecutive capture-time gap exceeds ``time_gap`` seconds; within each
        batch of >=2 images run AgglomerativeClustering(metric='cosine',
        linkage='average', distance_threshold=l1). Singletons -> own stack.
        (modules/clustering.py)
  * L2: within each L1 stack run the same clustering on openclip_l14 vectors at
        ``l2`` (modules/sub_clustering.compute_sub_clusters).

Outputs montages (best thumbnail per stack overview + per-stack member grids
split by substack) so the grouping can be judged visually.

Usage:
  python scripts/research/clip_culling/stack_tune_offline.py \
      --folder-id 72078 --l1 0.18 --gap 600 --l2 0.04 --tag baseline
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import datetime

import numpy as np
import psycopg2
from PIL import Image, ImageDraw, ImageFont
from sklearn.cluster import AgglomerativeClustering

L1_SPACE_ID = 1   # mobilenet_v2_imagenet_gap (1280-d), image_embeddings
L2_SPACE_ID = 5   # openclip_l14_laion2b_image (768-d), image_embeddings_768

OUT_DIR = os.path.join("reports", "clip-culling", "stack-tune")


def connect():
    return psycopg2.connect(
        host="127.0.0.1", port=5432, dbname="image_scoring",
        user="postgres", password="postgres",
    )


def _parse_vec(text):
    if not text:
        return None
    arr = np.fromstring(text.strip().lstrip("[").rstrip("]"), sep=",", dtype=np.float32)
    if arr.size == 0 or not np.isfinite(arr).all():
        return None
    return arr


def load_folder(conn, folder_id):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT i.id, i.file_name, i.thumbnail_path_win, i.score_general,
               e.date_time_original
        FROM images i LEFT JOIN image_exif e ON e.image_id = i.id
        WHERE i.folder_id = %s
        """,
        (folder_id,),
    )
    imgs = {}
    order = []
    for iid, name, thumb, score, dto in cur.fetchall():
        imgs[iid] = {
            "id": iid, "file_name": name, "thumb": thumb,
            "score": float(score or 0.0), "time": dto,
        }
        order.append(iid)

    ids = list(imgs.keys())
    emb1 = _load_emb(cur, "image_embeddings", L1_SPACE_ID, ids)
    emb2 = _load_emb(cur, "image_embeddings_768", L2_SPACE_ID, ids)
    cur.close()
    for iid in ids:
        imgs[iid]["v1"] = emb1.get(iid)
        imgs[iid]["v2"] = emb2.get(iid)
    return imgs, order


def _load_emb(cur, table, space_id, ids):
    cur.execute(
        f"SELECT image_id, embedding::text FROM {table} "
        f"WHERE embedding_space_id = %s AND image_id = ANY(%s)",
        (space_id, ids),
    )
    out = {}
    for iid, txt in cur.fetchall():
        v = _parse_vec(txt)
        if v is not None:
            out[iid] = v
    return out


def _agglo(vecs, threshold):
    """Return integer labels for the row-stacked vectors at cosine/average."""
    if len(vecs) < 2:
        return [0] * len(vecs)
    X = np.vstack(vecs).astype(np.float32)
    model = AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=float(threshold),
    )
    return list(model.fit_predict(X))


def cluster_l1(imgs, order, l1, gap_s):
    """Replicate production L1: time-batch then cosine agglomerative per batch."""
    # Sort by capture time; None times sort last and become isolated singletons.
    timed = [(imgs[i]["time"], i) for i in order]
    timed.sort(key=lambda t: (t[0] is None, t[0] or datetime.min))

    batches = []
    cur_batch = []
    prev_t = None
    for t, iid in timed:
        if t is None:
            if cur_batch:
                batches.append(cur_batch)
                cur_batch = []
            batches.append([iid])
            prev_t = None
            continue
        if prev_t is not None and (t - prev_t).total_seconds() > gap_s:
            batches.append(cur_batch)
            cur_batch = []
        cur_batch.append(iid)
        prev_t = t
    if cur_batch:
        batches.append(cur_batch)

    stacks = []
    for batch in batches:
        valid = [i for i in batch if imgs[i]["v1"] is not None]
        missing = [i for i in batch if imgs[i]["v1"] is None]
        if len(valid) >= 2:
            labels = _agglo([imgs[i]["v1"] for i in valid], l1)
            groups = defaultdict(list)
            for lbl, iid in zip(labels, valid):
                groups[lbl].append(iid)
            stacks.extend(groups.values())
        elif valid:
            stacks.append(valid)
        for i in missing:  # no L1 embedding -> isolated
            stacks.append([i])
    return stacks


def cluster_l2(imgs, stack_ids, l2):
    valid = [i for i in stack_ids if imgs[i]["v2"] is not None]
    missing = [i for i in stack_ids if imgs[i]["v2"] is None]
    subs = []
    if len(valid) >= 2:
        labels = _agglo([imgs[i]["v2"] for i in valid], l2)
        groups = defaultdict(list)
        for lbl, iid in zip(labels, valid):
            groups[lbl].append(iid)
        subs.extend(groups.values())
    elif valid:
        subs.append(valid)
    if missing:
        subs.append(missing)
    return subs


# ---------- montage rendering ----------

def _load_thumb(path, box):
    try:
        im = Image.open(path).convert("RGB")
        im.thumbnail((box, box))
        return im
    except Exception:
        return Image.new("RGB", (box, box), (40, 40, 40))


def _font():
    try:
        return ImageFont.truetype("arial.ttf", 16)
    except Exception:
        return ImageFont.load_default()


def montage(cells, cols, box, out_path, pad=4, label_h=20):
    """cells: list of (thumb_path, label). Renders a labeled grid."""
    if not cells:
        return
    rows = (len(cells) + cols - 1) // cols
    cw, ch = box + pad, box + pad + label_h
    canvas = Image.new("RGB", (cols * cw + pad, rows * ch + pad), (15, 15, 15))
    draw = ImageDraw.Draw(canvas)
    font = _font()
    for idx, (path, label) in enumerate(cells):
        r, c = divmod(idx, cols)
        x, y = pad + c * cw, pad + r * ch
        canvas.paste(_load_thumb(path, box), (x, y))
        draw.text((x + 2, y + box + 2), label, fill=(230, 230, 230), font=font)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder-id", type=int, default=72078)
    ap.add_argument("--l1", type=float, default=0.18)
    ap.add_argument("--gap", type=float, default=600)
    ap.add_argument("--l2", type=float, default=0.04)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--drill", type=int, default=8,
                    help="render member grids for the N largest stacks")
    args = ap.parse_args()

    conn = connect()
    imgs, order = load_folder(conn, args.folder_id)
    conn.close()

    n = len(imgs)
    cov1 = sum(1 for i in imgs.values() if i["v1"] is not None)
    cov2 = sum(1 for i in imgs.values() if i["v2"] is not None)

    stacks = cluster_l1(imgs, order, args.l1, args.gap)
    stacks.sort(key=lambda s: -len(s))

    sub_counts = []
    multi_leaf = 0
    for s in stacks:
        subs = cluster_l2(imgs, s, args.l2) if len(s) >= 2 else [s]
        sub_counts.append(len(subs))
        if len(subs) >= 2:
            multi_leaf += 1

    sizes = sorted((len(s) for s in stacks), reverse=True)
    singles = sum(1 for s in stacks if len(s) == 1)

    print(f"=== tag={args.tag}  l1={args.l1} gap={args.gap}s l2={args.l2} ===")
    print(f"images={n}  L1cov={cov1}/{n}  L2cov={cov2}/{n}")
    print(f"root_stacks={len(stacks)}  singletons={singles}  "
          f"multi_image={len(stacks)-singles}")
    print(f"size_dist(top15)={sizes[:15]}  max={sizes[0] if sizes else 0}")
    print(f"total_substacks={sum(sub_counts)}  multi_leaf_stacks(>=2 subs)={multi_leaf}")

    # Overview: best thumb per stack
    overview_cells = []
    for si, s in enumerate(stacks):
        best = max(s, key=lambda i: imgs[i]["score"])
        overview_cells.append((imgs[best]["thumb"], f"S{si} n={len(s)}"))
    ov = montage(overview_cells, cols=10, box=190,
                 out_path=os.path.join(OUT_DIR, f"{args.tag}_overview.jpg"))
    print(f"overview -> {ov}")

    # Drill: member grids (split by substack) for the N largest multi-image stacks
    drill_paths = []
    drilled = 0
    for si, s in enumerate(stacks):
        if len(s) < 2 or drilled >= args.drill:
            continue
        subs = cluster_l2(imgs, s, args.l2)
        cells = []
        for sub_idx, sub in enumerate(subs):
            for iid in sorted(sub, key=lambda i: -imgs[i]["score"]):
                cells.append((imgs[iid]["thumb"],
                              f"sub{sub_idx} {imgs[iid]['file_name'][:8]} {imgs[iid]['score']:.2f}"))
        p = montage(cells, cols=min(6, len(cells)), box=210,
                    out_path=os.path.join(OUT_DIR, f"{args.tag}_S{si}_n{len(s)}_subs{len(subs)}.jpg"))
        drill_paths.append(p)
        drilled += 1
    for p in drill_paths:
        print(f"drill -> {p}")


if __name__ == "__main__":
    main()
