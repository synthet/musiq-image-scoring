"""Tests for the bird-crop CSV/TSV exporters.

Focused on ``export_focus_arm_b``: it reads a nested key that does not match its
own function name (``arm_b_rule_proposal``), and it must refuse to emit a row
when the rule was never scored. Both are silent-failure shapes — a wrong key or
a missing guard produces an empty tables directory, not an error.
"""

from __future__ import annotations

import csv

import pytest

from scripts.research.bird_crop import export_results


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(export_results, "OUT_DIR", tmp_path / "tables")
    return tmp_path / "tables"


def _payload(vs_labels: dict, *, available: bool = True) -> dict:
    return {
        "config": {"image_ids_file": "reports/bird-crop/study_image_ids.txt"},
        "arm_b_rule_proposal": {
            "available": available,
            "rule": "flag when crop laplacian_variance <= p10 AND the AF centre falls outside the bird box",
            "threshold_laplacian_variance_p10": 12.5,
            "n_with_af": 216,
            "flag_rate": 0.0463,
            "vs_labels": vs_labels,
        },
    }


_SCORED = {
    "available": True,
    "ground_truth_kind": "agent-derived",
    "positive_class": "reject",
    "n_eligible": 216,
    "n_flagged": 10,
    "base_reject_rate": 0.3009,
    "true_positives": 6,
    "false_positives": 4,
    "false_negatives": 59,
    "precision_vs_reject": 0.6,
    "recall_vs_reject": 0.0923,
    "precision_lift_vs_base": 1.9942,
}


def _read_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_exports_the_scored_rule(out_dir):
    path = export_results.export_focus_arm_b(_payload(_SCORED), tsv=False)

    assert path is not None
    rows = _read_rows(path)
    assert len(rows) == 1
    assert rows[0]["precision_vs_reject"] == "0.6"
    assert rows[0]["recall_vs_reject"] == "0.0923"
    assert rows[0]["n_with_af"] == "216"


def test_ground_truth_kind_travels_with_the_numbers(out_dir):
    """An agent-derived precision must never be exportable as bare precision."""
    path = export_results.export_focus_arm_b(_payload(_SCORED), tsv=False)

    rows = _read_rows(path)
    assert rows[0]["ground_truth_kind"] == "agent-derived"


def test_reads_arm_b_rule_proposal_not_arm_b(out_dir):
    """The payload key is ``arm_b_rule_proposal``; ``arm_b`` alone must not work."""
    wrong = {"config": {}, "arm_b": _payload(_SCORED)["arm_b_rule_proposal"]}

    assert export_results.export_focus_arm_b(wrong, tsv=False) is None


def test_unscored_rule_emits_nothing(out_dir):
    """No label overlap means the rule stays unscored — not a row of blanks."""
    unscored = {"available": False, "reason": "label_set.csv missing"}

    assert export_results.export_focus_arm_b(_payload(unscored), tsv=False) is None
    assert not out_dir.exists()


def test_unavailable_arm_emits_nothing(out_dir):
    assert export_results.export_focus_arm_b(
        _payload(_SCORED, available=False), tsv=False
    ) is None


def test_tsv_variant_is_tab_delimited(out_dir):
    path = export_results.export_focus_arm_b(_payload(_SCORED), tsv=True)

    assert path is not None
    assert path.suffix == ".tsv"
    assert "\t" in path.read_text(encoding="utf-8").splitlines()[0]
