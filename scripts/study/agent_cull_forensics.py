#!/usr/bin/env python3
"""Forensics for picked advisory gap (stack 29157 / image 195193)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGET_IMAGE_ID = 195193
DEFAULT_STACK = 29157
DEFAULT_SUB_STACK = 72253


def _load_group(group_id: int) -> dict:
    from modules.agent_cull.repository import get_review_group

    group = get_review_group(group_id) or {}
    for key in ("request_json", "response_validated", "response_raw"):
        val = group.get(key)
        if isinstance(val, str):
            try:
                group[key] = json.loads(val)
            except json.JSONDecodeError:
                pass
    return group


def _picked_set_from_packet(request: dict) -> dict:
    picked = request.get("picked_image_ids") or []
    images = {int(img["id"]): img for img in request.get("images") or [] if img.get("id") is not None}
    rows = []
    for pid in picked:
        img = images.get(int(pid)) or {}
        scores = img.get("scores") or {}
        rows.append(
            {
                "image_id": int(pid),
                "file_name": img.get("file_name"),
                "score_technical": scores.get("score_technical"),
                "clip_quality_v0": scores.get("clip_quality_v0"),
                "topiq": scores.get("topiq"),
                "spaq": scores.get("spaq"),
            }
        )
    rows.sort(key=lambda r: float(r.get("score_technical") or 0), reverse=True)
    return {"picked_image_ids": picked, "picked_scores": rows}


def _run_advisory_smoke(thumb_path: str, provider: str, image_id: int) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/study/agent_cull_vision_smoke.py"),
        thumb_path,
        provider,
        str(image_id),
        "--advisory-prompt",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), check=False)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "stdout_head": proc.stdout[:2000], "stderr_head": proc.stderr[:500]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Picked advisory forensics")
    parser.add_argument("--group-id", type=int, action="append", default=[99, 100])
    parser.add_argument("--stack-id", type=int, default=DEFAULT_STACK)
    parser.add_argument("--sub-stack-id", type=int, default=DEFAULT_SUB_STACK)
    parser.add_argument("--image-id", type=int, default=TARGET_IMAGE_ID)
    parser.add_argument("--provider", default="antigravity")
    parser.add_argument("--output", type=Path, help="Write JSON report here")
    args = parser.parse_args(argv)

    from modules.agent_cull.config import load_agent_cull_config
    from modules.agent_cull.discovery_db import inspect_review_unit_for_run, load_unit_rows
    from modules.agent_cull.mode_profiles import apply_mode_profile
    from modules.agent_cull.payload import build_review_packet, enrich_unit_rows

    cfg = apply_mode_profile(load_agent_cull_config(), "technical_focus")
    unit = inspect_review_unit_for_run(cfg, stack_id=args.stack_id, sub_stack_id=args.sub_stack_id)
    report: dict = {
        "stack_id": args.stack_id,
        "sub_stack_id": args.sub_stack_id,
        "target_image_id": args.image_id,
        "groups": [],
        "current_packet_picked_set": None,
        "advisory_smoke": None,
    }

    if unit:
        rows = load_unit_rows(unit)
        enrich_unit_rows(rows, cfg)
        packet = build_review_packet(unit, rows, cfg)
        report["current_packet_picked_set"] = _picked_set_from_packet(packet)
        manifest = packet.get("thumbnail_manifest") or []
        thumb = next((m for m in manifest if int(m.get("image_id", 0)) == args.image_id), None)
        if thumb and thumb.get("path"):
            report["advisory_smoke"] = _run_advisory_smoke(
                str(thumb["path"]), args.provider, args.image_id
            )
        else:
            report["advisory_smoke"] = {"ok": False, "error": "thumbnail_not_in_manifest"}

    for gid in args.group_id:
        group = _load_group(int(gid))
        req = group.get("request_json") or {}
        resp = group.get("response_validated") or {}
        report["groups"].append(
            {
                "group_id": gid,
                "review_picked_quality": req.get("review_picked_quality"),
                "picked_set": _picked_set_from_packet(req) if req else None,
                "picked_image_advisories": resp.get("picked_image_advisories"),
                "viewed_image_ids": resp.get("viewed_image_ids"),
                "vision_used": resp.get("vision_used"),
            }
        )

    text = json.dumps(report, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
