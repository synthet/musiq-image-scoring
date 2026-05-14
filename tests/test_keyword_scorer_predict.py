"""Unit tests for KeywordScorer.predict ranking and threshold behavior."""

from unittest.mock import MagicMock

import pytest

torch = pytest.importorskip("torch")


@pytest.mark.ml
def test_predict_drops_keywords_below_threshold(monkeypatch):
    from modules.tagging import KeywordScorer

    scorer = KeywordScorer.__new__(KeywordScorer)
    scorer.device = "cpu"
    scorer.model_name = "stub"
    scorer.model = None
    scorer.processor = None
    scorer.last_image_embedding = None
    scorer.load_model = lambda: None

    mock_outputs = MagicMock()
    # One dominant class after softmax; others stay below 0.5
    mock_outputs.logits_per_image = torch.tensor([[8.0, 0.0, 0.0, 0.0]])
    scorer.model = MagicMock(return_value=mock_outputs)
    scorer.processor = MagicMock(
        return_value={"pixel_values": torch.zeros(1, 3, 2, 2), "input_ids": torch.ones(1, 8, dtype=torch.long)}
    )

    monkeypatch.setattr("modules.thumbnails.open_image_for_ml", lambda _path: MagicMock())
    monkeypatch.setattr(
        "modules.embeddings_extract.extract_clip_image_features_from_outputs",
        lambda _outputs: None,
    )

    kws = ["a", "b", "c", "d"]
    out = scorer.predict("/fake.jpg", keywords=kws, threshold=0.5, top_k=5)
    assert out == ["a"]


@pytest.mark.ml
def test_predict_top_k_after_threshold(monkeypatch):
    from modules.tagging import KeywordScorer

    scorer = KeywordScorer.__new__(KeywordScorer)
    scorer.device = "cpu"
    scorer.model_name = "stub"
    scorer.model = None
    scorer.processor = None
    scorer.last_image_embedding = None
    scorer.load_model = lambda: None

    mock_outputs = MagicMock()
    mock_outputs.logits_per_image = torch.tensor([[2.0, 1.5, 1.0]])
    scorer.model = MagicMock(return_value=mock_outputs)
    scorer.processor = MagicMock(
        return_value={"pixel_values": torch.zeros(1, 3, 2, 2), "input_ids": torch.ones(1, 8, dtype=torch.long)}
    )

    monkeypatch.setattr("modules.thumbnails.open_image_for_ml", lambda _path: MagicMock())
    monkeypatch.setattr(
        "modules.embeddings_extract.extract_clip_image_features_from_outputs",
        lambda _outputs: None,
    )

    kws = ["x", "y", "z"]
    probs = torch.tensor([[2.0, 1.5, 1.0]]).softmax(dim=1)[0].tolist()
    min_p = min(probs)
    out = scorer.predict("/fake.jpg", keywords=kws, threshold=min_p - 1e-6, top_k=2)
    assert len(out) == 2
    assert set(out).issubset(set(kws))
