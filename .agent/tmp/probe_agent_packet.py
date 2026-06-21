#!/usr/bin/env python3
"""One-off probe: agent cull packet scores + thumbnail path visibility."""
from __future__ import annotations

import json
import os
import sys

from modules import db, thumbnails
from modules.agent_cull.config import load_agent_cull_config
from modules.agent_cull.discovery_db import inspect_review_unit_for_run, load_unit_rows
from modules.agent_cull.payload import build_review_packet
from modules.db_legacy import get_batch_image_model_scores


def main() -> int:
    stack_id = int(sys.argv[1]) if len(sys.argv) > 1 else 29154
    sub_stack_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    cfg = load_agent_cull_config()
    unit = inspect_review_unit_for_run(cfg, stack_id=stack_id, sub_stack_id=sub_stack_id)
    if unit is None:
        print(json.dumps({"error": "no_unit", "stack_id": stack_id, "sub_stack_id": sub_stack_id}))
        return 1

    rows = load_unit_rows(unit)
    ims = get_batch_image_model_scores(list(unit.image_ids))
    packet = build_review_packet(unit, rows, cfg)
    manifest = packet.get("thumbnail_manifest") or []

    samples = []
    for iid in unit.image_ids[:6]:
        row = rows.get(iid, {})
        raw_tp = row.get("thumbnail_path")
        raw_tw = row.get("thumbnail_path_win")
        resolved = thumbnails._resolve_thumbnail_filesystem_path(raw_tp, raw_tw)
        model_scores = ims.get(iid, {})
        img_entry = next((x for x in packet.get("images") or [] if x.get("id") == iid), {})
        samples.append(
            {
                "image_id": iid,
                "raw_thumbnail_path": raw_tp,
                "raw_exists": bool(raw_tp and os.path.isfile(str(raw_tp))),
                "resolved_path": resolved,
                "resolved_exists": bool(resolved and os.path.isfile(resolved)),
                "scores_packet": img_entry.get("scores"),
                "model_scores": {
                    k: v.get("normalized") if isinstance(v, dict) else v
                    for k, v in model_scores.items()
                },
            }
        )

    out = {
        "review_unit_key": unit.review_unit_key,
        "image_count": len(unit.image_ids),
        "manifest_count": len(manifest),
        "manifest_sample": manifest[0] if manifest else None,
        "manifest_path_exists": bool(
            manifest and manifest[0].get("path") and os.path.isfile(str(manifest[0]["path"]))
        ),
        "docker_container": os.environ.get("DOCKER_CONTAINER"),
        "thumb_dir": getattr(thumbnails, "THUMB_DIR", None),
        "project_root": str(getattr(thumbnails, "PROJECT_ROOT", "")),
        "samples": samples,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
