"""Unit tests for CLIP accessibility compose and ranking helpers."""

from unittest.mock import patch

import numpy as np

from modules import clip_accessibility


def test_compose_alt_text_joins_top_prompts():
    ranked = [
        ("a photo of a red barn", 0.9),
        ("a rural landscape at sunset", 0.8),
        ("a photo of a red barn", 0.7),
    ]
    text = clip_accessibility.compose_alt_text(ranked, top_k=2, max_chars=500)
    assert "Red barn" in text or "red barn" in text.lower()
    assert text.endswith(".")


def test_compose_alt_text_truncates_to_max_chars():
    ranked = [("a photograph of " + "word " * 80, 1.0)]
    text = clip_accessibility.compose_alt_text(ranked, top_k=1, max_chars=40)
    assert len(text) <= 40


def test_compose_extended_description_includes_keywords():
    ranked = [
        ("a close-up photograph of a dog", 0.9),
        ("a pet in a park", 0.5),
    ]
    text = clip_accessibility.compose_extended_description(
        ranked,
        keywords=["dog", "park"],
        top_k=2,
        max_chars=1000,
    )
    assert "dog" in text.lower() or "Dog" in text
    assert "Keywords:" in text


def test_rank_prompts_by_embedding_orders_by_similarity():
    prompts = ["alpha", "beta", "gamma"]
    text_mat = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    image_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    with patch.object(clip_accessibility, "_batch_clip_text_embeddings", return_value=text_mat):
        ranked = clip_accessibility._rank_prompts_by_embedding(image_emb, prompts)

    assert ranked[0][0] == "alpha"
    assert ranked[0][1] > ranked[1][1]


def test_describe_from_clip_uses_stored_embedding(monkeypatch):
    image_emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    ranked = [("a photo of mountains", 0.95)]

    monkeypatch.setattr(clip_accessibility, "load_prompt_bank", lambda path=None: ["a photo of mountains"])
    monkeypatch.setattr(clip_accessibility, "get_stored_clip_embedding", lambda image_id: image_emb)
    monkeypatch.setattr(clip_accessibility, "_rank_prompts_by_embedding", lambda emb, prompts: ranked)

    result = clip_accessibility.describe_from_clip(image_id=42, overwrite=True)
    assert result["alt_text"]
    assert result["extended_description"]
    assert result["top_prompts"][0]["prompt"] == "a photo of mountains"


def test_describe_from_clip_no_prompts_returns_error():
    with patch.object(clip_accessibility, "load_prompt_bank", return_value=[]):
        result = clip_accessibility.describe_from_clip(image_id=1, overwrite=True)
    assert result.get("error")


def test_clean_prompt_text_strips_photo_prefix():
    assert clip_accessibility._clean_prompt_text("a photo of a cat") == "A cat"
