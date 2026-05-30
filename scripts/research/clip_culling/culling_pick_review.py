#!/usr/bin/env python3
"""Compare candidate culling embedding models by pick/reject quality.

Reads the E2E DB (image_scoring_test @5433) where all candidate towers are
populated, sub-clusters each burst stack at a *matched granularity* (fixed K so
the only variable is embedding geometry), keeps the best-by-score per micro-group
and rejects the rest, then scores those decisions against HUMAN ground truth
(rating + label; cull_decision is excluded — it is MobileNet-pipeline-derived).

Outputs an aggregate metrics table and, for two stacks, a per-cluster thumbnail
manifest for visual review.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import psycopg2

SPACES = {
    "mobilenet_v2_imagenet_gap": ("image_embeddings", 1280),
    "clip_vit_b32_image": ("image_embeddings_512", 512),
    "openclip_l14_laion2b_image": ("image_embeddings_768", 768),
    "openai_clip_vit_l14_image": ("image_embeddings_768", 768),
    "siglip2_base_image": ("image_embeddings_768", 768),
    "dinov2_reg_base_image": ("image_embeddings_768", 768),
}

ELIGIBLE_SQL = """
  select i.stack_id, count(*) n
  from images i
  where i.stack_id is not null and i.thumbnail_path<>''
        and i.rating is not null and i.label is not null
  group by i.stack_id having count(*) between 8 and 19
  order by n desc, i.stack_id limit 12
"""


def conn():
    return psycopg2.connect(host="127.0.0.1", port=5433, dbname="image_scoring_test",
                            user="postgres", password="postgres")


def load_stack(cur, stack_id):
    cur.execute("""select id, score_general, rating, label, cull_decision,
                          thumbnail_path, file_name
                   from images where stack_id=%s and thumbnail_path<>''
                     and rating is not null and label is not null""", (stack_id,))
    rows = []
    for r in cur.fetchall():
        rows.append(dict(id=r[0], score_general=float(r[1] or 0), rating=int(r[2] or 0),
                         label=(r[3] or ""), cull=(r[4] or ""), thumb=r[5], name=r[6]))
    return rows


def load_emb(cur, space, ids):
    tbl, dim = SPACES[space]
    cur.execute(f"""select t.image_id, t.embedding from {tbl} t
                    join embedding_spaces e on e.id=t.embedding_space_id
                    where e.code=%s and t.image_id = any(%s)""", (space, ids))
    out = {}
    for iid, v in cur.fetchall():
        arr = np.asarray(json.loads(v), dtype=np.float32) if isinstance(v, str) \
            else np.frombuffer(v, dtype=np.float32)
        out[int(iid)] = arr
    return out


def cluster_fixed_k(rows, emb, k):
    """Agglomerative cosine, n_clusters=k. Returns list[list[row]] + silhouette."""
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import silhouette_score
    valid = [r for r in rows if r["id"] in emb]
    if len(valid) < k or k < 2:
        return [valid], float("nan")
    X = np.vstack([emb[r["id"]] for r in valid]).astype(np.float32)
    labels = AgglomerativeClustering(n_clusters=k, metric="cosine",
                                     linkage="average").fit_predict(X)
    try:
        sil = float(silhouette_score(X, labels, metric="cosine"))
    except Exception:
        sil = float("nan")
    buckets = {}
    for lab, r in zip(labels, valid):
        buckets.setdefault(int(lab), []).append(r)
    return list(buckets.values()), sil


def decide(clusters, m=3):
    """Best-m by score_general per cluster -> pick; rest -> reject."""
    picks, rejects = [], []
    for grp in clusters:
        srt = sorted(grp, key=lambda r: -r["score_general"])
        picks += srt[:m]
        rejects += srt[m:]
    return picks, rejects


def is_human_reject(r):
    return r["rating"] <= 2 or r["label"].lower() == "red"


def is_human_keeper(r):
    return r["rating"] >= 4


def main():
    c = conn(); cur = c.cursor()
    cur.execute(ELIGIBLE_SQL)
    stacks = [(r[0], r[1]) for r in cur.fetchall()]
    print(f"Eligible stacks: {len(stacks)} -> {[s for s,_ in stacks]}\n")

    agg = {s: dict(kept_r=[], rej_r=[], sil=[], misdrop=0, badpick=0, npick=0, nrej=0)
           for s in SPACES}

    for stack_id, n in stacks:
        rows = load_stack(cur, stack_id)
        k = max(2, round(len(rows) / 4))
        for space in SPACES:
            emb = load_emb(cur, space, [r["id"] for r in rows])
            clusters, sil = cluster_fixed_k(rows, emb, k)
            picks, rejects = decide(clusters, m=3)
            a = agg[space]
            a["sil"].append(sil)
            a["kept_r"] += [r["rating"] for r in picks]
            a["rej_r"] += [r["rating"] for r in rejects]
            a["npick"] += len(picks); a["nrej"] += len(rejects)
            a["misdrop"] += sum(1 for r in rejects if is_human_keeper(r))  # good frame dropped
            a["badpick"] += sum(1 for r in picks if is_human_reject(r))    # bad frame kept

    print(f"{'space':30} {'sil':>6} {'mean_keep':>9} {'mean_rej':>8} {'gap':>5} "
          f"{'misdrop':>7} {'badpick':>7}")
    ranked = []
    for space, a in agg.items():
        sil = np.nanmean(a["sil"])
        mk = np.mean(a["kept_r"]); mr = np.mean(a["rej_r"]); gap = mk - mr
        score = gap - 0.05 * (a["misdrop"] + a["badpick"])
        ranked.append((score, space, sil, mk, mr, gap, a["misdrop"], a["badpick"]))
    for score, space, sil, mk, mr, gap, md, bp in sorted(ranked, reverse=True):
        print(f"{space:30} {sil:6.3f} {mk:9.3f} {mr:8.3f} {gap:5.2f} {md:7d} {bp:7d}")

    # Visual manifest for 2 stacks
    review_stacks = [s for s, _ in stacks[:2]]
    manifest = {}
    for stack_id in review_stacks:
        rows = load_stack(cur, stack_id)
        k = max(2, round(len(rows) / 4))
        manifest[stack_id] = {"n": len(rows), "k": k, "models": {}}
        for space in SPACES:
            emb = load_emb(cur, space, [r["id"] for r in rows])
            clusters, sil = cluster_fixed_k(rows, emb, k)
            picks, rejects = decide(clusters, m=3)
            pick_ids = {r["id"] for r in picks}
            cl = []
            for grp in clusters:
                srt = sorted(grp, key=lambda r: -r["score_general"])
                cl.append([{"id": r["id"], "name": r["name"], "rating": r["rating"],
                            "label": r["label"], "score": round(r["score_general"], 1),
                            "thumb": r["thumb"], "pick": r["id"] in pick_ids} for r in srt])
            manifest[stack_id]["models"][space] = {"sil": sil, "clusters": cl}
    with open("reports/clip-culling/pick_review_manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"\nWrote manifest for stacks {review_stacks} -> reports/clip-culling/pick_review_manifest.json")
    c.close()


if __name__ == "__main__":
    sys.exit(main())
