"""Structural tests for the local QPT V2 (HiViT-T) re-implementation.

These do NOT need the upstream checkpoint — they verify the module wiring
(parameter count, forward shape, batch handling) so the architecture stays
loadable by ``QptV2HiViT.load_state_dict(strict=...)`` against ``iqa.pth``.

Marked ``ml`` because they require torch.
"""

import pytest

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.ml

from modules.qpt_v2_arch import QptV2HiViT  # noqa: E402


def test_param_count_matches_checkpoint():
    # iqa.pth ckpt['params'] holds 172 tensors totalling 18,859,789 elements
    # (incl. the relative_position_index buffer, 196*196=38,416, which is not a
    # trainable parameter). Matching both guarantees strict-load compatibility.
    model = QptV2HiViT()
    sd = model.state_dict()
    assert len(sd) == 172
    assert sum(t.numel() for t in sd.values()) == 18_859_789


def test_forward_returns_one_score_per_image():
    model = QptV2HiViT().eval()
    x = torch.randn(2, 3, 224, 224)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (2,)
    assert torch.isfinite(out).all()


def test_single_image_forward_is_scalar_per_item():
    model = QptV2HiViT().eval()
    x = torch.randn(1, 3, 224, 224)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (1,)
    assert isinstance(out.item(), float)
