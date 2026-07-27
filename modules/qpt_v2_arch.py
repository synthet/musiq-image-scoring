"""Local re-implementation of the QPT V2 (HiViT-T) image-quality scorer.

Upstream (``KeiChiTse/QPT-V2``) released **checkpoints only** — the inference
code is an unfulfilled TODO. This module reconstructs the architecture directly
from the published ``iqa.pth`` state dict (``ckpt['params']``, 18.9M params), so
the checkpoint loads with ``strict=True`` (all 172 tensors map by name + shape).

Recovered structure (see docs/planning/models/CALIBRATION_LAYER_185_STATUS.md):

    patch_embed : Conv2d(3->96, k=4, s=4) + LayerNorm(96)     224^2 -> 56^2 x96
    blocks.0-1  : FFN-only (norm2 + mlp), dim 96,  mlp_ratio 3.0
    blocks.2    : PatchMerge  LN(384) + Linear(384->192, bias=False)  56->28
    blocks.3-4  : FFN-only, dim 192, mlp_ratio 3.0
    blocks.5    : PatchMerge  LN(768) + Linear(768->384, bias=False)  28->14
    + absolute_pos_embed (1,196,384) at the main stage
    blocks.6-15 : attention (norm1+attn, norm2+mlp), dim 384, 6 heads, mlp_ratio 4.0
                  relative_position_bias_table (729=27^2, 6) via shared
                  relative_position_index (196,196)
    norm        : LayerNorm(384) -> mean-pool over 196 tokens
    quality_regressor.fc_cls : Linear(384->64) -> GELU -> Dropout -> Linear(64->1)

ACCURACY CAVEAT: the forward-pass conventions (patch-merge neighbour order,
relative-position indexing, pooling, and inference preprocessing) are not
documented upstream; a community attempt to run these weights reported
unsatisfactory results (QPT-V2 issue #2). Treat scores as provisional until
validated against a labelled set.
"""

from __future__ import annotations

import logging

import torch
from torch import nn

logger = logging.getLogger(__name__)

# HiViT-T config as dictated by the QPT V2 iqa.pth checkpoint.
_STEM_DIM = 96
_MAIN_DIM = 384
_NUM_HEADS = 6
_DEPTHS = (2, 2, 10)        # stem stage 1, stem stage 2, main stage
_STEM_MLP_RATIO = 3.0
_MAIN_MLP_RATIO = 4.0
_MAIN_GRID = 14             # 14 x 14 = 196 tokens at the main stage


class _Mlp(nn.Module):
    def __init__(self, dim: int, hidden: int) -> None:
        super().__init__()
        self.fc1 = nn.Linear(dim, hidden)
        self.act = nn.GELU()
        self.fc2 = nn.Linear(hidden, dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(self.act(self.fc1(x)))


class _BlockNoAttn(nn.Module):
    """Stem-stage block: FFN only (operates on (B, H, W, C))."""

    def __init__(self, dim: int, mlp_ratio: float) -> None:
        super().__init__()
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = _Mlp(dim, int(dim * mlp_ratio))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.mlp(self.norm2(x))


class _PatchMerge(nn.Module):
    """Concatenate 2x2 neighbours then LayerNorm + linear reduce (4C -> 2C)."""

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(dim * 4)
        self.reduction = nn.Linear(dim * 4, dim * 2, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, H, W, C) -> (B, H/2, W/2, 4C)
        x0 = x[:, 0::2, 0::2, :]
        x1 = x[:, 1::2, 0::2, :]
        x2 = x[:, 0::2, 1::2, :]
        x3 = x[:, 1::2, 1::2, :]
        x = torch.cat([x0, x1, x2, x3], dim=-1)
        return self.reduction(self.norm(x))


class _Attention(nn.Module):
    def __init__(self, dim: int, num_heads: int, grid: int) -> None:
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = dim // num_heads
        self.scale = self.head_dim ** -0.5
        self.qkv = nn.Linear(dim, dim * 3, bias=True)
        self.proj = nn.Linear(dim, dim)
        # (2*grid-1)^2 relative positions x heads
        self.relative_position_bias_table = nn.Parameter(
            torch.zeros((2 * grid - 1) * (2 * grid - 1), num_heads)
        )

    def forward(self, x: torch.Tensor, rpe_index: torch.Tensor) -> torch.Tensor:
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, self.head_dim).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        attn = (q @ k.transpose(-2, -1)) * self.scale
        bias = self.relative_position_bias_table[rpe_index].view(N, N, -1).permute(2, 0, 1)
        attn = attn + bias.unsqueeze(0)
        attn = attn.softmax(dim=-1)
        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        return self.proj(x)


class _BlockAttn(nn.Module):
    """Main-stage transformer block (operates on (B, N, C))."""

    def __init__(self, dim: int, num_heads: int, mlp_ratio: float, grid: int) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = _Attention(dim, num_heads, grid)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = _Mlp(dim, int(dim * mlp_ratio))

    def forward(self, x: torch.Tensor, rpe_index: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.norm1(x), rpe_index)
        x = x + self.mlp(self.norm2(x))
        return x


class _PatchEmbed(nn.Module):
    def __init__(self, in_chans: int, dim: int) -> None:
        super().__init__()
        self.proj = nn.Conv2d(in_chans, dim, kernel_size=4, stride=4)
        self.norm = nn.LayerNorm(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.proj(x)                       # (B, C, H/4, W/4)
        x = x.permute(0, 2, 3, 1).contiguous()  # (B, H/4, W/4, C)
        return self.norm(x)


def _build_relative_position_index(grid: int) -> torch.Tensor:
    coords = torch.stack(torch.meshgrid(
        torch.arange(grid), torch.arange(grid), indexing="ij"))  # 2, g, g
    coords_flat = torch.flatten(coords, 1)                       # 2, N
    rel = coords_flat[:, :, None] - coords_flat[:, None, :]      # 2, N, N
    rel = rel.permute(1, 2, 0).contiguous()                      # N, N, 2
    rel[:, :, 0] += grid - 1
    rel[:, :, 1] += grid - 1
    rel[:, :, 0] *= 2 * grid - 1
    return rel.sum(-1)                                           # N, N


class QptV2HiViT(nn.Module):
    """HiViT-T backbone + single-value quality regressor matching ``iqa.pth``."""

    def __init__(self) -> None:
        super().__init__()
        self.patch_embed = _PatchEmbed(3, _STEM_DIM)
        self.absolute_pos_embed = nn.Parameter(torch.zeros(1, _MAIN_GRID * _MAIN_GRID, _MAIN_DIM))
        self.register_buffer("relative_position_index", _build_relative_position_index(_MAIN_GRID))

        blocks: list[nn.Module] = []
        # stem stage 1 (dim 96)
        for _ in range(_DEPTHS[0]):
            blocks.append(_BlockNoAttn(_STEM_DIM, _STEM_MLP_RATIO))
        blocks.append(_PatchMerge(_STEM_DIM))                    # -> 192
        # stem stage 2 (dim 192)
        for _ in range(_DEPTHS[1]):
            blocks.append(_BlockNoAttn(_STEM_DIM * 2, _STEM_MLP_RATIO))
        blocks.append(_PatchMerge(_STEM_DIM * 2))               # -> 384
        # main stage (dim 384)
        for _ in range(_DEPTHS[2]):
            blocks.append(_BlockAttn(_MAIN_DIM, _NUM_HEADS, _MAIN_MLP_RATIO, _MAIN_GRID))
        self.blocks = nn.ModuleList(blocks)

        self.norm = nn.LayerNorm(_MAIN_DIM)
        self.quality_regressor = nn.Module()
        self.quality_regressor.fc_cls = nn.Sequential(
            nn.Linear(_MAIN_DIM, 64), nn.GELU(), nn.Dropout(0.0), nn.Linear(64, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.patch_embed(x)                 # (B, 56, 56, 96)
        rpe_index = self.relative_position_index.view(-1)
        for blk in self.blocks:
            if isinstance(blk, _BlockAttn):
                if x.dim() == 4:                # entering main stage: flatten + pos embed
                    B, H, W, C = x.shape
                    x = x.reshape(B, H * W, C) + self.absolute_pos_embed
                x = blk(x, rpe_index)
            else:
                x = blk(x)
        x = self.norm(x)
        x = x.mean(dim=1)                       # global average pool over tokens
        return self.quality_regressor.fc_cls(x).squeeze(-1)


def load_qpt_v2(checkpoint_path: str, device: str = "cpu") -> QptV2HiViT | None:
    """Build the model and strict-load ``ckpt['params']``. Returns None on failure."""
    model = QptV2HiViT()
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    state = ckpt["params"] if isinstance(ckpt, dict) and "params" in ckpt else ckpt
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        logger.error(
            "QPT V2 checkpoint mismatch: missing=%s unexpected=%s",
            list(missing), list(unexpected),
        )
        return None
    model.eval().to(device)
    return model


__all__ = ["QptV2HiViT", "load_qpt_v2"]
