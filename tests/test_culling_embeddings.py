"""Tests for JIT culling-tower embedding ensure (two-level culling)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from modules.culling_embeddings import (
    EnsureResult,
    collect_stacked_image_ids,
    ensure_embeddings_for_space,
    resolve_embedding_paths,
)


def test_collect_stacked_image_ids_excludes_unstacked_and_singletons():
    by_stack = {
        None: [{"id": 1}, {"id": 2}],
        10: [{"id": 3}],
        20: [{"id": 4}, {"id": 5}, {"id": 6}],
    }
    assert collect_stacked_image_ids(by_stack) == [4, 5, 6]


def test_resolve_embedding_paths_prefers_thumbnail(tmp_path):
    thumb = tmp_path / "t.jpg"
    thumb.write_bytes(b"jpeg")
    rows = [
        {
            "id": 42,
            "file_path": "/photos/raw.nef",
            "thumbnail_path": str(thumb),
            "thumbnail_path_win": None,
        }
    ]
    resolved, n_thumb = resolve_embedding_paths(rows, use_thumbnails=True)
    assert n_thumb == 1
    assert resolved[0][0] == 42
    assert str(thumb) in resolved[0][1] or resolved[0][1].endswith("t.jpg")


def test_ensure_embeddings_no_op_when_all_present():
    with patch("modules.db._get_db_engine", return_value="postgres"), patch(
        "modules.db.get_images_missing_embedding_for_space", return_value=[]
    ), patch("modules.embedding_extractors.generate_and_persist") as gen:
        result = ensure_embeddings_for_space("openclip_l14_laion2b_image", [1, 2, 3])
    gen.assert_not_called()
    assert result == EnsureResult("openclip_l14_laion2b_image", 3, 0, 0, 3)


def test_ensure_embeddings_persists_missing_rows():
    missing = [{"id": 5, "file_path": "/a.jpg", "thumbnail_path": "", "thumbnail_path_win": None}]
    embedder = MagicMock()
    with patch("modules.db._get_db_engine", return_value="postgres"), patch(
        "modules.db.get_images_missing_embedding_for_space", return_value=missing
    ), patch(
        "modules.db.get_image_embeddings_batch_for_space", return_value={5: b"\x00" * 4}
    ), patch(
        "modules.embedding_extractors.CullingEmbedder", return_value=embedder
    ), patch(
        "modules.embedding_extractors.generate_and_persist", return_value=1
    ) as gen, patch(
        "modules.culling_embeddings.resolve_embedding_paths",
        return_value=([(5, "/local/a.jpg")], 0),
    ):
        result = ensure_embeddings_for_space("openclip_l14_laion2b_image", [5, 6])

    gen.assert_called_once()
    embedder.unload.assert_called_once()
    assert result.missing_before == 1
    assert result.persisted == 1
    assert result.covered_after == 1


def test_ensure_embeddings_skips_unsupported_space():
    with patch("modules.embedding_extractors.generate_and_persist") as gen:
        result = ensure_embeddings_for_space("mobilenet_v2_imagenet_gap", [1])
    gen.assert_not_called()
    assert result.persisted == 0


def test_selection_calls_ensure_when_two_level_enabled():
    pytest.importorskip("sklearn")
    from modules.selection import SelectionConfig, SelectionService

    svc = SelectionService()
    cfg = SelectionConfig(two_level_enabled=True)
    mock_images = [
        {"id": 1, "stack_id": 100, "score_general": 0.9, "file_path": "/mock/1.jpg"},
        {"id": 2, "stack_id": 100, "score_general": 0.8, "file_path": "/mock/2.jpg"},
    ]

    def mock_cluster(*args, **kwargs):
        yield

    svc._cluster_engine.cluster_images = mock_cluster

    with patch("os.path.exists", return_value=True), \
         patch("modules.utils.convert_path_to_local", return_value="/mock/path"), \
         patch("modules.db.list_folder_paths_under_scope", return_value=["/mock/path"]), \
         patch("modules.db.get_images_by_folder", side_effect=[mock_images, mock_images]), \
         patch("modules.db.get_exif_fields_for_quality_tiebreak", return_value={}), \
         patch("modules.db.clear_sub_stacks_for_folder", return_value=(True, "ok")), \
         patch("modules.selection.ensure_embeddings_for_space") as ensure_mock, \
         patch("modules.db.get_image_embeddings_batch_for_space", return_value={}), \
         patch("modules.db.create_sub_stacks_batch", return_value=(True, "ok")), \
         patch("modules.db.batch_update_cull_decisions"), \
         patch("modules.selection.write_selection_metadata", return_value=(True, True)):
        ensure_mock.return_value = EnsureResult("openclip_l14_laion2b_image", 2, 2, 2, 2)
        svc.run("/mock/path", cfg=cfg)

    ensure_mock.assert_called_once()
    args, _kwargs = ensure_mock.call_args
    assert args[0] == "openclip_l14_laion2b_image"
    assert sorted(args[1]) == [1, 2]


def test_selection_skips_ensure_when_two_level_disabled():
    pytest.importorskip("sklearn")
    from modules.selection import SelectionConfig, SelectionService

    svc = SelectionService()
    cfg = SelectionConfig(two_level_enabled=False)
    mock_images = [
        {"id": 1, "stack_id": 100, "score_general": 0.9, "file_path": "/mock/1.jpg"},
        {"id": 2, "stack_id": 100, "score_general": 0.8, "file_path": "/mock/2.jpg"},
    ]

    def mock_cluster(*args, **kwargs):
        yield

    svc._cluster_engine.cluster_images = mock_cluster

    with patch("os.path.exists", return_value=True), \
         patch("modules.utils.convert_path_to_local", return_value="/mock/path"), \
         patch("modules.db.list_folder_paths_under_scope", return_value=["/mock/path"]), \
         patch("modules.db.get_images_by_folder", side_effect=[mock_images, mock_images]), \
         patch("modules.db.get_exif_fields_for_quality_tiebreak", return_value={}), \
         patch("modules.selection.ensure_embeddings_for_space") as ensure_mock, \
         patch("modules.db.get_image_embeddings_batch", return_value={}), \
         patch("modules.db.batch_update_cull_decisions"), \
         patch("modules.selection.write_selection_metadata", return_value=(True, True)):
        svc.run("/mock/path", cfg=cfg)

    ensure_mock.assert_not_called()
