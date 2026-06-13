"""Stale-state fingerprint checks for agent cull review groups."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from modules import db

ImageState = tuple[int | None, str | None]


def _parse_json_field(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def state_snapshot_from_packet(packet: dict[str, Any]) -> dict[int, ImageState]:
    out: dict[int, ImageState] = {}
    for img in packet.get("images") or []:
        if not isinstance(img, dict) or "id" not in img:
            continue
        iid = int(img["id"])
        pick = img.get("pick_status")
        try:
            pick_status = int(pick) if pick is not None else None
        except (TypeError, ValueError):
            pick_status = None
        cull = img.get("cull_decision")
        cull_decision = str(cull) if cull is not None else None
        out[iid] = (pick_status, cull_decision)
    return out


def compute_state_fingerprint(states: dict[int, ImageState]) -> str:
    payload = [
        {"id": iid, "pick_status": ps, "cull_decision": cd}
        for iid, (ps, cd) in sorted(states.items())
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_current_image_states(image_ids: list[int]) -> dict[int, ImageState]:
    if not image_ids:
        return {}
    connector = db.get_connector()
    placeholders = ",".join("?" * len(image_ids))
    rows = connector.query_all(
        f"SELECT id, pick_status, cull_decision FROM images WHERE id IN ({placeholders})",
        tuple(image_ids),
    )
    out: dict[int, ImageState] = {}
    for row in rows or []:
        iid = int(row["id"])
        pick = row.get("pick_status")
        try:
            pick_status = int(pick) if pick is not None else None
        except (TypeError, ValueError):
            pick_status = None
        cull = row.get("cull_decision")
        cull_decision = str(cull) if cull is not None else None
        out[iid] = (pick_status, cull_decision)
    return out


def check_group_staleness(group_id: int) -> bool:
    """Return True when live image state no longer matches the stored review packet."""
    row = db.get_connector().query_one(
        "SELECT request_json FROM agent_cull_review_groups WHERE id = ?",
        (group_id,),
    )
    if not row:
        return True
    packet = _parse_json_field(row.get("request_json"))
    if not packet:
        return True
    expected = state_snapshot_from_packet(packet)
    if not expected:
        return True
    current = load_current_image_states(list(expected.keys()))
    if set(current.keys()) != set(expected.keys()):
        return True
    return compute_state_fingerprint(expected) != compute_state_fingerprint(current)
