"""StudentScorerService unit tests (AC-8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.student_scoring import (
    ALL_VECTOR_KEYS,
    StudentScorerError,
    StudentScorerService,
    reset_student_service,
)
from modules.score_normalization import DEFAULT_COMPOSITE_WEIGHTS, DEFAULT_PERCENTILE_ANCHORS


@pytest.fixture(autouse=True)
def _reset():
    reset_student_service()
    yield
    reset_student_service()


def _write_mock_bundle(tmp_path: Path, *, bad_checksum: bool = False) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    mock = {k: 0.42 for k in ALL_VECTOR_KEYS}
    mock["spaq"] = 0.6
    mock["ava"] = 0.4
    mock["liqe"] = 0.7
    mock["topiq"] = 0.55
    mock["arniqa"] = 0.5
    (bundle / "weights_placeholder.json").write_text("{}", encoding="utf-8")
    meta = {
        "weights_sha256": "placeholder",
        "manifest_id": "msm_test",
        "protocol_id": "ssp_test",
        "bundle_id": "bundle_test",
        "fusion": DEFAULT_COMPOSITE_WEIGHTS,
        "percentile_anchors": DEFAULT_PERCENTILE_ANCHORS,
        "mock_vector": mock,
        "preprocessing_fingerprint": "fp1",
        "architecture": {"backbone": "convnext_tiny", "input_size": 512},
    }
    if bad_checksum:
        # Simulate weights.pt with wrong digest
        weights = bundle / "weights.pt"
        weights.write_bytes(b"not-a-real-checkpoint")
        meta["weights_sha256"] = "0" * 64
        (bundle / "weights_placeholder.json").unlink()
    (bundle / "bundle.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return bundle


def test_checkpoint_metadata_and_checksum_are_required(tmp_path):
    svc = StudentScorerService()
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(StudentScorerError, match="bundle.meta"):
        svc.load_bundle(empty)

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "bundle.meta.json").write_text(json.dumps({"weights_sha256": "x"}), encoding="utf-8")
    with pytest.raises(StudentScorerError, match="manifest_id"):
        svc.load_bundle(bad)

    bundle = _write_mock_bundle(tmp_path, bad_checksum=True)
    with pytest.raises(StudentScorerError, match="checksum"):
        svc.load_bundle(bundle)


def test_vector_contains_proxies_composites_and_uncertainty(tmp_path):
    svc = StudentScorerService()
    svc.load_bundle(_write_mock_bundle(tmp_path))
    vec = svc.predict_vector(str(tmp_path / "img.jpg"))
    for key in ALL_VECTOR_KEYS:
        assert key in vec


def test_composites_use_bundle_frozen_config(tmp_path):
    from scripts.research.student_scorer.common import compute_composites_frozen

    svc = StudentScorerService()
    bundle = _write_mock_bundle(tmp_path)
    meta = json.loads((bundle / "bundle.meta.json").read_text(encoding="utf-8"))
    svc.load_bundle(bundle)
    vec = svc.predict_vector(str(tmp_path / "img.jpg"))
    teachers = {k: vec[k] for k in ("spaq", "ava", "liqe", "topiq", "arniqa")}
    expected = compute_composites_frozen(
        teachers, fusion=meta["fusion"], anchors=meta["percentile_anchors"]
    )
    assert abs(vec["general"] - expected["general"]) < 1e-6


def test_prediction_cache_invalidates_on_input_or_checkpoint_change(tmp_path):
    svc = StudentScorerService()
    bundle = _write_mock_bundle(tmp_path)
    svc.load_bundle(bundle)
    img_a = tmp_path / "a.jpg"
    img_b = tmp_path / "b.jpg"
    img_a.write_bytes(b"a")
    img_b.write_bytes(b"b")
    svc.predict_vector(str(img_a))
    assert svc.predict_calls == 1
    svc.predict_vector(str(img_a))
    assert svc.predict_calls == 1  # cache hit
    svc.predict_vector(str(img_b))
    assert svc.predict_calls == 2
    # Checkpoint / fingerprint change
    meta = json.loads((bundle / "bundle.meta.json").read_text(encoding="utf-8"))
    meta["preprocessing_fingerprint"] = "fp2"
    (bundle / "bundle.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    svc.load_bundle(bundle)
    svc.predict_vector(str(img_a))
    assert svc.predict_calls == 3
