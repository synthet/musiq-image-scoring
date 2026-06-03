"""Factory for the production registry-driven scoring engine."""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Tuple

from modules.engines.host import MultiModelHost
from modules.engines.liqe_model import LiqeModelWrapper
from modules.engines.musiq_model import make_musiq_wrappers
from modules.engines.registry import ModelRegistry, get_registry

logger = logging.getLogger(__name__)

_DEFAULT_MUSIQ_NAMES: Tuple[str, ...] = ("spaq", "ava")


def ensure_production_registry(
    backend: Any,
    *,
    registry: Optional[ModelRegistry] = None,
    musiq_names: Optional[List[str]] = None,
    liqe_scorer: Optional[Any] = None,
) -> ModelRegistry:
    """Register MUSIQ-family and LIQE wrappers on the process registry.

    Shadow / LLM models (e.g. ``topiq``, ``cursor``) register at import time in
    ``modules.engines``. Idempotent for repeated calls with the same backend.
    """
    reg = registry or get_registry()
    names = musiq_names if musiq_names is not None else list(_DEFAULT_MUSIQ_NAMES)
    for wrapper in make_musiq_wrappers(backend, names=names):
        reg.register(wrapper)

    liqe = reg.get("liqe")
    if liqe is None:
        reg.register(LiqeModelWrapper(scorer=liqe_scorer))
    elif liqe_scorer is not None and getattr(liqe, "_scorer", None) is not liqe_scorer:
        reg.register(LiqeModelWrapper(scorer=liqe_scorer))
    return reg


def create_production_scoring_host(
    *,
    liqe_scorer: Optional[Any] = None,
    registry: Optional[ModelRegistry] = None,
) -> MultiModelHost:
    """Build ``MultiModelHost`` backed by ``MultiModelMUSIQ`` and the model registry."""
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    backend = MultiModelMUSIQ()
    reg = ensure_production_registry(
        backend,
        registry=registry,
        liqe_scorer=liqe_scorer,
    )
    version = getattr(backend, "VERSION", None)
    return MultiModelHost(backend=backend, registry=reg, version=version)


def load_production_models(
    host: MultiModelHost,
    *,
    log: Optional[Callable[[str, str], None]] = None,
) -> Tuple[bool, str]:
    """Load every active registry model; fail only when a production model cannot load."""
    def _emit(msg: str, level: str = "INFO") -> None:
        if log is not None:
            log(msg, level)
        else:
            logger.log(logging.WARNING if level == "WARNING" else logging.INFO, msg)

    _emit("Loading scoring models from registry...")
    statuses = host.load_enabled_and_shadow()
    production = [m.name for m in host.registry.enabled()]
    failed_prod = [n for n in production if not statuses.get(n)]
    if failed_prod:
        return False, f"Production model(s) failed to load: {', '.join(failed_prod)}"

    for name, ok in sorted(statuses.items()):
        if name in production:
            continue
        if not ok:
            _emit(f"Shadow model {name} not loaded (scoring continues)", "WARNING")

    return True, "ok"


__all__ = [
    "create_production_scoring_host",
    "ensure_production_registry",
    "load_production_models",
]
