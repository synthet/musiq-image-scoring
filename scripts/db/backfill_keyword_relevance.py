"""Backfill ``image_keywords.relevance_weight`` from stored CLIP embeddings.

For every ``image_keywords`` row still at the default weight (``1.0``) whose
keyword is a plain CLIP keyword (not a ``species:`` tag) and whose image has a
stored CLIP image embedding (``clip_vit_b32_image``, 512-d), recompute the
relevance weight as ``cosine_to_relevance(cos(image_emb, text_emb))`` where the
text embedding is the CLIP text tower applied to ``"a photo of {keyword}"``.

This reuses the persisted image embeddings, so no image vision-tower pass is
needed — only the (much cheaper) text tower runs, once per unique keyword.

Postgres only (embeddings live in Postgres). Run under the ML venv
(``~/.venvs/tf``) in WSL where torch/transformers are available:

    python -m scripts.db.backfill_keyword_relevance --dry-run --limit 500
    python -m scripts.db.backfill_keyword_relevance            # apply all

The job is idempotent and resumable: it only touches rows still at the default
weight, so re-running after an interruption continues where it left off.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db  # noqa: E402
from modules.embedding_spaces import CLIP_IMAGE_SPACE_CODE  # noqa: E402
from modules.keyword_relevance import cosine_to_relevance  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Rows at exactly the default are treated as "unset". Use a tiny epsilon so we
# don't skip legitimately-computed weights that happen to be near 1.0.
DEFAULT_WEIGHT = 1.0
DEFAULT_EPS = 1e-9
TEXT_BATCH = 256
UPDATE_BATCH = 500


def _load_clip():
    """Load the configured CLIP model + processor (text tower used here)."""
    import torch
    from transformers import CLIPModel, CLIPProcessor

    from modules import config

    name = (config.get_config_section("tagging") or {}).get(
        "clip_model", "openai/clip-vit-base-patch32"
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Loading CLIP model %s on %s ...", name, device)
    model = CLIPModel.from_pretrained(name).to(device)
    processor = CLIPProcessor.from_pretrained(name)
    model.eval()
    return model, processor, device


def _encode_text(model, processor, device, keywords: list[str]) -> dict[str, np.ndarray]:
    """Return keyword -> L2-normalized text embedding (float32) for the prompts."""
    import torch

    out: dict[str, np.ndarray] = {}
    for start in range(0, len(keywords), TEXT_BATCH):
        chunk = keywords[start : start + TEXT_BATCH]
        prompts = [f"a photo of {k}" for k in chunk]
        inputs = processor(text=prompts, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            feats = model.get_text_features(**inputs)
        feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        feats = feats.detach().cpu().to(torch.float32).numpy()
        for kw, vec in zip(chunk, feats):
            out[kw] = vec.reshape(-1)
    return out


def _emb_to_vec(raw: bytes | None) -> np.ndarray | None:
    if not raw:
        return None
    arr = np.frombuffer(raw, dtype=np.float32)
    return arr.reshape(-1) if arr.size else None


def run(dry_run: bool = False, limit: int | None = None) -> None:
    if db._get_db_engine() != "postgres":  # noqa: SLF001 — engine probe
        logger.error("Backfill requires the Postgres engine (embeddings are Postgres-only).")
        return

    where_limit = ""
    params: tuple = ()
    if limit and limit > 0:
        where_limit = "LIMIT %s"
        params = (int(limit),)

    from modules import db_postgres

    rows = db_postgres.execute_select(
        f"""
        SELECT ik.image_id   AS image_id,
               ik.keyword_id AS keyword_id,
               kd.keyword_display AS keyword_display,
               kd.keyword_norm    AS keyword_norm
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        WHERE ik.relevance_weight BETWEEN %s AND %s
          AND kd.keyword_norm NOT LIKE 'species:%%'
        ORDER BY ik.image_id
        {where_limit}
        """,
        (DEFAULT_WEIGHT - DEFAULT_EPS, DEFAULT_WEIGHT + DEFAULT_EPS, *params),
    )
    logger.info("Candidate rows at default weight: %d", len(rows))
    if not rows:
        return

    image_ids = sorted({int(r["image_id"]) for r in rows})
    keywords = sorted({(r["keyword_display"] or r["keyword_norm"]) for r in rows})

    # Fetch stored CLIP image embeddings in batches.
    emb: dict[int, np.ndarray] = {}
    for start in range(0, len(image_ids), 1000):
        chunk = image_ids[start : start + 1000]
        raw = db.get_image_embeddings_batch_for_space(CLIP_IMAGE_SPACE_CODE, chunk)
        for iid, b in raw.items():
            vec = _emb_to_vec(b)
            if vec is not None:
                emb[int(iid)] = vec
    logger.info("Images with a stored CLIP embedding: %d / %d", len(emb), len(image_ids))

    model, processor, device = _load_clip()
    text_vecs = _encode_text(model, processor, device, keywords)

    updates: list[tuple[float, int, int]] = []
    applied = skipped_no_emb = skipped_dim = 0
    for r in rows:
        iid = int(r["image_id"])
        img_vec = emb.get(iid)
        if img_vec is None:
            skipped_no_emb += 1
            continue
        kw = r["keyword_display"] or r["keyword_norm"]
        tvec = text_vecs.get(kw)
        if tvec is None or tvec.shape != img_vec.shape:
            skipped_dim += 1
            continue
        cosine = float(np.dot(img_vec, tvec))
        weight = cosine_to_relevance(cosine)
        updates.append((weight, iid, int(r["keyword_id"])))
        applied += 1

    logger.info(
        "Computed %d weights (skipped %d no-embedding, %d dim/missing-text). dry_run=%s",
        applied, skipped_no_emb, skipped_dim, dry_run,
    )
    if dry_run or not updates:
        for w, iid, kid in updates[:10]:
            logger.info("  would set image_id=%s keyword_id=%s -> %.4f", iid, kid, w)
        return

    written = 0
    for start in range(0, len(updates), UPDATE_BATCH):
        chunk = updates[start : start + UPDATE_BATCH]

        def _tx(tx, _chunk=chunk):
            for w, iid, kid in _chunk:
                tx.execute(
                    "UPDATE image_keywords SET relevance_weight = ? "
                    "WHERE image_id = ? AND keyword_id = ?",
                    (w, iid, kid),
                )

        db.get_connector().run_transaction(_tx)
        written += len(chunk)
        if written % 5000 == 0 or written == len(updates):
            logger.info("Updated %d / %d rows ...", written, len(updates))

    logger.info("Backfill complete. Updated %d image_keywords rows.", written)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Compute but do not write.")
    ap.add_argument("--limit", type=int, default=None, help="Cap candidate rows (testing).")
    args = ap.parse_args()
    run(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
