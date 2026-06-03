"""Mocked SelectionService test for two-level culling path."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("sklearn")

from modules.selection import SelectionConfig, SelectionService


def test_selection_two_level_path_mocked():
    svc = SelectionService()
    cfg = SelectionConfig(two_level_enabled=True)

    e1 = np.array([1.0, 0.0], dtype=np.float32).tobytes()
    e3 = np.array([0.0, 1.0], dtype=np.float32).tobytes()

    mock_images = [
        {"id": 1, "stack_id": 100, "score_general": 0.9, "file_path": "/mock/1.jpg"},
        {"id": 2, "stack_id": 100, "score_general": 0.8, "file_path": "/mock/2.jpg"},
        {"id": 3, "stack_id": 100, "score_general": 0.7, "file_path": "/mock/3.jpg"},
        {"id": 4, "stack_id": 100, "score_general": 0.6, "file_path": "/mock/4.jpg"},
    ]

    def mock_cluster(*args, **kwargs):
        yield

    svc._cluster_engine.cluster_images = mock_cluster

    def emb_for_space(space, ids):
        return {i: e1 if i in (1, 2) else e3 for i in ids}

    created_subs = []

    def capture_subs(data):
        created_subs.extend(data)
        return True, "ok"

    with patch("os.path.exists", return_value=True), \
         patch("modules.utils.convert_path_to_local", return_value="/mock/path"), \
         patch("modules.db.list_folder_paths_under_scope", return_value=["/mock/path"]), \
         patch("modules.db.get_images_by_folder", side_effect=[mock_images, mock_images]), \
         patch("modules.db.get_exif_fields_for_quality_tiebreak", return_value={}), \
         patch("modules.db.clear_sub_stacks_for_folder", return_value=(True, "ok")), \
         patch("modules.db.get_image_embeddings_batch_for_space", side_effect=emb_for_space), \
         patch("modules.db.create_sub_stacks_batch", side_effect=capture_subs), \
         patch("modules.db.batch_update_cull_decisions") as mock_batch, \
         patch("modules.selection.write_selection_metadata", return_value=(True, True)):

        summary = svc.run("/mock/path", cfg=cfg)

    assert summary.status == "completed"
    assert len(created_subs) >= 1
    assert mock_batch.called
    _, kwargs = mock_batch.call_args
    assert kwargs.get("policy_version") == "2.0"
