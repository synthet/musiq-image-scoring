"""Tests for GET /api/images/{id} detail payload enrichments."""

import json
from unittest.mock import MagicMock, patch

import pytest

from modules.api import _image_detail_payload, _parse_json_object_column


class TestParseJsonObjectColumn:
    def test_parses_string(self):
        assert _parse_json_object_column('{"a": 1}') == {"a": 1}

    def test_returns_dict_unchanged(self):
        assert _parse_json_object_column({"b": 2}) == {"b": 2}

    def test_invalid_returns_none(self):
        assert _parse_json_object_column("not-json") is None
        assert _parse_json_object_column("") is None
        assert _parse_json_object_column(None) is None


@pytest.mark.parametrize(
    "metadata,scores_json,expect_indexing,expect_scores",
    [
        ('{"indexing_hash_mode":"preview"}', '{"image_path":"/x"}', True, True),
        ("not-json", "also-bad", False, False),
    ],
)
def test_image_detail_payload_enrichments(metadata, scores_json, expect_indexing, expect_scores):
    row = {
        "id": 42,
        "file_path": "/p.jpg",
        "file_name": "p.jpg",
        "metadata": metadata,
        "scores_json": scores_json,
    }

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = row
    mock_conn.cursor.return_value = mock_cursor

    emb_map = {42: {"mobilenet_v2_imagenet_gap": True, "clip_vit_b32_image": False}}

    with (
        patch("modules.api.db.get_db", return_value=mock_conn),
        patch("modules.api.db.get_all_paths", return_value=[]),
        patch("modules.api.db.get_resolved_path", return_value="/p.jpg"),
        patch("modules.api.db.get_image_phase_statuses", return_value={}),
        patch("modules.api.db.get_image_technical_failure", return_value=None),
        patch("modules.api.db.get_batch_image_embedding_presence", return_value=emb_map),
        patch("modules.api.db.get_image_model_scores", return_value={}),
        patch("modules.api._row_to_dict", side_effect=lambda r, **kw: dict(r)),
    ):
        data = _image_detail_payload(42)

    assert data["embeddings_present"] == emb_map[42]
    if expect_indexing:
        assert data["indexing_metadata"] == json.loads(metadata)
    else:
        assert "indexing_metadata" not in data
    if expect_scores:
        assert data["scores_json_parsed"] == json.loads(scores_json)
    else:
        assert "scores_json_parsed" not in data
    assert data["metadata"] == metadata
    assert data["scores_json"] == scores_json
