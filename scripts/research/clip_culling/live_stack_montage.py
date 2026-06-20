"""Render a montage of the LIVE persisted stacks for a folder (verification).

Reads actual images.stack_id / sub_stack_id from Postgres (not a recomputation)
so we can eyeball what the gallery will show after re-cluster + substack backfill.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import psycopg2
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join("reports", "clip-culling", "stack-tune")


def conn():
    return psycopg2.connect(host="127.0.0.1", port=5432, dbname="image_scoring",
                            user="postgres", password="postgres")


def thumb(path, box):
    try:
        im = Image.open(path).convert("RGB"); im.thumbnail((box, box)); return im
    except Exception:
        return Image.new("RGB", (box, box), (40, 40, 40))


def font():
    try:
        return ImageFont.truetype("arial.ttf", 15)
    except Exception:
        return ImageFont.load_default()


def montage(cells, cols, box, out, label_h=20, pad=4):
    if not cells:
        return None
    rows = (len(cells) + cols - 1) // cols
    cw, ch = box + pad, box + pad + label_h
    cv = Image.new("RGB", (cols * cw + pad, rows * ch + pad), (15, 15, 15))
    d = ImageDraw.Draw(cv); f = font()
    for i, (p, lbl) in enumerate(cells):
        r, c = divmod(i, cols); x, y = pad + c * cw, pad + r * ch
        cv.paste(thumb(p, box), (x, y)); d.text((x + 2, y + box + 2), lbl, fill=(230, 230, 230), font=f)
    os.makedirs(os.path.dirname(out), exist_ok=True); cv.save(out); return out


def main():
    folder_id = int(sys.argv[1]) if len(sys.argv) > 1 else 72078
    c = conn(); cur = c.cursor()
    cur.execute(
        "SELECT id, file_name, thumbnail_path_win, score_general, stack_id, sub_stack_id "
        "FROM images WHERE folder_id=%s AND stack_id IS NOT NULL", (folder_id,))
    stacks = defaultdict(list)
    for iid, name, thmb, score, sid, ssid in cur.fetchall():
        stacks[sid].append({"id": iid, "name": name, "thumb": thmb,
                            "score": float(score or 0), "sub": ssid})
    c.close()

    order = sorted(stacks, key=lambda s: -len(stacks[s]))
    # Overview: best image per live stack
    cells = []
    for sid in order:
        members = stacks[sid]
        best = max(members, key=lambda m: m["score"])
        nsub = len({m["sub"] for m in members if m["sub"] is not None})
        cells.append((best["thumb"], f"st{sid} n={len(members)} subs={nsub}"))
    print("live stacks:", len(order), "sizes:", [len(stacks[s]) for s in order])
    print(montage(cells, cols=9, box=200, out=os.path.join(OUT, "live_overview.jpg")))


if __name__ == "__main__":
    main()
