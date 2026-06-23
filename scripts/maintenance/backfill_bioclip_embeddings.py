#!/usr/bin/env python3
"""Backfill ``bioclip_2_image`` (768-d) for images missing that embedding space.

Uses BioCLIP 2 via OpenCLIP (``hf-hub:imageomics/bioclip-2``). Postgres-only.

Example::

    source ~/.venvs/tf/bin/activate
    python -m scripts.backfill_bioclip_embeddings --dry-run
    python -m scripts.backfill_bioclip_embeddings --batch-size 32
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import List, Tuple

from modules.embedding_spaces import BIOCLIP_IMAGE_SPACE_CODE

logger = logging.getLogger("backfill_bioclip_embeddings")

MODEL_ID = "hf-hub:imageomics/bioclip-2"


def _missing_rows(folder_id: int | None, limit: int | None) -> List[Tuple[int, str, str]]:
    from modules import db_postgres
    from modules.embedding_spaces import get_embedding_space_id

    space_id = get_embedding_space_id(BIOCLIP_IMAGE_SPACE_CODE)
    if space_id is None:
        raise RuntimeError(
            f"Space {BIOCLIP_IMAGE_SPACE_CODE!r} not registered; run alembic upgrade head."
        )

    sql = (
        "SELECT i.id, i.file_path, COALESCE(i.thumbnail_path, '') AS thumbnail_path "
        "FROM images i "
        "WHERE i.file_path IS NOT NULL AND i.file_path <> '' "
        "AND NOT EXISTS (SELECT 1 FROM image_embeddings_768 e "
        "WHERE e.image_id = i.id AND e.embedding_space_id = %s)"
    )
    params: list = [space_id]
    if folder_id is not None:
        sql += " AND i.folder_id = %s"
        params.append(folder_id)
    sql += " ORDER BY i.id"
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    rows = db_postgres.execute_select(sql, tuple(params))
    return [(int(r["id"]), str(r["file_path"]), str(r["thumbnail_path"])) for r in rows]


def _resolve_paths(rows, use_thumbnails: bool) -> Tuple[List[Tuple[int, str]], int]:
    import os

    from modules import utils

    resolved: List[Tuple[int, str]] = []
    n_thumb = 0
    for image_id, file_path, thumb in rows:
        path = file_path
        if use_thumbnails and thumb:
            local_thumb = utils.convert_path_to_local(thumb)
            if os.path.exists(local_thumb):
                path = thumb
                n_thumb += 1
        resolved.append((image_id, utils.convert_path_to_local(path)))
    return resolved, n_thumb


class BioCLIPEmbedder:
    """Batch image embedder for BioCLIP 2 (768-d, L2-normalized)."""

    def __init__(self, device: str | None = None, fp16: bool = True):
        self._device = device
        self._fp16 = fp16
        self._model = None
        self._preprocess = None

    @property
    def device(self) -> str:
        if self._device is None:
            import torch

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    @property
    def fp16(self) -> bool:
        return self._fp16 and self.device == "cuda"

    def load(self) -> None:
        if self._model is not None:
            return
        import open_clip

        logger.info("Loading BioCLIP 2 (%s) on %s...", MODEL_ID, self.device)
        model, _, preprocess = open_clip.create_model_and_transforms(MODEL_ID)
        model = model.to(self.device).eval()
        if self.fp16:
            model = model.half()
        self._model = model
        self._preprocess = preprocess
        logger.info("BioCLIP 2 loaded.")

    def unload(self) -> None:
        self._model = None
        self._preprocess = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def embed_paths(self, rows: List[Tuple[int, str]], batch_size: int) -> int:
        import numpy as np
        import torch

        from modules import db
        from modules.thumbnails import open_image_for_ml

        self.load()
        persisted = 0
        total = len(rows)
        t0 = time.time()
        last_log = t0
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            tensors = []
            ids: List[int] = []
            for image_id, path in chunk:
                try:
                    img = open_image_for_ml(path).convert("RGB")
                    t = self._preprocess(img)
                    tensors.append(t)
                    ids.append(image_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Cannot open image_id=%s path=%s: %s", image_id, path, exc)
            if not tensors:
                continue
            batch = torch.stack(tensors).to(self.device)
            if self.fp16:
                batch = batch.half()
            with torch.no_grad():
                feats = self._model.encode_image(batch)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            vecs = feats.float().cpu().numpy()
            persist_rows = [
                (ids[i], np.asarray(vecs[i], dtype=np.float32), MODEL_ID) for i in range(len(ids))
            ]
            persisted += db.update_image_embeddings_batch_for_space(
                BIOCLIP_IMAGE_SPACE_CODE, persist_rows
            )
            processed = min(start + batch_size, total)
            now = time.time()
            if now - last_log >= 30 or processed >= total:
                rate = processed / max(now - t0, 1e-6)
                eta = (total - processed) / max(rate, 1e-6)
                logger.info(
                    "[%s] %d/%d (%.1f%%) persisted=%d %.1f img/s ETA %.0f min",
                    BIOCLIP_IMAGE_SPACE_CODE,
                    processed,
                    total,
                    100 * processed / max(total, 1),
                    persisted,
                    rate,
                    eta / 60,
                )
                last_log = now
        return persisted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder-id", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default=None, help="cuda | cpu (default: auto)")
    parser.add_argument("--no-fp16", action="store_true")
    parser.add_argument("--no-thumbnails", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from modules import db

    db.init_db()
    if db._get_db_engine() != "postgres":  # noqa: SLF001
        logger.error("Backfill requires database.engine = 'postgres'.")
        return 2

    rows = _missing_rows(args.folder_id, args.limit)
    logger.info("Images missing %s: %d", BIOCLIP_IMAGE_SPACE_CODE, len(rows))
    if args.dry_run or not rows:
        return 0

    local_rows, n_thumb = _resolve_paths(rows, use_thumbnails=not args.no_thumbnails)
    logger.info(
        "Loading %d via thumbnail, %d via original file", n_thumb, len(local_rows) - n_thumb
    )

    embedder = BioCLIPEmbedder(device=args.device, fp16=not args.no_fp16)
    t0 = time.time()
    try:
        persisted = embedder.embed_paths(local_rows, batch_size=args.batch_size)
    finally:
        embedder.unload()
    elapsed = time.time() - t0
    logger.info(
        "Persisted %d/%d embeddings for %s in %.1f min",
        persisted,
        len(rows),
        BIOCLIP_IMAGE_SPACE_CODE,
        elapsed / 60,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
