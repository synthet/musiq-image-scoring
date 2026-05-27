"""Unit tests for the multi-space embedding plumbing (no live DB required).

Covers:

* Pure extractors in ``modules.embeddings_extract`` (L2-normalization, shape
  handling, defensive Nones).
* ``modules.db._pg_embedding_table_for_dim`` dim→table mapping.
* ``modules.db.update_image_embeddings_batch_for_space`` validates dim against
  ``SPACE_DIMS`` and no-ops when the DB engine is not Postgres.
"""

from __future__ import annotations

import numpy as np
import pytest


def test_l2_normalize_unit_vector_norm_is_one():
    from modules.embeddings_extract import l2_normalize

    vec = np.array([3.0, 4.0], dtype=np.float32)
    out = l2_normalize(vec)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-6


def test_l2_normalize_zero_vector_stays_zero():
    from modules.embeddings_extract import l2_normalize

    vec = np.zeros(8, dtype=np.float32)
    out = l2_normalize(vec)
    assert np.allclose(out, vec)


def test_extract_clip_image_features_from_outputs_reshapes_and_normalizes():
    from modules.embeddings_extract import extract_clip_image_features_from_outputs

    class _FakeCLIPOutputs:
        def __init__(self, embeds):
            self.image_embeds = embeds

    arr = np.arange(512, dtype=np.float32).reshape(1, 512)
    out = extract_clip_image_features_from_outputs(_FakeCLIPOutputs(arr))
    assert out is not None
    assert out.shape == (512,)
    assert out.dtype == np.float32
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-5


def test_extract_clip_image_features_handles_missing_attr():
    from modules.embeddings_extract import extract_clip_image_features_from_outputs

    class _NoEmbeds:
        pass

    assert extract_clip_image_features_from_outputs(_NoEmbeds()) is None


def test_extract_bioclip_image_features_normalizes_raw_tensor_like():
    from modules.embeddings_extract import extract_bioclip_image_features

    arr = np.array([[0.0, 3.0, 4.0] + [0.0] * 765], dtype=np.float32)
    out = extract_bioclip_image_features(arr)
    assert out is not None
    assert out.shape == (768,)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-5


def test_extract_blip_image_features_with_mocked_vision_model():
    from modules.embeddings_extract import extract_blip_image_features

    class _PoolerOut:
        def __init__(self, tensor):
            self.pooler_output = tensor

    class _VisionModel:
        def __call__(self, pixel_values):
            assert pixel_values is pixel_values_sentinel  # identity check
            return _PoolerOut(np.arange(768, dtype=np.float32).reshape(1, 768))

    class _Blip:
        def __init__(self):
            self.vision_model = _VisionModel()

    pixel_values_sentinel = object()
    out = extract_blip_image_features(_Blip(), pixel_values_sentinel)
    assert out is not None
    assert out.shape == (768,)
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-5


def test_pg_embedding_table_for_dim_resolves_known_dims():
    from modules import db

    assert db._pg_embedding_table_for_dim(1280) == "image_embeddings"
    assert db._pg_embedding_table_for_dim(512) == "image_embeddings_512"
    assert db._pg_embedding_table_for_dim(768) == "image_embeddings_768"


def test_pg_embedding_table_for_dim_rejects_unknown_dim():
    from modules import db

    with pytest.raises(ValueError):
        db._pg_embedding_table_for_dim(2048)


def test_update_image_embeddings_batch_for_space_noop_on_empty_rows():
    from modules import db

    assert db.update_image_embeddings_batch_for_space("clip_vit_b32_image", []) == 0


def test_update_image_embeddings_batch_for_space_noop_when_engine_not_postgres(monkeypatch):
    from modules import db

    monkeypatch.setattr(db, "_get_db_engine", lambda: "firebird")
    vec = np.random.rand(512).astype(np.float32)
    # Non-Postgres engines return 0 and must not raise.
    assert db.update_image_embeddings_batch_for_space(
        "clip_vit_b32_image", [(1, vec, None)]
    ) == 0


def test_update_image_embeddings_batch_for_space_rejects_unknown_space(monkeypatch):
    from modules import db

    monkeypatch.setattr(db, "_get_db_engine", lambda: "postgres")
    vec = np.random.rand(512).astype(np.float32)
    # Unknown codes short-circuit with a warning, not an exception.
    assert db.update_image_embeddings_batch_for_space(
        "not_a_real_space", [(1, vec, None)]
    ) == 0


def test_update_image_embeddings_batch_for_space_raises_on_dim_mismatch(monkeypatch):
    """Dim mismatch vs registry raises ValueError before any write."""
    from modules import db
    from modules import embedding_spaces

    monkeypatch.setattr(db, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(embedding_spaces, "get_embedding_space_id", lambda code: 42)

    # Passing a 256-d vector for a 512-d space must fail loudly and never
    # open a DB connection (would raise psycopg2 errors in test env without Postgres).
    bad = np.random.rand(256).astype(np.float32)
    with pytest.raises(ValueError):
        db.update_image_embeddings_batch_for_space(
            "clip_vit_b32_image", [(1, bad, None)]
        )


def test_tagging_runner_persist_embeddings_gated_by_flags(monkeypatch):
    """TaggingRunner._persist_tagging_embeddings only flushes what flags allow."""
    from modules import tagging

    calls: list[tuple[str, int, int]] = []

    def fake_upsert(space_code, rows):
        for image_id, vec, _mv in rows:
            calls.append((space_code, int(image_id), int(np.asarray(vec).shape[0])))
        return len(rows)

    class _FakeScorer:
        model_name = "openai/clip-vit-base-patch32"
        last_image_embedding = np.random.rand(512).astype(np.float32)

    class _FakeCaptioner:
        model_name = "Salesforce/blip-image-captioning-base"
        last_image_embedding = np.random.rand(768).astype(np.float32)

    runner = tagging.TaggingRunner()
    runner.scorer = _FakeScorer()
    runner.captioner = _FakeCaptioner()
    monkeypatch.setattr(
        tagging.db, "update_image_embeddings_batch_for_space", fake_upsert, raising=True
    )

    runner._persist_tagging_embeddings(image_id=7, persist_clip=True, persist_blip=False)
    assert calls == [("clip_vit_b32_image", 7, 512)]

    calls.clear()
    runner._persist_tagging_embeddings(image_id=8, persist_clip=False, persist_blip=True)
    assert calls == [("blip_vit_b16_image", 8, 768)]
