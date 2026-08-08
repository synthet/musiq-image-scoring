"""Unit tests for the report's crop-vs-full-frame verdict rules (no DB/GPU).

These encode a judgement — when a measured difference is worth calling a benefit —
so they are pinned by tests rather than left to whoever reads the JSON next.
"""

from __future__ import annotations

from scripts.research.bird_crop.report import (
    COMPLEMENT,
    NO_BENEFIT,
    verdict_caption,
    verdict_embedding,
)


def _require(result):
    """Unwrap a verdict, asserting the rule actually produced one."""
    assert result is not None, "expected a measured verdict, got None"
    return result


def _embedding_summary(cells):
    """cells: {(model, long_edge): {source: pair_margin}} -> eval_summary shape."""
    runs = []
    for (model, long_edge), sources in cells.items():
        for source, margin in sources.items():
            runs.append({
                "model": model,
                "source": source,
                "long_edge": long_edge,
                "pair_margin": {"pair_margin": margin},
            })
    return {"embedding": {"runs": runs}}


def _caption_summary(cells):
    """cells: {long_edge: {source: burst_caption_uniqueness}}."""
    runs = []
    for long_edge, sources in cells.items():
        for source, uniq in sources.items():
            runs.append({
                "model": "blip",
                "source": source,
                "long_edge": long_edge,
                "metrics": {"burst_caption_uniqueness": uniq},
            })
    return {"caption": {"runs": runs}}


# --------------------------------------------------------------------------
# Absent eval must not masquerade as a measured verdict
# --------------------------------------------------------------------------
def test_embedding_verdict_is_none_without_an_eval():
    assert verdict_embedding(None) is None
    assert verdict_embedding({}) is None
    assert verdict_embedding({"embedding": {"runs": []}}) is None


def test_caption_verdict_is_none_without_an_eval():
    assert verdict_caption(None) is None
    assert verdict_caption({"caption": {"runs": []}}) is None


def test_embedding_verdict_is_none_when_no_full_frame_baseline():
    """A crop-only sweep has nothing to compare against."""
    summary = _embedding_summary({("clip_b32", 224): {"crop": 0.30, "croppad25": 0.31}})

    assert verdict_embedding(summary) is None


# --------------------------------------------------------------------------
# Materiality bar
# --------------------------------------------------------------------------
def test_small_gain_is_reported_as_no_benefit():
    """The real sweep landed here: crop wins cells, but by noise."""
    summary = _embedding_summary({
        ("clip_b32", 224): {"file": 0.2044, "crop": 0.1994, "croppad50": 0.2054},
        ("openai", 384): {"file": 0.2693, "crop": 0.2675, "croppad50": 0.2715},
    })

    verdict, detail = _require(verdict_embedding(summary))

    assert verdict == NO_BENEFIT
    assert "materiality bar" in detail


def test_large_gain_is_reported_as_complementary():
    summary = _embedding_summary({("clip_b32", 224): {"file": 0.20, "crop": 0.30}})

    verdict, detail = _require(verdict_embedding(summary))

    assert verdict == COMPLEMENT
    assert "+0.1000" in detail


def test_large_loss_is_reported_as_no_benefit():
    summary = _embedding_summary({("clip_b32", 224): {"file": 0.30, "crop": 0.20}})

    verdict, detail = _require(verdict_embedding(summary))

    assert verdict == NO_BENEFIT
    assert "degrades" in detail


def test_verdict_uses_the_best_crop_source_not_the_first():
    """A tight crop losing must not hide a padded crop winning."""
    summary = _embedding_summary({
        ("clip_b32", 224): {"file": 0.20, "crop": 0.10, "croppad50": 0.30},
    })

    verdict, _ = _require(verdict_embedding(summary))

    assert verdict == COMPLEMENT


def test_crop_win_count_is_reported():
    summary = _embedding_summary({
        ("clip_b32", 224): {"file": 0.20, "crop": 0.21},
        ("clip_b32", 384): {"file": 0.20, "crop": 0.19},
    })

    _, detail = _require(verdict_embedding(summary))

    assert "in 1 of them" in detail


# --------------------------------------------------------------------------
# Caption track
# --------------------------------------------------------------------------
def test_caption_gain_is_reported_as_complementary():
    """The real sweep landed here: +0.105 within-burst uniqueness."""
    summary = _caption_summary({
        224: {"file": 0.41, "crop": 0.52},
        384: {"file": 0.42, "crop": 0.52},
    })

    verdict, detail = _require(verdict_caption(summary))

    assert verdict == COMPLEMENT
    assert "distinguish frames" in detail


def test_caption_noise_is_reported_as_no_benefit():
    summary = _caption_summary({224: {"file": 0.41, "crop": 0.415}})

    verdict, detail = _require(verdict_caption(summary))

    assert verdict == NO_BENEFIT
    assert "No material change" in detail
