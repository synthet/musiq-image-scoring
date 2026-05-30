#!/usr/bin/env python3
"""Uniform inference wrappers for CLIP/HF towers + scoring heads (8 GB VRAM).

- ``Tower``: open_clip ``embed`` / ``encode_text``.
- ``HFImageTower``: transformers DINOv2-reg / SigLIP2 (768-d).
- ``AestheticHead``: LAION MLP on OpenAI CLIP L/14 768-d embeddings.
- ``PromptMargin``: zero-weight prompt-margin (CLIP-IQA style).

Sequential load + fp16 on CUDA; frees VRAM between towers. Records VRAM + ms/img.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("clip_culling.wrappers")


def l2_normalize(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    n = np.linalg.norm(arr, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return arr / n


@dataclass
class Telemetry:
    images: int = 0
    seconds: float = 0.0
    peak_vram_mb: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def ms_per_image(self) -> float:
        return 1000.0 * self.seconds / self.images if self.images else 0.0

    def as_dict(self) -> dict:
        return {
            "images": self.images,
            "seconds": round(self.seconds, 2),
            "ms_per_image": round(self.ms_per_image, 1),
            "peak_vram_mb": round(self.peak_vram_mb, 1),
            **self.extra,
        }


class Tower:
    """open_clip tower with a uniform embed/encode_text surface."""

    def __init__(
        self,
        model_name: str,
        pretrained: str,
        device: str | None = None,
        fp16: bool = True,
        *,
        preprocess_size: int | None = None,
    ):
        import torch

        self.model_name = model_name
        self.pretrained = pretrained
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fp16 = fp16 and self.device == "cuda"
        self.preprocess_size = preprocess_size
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.telemetry = Telemetry(
            extra={"preprocess_size": preprocess_size} if preprocess_size else {}
        )

    def load(self):
        if self.model is not None:
            return
        import open_clip
        import torch

        logger.info("Loading tower %s/%s on %s (fp16=%s, preprocess_size=%s)",
                    self.model_name, self.pretrained, self.device, self.fp16,
                    self.preprocess_size)
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        if self.preprocess_size:
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                image_size=self.preprocess_size,
            )
        else:
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                self.model_name, pretrained=self.pretrained
            )
        self.model = self.model.to(self.device).eval()
        if self.fp16:
            self.model = self.model.half()
        self.tokenizer = open_clip.get_tokenizer(self.model_name)

    def unload(self):
        import torch

        self.model = None
        self.preprocess = None
        self.tokenizer = None
        if self.device == "cuda":
            torch.cuda.empty_cache()

    def embed(self, pils, batch_size: int = 32) -> np.ndarray:
        import torch

        self.load()
        out = []
        t0 = time.time()
        for i in range(0, len(pils), batch_size):
            chunk = pils[i:i + batch_size]
            tensors = torch.stack([self.preprocess(im) for im in chunk]).to(self.device)
            if self.fp16:
                tensors = tensors.half()
            with torch.no_grad():
                feats = self.model.encode_image(tensors)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            out.append(feats.float().cpu().numpy())
        emb = np.concatenate(out, axis=0) if out else np.zeros((0, 768), np.float32)
        self.telemetry.images += len(pils)
        self.telemetry.seconds += time.time() - t0
        if self.device == "cuda":
            self.telemetry.peak_vram_mb = max(
                self.telemetry.peak_vram_mb,
                torch.cuda.max_memory_allocated() / (1024 * 1024),
            )
        return l2_normalize(emb)

    @property
    def logit_scale(self) -> float:
        """CLIP temperature (exp of learned logit_scale); ~100 for CLIP."""
        self.load()
        try:
            return float(self.model.logit_scale.exp().detach().cpu())
        except Exception:  # noqa: BLE001
            return 100.0

    def predict_keywords(self, emb: np.ndarray, taxonomy: list[str],
                         prompt_tmpl: str = "a photo of {k}",
                         threshold: float = 0.2, top_k: int = 5) -> list[list[str]]:
        """Zero-shot keywords per image via softmax over a closed taxonomy.

        Mirrors ``KeywordScorer.predict`` (CLIP B/32 baseline) so towers compare
        head-to-head: same prompt template, threshold, and top_k.
        """
        emb = l2_normalize(emb)
        text = self.encode_text([prompt_tmpl.format(k=k) for k in taxonomy])
        logits = (emb @ text.T) * self.logit_scale  # (N, T)
        logits -= logits.max(axis=1, keepdims=True)
        e = np.exp(logits)
        probs = e / e.sum(axis=1, keepdims=True)
        out = []
        for row in probs:
            ranked = sorted(
                ((taxonomy[i], float(p)) for i, p in enumerate(row) if p >= threshold),
                key=lambda kv: kv[1], reverse=True,
            )
            out.append([k for k, _ in ranked[:top_k]])
        return out

    def encode_text(self, prompts) -> np.ndarray:
        import torch

        self.load()
        tokens = self.tokenizer(list(prompts)).to(self.device)
        with torch.no_grad():
            feats = self.model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return l2_normalize(feats.float().cpu().numpy())


class TimmImageTower:
    """timm vision backbone (DINOv2 base 768-d when HF with-registers unavailable)."""

    def __init__(
        self,
        timm_name: str,
        device: str | None = None,
        fp16: bool = True,
        *,
        preprocess_size: int | None = None,
    ):
        import torch

        self.timm_name = timm_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fp16 = fp16 and self.device == "cuda"
        self.preprocess_size = preprocess_size
        self.model = None
        self.preprocess = None
        extra = {"timm_name": timm_name}
        if preprocess_size:
            extra["preprocess_size"] = preprocess_size
        self.telemetry = Telemetry(extra=extra)

    def load(self):
        if self.model is not None:
            return
        import timm
        import torch

        logger.info("Loading timm %s on %s (fp16=%s, preprocess_size=%s)",
                    self.timm_name, self.device, self.fp16, self.preprocess_size)
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        self.model = timm.create_model(self.timm_name, pretrained=True, num_classes=0)
        self.model = self.model.to(self.device).eval()
        if self.fp16:
            self.model = self.model.half()
        cfg = timm.data.resolve_model_data_config(self.model)
        if self.preprocess_size:
            cfg = dict(cfg)
            cfg["input_size"] = (self.preprocess_size, self.preprocess_size)
        self.preprocess = timm.data.create_transform(**cfg, is_training=False)

    def unload(self):
        import torch

        self.model = None
        self.preprocess = None
        if self.device == "cuda":
            torch.cuda.empty_cache()

    def embed(self, pils, batch_size: int = 32) -> np.ndarray:
        import torch

        self.load()
        out = []
        t0 = time.time()
        for i in range(0, len(pils), batch_size):
            chunk = pils[i:i + batch_size]
            tensors = torch.stack([self.preprocess(im) for im in chunk]).to(self.device)
            if self.fp16:
                tensors = tensors.half()
            with torch.no_grad():
                feats = self.model(tensors)
                feats = feats / feats.norm(dim=-1, keepdim=True)
            out.append(feats.float().cpu().numpy())
        emb = np.concatenate(out, axis=0) if out else np.zeros((0, 768), np.float32)
        self.telemetry.images += len(pils)
        self.telemetry.seconds += time.time() - t0
        if self.device == "cuda":
            self.telemetry.peak_vram_mb = max(
                self.telemetry.peak_vram_mb,
                torch.cuda.max_memory_allocated() / (1024 * 1024),
            )
        return l2_normalize(emb)

    def encode_text(self, prompts) -> np.ndarray:
        raise NotImplementedError("timm tower has no text encoder")


class HFImageTower:
    """Hugging Face vision tower (DINOv2-reg or SigLIP2) with uniform embed surface."""

    def __init__(
        self,
        hf_model_id: str,
        *,
        kind: str,
        device: str | None = None,
        fp16: bool = True,
    ):
        import torch

        self.hf_model_id = hf_model_id
        self.kind = kind  # "dinov2" | "siglip2"
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fp16 = fp16 and self.device == "cuda"
        self.model = None
        self.processor = None
        self.telemetry = Telemetry(extra={"kind": kind, "hf_model_id": hf_model_id})

    def load(self):
        if self.model is not None:
            return
        import torch
        from transformers import AutoImageProcessor, AutoModel, AutoProcessor

        logger.info("Loading HF tower %s (%s) on %s (fp16=%s)",
                    self.hf_model_id, self.kind, self.device, self.fp16)
        if self.device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        if self.kind == "siglip2":
            self.processor = AutoProcessor.from_pretrained(self.hf_model_id)
        else:
            self.processor = AutoImageProcessor.from_pretrained(self.hf_model_id)
        dtype = torch.float16 if self.fp16 else torch.float32
        self.model = AutoModel.from_pretrained(self.hf_model_id, torch_dtype=dtype)
        self.model = self.model.to(self.device).eval()

    def unload(self):
        import torch

        self.model = None
        self.processor = None
        if self.device == "cuda":
            torch.cuda.empty_cache()

    def _pil_batch(self, pils):
        if self.kind == "siglip2":
            return self.processor(images=list(pils), return_tensors="pt")
        return self.processor(images=list(pils), return_tensors="pt")

    def _image_features(self, pixel_values) -> np.ndarray:
        import torch

        pixel_values = pixel_values.to(self.device)
        if self.fp16:
            pixel_values = pixel_values.half()
        with torch.no_grad():
            if self.kind == "siglip2":
                feats = self.model.get_image_features(pixel_values=pixel_values)
            else:
                out = self.model(pixel_values=pixel_values)
                if hasattr(out, "pooler_output") and out.pooler_output is not None:
                    feats = out.pooler_output
                else:
                    feats = out.last_hidden_state[:, 0]
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.float().cpu().numpy()

    def embed(self, pils, batch_size: int = 32) -> np.ndarray:
        import torch

        self.load()
        out = []
        t0 = time.time()
        for i in range(0, len(pils), batch_size):
            chunk = pils[i:i + batch_size]
            batch = self._pil_batch(chunk)
            out.append(self._image_features(batch["pixel_values"]))
        emb = np.concatenate(out, axis=0) if out else np.zeros((0, 768), np.float32)
        self.telemetry.images += len(pils)
        self.telemetry.seconds += time.time() - t0
        if self.device == "cuda":
            self.telemetry.peak_vram_mb = max(
                self.telemetry.peak_vram_mb,
                torch.cuda.max_memory_allocated() / (1024 * 1024),
            )
        return l2_normalize(emb)

    def encode_text(self, prompts) -> np.ndarray:
        if self.kind != "siglip2":
            raise NotImplementedError(f"{self.kind} has no text encoder")
        import torch

        self.load()
        inputs = self.processor(text=list(prompts), padding=True, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items() if k != "pixel_values"}
        with torch.no_grad():
            feats = self.model.get_text_features(**inputs)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return l2_normalize(feats.float().cpu().numpy())

    @property
    def logit_scale(self) -> float:
        self.load()
        try:
            import torch
            if hasattr(self.model, "logit_scale"):
                return float(self.model.logit_scale.exp().detach().cpu())
            if hasattr(self.model, "logit_bias"):
                return 10.0
        except Exception:  # noqa: BLE001
            pass
        return 10.0

    def predict_keywords_sigmoid(
        self,
        emb: np.ndarray,
        taxonomy: list[str],
        prompt_tmpl: str = "a photo of {k}",
        threshold: float = 0.2,
        top_k: int = 5,
    ) -> list[list[str]]:
        """SigLIP2-style per-tag sigmoid (independent tags, not softmax)."""
        emb = l2_normalize(emb)
        text = self.encode_text([prompt_tmpl.format(k=k) for k in taxonomy])
        logits = (emb @ text.T) * self.logit_scale
        probs = 1.0 / (1.0 + np.exp(-logits))
        out = []
        for row in probs:
            ranked = sorted(
                ((taxonomy[i], float(p)) for i, p in enumerate(row) if p >= threshold),
                key=lambda kv: kv[1], reverse=True,
            )
            out.append([k for k, _ in ranked[:top_k]])
        return out


class AestheticHead:
    """LAION improved-aesthetic-predictor MLP on 768-d OpenAI CLIP L/14 embeddings."""

    def __init__(self, weights_path: str, device: str | None = None):
        import torch

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.weights_path = weights_path
        self.model = None

    def _build(self):
        import torch.nn as nn

        class MLP(nn.Module):
            def __init__(self, input_size=768):
                super().__init__()
                self.layers = nn.Sequential(
                    nn.Linear(input_size, 1024),
                    nn.Dropout(0.2),
                    nn.Linear(1024, 128),
                    nn.Dropout(0.2),
                    nn.Linear(128, 64),
                    nn.Dropout(0.1),
                    nn.Linear(64, 16),
                    nn.Linear(16, 1),
                )

            def forward(self, x):
                return self.layers(x)

        return MLP()

    def load(self):
        if self.model is not None:
            return
        import torch

        self.model = self._build()
        state = torch.load(self.weights_path, map_location="cpu")
        self.model.load_state_dict(state)
        self.model = self.model.to(self.device).eval()

    def score(self, emb: np.ndarray) -> np.ndarray:
        """Score L2-normalized 768-d embeddings -> aesthetic value (~1..10)."""
        import torch

        self.load()
        x = torch.from_numpy(l2_normalize(emb)).float().to(self.device)
        with torch.no_grad():
            y = self.model(x).squeeze(-1)
        return y.float().cpu().numpy()


class PromptMargin:
    """Zero-weight prompt-margin (CLIP-IQA style) over L2-normalized cosine."""

    def __init__(self, tower: Tower):
        self.tower = tower
        self._text_cache: dict[tuple, np.ndarray] = {}

    def _text(self, prompts: tuple) -> np.ndarray:
        if prompts not in self._text_cache:
            self._text_cache[prompts] = self.tower.encode_text(list(prompts))
        return self._text_cache[prompts]

    def score(self, emb: np.ndarray, pos: list[str], neg: list[str], w: float = 1.0) -> np.ndarray:
        """margin = mean cos(img, pos) - w * mean cos(img, neg). Higher = more 'pos'."""
        emb = l2_normalize(emb)
        pos_t = self._text(tuple(pos))
        neg_t = self._text(tuple(neg))
        pos_cos = emb @ pos_t.T  # (N, P)
        neg_cos = emb @ neg_t.T  # (N, M)
        return pos_cos.mean(axis=1) - w * neg_cos.mean(axis=1)

    def softmax_pair(self, emb: np.ndarray, pos: list[str], neg: list[str],
                     temp: float = 100.0) -> np.ndarray:
        """CLIP-IQA closed-set prob of 'pos' vs 'neg' (antonym softmax)."""
        emb = l2_normalize(emb)
        pos_cos = (emb @ self._text(tuple(pos)).T).mean(axis=1)
        neg_cos = (emb @ self._text(tuple(neg)).T).mean(axis=1)
        logits = np.stack([pos_cos, neg_cos], axis=1) * temp
        logits -= logits.max(axis=1, keepdims=True)
        e = np.exp(logits)
        return e[:, 0] / e.sum(axis=1)
