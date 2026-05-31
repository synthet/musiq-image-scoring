"""Production embedding extractors for the optional culling towers.

Generates 768-d image embeddings for the towers evaluated in the 2026-05-29
culling spike (OpenCLIP L/14, OpenAI CLIP L/14, DINOv2-reg base, SigLIP2 base)
and persists them into the pgvector fact tables via
``db.update_image_embeddings_batch_for_space``.

Design:

* **Opt-in.** Nothing runs unless a space code is requested (typically from
  ``embeddings.culling_spaces`` in config, or the backfill script). Importing
  this module never loads ML deps.
* **Lazy ML imports.** ``torch`` / ``open_clip`` / ``timm`` / ``transformers``
  are imported inside loaders so the module is import-safe without a GPU/ML env.
* **Selectable per level.** Once vectors exist, point any
  ``culling.two_level.level*.embedding_space`` at the space code; the two-level
  pipeline reads them through ``db.get_image_embeddings_batch_for_space``.

Verdicts / thresholds for each tower:
``docs/reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from modules.embedding_spaces import (
    CULLING_TOWER_IMAGE_DIM,
    DINOV2_REG_BASE_IMAGE_SPACE_CODE,
    OPENAI_CLIP_L14_IMAGE_SPACE_CODE,
    OPENCLIP_L14_IMAGE_SPACE_CODE,
    SIGLIP2_BASE_IMAGE_SPACE_CODE,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CullingSpaceSpec:
    """Loader recipe for one optional culling embedding space."""

    code: str
    loader: str  # "open_clip" | "timm" | "hf_siglip2" | "hf_dinov2"
    model_name: str
    pretrained: str | None = None
    dim: int = CULLING_TOWER_IMAGE_DIM


# Registry: space code -> loader recipe. Codes must match
# modules/embedding_spaces.SPACE_DIMS and migration 0029.
SUPPORTED_CULLING_SPACES: dict[str, CullingSpaceSpec] = {
    OPENCLIP_L14_IMAGE_SPACE_CODE: CullingSpaceSpec(
        OPENCLIP_L14_IMAGE_SPACE_CODE, "open_clip", "ViT-L-14", "laion2b_s32b_b82k"
    ),
    OPENAI_CLIP_L14_IMAGE_SPACE_CODE: CullingSpaceSpec(
        OPENAI_CLIP_L14_IMAGE_SPACE_CODE, "open_clip", "ViT-L-14-quickgelu", "openai"
    ),
    DINOV2_REG_BASE_IMAGE_SPACE_CODE: CullingSpaceSpec(
        DINOV2_REG_BASE_IMAGE_SPACE_CODE, "timm", "vit_base_patch14_dinov2.lvd142m"
    ),
    SIGLIP2_BASE_IMAGE_SPACE_CODE: CullingSpaceSpec(
        SIGLIP2_BASE_IMAGE_SPACE_CODE, "hf_siglip2", "google/siglip2-base-patch16-224"
    ),
}


def is_supported(space_code: str) -> bool:
    return space_code in SUPPORTED_CULLING_SPACES


def get_spec(space_code: str) -> CullingSpaceSpec:
    try:
        return SUPPORTED_CULLING_SPACES[space_code]
    except KeyError as exc:
        raise ValueError(
            f"Unknown culling embedding space {space_code!r}; supported: "
            f"{sorted(SUPPORTED_CULLING_SPACES)}"
        ) from exc


def _l2_normalize(arr):
    import numpy as np

    arr = np.asarray(arr, dtype=np.float32)
    n = np.linalg.norm(arr, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return arr / n


class CullingEmbedder:
    """Lazily-loaded image embedder for one culling space (fp16 on CUDA).

    Construct with a space code, call :meth:`embed` (PIL images) or
    :meth:`embed_paths`. Call :meth:`unload` to free VRAM between spaces.
    """

    def __init__(self, space_code: str, device: str | None = None, fp16: bool = True):
        self.spec = get_spec(space_code)
        self.code = self.spec.code
        self._device = device
        self._fp16 = fp16
        self._model = None
        self._preprocess = None  # open_clip / timm transform
        self._processor = None  # HF processor

    # -- device -----------------------------------------------------------
    @property
    def device(self) -> str:
        if self._device is None:
            import torch

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        return self._device

    @property
    def fp16(self) -> bool:
        return self._fp16 and self.device == "cuda"

    # -- load / unload ----------------------------------------------------
    def load(self) -> None:
        if self._model is not None:
            return
        if self.spec.loader == "open_clip":
            self._load_open_clip()
        elif self.spec.loader == "timm":
            self._load_timm()
        elif self.spec.loader in ("hf_siglip2", "hf_dinov2"):
            self._load_hf()
        else:  # pragma: no cover - guarded by get_spec
            raise ValueError(f"Unknown loader {self.spec.loader!r}")
        logger.info(
            "CullingEmbedder loaded space=%s loader=%s model=%s device=%s fp16=%s",
            self.code,
            self.spec.loader,
            self.spec.model_name,
            self.device,
            self.fp16,
        )

    def _load_open_clip(self) -> None:
        import open_clip

        model, _, preprocess = open_clip.create_model_and_transforms(
            self.spec.model_name, pretrained=self.spec.pretrained
        )
        model = model.to(self.device).eval()
        if self.fp16:
            model = model.half()
        self._model = model
        self._preprocess = preprocess

    def _load_timm(self) -> None:
        import timm

        model = timm.create_model(self.spec.model_name, pretrained=True, num_classes=0)
        model = model.to(self.device).eval()
        if self.fp16:
            model = model.half()
        cfg = timm.data.resolve_model_data_config(model)
        self._model = model
        self._preprocess = timm.data.create_transform(**cfg, is_training=False)

    def _load_hf(self) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModel, AutoProcessor

        if self.spec.loader == "hf_siglip2":
            self._processor = AutoProcessor.from_pretrained(self.spec.model_name)
        else:
            self._processor = AutoImageProcessor.from_pretrained(self.spec.model_name)
        dtype = torch.float16 if self.fp16 else torch.float32
        model = AutoModel.from_pretrained(self.spec.model_name, torch_dtype=dtype)
        self._model = model.to(self.device).eval()

    def unload(self) -> None:
        self._model = None
        self._preprocess = None
        self._processor = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — best-effort
            pass

    # -- embed ------------------------------------------------------------
    def embed(self, pil_images: Sequence, batch_size: int = 32):
        """Return an ``(N, dim)`` L2-normalized float32 array for PIL images."""
        import numpy as np

        self.load()
        if not pil_images:
            return np.zeros((0, self.spec.dim), np.float32)
        if self.spec.loader == "open_clip":
            out = self._embed_open_clip(pil_images, batch_size)
        elif self.spec.loader == "timm":
            out = self._embed_timm(pil_images, batch_size)
        else:
            out = self._embed_hf(pil_images, batch_size)
        if out.shape[1] != self.spec.dim:
            raise ValueError(
                f"Embedder for {self.code!r} produced dim {out.shape[1]}, "
                f"expected {self.spec.dim}"
            )
        return _l2_normalize(out)

    def _embed_open_clip(self, pils, batch_size):
        import numpy as np
        import torch

        out = []
        for i in range(0, len(pils), batch_size):
            chunk = pils[i : i + batch_size]
            tensors = torch.stack([self._preprocess(im) for im in chunk]).to(self.device)
            if self.fp16:
                tensors = tensors.half()
            with torch.no_grad():
                feats = self._model.encode_image(tensors)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            out.append(feats.float().cpu().numpy())
        return np.concatenate(out, axis=0)

    def _embed_timm(self, pils, batch_size):
        import numpy as np
        import torch

        out = []
        for i in range(0, len(pils), batch_size):
            chunk = pils[i : i + batch_size]
            tensors = torch.stack([self._preprocess(im) for im in chunk]).to(self.device)
            if self.fp16:
                tensors = tensors.half()
            with torch.no_grad():
                feats = self._model(tensors)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            out.append(feats.float().cpu().numpy())
        return np.concatenate(out, axis=0)

    def _embed_hf(self, pils, batch_size):
        import numpy as np
        import torch

        out = []
        for i in range(0, len(pils), batch_size):
            chunk = pils[i : i + batch_size]
            batch = self._processor(images=list(chunk), return_tensors="pt")
            pixel_values = batch["pixel_values"].to(self.device)
            if self.fp16:
                pixel_values = pixel_values.half()
            with torch.no_grad():
                if self.spec.loader == "hf_siglip2":
                    feats = self._model.get_image_features(pixel_values=pixel_values)
                else:
                    res = self._model(pixel_values=pixel_values)
                    if getattr(res, "pooler_output", None) is not None:
                        feats = res.pooler_output
                    else:
                        feats = res.last_hidden_state[:, 0]
                feats = feats / feats.norm(dim=-1, keepdim=True)
            out.append(feats.float().cpu().numpy())
        return np.concatenate(out, axis=0)

    def embed_paths(
        self,
        paths: Sequence[str],
        batch_size: int = 32,
        load_workers: int = 8,
        max_load_px: int = 1024,
    ):
        """Load images from ``paths`` and embed. Returns ``(vectors, ok_paths)``.

        Uses :func:`modules.thumbnails.open_image_for_ml` so RAW files (NEF/CR2/…)
        are decoded via the same embedded-JPEG → rawpy → ImageMagick chain as the
        rest of the pipeline. Image loading (the bottleneck for RAW) is parallelized
        across ``load_workers`` threads — decode/subprocess work releases the GIL.
        Paths that fail to open are skipped (logged at WARNING); the returned
        vectors align row-for-row with ``ok_paths``.

        Decoded images are downscaled so the longest side is ``max_load_px`` before
        being held in memory. For NEF the "thumbnail" is often a full-resolution
        embedded preview (~70 MB decoded); a chunk of 128 such images would exhaust
        host RAM (OOM). All current culling towers preprocess to ≤ 518 px, so a
        1024-px cap is loss-free for inference while cutting per-image memory ~30×.
        """
        from concurrent.futures import ThreadPoolExecutor

        from modules.thumbnails import open_image_for_ml

        cap = max(0, int(max_load_px))

        def _load(p):
            try:
                im = open_image_for_ml(p).convert("RGB")
                if cap and (im.width > cap or im.height > cap):
                    im.thumbnail((cap, cap))  # in-place, preserves aspect, shrink-only
                return p, im
            except Exception as exc:  # noqa: BLE001 — skip unreadable file
                logger.warning("embed_paths: cannot open %s: %s", p, exc)
                return p, None

        pils: List = []
        ok_paths: List[str] = []
        workers = max(1, int(load_workers))
        if workers == 1:
            loaded = [_load(p) for p in paths]
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                loaded = list(ex.map(_load, paths))  # preserves input order
        for p, im in loaded:
            if im is not None:
                pils.append(im)
                ok_paths.append(p)
        vectors = self.embed(pils, batch_size=batch_size)
        return vectors, ok_paths


def generate_and_persist(
    space_code: str,
    rows: Iterable[Tuple[int, str]],
    *,
    batch_size: int = 32,
    model_version: str | None = None,
    embedder: CullingEmbedder | None = None,
) -> int:
    """Embed ``(image_id, file_path)`` rows and upsert into the fact table.

    Returns the number of embeddings persisted. Postgres-only (the underlying
    ``db.update_image_embeddings_batch_for_space`` is a no-op otherwise). The
    embedder is created on demand unless one is supplied (reuse across batches).
    """
    from modules import db

    rows = list(rows)
    if not rows:
        return 0

    own_embedder = embedder is None
    emb = embedder or CullingEmbedder(space_code)
    version = model_version or f"{emb.spec.loader}:{emb.spec.model_name}"

    import time

    total = len(rows)
    persisted = 0
    processed = 0
    t0 = time.time()
    last_log = t0
    # Load more images per step than one GPU batch so the loader thread pool stays
    # ahead of the GPU; embed() re-batches by ``batch_size`` for inference.
    load_chunk = max(batch_size * 4, 128)
    try:
        for start in range(0, total, load_chunk):
            chunk = rows[start : start + load_chunk]
            paths = [p for _id, p in chunk]
            id_by_path: dict[str, int] = {}
            for _id, p in chunk:
                id_by_path.setdefault(p, int(_id))
            vectors, ok_paths = emb.embed_paths(paths, batch_size=batch_size)
            persist_rows = [
                (id_by_path[p], vectors[i], version) for i, p in enumerate(ok_paths)
            ]
            persisted += db.update_image_embeddings_batch_for_space(
                space_code, persist_rows
            )
            processed += len(chunk)
            now = time.time()
            if now - last_log >= 30 or processed >= total:
                rate = processed / max(now - t0, 1e-6)
                eta = (total - processed) / max(rate, 1e-6)
                logger.info(
                    "[%s] %d/%d (%.1f%%) persisted=%d %.1f img/s ETA %.0f min",
                    space_code, processed, total, 100 * processed / max(total, 1),
                    persisted, rate, eta / 60,
                )
                last_log = now
    finally:
        if own_embedder:
            emb.unload()
    return persisted
