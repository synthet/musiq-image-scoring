"""
Integration tests for Selection workflow.

Requires: database with scored images, clustering dependencies.
Run with: pytest tests/test_selection_integration.py -v
Skip if DB unavailable or no test folder.
"""

import os
import pytest
from modules.selection import SelectionService, SelectionConfig, SelectionSummary
from modules.selection_policy import classify_sorted_ids, band_sizes


def test_selection_service_run_empty_path():
    """Empty path returns error summary."""
    svc = SelectionService()
    cfg = SelectionConfig()
    summary = svc.run("", cfg=cfg)
    assert "error" in summary.status.lower()
    assert summary.total_images == 0


def test_selection_service_run_nonexistent_path():
    """Nonexistent path returns error."""
    svc = SelectionService()
    cfg = SelectionConfig()
    summary = svc.run("/nonexistent/path/xyz", cfg=cfg)
    assert "error" in summary.status.lower() or "not found" in summary.status.lower()
    assert summary.total_images == 0


@pytest.mark.skipif(
    not os.environ.get("RUN_SELECTION_INTEGRATION"),
    reason="Set RUN_SELECTION_INTEGRATION=1 to run (requires DB + scored images)",
)
def test_selection_service_full_run():
    """Full run on folder with scored images (integration)."""
    test_folder = os.environ.get("SELECTION_TEST_FOLDER", "")
    if not test_folder or not os.path.exists(test_folder):
        pytest.skip("SELECTION_TEST_FOLDER not set or folder missing")
    svc = SelectionService()
    cfg = SelectionConfig(force_rescan=False)
    log_lines = []
    def progress(pct, msg):
        log_lines.append((pct, msg))
    summary = svc.run(test_folder, cfg=cfg, progress_cb=progress)
    assert summary.total_images >= 0
    assert summary.picked + summary.rejected + summary.neutral == summary.total_images or summary.total_images == 0


@pytest.mark.skipif(
    not os.environ.get("RUN_SELECTION_INTEGRATION"),
    reason="Set RUN_SELECTION_INTEGRATION=1 to run",
)
def test_selection_idempotency():
    """Running same folder twice produces same decisions."""
    test_folder = os.environ.get("SELECTION_TEST_FOLDER", "")
    if not test_folder or not os.path.exists(test_folder):
        pytest.skip("SELECTION_TEST_FOLDER not set or folder missing")
    svc = SelectionService()
    cfg = SelectionConfig(force_rescan=True)
    s1 = svc.run(test_folder, cfg=cfg)
    s2 = svc.run(test_folder, cfg=SelectionConfig(force_rescan=False))
    assert s1.picked == s2.picked
    assert s1.rejected == s2.rejected
    assert s1.neutral == s2.neutral


from unittest.mock import patch
def test_selection_service_with_diversity_mocked():
    """Test that SelectionService runs successfully when diversity is enabled.
    We mock the DB list of images and groups so it doesn't need a real folder or rescans.
    """
    svc = SelectionService()
    cfg = SelectionConfig(
        diversity_enabled=True,
        diversity_lambda=0.5,
        pick_fraction=0.5,
        reject_fraction=0.0,
        two_level_enabled=False,
        sub_cluster_distance_threshold=None,
    )
    
    import numpy as np
    e1 = np.array([1.0, 0.0], dtype=np.float32).tobytes()
    e2 = np.array([0.9, 0.1], dtype=np.float32).tobytes()
    e3 = np.array([0.0, 1.0], dtype=np.float32).tobytes()
    # e4 is missing

    mock_images = [
        {"id": 1, "stack_id": 100, "score_general": 90, "file_path": "/mock/1.jpg"},
        {"id": 2, "stack_id": 100, "score_general": 80, "file_path": "/mock/2.jpg"},
        {"id": 3, "stack_id": 100, "score_general": 70, "file_path": "/mock/3.jpg"},
        {"id": 4, "stack_id": 100, "score_general": 60, "file_path": "/mock/4.jpg"},
    ]

    def mock_cluster(*args, **kwargs):
        yield

    svc._cluster_engine.cluster_images = mock_cluster

    with patch('os.path.exists', return_value=True), \
         patch('modules.utils.convert_path_to_local', return_value='/mock/path'), \
         patch('modules.db.list_folder_paths_under_scope', return_value=['/mock/path']), \
         patch('modules.db.get_images_by_folder', side_effect=[mock_images, mock_images]), \
         patch('modules.db.get_exif_fields_for_quality_tiebreak', return_value={}), \
         patch('modules.db.batch_update_cull_decisions'), \
         patch('modules.selection.write_selection_metadata', return_value=(True, True)), \
         patch('modules.db.get_image_embeddings_batch', return_value={1: e1, 2: e2, 3: e3}):

        summary = svc.run("/mock/path", cfg=cfg)

        assert summary.status == "completed"
        assert summary.total_images == 4
        assert summary.total_stacks == 1
        assert summary.picked == 2  # 0.5 fraction of 4
        assert summary.sidecar_written == 4
