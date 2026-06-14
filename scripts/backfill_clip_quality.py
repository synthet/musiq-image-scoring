#!/usr/bin/env python3
"""Backfill ``clip_quality_v0`` over existing images (Postgres).

Computes the auxiliary CLIP prompt-quality score from already-persisted
``clip_vit_b32_image`` (512-d) embeddings and upserts it into
``image_model_scores`` (model ``clip_quality_v0``). Images without a B/32
embedding are skipped (``ensure=False`` — no GPU image inference here; run the
keywords phase or ``scripts/backfill_culling_embeddings.py --space
clip_vit_b32_image`` first if you need to generate them).

Run in WSL with the app venv (CLIP text tower)::

    source ~/.venvs/tf/bin/activate
    python -m scripts.backfill_clip_quality --batch-size 1000
    python -m scripts.backfill_clip_quality --folder-id 62 --dry-run

Postgres-only. See modules/clip_quality.py and reports/clip-culling/prompt-quality/.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

logger = logging.getLogger("backfill_clip_quality")


def _ids_with_b32(folder_id: int | None, limit: int | None) -> list[int]:
    from modules import db_postgres
    from modules.embedding_spaces import CLIP_IMAGE_SPACE_CODE, get_embedding_space_id

    sid = get_embedding_space_id(CLIP_IMAGE_SPACE_CODE)
    if sid is None:
        raise RuntimeError(f"Space {CLIP_IMAGE_SPACE_CODE!r} not registered.")
    sql = (
        "SELECT e.image_id FROM image_embeddings_512 e "
        "JOIN images i ON i.id = e.image_id "
        "WHERE e.embedding_space_id = %s"
    )
    params: list = [sid]
    if folder_id is not None:
        sql += " AND i.folder_id = %s"
        params.append(folder_id)
    sql += " ORDER BY e.image_id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = db_postgres.execute_select(sql, tuple(params))
    return [int(r["image_id"]) for r in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder-id", type=int, default=None, help="Restrict to one folder")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of images")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true", help="Count eligible images only")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from modules import clip_quality, db

    db.init_db()
    if db._get_db_engine() != "postgres":  # noqa: SLF001
        logger.error("Backfill requires database.engine = 'postgres'.")
        return 2

    ids = _ids_with_b32(args.folder_id, args.limit)
    logger.info("Images with %s embeddings: %d", "clip_vit_b32_image", len(ids))
    if args.dry_run or not ids:
        return 0

    total = len(ids)
    scored = 0
    t0 = time.time()
    last_log = t0
    for start in range(0, total, args.batch_size):
        batch = ids[start:start + args.batch_size]
        # ensure=False: embeddings already exist (we selected on them).
        out = clip_quality.compute_clip_quality(batch, persist=True, ensure=False)
        scored += len(out)
        now = time.time()
        if now - last_log >= 15 or start + args.batch_size >= total:
            processed = min(start + args.batch_size, total)
            rate = processed / max(now - t0, 1e-6)
            eta = (total - processed) / max(rate, 1e-6)
            logger.info("clip_quality_v0 %d/%d (%.1f%%) scored=%d %.0f img/s ETA %.0f min",
                        processed, total, 100 * processed / total, scored, rate, eta / 60)
            last_log = now

    logger.info("Done: persisted clip_quality_v0 for %d/%d images in %.1f min",
                scored, total, (time.time() - t0) / 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
