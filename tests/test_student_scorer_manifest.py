"""Manifest / B0 / provenance tests for student scorer (AC-1, AC-2, AC-4)."""

from __future__ import annotations

import pytest

from modules.score_normalization import DEFAULT_COMPOSITE_WEIGHTS, DEFAULT_PERCENTILE_ANCHORS
from scripts.research.student_scorer.common import (
    PROVENANCE_AUTOMATIC,
    PROVENANCE_HUMAN,
    PROVENANCE_UNKNOWN,
    classify_label_provenance,
    compute_composites_frozen,
)
from scripts.research.student_scorer.data import (
    compute_manifest_id,
    validate_manifest_against_protocol,
)


def _sample_rows(n: int = 3):
    rows = []
    for i in range(n):
        rows.append(
            {
                "image_id": i + 1,
                "path_token": f"photos/a{i}.nef",
                "teacher_normalized": {
                    "spaq": 0.5 + i * 0.01,
                    "ava": 0.4,
                    "liqe": 0.6,
                    "topiq": 0.55,
                    "arniqa": 0.5,
                },
            }
        )
    return rows


def test_manifest_id_is_order_stable():
    meta = {
        "contract_hash": "abc",
        "protocol_id": "ssp_test",
        "teachers": ["spaq", "ava"],
        "preprocessing": {"fingerprint": "fp1"},
    }
    rows = _sample_rows(5)
    reversed_rows = list(reversed(rows))
    assert compute_manifest_id(meta=meta, rows=rows) == compute_manifest_id(
        meta=meta, rows=reversed_rows
    )


def test_manifest_rejects_checksum_or_protocol_mismatch():
    meta = {"protocol_id": "ssp_a", "contract_hash": "c1", "checksum": "deadbeef"}
    with pytest.raises(ValueError, match="protocol_id"):
        validate_manifest_against_protocol(meta, expected_protocol_id="ssp_other")
    with pytest.raises(ValueError, match="checksum"):
        validate_manifest_against_protocol(meta, expected_checksum="cafebabe")
    with pytest.raises(ValueError, match="contract_hash"):
        validate_manifest_against_protocol(meta, expected_contract_hash="other")


def test_composite_replay_matches_frozen_config():
    scores = {
        "liqe": 0.7,
        "spaq": 0.5,
        "topiq": 0.6,
        "arniqa": 0.55,
        "ava": 0.4,
    }
    a = compute_composites_frozen(
        scores, fusion=DEFAULT_COMPOSITE_WEIGHTS, anchors=DEFAULT_PERCENTILE_ANCHORS
    )
    b = compute_composites_frozen(
        scores, fusion=DEFAULT_COMPOSITE_WEIGHTS, anchors=DEFAULT_PERCENTILE_ANCHORS
    )
    assert a == b
    assert set(a) == {"general", "technical", "aesthetic"}
    for v in a.values():
        assert 0.0 <= v <= 1.0


def test_unknown_label_provenance_is_not_human():
    prov = classify_label_provenance(rating=4, pick_status=1, cull_decision="keep")
    assert prov["rating"] == PROVENANCE_UNKNOWN
    assert prov["pick_status"] == PROVENANCE_UNKNOWN
    assert PROVENANCE_HUMAN not in prov.values()

    human = classify_label_provenance(
        rating=4, rating_source="human", pick_status=1, pick_source="user"
    )
    assert human["rating"] == PROVENANCE_HUMAN
    assert human["pick_status"] == PROVENANCE_HUMAN

    auto = classify_label_provenance(rating=3, rating_source="pipeline")
    assert auto["rating"] == PROVENANCE_AUTOMATIC
