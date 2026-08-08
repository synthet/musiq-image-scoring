"""Export a deployable student checkpoint bundle (local artifacts only)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.research.student_scorer.common import (
    DEFAULT_TEACHERS,
    ensure_artifacts_dir,
    read_json,
    sha256_file,
    stable_hash,
    write_json,
)
from scripts.research.student_scorer.models import ALL_OUTPUT_KEYS, StudentArchConfig, build_image_student


def export_bundle(
    *,
    weights_path: Path | None,
    arch: StudentArchConfig,
    manifest_id: str,
    protocol_id: str,
    metrics: dict[str, Any] | None = None,
    fusion: dict[str, Any] | None = None,
    anchors: dict[str, Any] | None = None,
    preprocessing_fingerprint: str | None = None,
    out_dir: Path | None = None,
) -> Path:
    dest = out_dir or (ensure_artifacts_dir(manifest_id) / "bundles" / "v1")
    dest.mkdir(parents=True, exist_ok=True)

    meta = {
        "format": "vexlum_student_bundle_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest_id": manifest_id,
        "protocol_id": protocol_id,
        "architecture": {
            "backbone": arch.backbone,
            "fine_tune": arch.fine_tune,
            "input_size": arch.input_size,
            "teachers": list(arch.teachers),
            "output_keys": list(ALL_OUTPUT_KEYS),
        },
        "preprocessing_fingerprint": preprocessing_fingerprint,
        "fusion": fusion,
        "percentile_anchors": anchors,
        "metrics": metrics or {},
        "dependencies": {"torch": None, "timm": None},
    }
    try:
        import torch
        import timm

        meta["dependencies"]["torch"] = torch.__version__
        meta["dependencies"]["timm"] = getattr(timm, "__version__", "unknown")
    except ImportError:
        pass

    weights_out = dest / "weights.pt"
    if weights_path and weights_path.is_file():
        import shutil

        shutil.copy2(weights_path, weights_out)
    else:
        # Create a randomly initialized reference bundle for wiring tests only
        try:
            import torch

            model = build_image_student(StudentArchConfig(pretrained=False, backbone=arch.backbone))
            torch.save({"state_dict": model.state_dict(), "arch": meta["architecture"]}, weights_out)
        except Exception as exc:
            write_json(dest / "weights_placeholder.json", {"error": str(exc), "note": "install student deps"})
            weights_out = dest / "weights_placeholder.json"

    meta["weights_sha256"] = sha256_file(weights_out)
    meta["bundle_id"] = "bundle_" + stable_hash(meta)[:16]
    write_json(dest / "bundle.meta.json", meta)
    write_json(dest / "checksums.sha256.json", {"weights": meta["weights_sha256"], "bundle_id": meta["bundle_id"]})
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export student checkpoint bundle")
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=None)
    parser.add_argument("--backbone", default="convnext_tiny")
    args = parser.parse_args(argv)
    meta = read_json(args.manifest_dir / "manifest.meta.json")
    dest = export_bundle(
        weights_path=args.weights,
        arch=StudentArchConfig(backbone=args.backbone, pretrained=False),
        manifest_id=str(meta.get("manifest_id")),
        protocol_id=str(meta.get("protocol_id")),
        fusion=meta.get("fusion"),
        anchors=meta.get("percentile_anchors"),
        preprocessing_fingerprint=(meta.get("preprocessing") or {}).get("fingerprint"),
    )
    print(json.dumps({"bundle_dir": str(dest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
