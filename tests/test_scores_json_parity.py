"""Tests for scores_json parity audit and Gradio legacy timing helper."""

import json

import pytest

from modules import db_legacy as dbl
from modules.ui import common


def test_legacy_model_times_from_details_empty():
    assert common.legacy_model_times_from_details({}) == {}


def test_legacy_model_times_from_details_parses_summary():
    blob = {
        "summary": {
            "performance": {
                "model_times": {"spaq": 0.42, "liqe": 1.1},
            }
        }
    }
    details = {"scores_json": json.dumps(blob)}
    assert common.legacy_model_times_from_details(details) == {"spaq": 0.42, "liqe": 1.1}


def test_get_scores_json_parity_report_postgres(monkeypatch):
    class FakeConn:
        def query_one(self, sql, params=None):
            if "NOT (EXISTS" in sql:
                return {"c": 2}
            if "scores_json IS NULL" in sql:
                return {"c": 5}
            if "scores_json IS NOT NULL" in sql and "EXISTS" in sql:
                return {"c": 10}
            if "COUNT(*)" in sql:
                return {"c": 12}
            return {"c": 0}

    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    dbl.reset_postgres_scores_json_column_cache()
    monkeypatch.setattr(dbl, "_postgres_images_has_scores_json_column", lambda: True)
    monkeypatch.setattr(dbl, "get_connector", lambda: FakeConn())
    report = dbl.get_scores_json_parity_report()
    assert report["legacy_scores_json_rows"] == 12
    assert report["column_only"] == 2
    assert "error" not in report


def test_get_scores_json_parity_report_firebird_empty(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "firebird")
    assert dbl.get_scores_json_parity_report() == {}


def test_backfill_image_model_scores_from_scores_json(monkeypatch):
    written = []

    class FakeConn:
        def query(self, sql, params=None):
            return [
                {
                    "id": 99,
                    "scores_json": json.dumps(
                        {
                            "models": {
                                "spaq": {
                                    "score": 0.8,
                                    "normalized_score": 0.75,
                                    "status": "success",
                                }
                            }
                        }
                    ),
                    "model_version": "1.0.0",
                }
            ]

    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "get_connector", lambda: FakeConn())

    def _capture_write(image_id, result, model_version):
        written.append((image_id, result, model_version))

    monkeypatch.setattr(dbl, "_write_image_model_scores", _capture_write)
    n = dbl.backfill_image_model_scores_from_scores_json()
    assert n == 1
    assert written[0][0] == 99
    assert "spaq" in written[0][1]["models"]
