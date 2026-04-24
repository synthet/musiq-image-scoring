"""
Unit tests for ClusteringEngine._select_best_image().

Tests cover:
  - score strategy (default)
  - centroid strategy
  - balanced strategy
  - edge cases: single image, no embeddings, missing embeddings, all-equal scores
"""

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Stub heavy / unavailable dependencies before importing clustering
# ---------------------------------------------------------------------------

def _stub(name, **attrs):
    """Create and register a stub module unless it already exists.

    Returns ``(module, was_created)`` so callers can avoid mutating attributes
    on a real module that happens to already be loaded by an earlier test —
    overwriting attributes on a real module corrupts it for the rest of the
    pytest session (e.g. replacing ``pydantic.BaseModel`` with ``object``
    breaks every later test that imports gradio, pydantic, or FastAPI).
    """
    created = False
    if name not in sys.modules:
        parent = name.rsplit(".", 1)[0] if "." in name else None
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
        if parent and parent in sys.modules:
            setattr(sys.modules[parent], name.rsplit(".", 1)[1], mod)
        created = True
    return sys.modules[name], created


# sklearn stubs (not installed in pytest environment)
_stub("sklearn")
_stub("sklearn.cluster", AgglomerativeClustering=MagicMock())

# PIL stubs (only when not already imported)
_stub("PIL")
_stub("PIL.Image")


# pydantic stub (needed by modules.events when pydantic itself is missing).
# Only inject the placeholder BaseModel/Field when we actually created the
# stub module — never mutate the real pydantic that another test imported.
_pydantic, _pydantic_was_stubbed = _stub("pydantic")
if _pydantic_was_stubbed:
    class _Field:
        def __call__(self, *a, **kw):
            return kw.get("default", None)

    _pydantic.BaseModel = object
    _pydantic.Field = _Field()

# Heavy project-internal stubs (avoid DB / TF / fdb imports)
_stub("modules.events", event_manager=MagicMock())
_stub("modules.db")
_stub("modules.utils")

def _get_config_section(section):
    if section == "clustering":
        return {
            "best_image_strategy": "score",
            "best_image_alpha": 0.65,
            "default_threshold": 0.15,
            "default_time_gap": 120,
            "force_rescan_default": False,
            "clustering_batch_size": 32,
        }
    if section == "processing":
        return {"clustering_batch_size": 32}
    return {}

_stub("modules.config", get_config_section=_get_config_section)
_stub("modules.phases", PhaseCode=MagicMock(), PhaseStatus=MagicMock())
_stub("modules.phases_policy",
      explain_phase_run_decision=MagicMock(return_value={"should_run": True, "reason": ""}))
_stub("modules.version", APP_VERSION="test")

# Now safe to import
from modules.clustering import ClusteringEngine  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine():
    """Instantiate ClusteringEngine without disk I/O or model loading."""
    with (
        patch.object(ClusteringEngine, "_ensure_cache_dir"),
        patch.object(ClusteringEngine, "_load_cache"),
    ):
        engine = ClusteringEngine.__new__(ClusteringEngine)
        engine.feature_cache = {}
        engine.cache_dir = "/tmp/fake_cache"
        engine.model = None
        engine.is_running = False
        engine.status_message = "Idle"
        engine.current = 0
        engine.total = 0
    return engine


def cfg_patch(strategy="score", alpha=0.65):
    """Patch modules.clustering.config.get_config_section for clustering config."""
    return patch(
        "modules.clustering.config.get_config_section",
        return_value={
            "best_image_strategy": strategy,
            "best_image_alpha": alpha,
        },
    )


# ---------------------------------------------------------------------------
# Tests: score strategy
# ---------------------------------------------------------------------------

class TestSelectBestImageScore:
    def test_returns_highest_score(self):
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: 0.4, 2: 0.9, 3: 0.6}
        with cfg_patch("score"):
            result = engine._select_best_image(img_ids, id_to_score)
        assert result == 2

    def test_single_image_returns_it(self):
        engine = make_engine()
        with cfg_patch("score"):
            result = engine._select_best_image([42], {42: 0.5})
        assert result == 42

    def test_empty_returns_none(self):
        engine = make_engine()
        with cfg_patch("score"):
            result = engine._select_best_image([], {})
        assert result is None

    def test_none_scores_treated_as_zero(self):
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: None, 2: None, 3: None}
        with cfg_patch("score"):
            result = engine._select_best_image(img_ids, id_to_score)
        assert result in img_ids

    def test_all_equal_scores(self):
        engine = make_engine()
        img_ids = [10, 20, 30]
        id_to_score = {10: 0.5, 20: 0.5, 30: 0.5}
        with cfg_patch("score"):
            result = engine._select_best_image(img_ids, id_to_score)
        assert result in img_ids


# ---------------------------------------------------------------------------
# Tests: centroid strategy
# ---------------------------------------------------------------------------



    def test_prefers_stack_representative_strategy_over_legacy_key(self):
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: 0.9, 2: 0.1, 3: 0.2}
        id_to_feature = {
            1: np.array([1.0, 0.0, 0.0], dtype=np.float32),
            2: np.array([0.577, 0.577, 0.577], dtype=np.float32),
            3: np.array([0.0, 0.0, 1.0], dtype=np.float32),
        }
        with patch(
            "modules.clustering.config.get_config_section",
            return_value={
                "stack_representative_strategy": "centroid",
                "best_image_strategy": "score",
                "best_image_alpha": 0.65,
            },
        ):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature)
        assert result == 2
class TestSelectBestImageCentroid:
    def _make_feats(self):
        """Three 3-D embeddings: id=2 is closest to the centroid direction."""
        f1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        f2 = np.array([0.577, 0.577, 0.577], dtype=np.float32)  # near centroid
        f3 = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        return {1: f1, 2: f2, 3: f3}

    def test_picks_closest_to_centroid(self):
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: 0.9, 2: 0.5, 3: 0.7}  # id=1 has best score but is far
        id_to_feature = self._make_feats()
        with cfg_patch("centroid"):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature)
        assert result == 2

    def test_fallback_to_score_when_no_embeddings(self):
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: 0.3, 2: 0.8, 3: 0.5}
        with cfg_patch("centroid"):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature=None)
        assert result == 2

    def test_single_image_returns_it(self):
        engine = make_engine()
        feat = {99: np.array([0.5, 0.5], dtype=np.float32)}
        with cfg_patch("centroid"):
            result = engine._select_best_image([99], {99: 0.7}, feat)
        assert result == 99

    def test_handles_partial_embeddings(self):
        """Only id=2 has an embedding; centroid == that embedding → id=2 wins."""
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: 0.1, 2: 0.2, 3: 0.3}
        id_to_feature = {2: np.array([1.0, 0.0], dtype=np.float32)}
        with cfg_patch("centroid"):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature)
        assert result == 2


# ---------------------------------------------------------------------------
# Tests: balanced strategy
# ---------------------------------------------------------------------------

class TestSelectBestImageBalanced:
    def _setup(self):
        img_ids = [1, 2, 3]
        # id=1: best quality score, far from centroid
        # id=2: moderate score, closest to centroid
        id_to_score = {1: 1.0, 2: 0.5, 3: 0.0}
        f1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        f2 = np.array([0.577, 0.577, 0.577], dtype=np.float32)
        f3 = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        id_to_feature = {1: f1, 2: f2, 3: f3}
        return img_ids, id_to_score, id_to_feature

    def test_pure_representativeness_picks_centroid_image(self):
        engine = make_engine()
        img_ids, id_to_score, id_to_feature = self._setup()
        with cfg_patch("balanced", alpha=0.0):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature)
        assert result == 2

    def test_pure_quality_picks_highest_score_image(self):
        engine = make_engine()
        img_ids, id_to_score, id_to_feature = self._setup()
        with cfg_patch("balanced", alpha=1.0):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature)
        assert result == 1

    def test_fallback_to_score_when_no_embeddings(self):
        engine = make_engine()
        img_ids = [1, 2, 3]
        id_to_score = {1: 0.1, 2: 0.9, 3: 0.5}
        with cfg_patch("balanced"):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature=None)
        assert result == 2

    def test_default_alpha_used_when_missing_from_config(self):
        """Missing alpha key should default to 0.65 without raising."""
        engine = make_engine()
        img_ids = [1, 2]
        id_to_score = {1: 0.8, 2: 0.2}
        id_to_feature = {
            1: np.array([1.0, 0.0], dtype=np.float32),
            2: np.array([0.0, 1.0], dtype=np.float32),
        }
        with patch(
            "modules.clustering.config.get_config_section",
            return_value={"best_image_strategy": "balanced"},  # no alpha key
        ):
            result = engine._select_best_image(img_ids, id_to_score, id_to_feature)
        assert result in img_ids
