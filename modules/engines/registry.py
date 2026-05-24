"""Registry for `IScoringModel` instances.

Each model wrapper registers one instance at import time (via
`modules/engines/__init__.py`). The host (`MultiModelHost`) uses the registry
to enumerate which models to load and run per image.

Production vs. shadow membership is read from `scoring.models` in `config.json`:
    "scoring": {
      "models": {
        "spaq":   { "enabled": true,  "shadow": false },
        "topiq":  { "enabled": true,  "shadow": false }
      }
    }

`enabled=true, shadow=false`  → production: inferred and fused.
`enabled=false, shadow=true`  → shadow: inferred and stored, NOT fused.
`enabled=true, shadow=true`   → treated as shadow (shadow wins; production
                                must explicitly set shadow=false).
`enabled=false, shadow=false` → skipped entirely.

A model that is registered but absent from config is treated as enabled
(so default behavior matches today's hardcoded list).
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from modules.engines.base import IScoringModel

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Process-wide registry of scoring models. Not thread-safe for register;
    callers register at import time before workers spin up."""

    def __init__(self) -> None:
        self._models: Dict[str, IScoringModel] = {}
        self._lock = threading.Lock()

    def register(self, model: IScoringModel) -> None:
        if not getattr(model, "name", ""):
            raise ValueError("IScoringModel must have a non-empty `name`")
        with self._lock:
            existing = self._models.get(model.name)
            if existing is not None and existing is not model:
                logger.warning(
                    "Replacing already-registered scoring model %r (was %s, now %s)",
                    model.name,
                    type(existing).__name__,
                    type(model).__name__,
                )
            self._models[model.name] = model

    def unregister(self, name: str) -> None:
        with self._lock:
            self._models.pop(name, None)

    def get(self, name: str) -> Optional[IScoringModel]:
        return self._models.get(name)

    def all_registered(self) -> List[IScoringModel]:
        return list(self._models.values())

    def enabled(self, config_section: Optional[Dict[str, Dict]] = None) -> List[IScoringModel]:
        """Production models: enabled, not shadow."""
        cfg = self._resolve_config(config_section)
        return [m for m in self._models.values() if _is_enabled(m.name, cfg) and not _is_shadow(m.name, cfg)]

    def shadow(self, config_section: Optional[Dict[str, Dict]] = None) -> List[IScoringModel]:
        """Shadow models: run and store, do not fuse."""
        cfg = self._resolve_config(config_section)
        return [m for m in self._models.values() if _is_shadow(m.name, cfg) and _is_active(m.name, cfg)]

    def all_active(self, config_section: Optional[Dict[str, Dict]] = None) -> List[IScoringModel]:
        """Models that should run for an image (production ∪ shadow)."""
        cfg = self._resolve_config(config_section)
        return [m for m in self._models.values() if _is_active(m.name, cfg)]

    def is_shadow(self, name: str, config_section: Optional[Dict[str, Dict]] = None) -> bool:
        cfg = self._resolve_config(config_section)
        return _is_shadow(name, cfg)

    @staticmethod
    def _resolve_config(config_section: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
        if config_section is not None:
            return config_section
        try:
            from modules.config import get_config_value

            return get_config_value("scoring.models", default={}) or {}
        except Exception as exc:
            logger.debug("Could not read scoring.models from config: %s", exc)
            return {}


def _entry(name: str, cfg: Dict[str, Dict]) -> Dict:
    entry = cfg.get(name)
    return entry if isinstance(entry, dict) else {}


def _is_shadow(name: str, cfg: Dict[str, Dict]) -> bool:
    return bool(_entry(name, cfg).get("shadow", False))


def _is_enabled(name: str, cfg: Dict[str, Dict]) -> bool:
    """Default True if the model is registered but absent from config."""
    entry = _entry(name, cfg)
    if not entry:
        return True
    return bool(entry.get("enabled", True))


def _is_active(name: str, cfg: Dict[str, Dict]) -> bool:
    """A model runs if it is enabled OR shadow."""
    return _is_enabled(name, cfg) or _is_shadow(name, cfg)


_registry: Optional[ModelRegistry] = None
_singleton_lock = threading.Lock()


def get_registry() -> ModelRegistry:
    """Process-wide singleton."""
    global _registry
    if _registry is None:
        with _singleton_lock:
            if _registry is None:
                _registry = ModelRegistry()
    return _registry


def reset_registry() -> None:
    """Test helper: drop all registrations."""
    global _registry
    with _singleton_lock:
        _registry = None


__all__ = ["ModelRegistry", "get_registry", "reset_registry"]
