"""Export stored embeddings aligned to a frozen student-scorer manifest.

Does not mutate Postgres. Writes NPZ under the manifest directory.

Usage::

    python -m scripts.research.student_scorer.export_embeddings_npz \\
      --manifest-dir artifacts/student_scorer/msm_8ef568a5db3d9f79 \\
      --space mobilenet_v2_imagenet_gap
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from modules.embedding_spaces import DEFAULT_EMBEDDING_SPACE_CODE, SPACE_DIMS
from scripts.research.student_scorer.common import (
    COMPOSITE_KEYS,
    DEFAULT_TEACHERS,
    read_json,
    write_json,
)
from scripts.research.student_scorer.data import validate_manifest_against_protocol


BATCH_SIZE = 2000


def load_manifest_rows(manifest_dir: Path) -> list[dict[str, Any]]:
    parquet = manifest_dir / "manifest.parquet"
    jsonl = manifest_dir / "manifest.jsonl"
    if parquet.is_file():
        try:
            import pandas as pd

            return pd.read_parquet(parquet).to_dict(orient="records")
        except Exception:
            pass
    if not jsonl.is_file():
        raise FileNotFoundError(f"No manifest.parquet or manifest.jsonl in {manifest_dir}")
    rows: list[dict[str, Any]] = []
    with jsonl.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def head_list(teachers: Sequence[str] | None = None) -> list[str]:
    return list(teachers or DEFAULT_TEACHERS) + list(COMPOSITE_KEYS)


def row_targets_and_masks(
    row: Mapping[str, Any],
    heads: Sequence[str],
    teachers: Sequence[str],
) -> tuple[list[float], list[bool]]:
    """Build target vector and mask for one manifest row (missing → masked)."""
    teacher_norm = row.get("teacher_normalized") or {}
    if isinstance(teacher_norm, str):
        teacher_norm = json.loads(teacher_norm)
    teacher_mask = row.get("teacher_mask") or {}
    if isinstance(teacher_mask, str):
        teacher_mask = json.loads(teacher_mask)

    targets: list[float] = []
    masks: list[bool] = []
    for h in heads:
        if h in teachers:
            present = bool(teacher_mask.get(h)) and teacher_norm.get(h) is not None
            targets.append(float(teacher_norm[h]) if present else 0.0)
            masks.append(present)
        else:
            # composite keys on images row
            key = f"score_{h}" if not h.startswith("score_") else h
            # heads use general/technical/aesthetic
            val = row.get(f"score_{h}", row.get(h))
            present = val is not None
            targets.append(float(val) if present else 0.0)
            masks.append(present)
    return targets, masks


def bytes_to_vec(raw: bytes | memoryview | Any, expected_dim: int) -> np.ndarray | None:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray, memoryview)):
        arr = np.frombuffer(bytes(raw), dtype=np.float32).copy()
    else:
        arr = np.asarray(raw, dtype=np.float32).reshape(-1)
    if arr.size != expected_dim:
        return None
    return arr


def align_embeddings_to_manifest(
    rows: Sequence[Mapping[str, Any]],
    split_of: Mapping[int, str],
    emb_by_id: Mapping[int, np.ndarray],
    *,
    teachers: Sequence[str],
    expected_dim: int,
) -> dict[str, np.ndarray | list]:
    """Intersect manifest rows with available embeddings; build NPZ arrays."""
    heads = head_list(teachers)
    image_ids: list[int] = []
    embeddings: list[np.ndarray] = []
    targets: list[list[float]] = []
    masks: list[list[bool]] = []
    splits: list[str] = []
    missing_ids: list[int] = []

    for row in rows:
        iid = int(row["image_id"])
        vec = emb_by_id.get(iid)
        if vec is None or vec.size != expected_dim:
            missing_ids.append(iid)
            continue
        t, m = row_targets_and_masks(row, heads, teachers)
        image_ids.append(iid)
        embeddings.append(vec.astype(np.float32, copy=False))
        targets.append(t)
        masks.append(m)
        splits.append(str(split_of.get(iid, "train")))

    n_manifest = len(rows)
    n_keep = len(image_ids)
    coverage = {
        "n_manifest": n_manifest,
        "n_with_embedding": n_keep,
        "n_missing_embedding": len(missing_ids),
        "overlap_rate": (n_keep / n_manifest) if n_manifest else 0.0,
        "expected_dim": expected_dim,
        "heads": heads,
        "full_target_count": int(
            sum(1 for m in masks if all(m[i] for i in range(len(teachers))))
        ),
    }
    return {
        "image_ids": np.asarray(image_ids, dtype=np.int64),
        "embeddings": np.stack(embeddings, axis=0) if embeddings else np.zeros((0, expected_dim), np.float32),
        "targets": np.asarray(targets, dtype=np.float64) if targets else np.zeros((0, len(heads)), np.float64),
        "masks": np.asarray(masks, dtype=bool) if masks else np.zeros((0, len(heads)), bool),
        "splits": np.asarray(splits, dtype=object),
        "coverage": coverage,
        "missing_ids_sample": missing_ids[:50],
    }


def fetch_embeddings_batched(
    image_ids: Sequence[int],
    space_code: str,
    *,
    batch_size: int = BATCH_SIZE,
) -> dict[int, np.ndarray]:
    from modules import db
    from modules.embedding_spaces import SPACE_DIMS

    expected_dim = SPACE_DIMS[space_code]
    out: dict[int, np.ndarray] = {}
    ids = list(image_ids)
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        raw = db.get_image_embeddings_batch_for_space(space_code, chunk)
        for iid, blob in raw.items():
            vec = bytes_to_vec(blob, expected_dim)
            if vec is not None:
                out[int(iid)] = vec
    return out


def export_embeddings_npz(
    *,
    manifest_dir: Path,
    space: str = DEFAULT_EMBEDDING_SPACE_CODE,
    expected_protocol_id: str | None = None,
    expected_checksum: str | None = None,
) -> Path:
    if space not in SPACE_DIMS:
        raise ValueError(f"unknown embedding space {space!r}")
    meta = read_json(manifest_dir / "manifest.meta.json")
    validate_manifest_against_protocol(
        meta,
        expected_checksum=expected_checksum or meta.get("checksum"),
        expected_protocol_id=expected_protocol_id or meta.get("protocol_id"),
        expected_contract_hash=meta.get("contract_hash"),
    )
    # Re-check file checksum against meta if present
    on_disk_checksum = meta.get("checksum")
    if expected_checksum and on_disk_checksum != expected_checksum:
        raise ValueError("manifest checksum mismatch")

    rows = load_manifest_rows(manifest_dir)
    split_data = read_json(manifest_dir / "splits.json")
    split_of = {int(a["image_id"]): a["split"] for a in split_data["assignments"]}
    teachers = list(meta.get("teachers") or DEFAULT_TEACHERS)
    expected_dim = SPACE_DIMS[space]

    emb_by_id = fetch_embeddings_batched([int(r["image_id"]) for r in rows], space)
    aligned = align_embeddings_to_manifest(
        rows,
        split_of,
        emb_by_id,
        teachers=teachers,
        expected_dim=expected_dim,
    )
    coverage = dict(aligned["coverage"])  # type: ignore[arg-type]
    coverage["space"] = space
    coverage["manifest_id"] = meta.get("manifest_id")
    coverage["protocol_id"] = meta.get("protocol_id")
    coverage["missing_ids_sample"] = aligned["missing_ids_sample"]

    out_dir = manifest_dir / "embeddings"
    out_dir.mkdir(parents=True, exist_ok=True)
    npz_path = out_dir / f"{space}.npz"
    np.savez_compressed(
        npz_path,
        image_ids=aligned["image_ids"],
        embeddings=aligned["embeddings"],
        targets=aligned["targets"],
        masks=aligned["masks"],
        splits=aligned["splits"],
        heads=np.array(head_list(teachers), dtype=object),
        space=np.array(space),
    )
    write_json(out_dir / f"{space}.coverage.json", coverage)
    return npz_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export embeddings NPZ for student baselines")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--space", default=DEFAULT_EMBEDDING_SPACE_CODE)
    parser.add_argument("--protocol-id", default=None)
    args = parser.parse_args(argv)
    path = export_embeddings_npz(
        manifest_dir=args.manifest_dir,
        space=args.space,
        expected_protocol_id=args.protocol_id,
    )
    cov = read_json(path.with_suffix("").with_name(path.stem + ".coverage.json"))
    # path is space.npz → coverage is space.coverage.json
    cov_path = path.parent / f"{args.space}.coverage.json"
    cov = read_json(cov_path)
    print(json.dumps({"npz": str(path), "coverage": cov}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
