"""Shadow IScoringModel proxies over the shared StudentScorerService.

Each wrapper returns one scalar. All wrappers share one backbone forward per
image via ``modules.student_scoring.get_student_service``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from modules.engines.base import IScoringModel
from modules.student_scoring import get_student_service

logger = logging.getLogger(__name__)

STUDENT_NAMESPACE = "vexlum_student_v1"
TEACHER_NAMES = frozenset({"spaq", "ava", "liqe", "topiq", "arniqa"})

# (registry_name, vector_key)
PROXY_SPECS: tuple[tuple[str, str], ...] = (
    (f"{STUDENT_NAMESPACE}_spaq_proxy", "spaq"),
    (f"{STUDENT_NAMESPACE}_ava_proxy", "ava"),
    (f"{STUDENT_NAMESPACE}_liqe_proxy", "liqe"),
    (f"{STUDENT_NAMESPACE}_topiq_proxy", "topiq"),
    (f"{STUDENT_NAMESPACE}_arniqa_proxy", "arniqa"),
    (f"{STUDENT_NAMESPACE}_general", "general"),
    (f"{STUDENT_NAMESPACE}_technical", "technical"),
    (f"{STUDENT_NAMESPACE}_aesthetic", "aesthetic"),
    (f"{STUDENT_NAMESPACE}_uncertainty", "uncertainty"),
)


class StudentProxyWrapper(IScoringModel):
    """One scalar head from the shared student vector."""

    framework = "torch"
    score_range = (0.0, 1.0)

    def __init__(self, name: str, vector_key: str) -> None:
        if name in TEACHER_NAMES:
            raise ValueError(f"student proxy must not reuse teacher name {name!r}")
        self.name = name
        self.vector_key = vector_key
        self.version = "unloaded"
        self._loaded = False

    def load(self) -> bool:
        service = get_student_service()
        bundle = os.environ.get("VEXLUM_STUDENT_BUNDLE") or _bundle_from_config()
        if not bundle:
            self.load_status = "failed"
            self._loaded = False
            return False
        try:
            meta = service.load_bundle(bundle)
        except Exception as exc:
            logger.error("Student bundle load failed for %s: %s", self.name, exc)
            self.load_status = "failed"
            self._loaded = False
            return False
        # Compact version within 64 chars: bundle + manifest short ids
        bid = str(meta.get("bundle_id", "bundle"))[-20:]
        mid = str(meta.get("manifest_id", "msm"))[-20:]
        self.version = f"{bid}/{mid}"[:64]
        self._loaded = True
        self.load_status = "loaded"
        return True

    def predict(self, image_path: str) -> dict[str, Any]:
        if not self._loaded:
            return {"score": None, "status": "not_loaded", "error": "Model not loaded"}
        try:
            score = get_student_service().head_score(image_path, self.vector_key)
            score = max(0.0, min(1.0, float(score)))
            return {"score": score, "status": "success", "error": None}
        except Exception as exc:
            logger.error("Student proxy %s failed: %s", self.name, exc)
            return {"score": None, "status": "failed", "error": str(exc)}


def _bundle_from_config() -> str | None:
    try:
        from modules.config import get_config_value

        cfg = get_config_value("scoring.student", default={}) or {}
        path = cfg.get("bundle_dir")
        return str(path) if path else None
    except Exception:
        return None


def make_student_proxies() -> list[StudentProxyWrapper]:
    return [StudentProxyWrapper(name, key) for name, key in PROXY_SPECS]


def register_student_proxies(registry=None) -> list[StudentProxyWrapper]:
    """Register all student proxies on the given (or global) registry."""
    if registry is None:
        from modules.engines.registry import get_registry

        registry = get_registry()
    proxies = make_student_proxies()
    for p in proxies:
        registry.register(p)
    return proxies


__all__ = [
    "PROXY_SPECS",
    "STUDENT_NAMESPACE",
    "StudentProxyWrapper",
    "make_student_proxies",
    "register_student_proxies",
]
