"""Unit tests for scripts/db/backfill_single_species.py (no DB / no ML).

Covers the pure CSV-reconciliation helper that keeps the legacy
``images.keywords`` string in sync when losing ``species:`` rows are dropped.
"""

from scripts.db.backfill_single_species import _csv_without


def test_csv_without_removes_losers_case_insensitive():
    csv = "birds,nature,species:Great Egret,species:Snowy Egret"
    out = _csv_without(csv, {"species:snowy egret"})
    assert out == "birds,nature,species:Great Egret"


def test_csv_without_preserves_order_and_non_species():
    csv = "nature,forest,wildlife,animals,birds,species:Snowy Egret,species:Great Egret"
    out = _csv_without(csv, {"species:snowy egret"})
    assert out == "nature,forest,wildlife,animals,birds,species:Great Egret"


def test_csv_without_handles_spaces_and_blanks():
    csv = "birds, species:Great Egret , species:Snowy Egret"
    out = _csv_without(csv, {"species:snowy egret"})
    assert out == "birds,species:Great Egret"


def test_csv_without_none_and_empty_passthrough():
    assert _csv_without(None, {"species:x"}) is None
    assert _csv_without("", {"species:x"}) == ""


def test_csv_without_noop_when_no_losers():
    csv = "birds,species:Great Egret"
    assert _csv_without(csv, set()) == "birds,species:Great Egret"
