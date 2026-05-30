#!/usr/bin/env python3
"""Download + cache scoring heads and record tower provenance.

Towers (OpenAI CLIP ViT-L/14, OpenCLIP laion2b ViT-L/14) are fetched lazily by
``open_clip.create_model_and_transforms`` into the HF cache; this module records
their source URLs and downloads the LAION aesthetic MLP head, recording size +
sha256 into a manifest for offline reuse.

Sources (see REFERENCES.md):
- OpenAI CLIP ViT-L/14:    https://huggingface.co/openai/clip-vit-large-patch14
- OpenCLIP laion2b L/14:   https://huggingface.co/laion/CLIP-ViT-L-14-laion2B-s32B-b82K
- LAION aesthetic head:    https://github.com/christophschuhmann/improved-aesthetic-predictor
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request

from scripts.research.clip_culling import common

logger = logging.getLogger("clip_culling.checkpoints")

AESTHETIC_URL = (
    "https://github.com/christophschuhmann/improved-aesthetic-predictor/"
    "raw/main/sac+logos+ava1-l14-linearMSE.pth"
)
AESTHETIC_FILE = common.CACHE_DIR / "sac+logos+ava1-l14-linearMSE.pth"

TOWER_PROVENANCE = {
    "openai_clip_vit_l14_image": {
        "open_clip": ("ViT-L-14-quickgelu", "openai"),
        "url": "https://huggingface.co/openai/clip-vit-large-patch14",
        "dim": 768,
    },
    "openclip_l14_laion2b_image": {
        "open_clip": ("ViT-L-14", "laion2b_s32b_b82k"),
        "url": "https://huggingface.co/laion/CLIP-ViT-L-14-laion2B-s32B-b82K",
        "dim": 768,
    },
    "dinov2_reg_base_image": {
        "timm": "vit_base_patch14_dinov2.lvd142m",
        "url": "https://huggingface.co/facebook/dinov2-with-registers-base",
        "note": "Spike uses timm DINOv2 base 768-d (transformers 4.37 lacks dinov2_with_registers)",
        "dim": 768,
    },
    "siglip2_base_image": {
        "hf": "google/siglip2-base-patch16-224",
        "url": "https://huggingface.co/google/siglip2-base-patch16-224",
        "dim": 768,
    },
}


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_aesthetic_head() -> str:
    common.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not AESTHETIC_FILE.exists():
        logger.info("Downloading LAION aesthetic head -> %s", AESTHETIC_FILE)
        urllib.request.urlretrieve(AESTHETIC_URL, AESTHETIC_FILE)
    size = AESTHETIC_FILE.stat().st_size
    digest = _sha256(AESTHETIC_FILE)
    logger.info("Aesthetic head: %d bytes sha256=%s", size, digest[:16])
    return str(AESTHETIC_FILE)


def write_manifest() -> dict:
    head = ensure_aesthetic_head()
    manifest = {
        "towers": TOWER_PROVENANCE,
        "aesthetic_head": {
            "url": AESTHETIC_URL,
            "path": head,
            "size": AESTHETIC_FILE.stat().st_size,
            "sha256": _sha256(AESTHETIC_FILE),
        },
    }
    common.write_json("checkpoints_manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    write_manifest()
