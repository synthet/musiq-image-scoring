#!/usr/bin/env python3
"""Compute spike embeddings for the seeded E2E images and persist them.

Streams images in chunks (decode -> embed -> upsert -> free) so an 8 GB GPU
never holds the whole corpus. Idempotent: images already embedded for a space
are skipped unless ``--force``.

    python -m scripts.research.clip_culling.embed_persist --tower dinov2,siglip2
    python -m scripts.research.clip_culling.embed_persist --tower all
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from scripts.research.clip_culling import common, checkpoints
from scripts.research.clip_culling.wrappers import HFImageTower, TimmImageTower, Tower
from modules import db, db_postgres

logger = logging.getLogger("clip_culling.embed")

# tower_key -> (space_code, kind, builder_args)
TOWERS: dict[str, tuple[str, str, dict[str, Any]]] = {
    "openai": (common.SPACE_OPENAI_L14, "open_clip", {
        "model_name": "ViT-L-14-quickgelu", "pretrained": "openai",
    }),
    "openclip": (common.SPACE_OPENCLIP_L14, "open_clip", {
        "model_name": "ViT-L-14", "pretrained": "laion2b_s32b_b82k",
    }),
    # HF dinov2_with_registers needs transformers>=4.40; timm DINOv2 base is 768-d equivalent.
    "dinov2": (common.SPACE_DINOV2, "timm", {
        "timm_name": "vit_base_patch14_dinov2.lvd142m",
    }),
    "siglip2": (common.SPACE_SIGLIP2, "hf", {
        "hf_model_id": "google/siglip2-base-patch16-224", "kind": "siglip2",
    }),
}

TOWER_KEYS_ALL = list(TOWERS.keys())


def _build_tower(kind: str, args: dict[str, Any]):
    if kind == "open_clip":
        return Tower(args["model_name"], args["pretrained"])
    if kind == "timm":
        return TimmImageTower(args["timm_name"])
    return HFImageTower(args["hf_model_id"], kind=args["kind"])


def _provenance_label(kind: str, args: dict[str, Any]) -> str:
    if kind == "open_clip":
        return f"{args['model_name']}/{args['pretrained']}"
    if kind == "timm":
        return f"timm/{args['timm_name']}"
    return args["hf_model_id"]


def _seeded_rows(folders: list[int]) -> list[dict]:
    fcsv = ",".join(str(f) for f in folders)
    rows = db_postgres.execute_select(
        f"SELECT id, file_path, thumbnail_path, thumbnail_path_win "
        f"FROM images WHERE folder_id IN ({fcsv}) ORDER BY id"
    )
    return [dict(r) for r in rows]


def _already_embedded(space_code: str) -> set[int]:
    from modules.embedding_spaces import get_embedding_space_id

    sid = get_embedding_space_id(space_code)
    if sid is None:
        return set()
    rows = db_postgres.execute_select(
        "SELECT image_id FROM image_embeddings_768 WHERE embedding_space_id=%s", (sid,)
    )
    return {r["image_id"] for r in rows}


def run(tower_key: str, folders: list[int], chunk: int = 64, force: bool = False) -> dict:
    common.assert_e2e()
    common.wait_for_db()
    common.register_l14_spaces()
    space_code, kind, builder_args = TOWERS[tower_key]
    rows = _seeded_rows(folders)
    done = set() if force else _already_embedded(space_code)
    todo = [r for r in rows if r["id"] not in done]
    logger.info("[%s] %d images total, %d already embedded, %d to do",
                space_code, len(rows), len(rows) - len(todo), len(todo))
    if not todo:
        return {"space": space_code, "embedded": 0, "skipped": len(rows)}

    tower = _build_tower(kind, builder_args)
    prov = _provenance_label(kind, builder_args)
    written = 0
    failed = 0
    for i in range(0, len(todo), chunk):
        batch = todo[i:i + chunk]
        pils, ids = [], []
        for r in batch:
            path = common.resolve_read_path(r)
            if not path:
                failed += 1
                continue
            try:
                pils.append(common.load_pil(path))
                ids.append(r["id"])
            except Exception as e:  # noqa: BLE001
                logger.warning("decode failed id=%s: %s", r["id"], e)
                failed += 1
        if not pils:
            continue
        emb = tower.embed(pils)
        persist = [(iid, emb[j], prov) for j, iid in enumerate(ids)]
        written += db.update_image_embeddings_batch_for_space(space_code, persist)
        logger.info("  %s: %d/%d embedded (%.0f ms/img, %.0f MB VRAM)",
                    space_code, written, len(todo),
                    tower.telemetry.ms_per_image, tower.telemetry.peak_vram_mb)
    tower.unload()
    stats = {
        "space": space_code,
        "embedded": written,
        "failed": failed,
        "telemetry": tower.telemetry.as_dict(),
    }
    logger.info("[%s] done: %s", space_code, stats)
    return stats


def _parse_tower_arg(raw: str) -> list[str]:
    if raw == "all":
        return TOWER_KEYS_ALL
    return [k.strip() for k in raw.split(",") if k.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tower",
        default="dinov2,siglip2",
        help="comma list or 'all': openai,openclip,dinov2,siglip2",
    )
    ap.add_argument("--folders", default="62,44,45,676")
    ap.add_argument("--chunk", type=int, default=64)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    folders = [int(x) for x in args.folders.split(",") if x.strip()]

    checkpoints.write_manifest()
    keys = _parse_tower_arg(args.tower)
    unknown = [k for k in keys if k not in TOWERS]
    if unknown:
        raise SystemExit(f"Unknown tower keys: {unknown}; valid: {TOWER_KEYS_ALL}")
    out = []
    for k in keys:
        out.append(run(k, folders, chunk=args.chunk, force=args.force))
    common.write_json("embed_persist_stats.json", out)


if __name__ == "__main__":
    main()
