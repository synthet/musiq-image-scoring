"""Torch Dataset over the P0 render cache aligned to a frozen manifest.

Reuses ``export_embeddings_npz.row_targets_and_masks`` / ``head_list`` so
E2 targets match E0/E1 bit-for-bit. Head order follows ``meta["teachers"]``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.research.student_scorer.common import COMPOSITE_KEYS, read_json
from scripts.research.student_scorer.export_embeddings_npz import (
    head_list,
    load_manifest_rows,
    row_targets_and_masks,
)
from scripts.research.student_scorer.objectives import teacher_disagreement
from scripts.research.student_scorer.render_p0 import default_cache_dir, shard_relpath

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def load_render_index(manifest_dir: Path) -> dict[int, dict[str, Any]]:
    path = manifest_dir / "renders" / "render_index.json"
    # Also accept artifacts path written by render_p0 (same relative under manifest_dir
    # when manifest lives under artifacts/student_scorer/<id>/).
    if not path.is_file():
        alt = Path(manifest_dir) / "renders" / "render_index.json"
        path = alt
    if not path.is_file():
        raise FileNotFoundError(f"render_index.json not found under {manifest_dir}/renders/")
    data = read_json(path)
    rows = data.get("images") if isinstance(data, dict) else data
    cache_dir = None
    if isinstance(data, dict):
        cache_dir = data.get("cache_dir")
    out: dict[int, dict[str, Any]] = {}
    for row in rows or []:
        item = dict(row)
        if cache_dir and "cache_dir" not in item:
            item["cache_dir"] = cache_dir
        out[int(row["image_id"])] = item
    return out


def resolve_render_path(
    entry: Mapping[str, Any],
    *,
    cache_dir: Path | None,
    image_id: int,
) -> Path:
    rel = entry.get("rel_path") or shard_relpath(image_id)
    base = Path(entry.get("cache_dir") or cache_dir or ".")
    return base / rel


def build_sample_arrays(
    rows: Sequence[Mapping[str, Any]],
    render_index: Mapping[int, Mapping[str, Any]],
    split_of: Mapping[int, str],
    *,
    teachers: Sequence[str],
    cache_dir: Path | None = None,
    splits_keep: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Filter to ok renders; return aligned lists for Dataset construction."""
    heads = head_list(teachers)
    image_ids: list[int] = []
    paths: list[str] = []
    targets: list[list[float]] = []
    masks: list[list[bool]] = []
    stored_composites: list[list[float]] = []
    composite_masks: list[list[bool]] = []
    uncertainty_targets: list[float] = []
    uncertainty_masks: list[bool] = []
    splits: list[str] = []
    resolved_methods: list[str] = []
    skipped = 0

    keep = set(splits_keep) if splits_keep else None

    for row in rows:
        iid = int(row["image_id"])
        sp = split_of.get(iid, "unknown")
        if keep is not None and sp not in keep:
            continue
        entry = render_index.get(iid)
        if not entry or entry.get("status") != "ok":
            skipped += 1
            continue
        path = resolve_render_path(entry, cache_dir=cache_dir, image_id=iid)
        if not path.is_file():
            skipped += 1
            continue

        tvec, mvec = row_targets_and_masks(row, heads, teachers)
        image_ids.append(iid)
        paths.append(str(path))
        targets.append(tvec)
        masks.append(mvec)
        # stored composites are the last 3 of the 8-head layout
        n_t = len(teachers)
        stored_composites.append(tvec[n_t : n_t + 3])
        composite_masks.append(mvec[n_t : n_t + 3])

        teacher_norm = row.get("teacher_normalized") or {}
        if isinstance(teacher_norm, str):
            import json

            teacher_norm = json.loads(teacher_norm)
        teacher_mask = row.get("teacher_mask") or {}
        if isinstance(teacher_mask, str):
            import json

            teacher_mask = json.loads(teacher_mask)
        present = {
            t: float(teacher_norm[t])
            for t in teachers
            if teacher_mask.get(t) and teacher_norm.get(t) is not None
        }
        if len(present) >= 2:
            uncertainty_targets.append(float(teacher_disagreement(present)))
            uncertainty_masks.append(True)
        else:
            uncertainty_targets.append(0.0)
            uncertainty_masks.append(False)

        splits.append(sp)
        resolved_methods.append(str(entry.get("resolved_method") or "unknown"))

    return {
        "image_ids": image_ids,
        "paths": paths,
        "targets": targets,
        "masks": masks,
        "stored_composites": stored_composites,
        "composite_masks": composite_masks,
        "uncertainty_targets": uncertainty_targets,
        "uncertainty_masks": uncertainty_masks,
        "splits": splits,
        "resolved_methods": resolved_methods,
        "heads": heads,
        "teachers": list(teachers),
        "n_skipped": skipped,
    }


class P0ImageDataset:
    """Minimal Dataset API (works with or without torchvision)."""

    def __init__(
        self,
        arrays: Mapping[str, Any],
        *,
        indices: Sequence[int] | None = None,
    ) -> None:
        self.heads = list(arrays["heads"])
        self.teachers = list(arrays["teachers"])
        all_ids = list(range(len(arrays["image_ids"])))
        self.indices = list(indices) if indices is not None else all_ids
        self._arrays = arrays

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, i: int) -> dict[str, Any]:
        from PIL import Image

        idx = self.indices[i]
        path = self._arrays["paths"][idx]
        img = Image.open(path).convert("RGB")
        arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC
        mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(1, 1, 3)
        std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(1, 1, 3)
        arr = (arr - mean) / std
        chw = np.transpose(arr, (2, 0, 1)).copy()

        return {
            "image": chw,
            "targets": np.asarray(self._arrays["targets"][idx], dtype=np.float32),
            "masks": np.asarray(self._arrays["masks"][idx], dtype=np.bool_),
            "stored_composites": np.asarray(
                self._arrays["stored_composites"][idx], dtype=np.float32
            ),
            "composite_masks": np.asarray(
                self._arrays["composite_masks"][idx], dtype=np.bool_
            ),
            "uncertainty_target": np.float32(self._arrays["uncertainty_targets"][idx]),
            "uncertainty_mask": bool(self._arrays["uncertainty_masks"][idx]),
            "image_id": int(self._arrays["image_ids"][idx]),
            "resolved_method": self._arrays["resolved_methods"][idx],
            "split": self._arrays["splits"][idx],
        }


def collate_p0(batch: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    import torch

    return {
        "image": torch.from_numpy(np.stack([b["image"] for b in batch])),
        "targets": torch.from_numpy(np.stack([b["targets"] for b in batch])),
        "masks": torch.from_numpy(np.stack([b["masks"] for b in batch])),
        "stored_composites": torch.from_numpy(
            np.stack([b["stored_composites"] for b in batch])
        ),
        "composite_masks": torch.from_numpy(
            np.stack([b["composite_masks"] for b in batch])
        ),
        "uncertainty_target": torch.tensor(
            [b["uncertainty_target"] for b in batch], dtype=torch.float32
        ),
        "uncertainty_mask": torch.tensor(
            [b["uncertainty_mask"] for b in batch], dtype=torch.bool
        ),
        "image_id": [b["image_id"] for b in batch],
        "resolved_method": [b["resolved_method"] for b in batch],
        "split": [b["split"] for b in batch],
    }


def prepare_manifest_arrays(
    manifest_dir: Path,
    *,
    cache_dir: Path | None = None,
    splits_keep: Sequence[str] | None = None,
) -> dict[str, Any]:
    meta = read_json(manifest_dir / "manifest.meta.json")
    teachers = list(meta["teachers"])
    rows = load_manifest_rows(manifest_dir)
    split_data = read_json(manifest_dir / "splits.json")
    split_of = {int(a["image_id"]): a["split"] for a in split_data["assignments"]}
    render_index = load_render_index(manifest_dir)
    resolved_cache = cache_dir
    if resolved_cache is None:
        # Prefer cache_dir recorded in index
        sample = next(iter(render_index.values()), None)
        if sample and sample.get("cache_dir"):
            resolved_cache = Path(sample["cache_dir"])
        else:
            resolved_cache = default_cache_dir(str(meta["manifest_id"]))
    arrays = build_sample_arrays(
        rows,
        render_index,
        split_of,
        teachers=teachers,
        cache_dir=resolved_cache,
        splits_keep=splits_keep,
    )
    arrays["meta"] = meta
    arrays["cache_dir"] = str(resolved_cache)
    arrays["composite_keys"] = list(COMPOSITE_KEYS)
    return arrays


def indices_for_split(arrays: Mapping[str, Any], split: str) -> list[int]:
    return [i for i, s in enumerate(arrays["splits"]) if s == split]
