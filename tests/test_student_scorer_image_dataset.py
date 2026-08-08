"""Tests for P0 image dataset + torch loss helpers + dry-build train."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.research.student_scorer.common import DEFAULT_TEACHERS, write_json
from scripts.research.student_scorer.export_embeddings_npz import head_list
from scripts.research.student_scorer.image_dataset import (
    P0ImageDataset,
    build_sample_arrays,
)
from scripts.research.student_scorer.train_image_model import run_train


def test_dataset_head_order_follows_manifest_teachers(tmp_path):
    teachers = ["arniqa", "ava", "liqe", "spaq", "topiq"]  # alphabetical, ≠ DEFAULT order
    assert list(teachers) != list(DEFAULT_TEACHERS)

    from PIL import Image

    jpg = tmp_path / "cache" / "7" / "7.jpg"
    jpg.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), color=(1, 2, 3)).save(jpg, "JPEG")

    rows = [
        {
            "image_id": 7,
            "teacher_normalized": {"arniqa": 0.5, "ava": 0.4},
            "teacher_mask": {
                "arniqa": True,
                "ava": True,
                "liqe": False,
                "spaq": False,
                "topiq": False,
            },
            "score_general": 0.55,
            "score_technical": None,
            "score_aesthetic": 0.4,
        }
    ]
    render_index = {
        7: {
            "image_id": 7,
            "rel_path": "7/7.jpg",
            "status": "ok",
            "resolved_method": "pil_open",
            "cache_dir": str(tmp_path / "cache"),
        }
    }
    arrays = build_sample_arrays(
        rows,
        render_index,
        {7: "train"},
        teachers=teachers,
        cache_dir=tmp_path / "cache",
    )
    assert arrays["heads"] == head_list(teachers)
    assert arrays["heads"][:5] == teachers
    # missing teachers masked, not treated as real supervision
    assert arrays["masks"][0][2] is False  # liqe
    assert arrays["targets"][0][2] == 0.0
    ds = P0ImageDataset(arrays)
    sample = ds[0]
    assert sample["targets"].shape == (8,)
    assert sample["masks"].dtype == np.bool_
    assert sample["masks"][2] == False  # noqa: E712


def test_dry_build_only_needs_no_gpu_or_renders(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.research.student_scorer.train_image_model.ensure_artifacts_dir",
        lambda run_id=None: tmp_path / "artifacts" / (run_id or "root"),
    )
    meta = {
        "manifest_id": "msm_dry",
        "checksum": "c",
        "protocol_id": "ssp_dry",
        "contract_hash": "h",
        "teachers": ["arniqa", "ava", "liqe", "spaq", "topiq"],
        "preprocessing": {"max_resolution": 512},
        "fusion": {},
        "percentile_anchors": {},
        "gates": {},
    }
    write_json(tmp_path / "manifest.meta.json", meta)
    (tmp_path / "manifest.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(tmp_path / "splits.json", {"assignments": []})

    # dry build still constructs the graph — needs torch+timm
    pytest.importorskip("torch")
    pytest.importorskip("timm")
    out = run_train(
        manifest_dir=tmp_path,
        experiment="E2",
        dry_build_only=True,
        epochs=0,
    )
    assert out["status"] == "built"
    assert out["backbone"] == "convnext_tiny"
    assert out["teachers"] == meta["teachers"]


@pytest.mark.ml
def test_torch_rescale_percentile_matches_scalar():
    pytest.importorskip("torch")
    import torch

    from modules.score_normalization import rescale_percentile
    from scripts.research.student_scorer.torch_losses import rescale_percentile_torch

    p02, p98 = 0.3, 0.8
    grid = [-0.1, 0.0, 0.15, 0.3, 0.3000001, 0.5, 0.8, 0.9, 1.0]
    for s in grid:
        got = float(rescale_percentile_torch(torch.tensor(s), p02, p98))
        exp = float(rescale_percentile(s, p02, p98))
        assert got == pytest.approx(exp, abs=1e-6), f"s={s}"


@pytest.mark.ml
def test_head_losses_are_coverage_normalized_torch():
    pytest.importorskip("torch")
    import torch

    from scripts.research.student_scorer.torch_losses import (
        coverage_normalized_teacher_loss,
        masked_huber_torch,
    )

    teachers = ["a", "b"]
    preds = {
        "a": torch.tensor([0.1, 0.2, 0.3, 0.4, 0.5]),
        "b": torch.tensor([0.9, 0.0, 0.0, 0.0, 0.0]),
    }
    targets = torch.zeros(5, 2)
    masks = torch.tensor(
        [
            [True, True],
            [True, False],
            [True, False],
            [True, False],
            [True, False],
        ]
    )
    loss = coverage_normalized_teacher_loss(preds, targets, masks, teachers)
    la = masked_huber_torch(preds["a"], targets[:, 0], masks[:, 0])
    lb = masked_huber_torch(preds["b"], targets[:, 1], masks[:, 1])
    assert float(loss) == pytest.approx(0.5 * (float(la) + float(lb)), abs=1e-6)


@pytest.mark.ml
def test_derived_and_direct_composites_both_reported():
    """Gate-bearing derived path differs from direct aux heads when they disagree."""
    from scripts.research.student_scorer.common import compute_composites_frozen
    from scripts.research.student_scorer.train_image_model import _slice_fidelity

    teachers = ["arniqa", "ava", "liqe", "spaq", "topiq"]
    fusion = {
        "general": {"liqe": 0.35, "spaq": 0.30, "topiq": 0.13, "arniqa": 0.10, "ava": 0.12},
        "technical": {"topiq": 0.30, "arniqa": 0.25, "spaq": 0.25, "liqe": 0.20},
        "aesthetic": {"ava": 0.40, "spaq": 0.50, "liqe": 0.10},
    }
    anchors = {
        "arniqa": {"p02": 0.467, "p98": 0.746},
        "ava": {"p02": 0.301, "p98": 0.524},
        "liqe": {"p02": 0.311, "p98": 0.998},
        "spaq": {"p02": 0.257, "p98": 0.76},
        "topiq": {"p02": 0.39, "p98": 0.709},
    }
    n = 20
    preds_derived = []
    preds_direct = []
    targets = []
    masks = []
    for i in range(n):
        # Vary teacher scores so Spearman is defined
        base = 0.35 + 0.02 * i
        teacher_scores = {t: min(0.95, base + 0.01 * j) for j, t in enumerate(teachers)}
        derived = compute_composites_frozen(teacher_scores, fusion=fusion, anchors=anchors)
        row_t = {**teacher_scores, **derived}
        targets.append(row_t)
        masks.append({k: True for k in row_t})
        preds_derived.append(dict(row_t))
        bad = dict(row_t)
        bad["general"] = 0.1  # constant wrong direct head
        preds_direct.append(bad)

    gates = {
        "composite_spearman_min": 0.95,
        "median_teacher_spearman_min": 0.90,
        "composite_mae_max": 0.03,
        "saturation_low": 0.02,
        "saturation_high": 0.98,
    }
    d_rep = _slice_fidelity(
        preds_derived, targets, masks, teachers, full_target_only=False, gates=gates
    )
    x_rep = _slice_fidelity(
        preds_direct, targets, masks, teachers, full_target_only=False, gates=gates
    )
    assert d_rep["gates"]["composite_spearman"]["pass"] is True
    assert x_rep["per_head"]["general"]["mae"] > d_rep["per_head"]["general"]["mae"]
    # Gate-bearing path is derived; nonsaturated MAE needs saturation_values (via _slice_fidelity)
    assert d_rep["all_required_passed"] is True
    assert x_rep["gates"]["composite_mae_nonsaturated"]["pass"] is False or (
        x_rep["per_head"]["general"]["mae"] > 0.03
    )


def _resume_run_config(**overrides):
    base = {
        "manifest_id": "msm_test",
        "protocol_id": "ssp_test",
        "experiment": "E2",
        "seed": 42,
        "epochs": 20,
        "limit": None,
        "batch_size": 16,
        "grad_accum": 2,
        "lr": 1e-4,
        "patience": 3,
        "backbone": "convnext_tiny",
        "fine_tune": "last_stage",
        "input": "P0",  # not guarded
    }
    base.update(overrides)
    return base


def test_resume_guard_ignores_unguarded_keys_but_catches_config_change():
    from scripts.research.student_scorer.train_image_model import _resume_guard

    base = _resume_guard(_resume_run_config())
    assert "input" not in base
    assert base == _resume_guard(_resume_run_config(input="P2"))
    assert base != _resume_guard(_resume_run_config(seed=7))
    assert base != _resume_guard(_resume_run_config(limit=500))
    assert base != _resume_guard(_resume_run_config(batch_size=8))


@pytest.mark.ml
def test_resume_state_roundtrip_restores_epoch_and_history(tmp_path):
    from scripts.research.student_scorer.train_image_model import (
        _load_resume_state,
        _resume_guard,
        _save_resume_state_atomic,
    )

    guard = _resume_guard(_resume_run_config())
    history = [{"epoch": 0, "val_masked_teacher_loss": 0.9}, {"epoch": 1, "val_masked_teacher_loss": 0.4}]
    path = tmp_path / "last.pt"
    _save_resume_state_atomic(
        path,
        {
            "history": history,
            "best_val": 0.4,
            "best_epoch": 1,
            "bad_epochs": 0,
            "next_epoch": 2,
            "guard": guard,
        },
    )

    assert not (tmp_path / "last.pt.tmp").exists()  # tmp+replace leaves nothing behind
    state = _load_resume_state(path, guard)
    assert state is not None
    assert state["next_epoch"] == 2
    assert state["history"] == history
    assert state["best_val"] == 0.4
    assert state["best_epoch"] == 1


@pytest.mark.ml
def test_resume_returns_none_when_no_checkpoint(tmp_path):
    from scripts.research.student_scorer.train_image_model import (
        _load_resume_state,
        _resume_guard,
    )

    guard = _resume_guard(_resume_run_config())
    assert _load_resume_state(tmp_path / "last.pt", guard) is None


@pytest.mark.ml
def test_resume_refuses_guard_mismatch(tmp_path):
    """A last.pt from a different run must never be silently continued into."""
    from scripts.research.student_scorer.train_image_model import (
        _load_resume_state,
        _resume_guard,
        _save_resume_state_atomic,
    )

    path = tmp_path / "last.pt"
    _save_resume_state_atomic(
        path, {"next_epoch": 5, "guard": _resume_guard(_resume_run_config(limit=500))}
    )

    with pytest.raises(RuntimeError, match="different run config"):
        _load_resume_state(path, _resume_guard(_resume_run_config()))
