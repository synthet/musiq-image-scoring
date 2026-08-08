"""Fast unit tests for embedding NPZ export and E0/E1 path separation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.research.student_scorer.data import validate_manifest_against_protocol
from scripts.research.student_scorer.export_embeddings_npz import (
    align_embeddings_to_manifest,
    head_list,
    row_targets_and_masks,
)
from scripts.research.student_scorer.train_embedding_head import (
    _fit_ridge_multioutput,
    run_embedding_baseline,
)


def test_row_targets_and_masks_alignment():
    teachers = ["spaq", "ava", "liqe"]
    heads = head_list(teachers)
    row = {
        "teacher_normalized": {"spaq": 0.5, "ava": 0.4},
        "teacher_mask": {"spaq": True, "ava": True, "liqe": False},
        "score_general": 0.55,
        "score_technical": None,
        "score_aesthetic": 0.4,
    }
    targets, masks = row_targets_and_masks(row, heads, teachers)
    assert heads == ["spaq", "ava", "liqe", "general", "technical", "aesthetic"]
    assert masks == [True, True, False, True, False, True]
    assert targets[0] == pytest.approx(0.5)
    assert targets[2] == 0.0  # masked missing teacher not used as real target


def test_align_embeddings_to_manifest_overlap():
    teachers = ["spaq", "ava"]
    rows = [
        {
            "image_id": 1,
            "teacher_normalized": {"spaq": 0.5, "ava": 0.4},
            "teacher_mask": {"spaq": True, "ava": True},
            "score_general": 0.5,
            "score_technical": 0.5,
            "score_aesthetic": 0.5,
        },
        {
            "image_id": 2,
            "teacher_normalized": {"spaq": 0.6, "ava": 0.3},
            "teacher_mask": {"spaq": True, "ava": True},
            "score_general": 0.6,
            "score_technical": 0.4,
            "score_aesthetic": 0.5,
        },
        {
            "image_id": 3,
            "teacher_normalized": {"spaq": 0.7, "ava": 0.2},
            "teacher_mask": {"spaq": True, "ava": True},
            "score_general": 0.7,
            "score_technical": 0.3,
            "score_aesthetic": 0.5,
        },
    ]
    split_of = {1: "train", 2: "val", 3: "test"}
    emb = {
        1: np.ones(4, dtype=np.float32),
        3: np.ones(4, dtype=np.float32) * 2,
        # 2 missing
    }
    aligned = align_embeddings_to_manifest(
        rows, split_of, emb, teachers=teachers, expected_dim=4
    )
    assert aligned["coverage"]["n_manifest"] == 3
    assert aligned["coverage"]["n_with_embedding"] == 2
    assert aligned["coverage"]["n_missing_embedding"] == 1
    assert list(aligned["image_ids"]) == [1, 3]
    assert aligned["embeddings"].shape == (2, 4)
    assert aligned["targets"].shape[1] == len(head_list(teachers))
    assert list(aligned["splits"]) == ["train", "test"]


def test_e0_and_e1_are_different_fit_kinds(tmp_path: Path):
    """E0 uses ridge; E1 uses MLP — reports must disagree on fit_kind."""
    rng = np.random.default_rng(0)
    n, d, h = 120, 16, 5
    X = rng.normal(size=(n, d))
    # Linear-ish targets so both can fit something
    W_true = rng.normal(size=(d, h))
    Y = X @ W_true + rng.normal(scale=0.05, size=(n, h))
    M = np.ones((n, h), dtype=bool)
    ids = np.arange(n)
    splits = np.array(["train"] * 80 + ["val"] * 20 + ["test"] * 10 + ["ood_test"] * 10)

    npz = tmp_path / "emb.npz"
    np.savez(
        npz,
        image_ids=ids,
        embeddings=X.astype(np.float32),
        targets=Y.astype(np.float64),
        masks=M,
        splits=splits,
    )

    manifest = tmp_path / "msm"
    manifest.mkdir()
    meta = {
        "manifest_id": "msm_test",
        "protocol_id": "ssp_test",
        "contract_hash": "c",
        "checksum": "deadbeef",
        "teachers": ["spaq", "ava", "liqe", "topiq", "arniqa"][:h],
    }
    # pad teachers to match h
    while len(meta["teachers"]) < h:
        meta["teachers"].append(f"t{len(meta['teachers'])}")
    meta["teachers"] = meta["teachers"][:h]
    # Actually heads = teachers + 3 composites in trainer — need Y cols match
    # Rebuild with proper head count
    teachers = ["spaq", "ava", "liqe"]
    heads_n = len(teachers) + 3
    Y2 = rng.normal(size=(n, heads_n))
    M2 = np.ones((n, heads_n), dtype=bool)
    np.savez(
        npz,
        image_ids=ids,
        embeddings=X.astype(np.float32),
        targets=Y2.astype(np.float64),
        masks=M2,
        splits=splits,
    )
    meta["teachers"] = teachers
    (manifest / "manifest.meta.json").write_text(
        __import__("json").dumps(meta), encoding="utf-8"
    )
    (manifest / "splits.json").write_text(
        __import__("json").dumps(
            {"assignments": [{"image_id": int(i), "split": str(s), "component_id": "c"} for i, s in zip(ids, splits)]}
        ),
        encoding="utf-8",
    )

    e0 = run_embedding_baseline(
        manifest_dir=manifest,
        embeddings_npz=npz,
        experiment="E0",
        seed=1,
        epochs=5,
    )
    e1 = run_embedding_baseline(
        manifest_dir=manifest,
        embeddings_npz=npz,
        experiment="E1",
        seed=1,
        epochs=8,
    )
    assert e0["fit_kind"] == "ridge"
    assert e1["fit_kind"] == "mlp"
    assert e0["experiment"] != e1["experiment"] or e0["fit_kind"] != e1["fit_kind"]
    assert "fidelity_test" in e0 and "fidelity_ood_test" in e0
    assert e0["selection_split"] == "val"


def test_train_refuses_protocol_mismatch(tmp_path: Path):
    meta = {"protocol_id": "ssp_a", "contract_hash": "c1", "checksum": "x"}
    with pytest.raises(ValueError, match="protocol_id"):
        validate_manifest_against_protocol(meta, expected_protocol_id="ssp_other")


def test_ridge_is_not_mlp_weights():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(50, 8))
    Y = rng.normal(size=(50, 3))
    M = np.ones_like(Y, dtype=bool)
    W, b = _fit_ridge_multioutput(X, Y, M)
    assert W.shape == (8, 3)
    assert b.shape == (3,)
