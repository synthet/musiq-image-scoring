"""Injectable model/engine abstractions for tests and alternate backends."""

from modules.engines.arniqa_model import ArniqaModelWrapper
from modules.engines.base import (
    IClusteringEngine,
    ILiqeScorer,
    IScoringEngine,
    IScoringModel,
    ITaggingEngine,
)
from modules.engines.claude_model import ClaudeModelWrapper
from modules.engines.cursor_model import CursorModelWrapper
from modules.engines.factory import (
    create_production_scoring_host,
    ensure_production_registry,
    ensure_student_proxies_registered,
    load_production_models,
)
from modules.engines.host import MultiModelHost
from modules.engines.liqe_model import LiqeModelWrapper
from modules.engines.mock import (
    MockClusteringEngine,
    MockLiqeScorer,
    MockScoringEngine,
    MockTaggingEngine,
)
from modules.engines.musiq_model import MusiqModelWrapper, make_musiq_wrappers
from modules.engines.qpt_v2_model import QptV2ModelWrapper
from modules.engines.registry import (
    ModelRegistry,
    get_registry,
    reset_registry,
)
from modules.engines.student_model import (
    StudentProxyWrapper,
    make_student_proxies,
    register_student_proxies,
)
from modules.engines.topiq_model import TopiqModelWrapper

__all__ = [
    "ArniqaModelWrapper",
    "ClaudeModelWrapper",
    "CursorModelWrapper",
    "IClusteringEngine",
    "ILiqeScorer",
    "IScoringEngine",
    "IScoringModel",
    "ITaggingEngine",
    "LiqeModelWrapper",
    "MockClusteringEngine",
    "MockLiqeScorer",
    "MockScoringEngine",
    "MockTaggingEngine",
    "ModelRegistry",
    "MultiModelHost",
    "MusiqModelWrapper",
    "QptV2ModelWrapper",
    "StudentProxyWrapper",
    "TopiqModelWrapper",
    "create_production_scoring_host",
    "ensure_production_registry",
    "ensure_student_proxies_registered",
    "get_registry",
    "load_production_models",
    "make_musiq_wrappers",
    "make_student_proxies",
    "register_student_proxies",
    "reset_registry",
]

# Register TOPIQ at import time. The wrapper lazy-loads its pyiqa backend on
# first `load()`, so this is cheap (no torch import here). Production vs.
# shadow membership is decided by `scoring.models` in config.
get_registry().register(TopiqModelWrapper())

# ARNIQA registers as a shadow scorer (#220 phase 2). Like TOPIQ it lazy-loads
# its pyiqa backend on first `load()`, so import stays cheap. It runs and stores
# to `image_model_scores` but is excluded from fusion (config default
# `scoring.models.arniqa: {enabled: false, shadow: true}`) until calibrated.
get_registry().register(ArniqaModelWrapper())

# QPT V2 is not registered until validation/calibration (#185) is complete.
# Re-enable: get_registry().register(QptV2ModelWrapper())

# LLM-judge engines (Cursor SDK, Claude Agent SDK). Both lazy-load their
# optional SDKs on first `load()` and are disabled by default in config, so
# registering them here is cheap and makes no network calls.
get_registry().register(CursorModelWrapper())
get_registry().register(ClaudeModelWrapper())

# Student proxies are NOT registered at import time. Registry treats models
# absent from scoring.models as enabled; auto-registering would activate them
# on older config.json files. Call register_student_proxies() from
# ensure_production_registry / an explicit shadow campaign setup once
# scoring.models contains the vexlum_student_v1_* entries (see config.example.json).
