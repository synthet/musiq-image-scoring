"""Backbone / head construction for student experiments.

Torch is optional at import time so fast unit tests can skip ML markers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from scripts.research.student_scorer.common import DEFAULT_TEACHERS


TEACHER_HEADS = list(DEFAULT_TEACHERS)
AUX_HEADS = ["general", "technical", "aesthetic", "uncertainty"]
ALL_OUTPUT_KEYS = TEACHER_HEADS + AUX_HEADS


@dataclass
class StudentArchConfig:
    backbone: str = "convnext_tiny"
    pretrained: bool = True
    fine_tune: str = "last_stage"  # frozen | last_stage | full | final_blocks
    input_size: int = 512
    dropout: float = 0.1
    teachers: tuple[str, ...] = DEFAULT_TEACHERS


def build_linear_multihead(
    in_dim: int,
    teachers: Sequence[str] = DEFAULT_TEACHERS,
) -> Any:
    """E0: standardized linear multi-output head (torch.nn if available)."""
    import torch.nn as nn

    out_dim = len(teachers) + len(AUX_HEADS)
    return nn.Linear(in_dim, out_dim)


def build_mlp_multihead(
    in_dim: int,
    teachers: Sequence[str] = DEFAULT_TEACHERS,
    hidden: Sequence[int] = (1024, 256),
    dropout: float = 0.1,
) -> Any:
    """E1: 2–3 layer MLP multi-output head."""
    import torch.nn as nn

    out_dim = len(teachers) + len(AUX_HEADS)
    layers: list[Any] = []
    prev = in_dim
    for h in hidden:
        layers.extend([nn.Linear(prev, h), nn.GELU(), nn.Dropout(dropout)])
        prev = h
    layers.append(nn.Linear(prev, out_dim))
    return nn.Sequential(*layers)


class StudentMultiHead:
    """Documentation placeholder; concrete module comes from ``build_image_student``."""

    pass


def build_image_student(cfg: StudentArchConfig | None = None) -> Any:
    """Construct ConvNeXt / DINOv2 / Swin student with multi-head outputs.

    Requires ``timm`` + ``torch``. Used by train_image_model / export_checkpoint.
    """
    import torch
    import torch.nn as nn

    cfg = cfg or StudentArchConfig()
    try:
        import timm
    except ImportError as exc:
        raise ImportError(
            "timm is required for image students; install requirements_student_scorer.txt"
        ) from exc

    backbone_map = {
        "convnext_tiny": "convnext_tiny.fb_in22k",
        "convnext_small": "convnext_small.fb_in22k",
        "swin_tiny": "swin_tiny_patch4_window7_224",
        "dinov2_vits14": "vit_small_patch14_dinov2.lvd142m",
        "mobilenetv3_large": "mobilenetv3_large_100.ra_in1k",
    }
    name = backbone_map.get(cfg.backbone, cfg.backbone)
    backbone = timm.create_model(name, pretrained=cfg.pretrained, num_classes=0)
    feat_dim = getattr(backbone, "num_features", None)
    if feat_dim is None:
        # Probe
        with torch.no_grad():
            dummy = torch.zeros(1, 3, cfg.input_size, cfg.input_size)
            feat_dim = int(backbone(dummy).shape[-1])

    out_dim = len(cfg.teachers) + len(AUX_HEADS)
    head = nn.Sequential(
        nn.Dropout(cfg.dropout),
        nn.Linear(feat_dim, out_dim),
    )

    class _Student(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = backbone
            self.head = head
            self.teachers = list(cfg.teachers)
            self.output_keys = list(cfg.teachers) + list(AUX_HEADS)
            self._apply_finetune_policy(cfg.fine_tune)

        def _apply_finetune_policy(self, policy: str) -> None:
            if policy == "frozen":
                for p in self.backbone.parameters():
                    p.requires_grad = False
            elif policy == "last_stage":
                for p in self.backbone.parameters():
                    p.requires_grad = False
                # Unfreeze last stage / blocks when present
                for attr in ("stages", "blocks", "layers"):
                    mod = getattr(self.backbone, attr, None)
                    if mod is None:
                        continue
                    try:
                        last = mod[-1]
                    except Exception:
                        continue
                    for p in last.parameters():
                        p.requires_grad = True
                    break
            elif policy == "final_blocks":
                for p in self.backbone.parameters():
                    p.requires_grad = False
                blocks = getattr(self.backbone, "blocks", None)
                if blocks is not None:
                    for blk in list(blocks)[-2:]:
                        for p in blk.parameters():
                            p.requires_grad = True
            # full: leave all trainable

        def forward(self, x: Any) -> dict[str, Any]:
            feats = self.backbone(x)
            if feats.ndim > 2:
                feats = feats.mean(dim=tuple(range(1, feats.ndim - 1)))
            logits = self.head(feats)
            out = {}
            for i, key in enumerate(self.output_keys):
                out[key] = logits[:, i]
            return out

    return _Student()


def vector_from_logits(output: dict[str, Any]) -> dict[str, float]:
    """Detach a model output dict to plain floats (batch size 1)."""
    result = {}
    for k, v in output.items():
        if hasattr(v, "detach"):
            result[k] = float(v.detach().reshape(-1)[0].cpu())
        else:
            result[k] = float(v)
    return result
