#!/usr/bin/env python3
"""Input-size sweep: embed/score at multiple long-edge sizes; cache NPZ on disk.

    python -m scripts.research.clip_culling.input_size_native
    python -m scripts.research.clip_culling.input_size_embed --track embedding \\
        --long-edges 128,224,384,512,768 --source thumb,file --models all
    python -m scripts.research.clip_culling.input_size_embed --track iqa \\
        --long-edges 224,384,512,768 --source thumb --subset 500 --models liqe,topiq,arniqa
    python -m scripts.research.clip_culling.input_size_embed --track caption \\
        --long-edges 224,384,512,768 --source thumb,file
"""

from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

import numpy as np

from scripts.research.clip_culling import common, checkpoints
from scripts.research.clip_culling.embed_persist import TOWERS, _build_tower
from scripts.research.clip_culling.wrappers import Tower, l2_normalize

logger = logging.getLogger("clip_culling.input_size_embed")

EMBEDDING_MODELS = {
    "mobilenet": ("mobilenet_v2_imagenet_gap", 1280, "mobilenet"),
    "clip_b32": ("clip_vit_b32_image", 512, "open_clip_b32"),
    **{k: (TOWERS[k][0], 768, k) for k in TOWERS},
}

IQA_MODELS = ("liqe", "topiq", "arniqa", "spaq", "ava", "koniq")

# Per-model long-edge grids (Phase 2).
IQA_LONG_EDGES_BY_MODEL: dict[str, tuple[int, ...]] = {
    "liqe": common.IQA_LONG_EDGES_STANDARD,
    "topiq": common.IQA_LONG_EDGES_STANDARD + common.IQA_LONG_EDGES_HIGH,
    "arniqa": common.IQA_LONG_EDGES_STANDARD + common.IQA_LONG_EDGES_HIGH,
    "spaq": common.MUSIQ_LONG_EDGES,
    "ava": common.MUSIQ_LONG_EDGES,
    "koniq": common.MUSIQ_LONG_EDGES,
}

BLIP_MODEL = "Salesforce/blip-image-captioning-base"


def _seeded_rows(folders: list[int]) -> list[dict]:
    fcsv = ",".join(str(f) for f in folders)
    from modules import db_postgres

    rows = db_postgres.execute_select(
        f"SELECT id, file_path, thumbnail_path, thumbnail_path_win "
        f"FROM images WHERE folder_id IN ({fcsv}) ORDER BY id"
    )
    return [dict(r) for r in rows]


def _subset_rows(rows: list[dict], n: int) -> list[dict]:
    if n <= 0 or n >= len(rows):
        return rows
    step = max(1, len(rows) // n)
    return rows[::step][:n]


def _load_batch_pils(
    batch: list[dict],
    source: str,
    long_edge: int,
) -> tuple[list, list[int]]:
    pils, ids = [], []
    for r in batch:
        path = common.resolve_read_path(r, source=source)
        if not path:
            continue
        try:
            pils.append(common.load_pil_resized(path, long_edge))
            ids.append(r["id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("decode failed id=%s: %s", r["id"], e)
    return pils, ids


def _save_npz(path: Path, ids: list[int], vectors: np.ndarray, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        image_ids=np.asarray(ids, dtype=np.int32),
        embeddings=vectors.astype(np.float32),
        meta=np.array([meta], dtype=object),
    )
    logger.info("Wrote %s (%d vectors)", path, len(ids))


def _save_caption_npz(path: Path, ids: list[int], captions: list[str], meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        image_ids=np.asarray(ids, dtype=np.int32),
        captions=np.asarray(captions, dtype=object),
        meta=np.array([meta], dtype=object),
    )
    logger.info("Wrote %s (%d captions)", path, len(ids))


class _MobileNetEmbedder:
    """1280-d MobileNetV2 GAP (matches clustering resize to 224)."""

    def __init__(self):
        self.model = None
        self.telemetry = {"images": 0, "seconds": 0.0, "peak_vram_mb": 0.0}

    def load(self):
        if self.model is not None:
            return
        from tensorflow.keras.applications import MobileNetV2

        self.model = MobileNetV2(
            weights="imagenet", include_top=False, pooling="avg", input_shape=(224, 224, 3)
        )

    def embed(self, pils, batch_size: int = 32) -> np.ndarray:
        import time

        from PIL import Image
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

        self.load()
        out = []
        t0 = time.time()
        batch_imgs = []
        for img in pils:
            img = img.convert("RGB").resize((224, 224), Image.LANCZOS)
            x = preprocess_input(np.array(img, dtype=np.float32))
            batch_imgs.append(x)
            if len(batch_imgs) >= batch_size:
                preds = self.model.predict(np.array(batch_imgs), verbose=0)
                out.append(preds)
                batch_imgs = []
        if batch_imgs:
            preds = self.model.predict(np.array(batch_imgs), verbose=0)
            out.append(preds)
        emb = np.concatenate(out, axis=0) if out else np.zeros((0, 1280), np.float32)
        self.telemetry["images"] += len(pils)
        self.telemetry["seconds"] += time.time() - t0
        return l2_normalize(emb)


def _build_embedding_runner(
    model_key: str,
    preprocess_size: int | None = None,
) -> tuple[Any, Callable[[list], np.ndarray]]:
    if model_key == "mobilenet":
        holder = _MobileNetEmbedder()
        return holder, holder.embed

    if model_key == "clip_b32":
        tower = Tower("ViT-B-32", "openai", preprocess_size=preprocess_size)
        return tower, tower.embed

    _space, kind, args = TOWERS[model_key]
    if kind == "open_clip":
        tower = Tower(
            args["model_name"],
            args["pretrained"],
            preprocess_size=preprocess_size,
        )
        return tower, tower.embed
    tower = _build_tower(kind, args)
    if preprocess_size and hasattr(tower, "preprocess_size"):
        tower.preprocess_size = preprocess_size
    return tower, tower.embed


def _unload_runner(runner: Any) -> None:
    if hasattr(runner, "unload"):
        runner.unload()


def run_embedding_sweep(
    models: list[str],
    long_edges: list[int],
    sources: list[str],
    folders: list[int],
    chunk: int = 64,
    preprocess_size: int | None = None,
    force: bool = False,
) -> list[dict]:
    rows = _seeded_rows(folders)
    stats = []
    for model_key in models:
        if model_key not in EMBEDDING_MODELS:
            raise ValueError(f"Unknown embedding model {model_key!r}; valid: {list(EMBEDDING_MODELS)}")
        runner, embed_fn = _build_embedding_runner(model_key, preprocess_size=preprocess_size)
        for source in sources:
            for long_edge in long_edges:
                path = common.npz_cache_path(
                    model_key, source, long_edge, preprocess_size=preprocess_size
                )
                if path.exists() and not force:
                    logger.info("Skip existing %s", path.name)
                    stats.append({"model": model_key, "source": source, "long_edge": long_edge, "skipped": True})
                    continue
                logger.info(
                    "[%s/%s long_edge=%d] embedding %d images (chunk=%d)",
                    model_key, source, long_edge, len(rows), chunk,
                )
                all_ids: list[int] = []
                all_emb: list[np.ndarray] = []
                for i in range(0, len(rows), chunk):
                    batch = rows[i : i + chunk]
                    pils, ids = _load_batch_pils(batch, source, long_edge)
                    if not pils:
                        continue
                    emb = embed_fn(pils)
                    all_ids.extend(ids)
                    all_emb.append(emb)
                    if (i // chunk) % 10 == 0 or i + chunk >= len(rows):
                        logger.info(
                            "[%s/%s le=%d] progress %d/%d images",
                            model_key, source, long_edge, len(all_ids), len(rows),
                        )
                if not all_emb:
                    logger.warning("No embeddings for %s %s %d", model_key, source, long_edge)
                    continue
                mat = np.concatenate(all_emb, axis=0)
                telem = getattr(runner, "telemetry", {})
                if hasattr(telem, "as_dict"):
                    telem = telem.as_dict()
                _save_npz(
                    path,
                    all_ids,
                    mat,
                    {
                        "model": model_key,
                        "source": source,
                        "long_edge": long_edge,
                        "preprocess_size": preprocess_size,
                        "n": len(all_ids),
                        "telemetry": telem,
                    },
                )
                stats.append({
                    "model": model_key,
                    "source": source,
                    "long_edge": long_edge,
                    "n": len(all_ids),
                    "path": str(path),
                    "preprocess_size": preprocess_size,
                })
        _unload_runner(runner)
    return stats


def _score_iqa_temp_path(pil_img, scorer, model_name: str, long_edge: int) -> float | None:
    import os

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        pil_img.convert("RGB").save(tmp.name, "JPEG", quality=90)
        path = tmp.name
    try:
        if model_name in ("liqe", "topiq", "arniqa"):
            scorer.max_dimension = long_edge
            res = scorer.predict(path)
            if res.get("status") == "success":
                return float(res["score"])
            return None
        if model_name in ("spaq", "ava", "koniq"):
            runner = scorer
            pre = runner.preprocess_image(path, resolution_override=long_edge)
            if not pre:
                return None
            return runner.predict_quality(pre, model_name)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return None


def _get_iqa_scorer(model_name: str):
    if model_name == "liqe":
        from modules.liqe import LiqeScorer

        return LiqeScorer(device="cuda" if __import__("torch").cuda.is_available() else "cpu")
    if model_name == "topiq":
        from modules.topiq import TopiqScorer

        return TopiqScorer(device="cuda" if __import__("torch").cuda.is_available() else "cpu")
    if model_name == "arniqa":
        from modules.arniqa import ArniqaScorer

        return ArniqaScorer(device="cuda" if __import__("torch").cuda.is_available() else "cpu")
    if model_name in ("spaq", "ava", "koniq"):
        from scripts.python.run_all_musiq_models import MultiModelMUSIQ

        runner = MultiModelMUSIQ()
        runner.load_model(model_name)
        return runner
    raise ValueError(model_name)


def _long_edges_for_iqa_model(model_name: str, cli_edges: list[int]) -> list[int]:
    """Merge CLI long-edges with model-specific defaults when CLI uses 'all' grid."""
    model_edges = IQA_LONG_EDGES_BY_MODEL.get(model_name)
    if not model_edges:
        return cli_edges
    return sorted(set(cli_edges) | set(model_edges))


def run_iqa_sweep(
    models: list[str],
    long_edges: list[int],
    source: str,
    folders: list[int],
    subset: int = 0,
    force: bool = False,
) -> list[dict]:
    rows = _seeded_rows(folders)
    if subset > 0:
        rows = _subset_rows(rows, subset)
    stats = []
    for model_name in models:
        try:
            scorer = _get_iqa_scorer(model_name)
        except Exception as e:  # noqa: BLE001
            logger.warning("IQA scorer %s unavailable: %s", model_name, e)
            stats.append({"model": model_name, "error": str(e)})
            continue
        model_edges = _long_edges_for_iqa_model(model_name, long_edges)
        for long_edge in model_edges:
            path = common.npz_cache_path(model_name, source, long_edge, track="iqa")
            if path.exists() and not force:
                stats.append({"model": model_name, "long_edge": long_edge, "skipped": True})
                continue
            ids, scores = [], []
            for r in rows:
                read_path = common.resolve_read_path(r, source=source)
                if not read_path:
                    continue
                try:
                    pil = common.load_pil_resized(read_path, long_edge)
                    sc = _score_iqa_temp_path(pil, scorer, model_name, long_edge)
                    if sc is not None and np.isfinite(sc):
                        ids.append(r["id"])
                        scores.append(sc)
                except Exception as e:  # noqa: BLE001
                    logger.debug("iqa fail id=%s: %s", r["id"], e)
            if not ids:
                continue
            _save_npz(
                path,
                ids,
                np.asarray(scores, dtype=np.float32).reshape(-1, 1),
                {"model": model_name, "source": source, "long_edge": long_edge, "track": "iqa"},
            )
            stats.append({"model": model_name, "long_edge": long_edge, "n": len(ids), "path": str(path)})
    return stats


class _BlipCaptioner:
    """BLIP base captioning at resized PIL inputs (matches tagging CaptionGenerator)."""

    def __init__(self):
        self.model = None
        self.processor = None
        self.device = "cuda" if __import__("torch").cuda.is_available() else "cpu"

    def load(self) -> None:
        if self.model is not None:
            return
        from transformers import BlipForConditionalGeneration, BlipProcessor

        self.processor = BlipProcessor.from_pretrained(BLIP_MODEL)
        self.model = BlipForConditionalGeneration.from_pretrained(BLIP_MODEL).to(self.device).eval()

    def unload(self) -> None:
        import torch

        self.model = None
        self.processor = None
        if self.device == "cuda":
            torch.cuda.empty_cache()

    def caption_batch(self, pils: list, max_new_tokens: int = 30) -> list[str]:
        import torch

        self.load()
        inputs = self.processor(images=pils, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self.model.generate(**inputs, max_new_tokens=max_new_tokens)
        return self.processor.batch_decode(out, skip_special_tokens=True)


def run_caption_sweep(
    long_edges: list[int],
    sources: list[str],
    folders: list[int],
    chunk: int = 32,
    subset: int = 0,
    force: bool = False,
) -> list[dict]:
    rows = _seeded_rows(folders)
    if subset > 0:
        rows = _subset_rows(rows, subset)
    captioner = _BlipCaptioner()
    stats = []
    model_key = "blip"
    try:
        for source in sources:
            for long_edge in long_edges:
                path = common.npz_cache_path(model_key, source, long_edge, track="caption")
                if path.exists() and not force:
                    stats.append({"model": model_key, "source": source, "long_edge": long_edge, "skipped": True})
                    continue
                all_ids: list[int] = []
                all_caps: list[str] = []
                for i in range(0, len(rows), chunk):
                    batch = rows[i : i + chunk]
                    pils, ids = _load_batch_pils(batch, source, long_edge)
                    if not pils:
                        continue
                    try:
                        caps = captioner.caption_batch(pils)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("BLIP batch failed: %s", e)
                        continue
                    all_ids.extend(ids)
                    all_caps.extend(caps)
                    if (i // chunk) % 10 == 0:
                        logger.info("[blip/%s le=%d] progress %d/%d", source, long_edge, len(all_ids), len(rows))
                if not all_ids:
                    continue
                _save_caption_npz(
                    path,
                    all_ids,
                    all_caps,
                    {"model": model_key, "source": source, "long_edge": long_edge, "track": "caption", "n": len(all_ids)},
                )
                stats.append({"model": model_key, "source": source, "long_edge": long_edge, "n": len(all_ids), "path": str(path)})
    finally:
        captioner.unload()
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--track", choices=("embedding", "iqa", "caption", "native"), default="embedding")
    ap.add_argument("--models", default="all", help="comma list or 'all'")
    ap.add_argument("--long-edges", default=",".join(str(x) for x in common.DEFAULT_LONG_EDGES))
    ap.add_argument("--source", default="thumb,file", help="thumb, file, or thumb,file")
    ap.add_argument("--folders", default="62,44,45,676")
    ap.add_argument("--chunk", type=int, default=64)
    ap.add_argument("--subset", type=int, default=0, help="IQA: max images (0=all)")
    ap.add_argument("--preprocess-size", type=int, default=0, help="Phase 2: override ViT input (0=default)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.track == "native":
        from scripts.research.clip_culling.input_size_native import main as native_main

        native_main()
        return

    common.assert_e2e()
    common.wait_for_db()

    long_edges = [int(x) for x in args.long_edges.split(",") if x.strip()]
    folders = [int(x) for x in args.folders.split(",") if x.strip()]
    preprocess_size = args.preprocess_size or None

    if args.track == "embedding":
        if args.models == "all":
            models = list(EMBEDDING_MODELS.keys())
        else:
            models = [m.strip() for m in args.models.split(",") if m.strip()]
        sources = [s.strip() for s in args.source.split(",") if s.strip()]
        checkpoints.write_manifest()
        out = run_embedding_sweep(
            models, long_edges, sources, folders,
            chunk=args.chunk, preprocess_size=preprocess_size, force=args.force,
        )
    elif args.track == "caption":
        sources = [s.strip() for s in args.source.split(",") if s.strip()]
        if not long_edges:
            long_edges = list(common.CAPTION_LONG_EDGES)
        out = run_caption_sweep(
            long_edges, sources, folders, chunk=args.chunk, subset=args.subset, force=args.force,
        )
    else:
        if args.models == "all":
            models = list(IQA_MODELS)
        else:
            models = [m.strip() for m in args.models.split(",") if m.strip()]
        source = args.source.split(",")[0].strip() or "thumb"
        out = run_iqa_sweep(
            models, long_edges, source, folders, subset=args.subset, force=args.force,
        )

    common.write_input_size_json("embed_stats.json", out)
    logger.info("Done: %d stat rows", len(out))


if __name__ == "__main__":
    main()
