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
    "MultiModelHost",
]
