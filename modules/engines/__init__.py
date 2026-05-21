"""Injectable model/engine abstractions for tests and alternate backends."""

from modules.engines.base import (
    IClusteringEngine,
    ILiqeScorer,
    IScoringEngine,
    IScoringModel,
    ITaggingEngine,
)
from modules.engines.mock import (
    MockClusteringEngine,
    MockLiqeScorer,
    MockScoringEngine,
    MockTaggingEngine,
)
from modules.engines.host import MultiModelHost
from modules.engines.liqe_model import LiqeModelWrapper
from modules.engines.musiq_model import MusiqModelWrapper, make_musiq_wrappers
from modules.engines.registry import (
    ModelRegistry,
    get_registry,
    reset_registry,
)
from modules.engines.topiq_model import TopiqModelWrapper

__all__ = [
    "IScoringEngine",
    "IScoringModel",
    "ILiqeScorer",
    "ITaggingEngine",
    "IClusteringEngine",
    "MockScoringEngine",
    "MockLiqeScorer",
    "MockTaggingEngine",
    "MockClusteringEngine",
    "ModelRegistry",
    "get_registry",
    "reset_registry",
    "MusiqModelWrapper",
    "make_musiq_wrappers",
    "LiqeModelWrapper",
    "TopiqModelWrapper",
    "MultiModelHost",
]

# Register one shadow-capable instance at import time. The wrapper lazy-loads
# its pyiqa backend on first `load()`, so this is cheap (no torch import here).
# Production vs. shadow membership is decided by `scoring.models` in config.
get_registry().register(TopiqModelWrapper())
