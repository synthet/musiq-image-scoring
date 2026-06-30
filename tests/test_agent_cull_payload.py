"""Unit tests for agent cull payload thumbnail downscaling (issue #256)."""

from __future__ import annotations

import os

import pytest

from modules.agent_cull import payload
from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.discovery import ReviewUnit

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _write_image(path: str, size: tuple[int, int]) -> str:
    Image.new("RGB", size, color=(120, 30, 200)).save(path, "JPEG", quality=90)
    return path


def test_prepare_thumbnail_passthrough_when_small(tmp_path):
    src = _write_image(str(tmp_path / "small.jpg"), (300, 200))
    out_path, w, h, downscaled = payload._prepare_thumbnail(src, max_edge=512)
    assert out_path == src
    assert (w, h) == (300, 200)
    assert downscaled is False


def test_prepare_thumbnail_downscales_when_large(tmp_path, monkeypatch):
    # Route the cache dir into tmp so the test never touches the repo thumbnails/
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        payload,
        "_downscale_cache_dir",
        lambda max_edge: str(cache_root / str(max_edge)),
    )
    src = _write_image(str(tmp_path / "big.jpg"), (2000, 1000))

    out_path, w, h, downscaled = payload._prepare_thumbnail(src, max_edge=512)

    assert downscaled is True
    assert out_path != src
    assert os.path.isfile(out_path)
    assert max(w, h) == 512  # longest edge clamped, aspect preserved
    assert (w, h) == (512, 256)

    # Second call hits the cache (no re-encode), returns the same path.
    out_path2, w2, h2, downscaled2 = payload._prepare_thumbnail(src, max_edge=512)
    assert out_path2 == out_path
    assert (w2, h2) == (w, h)
    assert downscaled2 is True


def test_prepare_thumbnail_disabled_when_max_edge_non_positive(tmp_path):
    src = _write_image(str(tmp_path / "img.jpg"), (2000, 1000))
    out_path, w, h, downscaled = payload._prepare_thumbnail(src, max_edge=0)
    assert out_path == src
    assert (w, h, downscaled) == (None, None, False)


def test_prepare_thumbnail_fail_safe_when_pillow_unavailable(tmp_path, monkeypatch):
    src = _write_image(str(tmp_path / "img.jpg"), (2000, 1000))
    monkeypatch.setattr(payload, "Image", None)
    out_path, w, h, downscaled = payload._prepare_thumbnail(src, max_edge=512)
    assert out_path == src
    assert (w, h, downscaled) == (None, None, False)


def test_prepare_thumbnail_fail_safe_on_unreadable_source(tmp_path):
    bad = str(tmp_path / "not-an-image.jpg")
    with open(bad, "wb") as fh:
        fh.write(b"not really a jpeg")
    out_path, w, h, downscaled = payload._prepare_thumbnail(bad, max_edge=512)
    assert out_path == bad
    assert (w, h, downscaled) == (None, None, False)


def _unit(image_ids: tuple[int, ...], picked, rejected) -> ReviewUnit:
    return ReviewUnit(
        stack_id=1,
        sub_stack_id=None,
        review_unit_key="stack:1",
        image_ids=image_ids,
        picked_ids=tuple(picked),
        rejected_ids=tuple(rejected),
        neutral_ids=(),
        usable_ids=image_ids,
        hierarchy_tier="flat_root",
    )


def test_build_review_packet_manifest_has_downscale_fields(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    monkeypatch.setattr(
        payload,
        "_downscale_cache_dir",
        lambda max_edge: str(cache_root / str(max_edge)),
    )
    thumb = _write_image(str(tmp_path / "thumb.jpg"), (2048, 1536))
    rows = {
        10: {"id": 10, "pick_status": 1, "thumbnail_path": thumb, "score_general": 0.8},
        11: {"id": 11, "pick_status": -1, "thumbnail_path": thumb, "score_general": 0.4},
    }
    cfg = AgentCullConfig()  # include_thumbnails True, max_thumbnail_edge_px 512 by default

    packet = payload.build_review_packet(_unit((10, 11), [10], [11]), rows, cfg)

    manifest = packet["thumbnail_manifest"]
    assert len(manifest) == 2
    for entry in manifest:
        assert entry["max_edge_px"] == 512
        assert entry["downscaled"] is True
        assert entry["width"] == 512
        assert entry["height"] == 384
        assert entry["source_path"] == thumb
        assert entry["path"] != thumb
        assert os.path.isfile(entry["path"])


def test_build_review_packet_no_downscale_passthrough(tmp_path):
    thumb = _write_image(str(tmp_path / "thumb.jpg"), (400, 300))
    rows = {
        10: {"id": 10, "pick_status": 1, "thumbnail_path": thumb},
        11: {"id": 11, "pick_status": -1, "thumbnail_path": thumb},
    }
    cfg = AgentCullConfig()

    packet = payload.build_review_packet(_unit((10, 11), [10], [11]), rows, cfg)

    for entry in packet["thumbnail_manifest"]:
        assert entry["downscaled"] is False
        assert entry["path"] == thumb
        assert "source_path" not in entry
        assert (entry["width"], entry["height"]) == (400, 300)


def test_build_review_packet_resolves_host_db_thumbnail_path(tmp_path, monkeypatch):
    from modules import thumbnails

    thumb_name = "abcdef0123456789abcdef0123456789.jpg"
    thumb_dir = tmp_path / "thumbnails" / "ab"
    thumb_dir.mkdir(parents=True)
    thumb_file = thumb_dir / thumb_name
    _write_image(str(thumb_file), (400, 300))
    monkeypatch.setattr(thumbnails, "THUMB_DIR", str(tmp_path / "thumbnails"))

    host_path = f"/mnt/d/Projects/image-scoring-backend/thumbnails/ab/{thumb_name}"
    rows = {
        10: {"id": 10, "pick_status": 1, "thumbnail_path": host_path, "score_general": 0.8},
        11: {"id": 11, "pick_status": -1, "thumbnail_path": host_path, "score_general": 0.4},
    }
    cfg = AgentCullConfig()

    packet = payload.build_review_packet(_unit((10, 11), [10], [11]), rows, cfg)

    assert len(packet["thumbnail_manifest"]) == 2
    for entry in packet["thumbnail_manifest"]:
        assert entry["path"] == str(thumb_file)
        assert os.path.isfile(entry["path"])


def test_enrich_unit_rows_adds_model_scores(monkeypatch):
    rows = {
        10: {"id": 10, "pick_status": 1},
        11: {"id": 11, "pick_status": -1},
    }
    cfg = AgentCullConfig()

    def _fake_batch(ids, *, include_shadow=False):
        return {
            10: {"clip_quality_v0": {"normalized": 0.61, "raw_score": 0.61, "status": "success"}},
            11: {"clip_quality_v0": {"normalized": 0.55, "raw_score": 0.55, "status": "success"}},
        }

    monkeypatch.setattr(payload, "get_batch_image_model_scores", _fake_batch)

    warnings = payload.enrich_unit_rows(rows, cfg)

    assert rows[10]["model_scores"]["clip_quality_v0"]["normalized"] == 0.61
    assert not warnings

    packet = payload.build_review_packet(_unit((10, 11), [10], [11]), rows, cfg)
    img10 = next(i for i in packet["images"] if i["id"] == 10)
    assert img10["scores"]["clip_quality_v0"] == 0.61
    assert img10["model_scores"]["clip_quality_v0"]["normalized"] == 0.61


def test_build_review_packet_surfaces_technical_and_exif():
    # blur/exif columns now loaded by discovery_db.load_unit_rows flow through.
    rows = {
        10: {
            "id": 10, "pick_status": 1, "score_general": 0.8,
            "blur": 0.12, "overexposed": 0.0, "underexposed": 0.03,
            "make": "NIKON", "model": "Z9", "lens_model": "200mm",
            "orientation": 1,
        },
        11: {"id": 11, "pick_status": -1, "score_general": 0.4},
    }
    packet = payload.build_review_packet(_unit((10, 11), [10], [11]), rows, AgentCullConfig())
    img10 = next(i for i in packet["images"] if i["id"] == 10)
    assert img10["technical"] == {"blur": 0.12, "overexposed": 0.0, "underexposed": 0.03}
    assert img10["exif"]["make"] == "NIKON"
    assert img10["exif"]["lens_model"] == "200mm"
    # Missing columns degrade to null, never raise.
    img11 = next(i for i in packet["images"] if i["id"] == 11)
    assert img11["technical"]["blur"] is None


def test_outlier_z_from_mean_sim_flags_dissimilar_member():
    # image 12 is far less similar to siblings -> high positive outlier z.
    z = payload._outlier_z_from_mean_sim({10: 0.95, 11: 0.94, 12: 0.60})
    assert z[12] > z[10] and z[12] > z[11]
    assert z[12] > 0


def test_outlier_z_from_mean_sim_needs_three_members():
    assert payload._outlier_z_from_mean_sim({10: 0.9, 11: 0.8}) == {}


def test_outlier_z_from_mean_sim_zero_variance():
    assert payload._outlier_z_from_mean_sim({10: 0.9, 11: 0.9, 12: 0.9}) == {10: 0.0, 11: 0.0, 12: 0.0}


def test_enrich_attaches_embedding_outlier_z(monkeypatch):
    rows = {
        10: {"id": 10, "pick_status": 1},
        11: {"id": 11, "pick_status": -1},
        12: {"id": 12, "pick_status": -1},
    }
    cfg = AgentCullConfig()  # block_embedding_outliers True by default
    monkeypatch.setattr(payload, "get_batch_image_model_scores", lambda ids, **k: {})
    monkeypatch.setattr(
        payload, "_fetch_unit_mean_cosine", lambda ids: {10: 0.95, 11: 0.94, 12: 0.60}
    )

    payload.enrich_unit_rows(rows, cfg)

    assert rows[12]["embedding_outlier_z"] > rows[10]["embedding_outlier_z"]
    packet = payload.build_review_packet(_unit((10, 11, 12), [10], [11, 12]), rows, cfg)
    img12 = next(i for i in packet["images"] if i["id"] == 12)
    assert img12["similarity"]["embedding_outlier_z"] == rows[12]["embedding_outlier_z"]


def test_enrich_outlier_skipped_when_gate_disabled(monkeypatch):
    import dataclasses

    rows = {10: {"id": 10}, 11: {"id": 11}, 12: {"id": 12}}
    base = AgentCullConfig()
    cfg = dataclasses.replace(
        base,
        local_gates=dataclasses.replace(base.local_gates, block_embedding_outliers=False),
    )
    monkeypatch.setattr(payload, "get_batch_image_model_scores", lambda ids, **k: {})

    def _boom(ids):  # must not be called when the gate is off
        raise AssertionError("mean cosine fetched despite disabled gate")

    monkeypatch.setattr(payload, "_fetch_unit_mean_cosine", _boom)
    payload.enrich_unit_rows(rows, cfg)
    assert all("embedding_outlier_z" not in r for r in rows.values())
