"""Unit tests for ``scripts/maintenance/backfill_legacy_model_scores.py``.

Pure-Python checks: model selection guard, batch loop wiring, SQL shape.
No real DB.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_module():
    """Load the maintenance script as ``backfill_legacy_model_scores``."""
    if "backfill_legacy_model_scores" in sys.modules:
        return sys.modules["backfill_legacy_model_scores"]
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "scripts" / "maintenance" / "backfill_legacy_model_scores.py"
    spec = importlib.util.spec_from_file_location("backfill_legacy_model_scores", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["backfill_legacy_model_scores"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_legacy_models_cover_all_five_columns():
    mod = _load_module()
    names = {m for m, _ in mod.LEGACY_MODELS}
    cols = {c for _, c in mod.LEGACY_MODELS}
    assert names == {"spaq", "ava", "koniq", "paq2piq", "liqe"}
    assert cols == {"score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe"}


def test_selected_models_default_returns_all():
    mod = _load_module()
    assert mod._selected_models(None) == list(mod.LEGACY_MODELS)


def test_selected_models_filters_by_name():
    mod = _load_module()
    out = mod._selected_models(["spaq", "liqe"])
    assert out == [("spaq", "score_spaq"), ("liqe", "score_liqe")]


def test_selected_models_rejects_unknown():
    mod = _load_module()
    with pytest.raises(SystemExit):
        mod._selected_models(["spaq", "bogus"])


def test_backfill_model_loops_until_empty():
    """``_backfill_model`` should keep inserting until a partial batch returns."""
    mod = _load_module()
    # Three batches: 100, 100, 37; loop should stop after the short batch.
    with patch.object(mod.db_postgres, "execute_write", side_effect=[100, 100, 37]) as exec_w:
        total = mod._backfill_model("spaq", "score_spaq", batch_size=100)
    assert total == 237
    assert exec_w.call_count == 3
    sql, params = exec_w.call_args_list[0].args
    assert "INSERT INTO image_model_scores" in sql
    assert "ON CONFLICT (image_id, model_name) DO NOTHING" in sql
    assert "score_spaq" in sql
    assert params == ("spaq", mod._MODEL_VERSION, "spaq", 100)


def test_backfill_model_stops_when_no_rows():
    mod = _load_module()
    with patch.object(mod.db_postgres, "execute_write", return_value=0) as exec_w:
        total = mod._backfill_model("ava", "score_ava", batch_size=500)
    assert total == 0
    assert exec_w.call_count == 1


def test_backfill_sql_uses_existing_timestamps():
    """Falls back to created_at, then CURRENT_TIMESTAMP for scored_at."""
    mod = _load_module()
    with patch.object(mod.db_postgres, "execute_write", return_value=0) as exec_w:
        mod._backfill_model("liqe", "score_liqe", batch_size=1)
    sql = exec_w.call_args.args[0]
    assert "COALESCE(i.updated_at, i.created_at, CURRENT_TIMESTAMP)" in sql
