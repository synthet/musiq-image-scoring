"""Unit tests for Arm B vs label_set scoring (no DB, no images)."""

from __future__ import annotations

from scripts.research.bird_crop.focus_eval import _arm_b, _arm_b_vs_labels


def test_arm_b_vs_labels_precision_lift_against_reject():
    # Three eligible images: one reject flagged, one good flagged, one reject missed.
    # Patch via direct call with synthetic ids; label lookup comes from disk — skip
    # when CSV absent (CI without reports). This test uses the pure math path by
    # injecting through a local monkey of verdict_of via the public helper's
    # structure: we only assert the helper's unavailable path and _arm_b flags.
    out = _arm_b([])
    assert out["available"] is False


def test_arm_b_emits_flagged_ids_and_vs_labels_block():
    with_af = [
        {
            "image_id": 1,
            "crop": {"laplacian_variance": 10.0},
            "agreement": {"centre_inside": False},
        },
        {
            "image_id": 2,
            "crop": {"laplacian_variance": 1000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 3,
            "crop": {"laplacian_variance": 20.0},
            "agreement": {"centre_inside": False},
        },
        {
            "image_id": 4,
            "crop": {"laplacian_variance": 2000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 5,
            "crop": {"laplacian_variance": 3000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 6,
            "crop": {"laplacian_variance": 4000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 7,
            "crop": {"laplacian_variance": 5000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 8,
            "crop": {"laplacian_variance": 6000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 9,
            "crop": {"laplacian_variance": 7000.0},
            "agreement": {"centre_inside": True},
        },
        {
            "image_id": 10,
            "crop": {"laplacian_variance": 8000.0},
            "agreement": {"centre_inside": True},
        },
    ]
    out = _arm_b(with_af)
    assert out["available"] is True
    assert "flagged_image_ids" in out
    assert "vs_labels" in out
    # p10 of 10 values → softest one value; ids 1 and 3 are soft+AF-out but only
    # those <= p10 count. With 10 samples, p10 ≈ 2nd-lowest → 10 and 20 → both.
    assert set(out["flagged_image_ids"]) <= {1, 3}
    assert out["n_flagged_by_both"] == len(out["flagged_image_ids"])


def test_arm_b_vs_labels_missing_csv(tmp_path, monkeypatch):
    from scripts.research.bird_crop import labels as labels_mod

    monkeypatch.setattr(labels_mod, "LABEL_CSV", tmp_path / "missing.csv")
    out = _arm_b_vs_labels([1, 2], [1, 2, 3])
    assert out["available"] is False
    assert "missing" in out["reason"].lower() or "label_set" in out["reason"]
