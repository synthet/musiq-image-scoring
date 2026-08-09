"""Shared student scorer service: one backbone load, one vector per image.

Shadow proxies in ``modules.engines.student_model`` read scalars from this
service. Production fusion is never modified here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

TEACHER_PROXY_KEYS = ("spaq", "ava", "liqe", "topiq", "arniqa")
COMPOSITE_KEYS = ("general", "technical", "aesthetic")
ALL_VECTOR_KEYS = TEACHER_PROXY_KEYS + COMPOSITE_KEYS + ("uncertainty",)


class StudentScorerError(RuntimeError):
    """Invalid or incompatible student checkpoint bundle."""


class StudentScorerService:
    """Process-wide lazy student scorer with path-level prediction cache."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bundle_dir: Path | None = None
        self._meta: dict[str, Any] | None = None
        self._model: Any | None = None
        self._device: str = "cpu"
        self._cache_key: str | None = None
        self._cache_vector: dict[str, float] | None = None
        self._predict_calls: int = 0

    @property
    def predict_calls(self) -> int:
        return self._predict_calls

    @property
    def loaded(self) -> bool:
        return self._model is not None or (
            self._meta is not None and self._meta.get("mock_vector") is not None
        )

    def reset(self) -> None:
        with self._lock:
            self._bundle_dir = None
            self._meta = None
            self._model = None
            self._cache_key = None
            self._cache_vector = None
            self._predict_calls = 0

    def load_bundle(self, bundle_dir: str | Path, *, device: str = "cpu") -> dict[str, Any]:
        """Load and validate a local bundle. Raises StudentScorerError on mismatch."""
        path = Path(bundle_dir)
        meta_path = path / "bundle.meta.json"
        if not meta_path.is_file():
            raise StudentScorerError(f"missing bundle.meta.json in {path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not meta.get("weights_sha256"):
            raise StudentScorerError("checkpoint metadata missing weights_sha256")
        if not meta.get("manifest_id") or not meta.get("protocol_id"):
            raise StudentScorerError("checkpoint metadata requires manifest_id and protocol_id")

        weights = path / "weights.pt"
        placeholder = path / "weights_placeholder.json"
        if weights.is_file():
            digest = _sha256_file(weights)
            if digest != meta["weights_sha256"]:
                raise StudentScorerError(
                    f"weights checksum mismatch: file={digest} meta={meta['weights_sha256']}"
                )
        elif placeholder.is_file():
            # Wiring / unit-test bundles without torch weights
            meta = dict(meta)
            meta.setdefault("mock_vector", {k: 0.5 for k in ALL_VECTOR_KEYS})
        else:
            raise StudentScorerError(f"no weights.pt in {path}")

        with self._lock:
            self._bundle_dir = path
            self._meta = meta
            self._device = device
            self._model = None
            self._cache_key = None
            self._cache_vector = None
            if weights.is_file():
                self._model = self._load_torch_model(weights, meta, device)
        return meta

    def _load_torch_model(self, weights: Path, meta: Mapping[str, Any], device: str) -> Any:
        import torch

        from scripts.research.student_scorer.models import StudentArchConfig, build_image_student

        arch = meta.get("architecture") or {}
        cfg = StudentArchConfig(
            backbone=str(arch.get("backbone", "convnext_tiny")),
            fine_tune="frozen",
            pretrained=False,
            input_size=int(arch.get("input_size", 512)),
        )
        model = build_image_student(cfg)
        blob = torch.load(weights, map_location=device, weights_only=False)
        state = blob["state_dict"] if isinstance(blob, dict) and "state_dict" in blob else blob
        model.load_state_dict(state, strict=False)
        model.to(device)
        model.eval()
        return model

    def _cache_token(self, image_path: str) -> str:
        p = Path(image_path)
        try:
            mtime = p.stat().st_mtime_ns
        except OSError:
            mtime = 0
        bundle = str(self._bundle_dir or "")
        fp = (self._meta or {}).get("preprocessing_fingerprint") or ""
        raw = f"{bundle}|{fp}|{image_path}|{mtime}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def predict_vector(self, image_path: str) -> dict[str, float]:
        """Return full multi-head vector; one backbone forward per cache miss."""
        with self._lock:
            if self._meta is None:
                raise StudentScorerError("student bundle not loaded")
            token = self._cache_token(image_path)
            if self._cache_key == token and self._cache_vector is not None:
                return dict(self._cache_vector)

            self._predict_calls += 1
            if self._meta.get("mock_vector") is not None and self._model is None:
                vector = {k: float(self._meta["mock_vector"].get(k, 0.5)) for k in ALL_VECTOR_KEYS}
            else:
                vector = self._infer(image_path)
            vector = self._ensure_composites(vector)

            self._cache_key = token
            self._cache_vector = dict(vector)
            return vector

    def _infer(self, image_path: str) -> dict[str, float]:
        import torch
        from PIL import Image
        from torchvision import transforms

        assert self._model is not None
        size = int((self._meta or {}).get("architecture", {}).get("input_size", 512))
        tfm = transforms.Compose(
            [
                transforms.Resize((size, size)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=(0.485, 0.456, 0.406),
                    std=(0.229, 0.224, 0.225),
                ),
            ]
        )
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            tensor = tfm(im).unsqueeze(0).to(self._device)
        with torch.no_grad():
            out = self._model(tensor)
        return {k: float(v.detach().reshape(-1)[0].cpu()) for k, v in out.items()}

    def _ensure_composites(self, vector: dict[str, float]) -> dict[str, float]:
        """Derive composites from proxy heads using bundle-frozen fusion when present."""
        from scripts.research.student_scorer.common import compute_composites_frozen

        meta = self._meta or {}
        fusion = meta.get("fusion")
        anchors = meta.get("percentile_anchors")
        if not fusion or not anchors:
            # Keep model heads if present; fill missing with 0.5
            out = {k: float(vector.get(k, 0.5)) for k in ALL_VECTOR_KEYS}
            return out
        teachers = {k: float(vector[k]) for k in TEACHER_PROXY_KEYS if k in vector}
        derived = compute_composites_frozen(teachers, fusion=fusion, anchors=anchors)
        out = dict(vector)
        for k, v in derived.items():
            out[k] = float(v)
        out.setdefault("uncertainty", float(vector.get("uncertainty", 0.0)))
        for k in ALL_VECTOR_KEYS:
            out.setdefault(k, 0.5)
        return out

    def head_score(self, image_path: str, head: str) -> float:
        if head not in ALL_VECTOR_KEYS and not head.endswith("_proxy"):
            # allow proxy naming: vexlum_student_v1_spaq_proxy → spaq
            pass
        key = head
        for t in TEACHER_PROXY_KEYS:
            if head.endswith(f"{t}_proxy") or head == t:
                key = t
                break
        for c in COMPOSITE_KEYS + ("uncertainty",):
            if head.endswith(c) or head == c:
                key = c
                break
        return float(self.predict_vector(image_path)[key])


_SERVICE: StudentScorerService | None = None
_SERVICE_LOCK = threading.Lock()


def get_student_service() -> StudentScorerService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = StudentScorerService()
        return _SERVICE


def reset_student_service() -> None:
    get_student_service().reset()


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


__all__ = [
    "ALL_VECTOR_KEYS",
    "COMPOSITE_KEYS",
    "StudentScorerError",
    "StudentScorerService",
    "TEACHER_PROXY_KEYS",
    "get_student_service",
    "reset_student_service",
]
