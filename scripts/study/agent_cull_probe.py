#!/usr/bin/env python3
"""Preflight probe: agent cull packet scores + thumbnail path visibility."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys


def _detect_runtime() -> str:
    explicit = (os.environ.get("AGENT_CULL_STUDY_RUNTIME") or "").strip().lower()
    if explicit in ("docker", "wsl", "host"):
        return explicit
    if os.environ.get("DOCKER_CONTAINER") or os.path.exists("/.dockerenv"):
        return "docker"
    if sys.platform.startswith("linux") and "microsoft" in platform.uname().release.lower():
        return "wsl"
    return "host"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent cull packet preflight probe")
    parser.add_argument("--stack-id", type=int, required=True)
    parser.add_argument("--sub-stack-id", type=int)
    parser.add_argument("--mode-profile", default="baseline_v2")
    parser.add_argument("--runtime", choices=["docker", "wsl", "host"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from modules import db, thumbnails
    from modules.agent_cull.config import load_agent_cull_config
    from modules.agent_cull.discovery_db import inspect_review_unit_for_run, load_unit_rows
    from modules.agent_cull.mode_profiles import apply_mode_profile
    from modules.agent_cull.payload import build_review_packet, enrich_unit_rows

    cfg = apply_mode_profile(load_agent_cull_config(), args.mode_profile)
    unit = inspect_review_unit_for_run(cfg, stack_id=args.stack_id, sub_stack_id=args.sub_stack_id)
    if unit is None:
        out = {
            "ok": False,
            "error": "no_unit",
            "stack_id": args.stack_id,
            "sub_stack_id": args.sub_stack_id,
        }
        print(json.dumps(out, indent=2))
        return 1

    rows = load_unit_rows(unit)
    score_warnings = enrich_unit_rows(rows, cfg)
    packet = build_review_packet(unit, rows, cfg, score_warnings=score_warnings)
    manifest = packet.get("thumbnail_manifest") or []

    samples = []
    for iid in unit.image_ids:
        row = rows.get(iid, {})
        raw_tp = row.get("thumbnail_path")
        raw_tw = row.get("thumbnail_path_win")
        resolved = thumbnails._resolve_thumbnail_filesystem_path(raw_tp, raw_tw)
        img_entry = next((x for x in packet.get("images") or [] if x.get("id") == iid), {})
        samples.append(
            {
                "image_id": iid,
                "file_name": row.get("file_name"),
                "raw_thumbnail_path": raw_tp,
                "raw_exists": bool(raw_tp and os.path.isfile(str(raw_tp))),
                "resolved_path": resolved,
                "resolved_exists": bool(resolved and os.path.isfile(resolved)),
                "scores_packet": img_entry.get("scores"),
                "model_scores_keys": sorted((img_entry.get("model_scores") or {}).keys()),
            }
        )

    runtime = args.runtime or _detect_runtime()
    manifest_ok = (
        not cfg.agent.include_thumbnails
        or len(manifest) >= len(unit.image_ids)
        and all(m.get("path") and os.path.isfile(str(m["path"])) for m in manifest)
    )

    out = {
        "ok": manifest_ok,
        "runtime": runtime,
        "mode_profile": args.mode_profile,
        "prompt_template_version": packet.get("prompt_template_version"),
        "review_unit_key": unit.review_unit_key,
        "stack_id": args.stack_id,
        "sub_stack_id": args.sub_stack_id,
        "image_count": len(unit.image_ids),
        "manifest_count": len(manifest),
        "include_thumbnails": cfg.agent.include_thumbnails,
        "manifest_sample": manifest[0] if manifest else None,
        "score_warnings": score_warnings,
        "docker_container": os.environ.get("DOCKER_CONTAINER"),
        "thumb_dir": getattr(thumbnails, "THUMB_DIR", None),
        "project_root": str(getattr(thumbnails, "PROJECT_ROOT", "")),
        "samples": samples,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0 if manifest_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
