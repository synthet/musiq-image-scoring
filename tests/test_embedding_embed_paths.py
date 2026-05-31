"""Regression tests for CullingEmbedder.embed_paths max_load_px downscale (OOM fix)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from modules import embedding_extractors as ee


@pytest.fixture
def embedder(monkeypatch):
    spec = MagicMock(
        code="openclip_vit_l14",
        dim=8,
        loader="timm",
        model_name="test",
        pretrained=None,
    )
    monkeypatch.setattr(ee, "get_spec", lambda _code: spec)
    return ee.CullingEmbedder("openclip_vit_l14")


def test_embed_paths_downscales_before_embed(monkeypatch, embedder):
    """Large decoded previews must be capped before batching (7.28.0 OOM fix)."""
    longest_sides: list[int] = []

    def fake_embed(pils, batch_size=32):
        for im in pils:
            longest_sides.append(max(im.width, im.height))
        return np.zeros((len(pils), 8), dtype=np.float32)

    monkeypatch.setattr(embedder, "embed", fake_embed)

    def fake_open(_path):
        return Image.new("RGB", (4000, 3000))

    with patch("modules.thumbnails.open_image_for_ml", fake_open):
        _vectors, ok_paths = embedder.embed_paths(
            ["/photos/sample.nef"],
            load_workers=1,
            max_load_px=1024,
        )

    assert ok_paths == ["/photos/sample.nef"]
    assert len(longest_sides) == 1
    assert longest_sides[0] <= 1024


def test_embed_paths_max_load_px_zero_skips_downscale(monkeypatch, embedder):
    longest_sides: list[int] = []

    def fake_embed(pils, batch_size=32):
        for im in pils:
            longest_sides.append(max(im.width, im.height))
        return np.zeros((len(pils), 8), dtype=np.float32)

    monkeypatch.setattr(embedder, "embed", fake_embed)

    def fake_open(_path):
        return Image.new("RGB", (2000, 1500))

    with patch("modules.thumbnails.open_image_for_ml", fake_open):
        embedder.embed_paths(["/x.jpg"], load_workers=1, max_load_px=0)

    assert longest_sides == [2000]


def test_embed_paths_skips_unreadable_paths(monkeypatch, embedder):
    captured: list = []

    def fake_embed(pils, batch_size=32):
        captured.extend(pils)
        return np.zeros((len(pils), 8), dtype=np.float32)

    monkeypatch.setattr(embedder, "embed", fake_embed)

    def fake_open(path):
        if path == "/bad.jpg":
            raise OSError("cannot open")
        return Image.new("RGB", (100, 100))

    with patch("modules.thumbnails.open_image_for_ml", fake_open):
        _vectors, ok_paths = embedder.embed_paths(
            ["/bad.jpg", "/ok.jpg"],
            load_workers=1,
        )

    assert ok_paths == ["/ok.jpg"]
    assert len(captured) == 1
