"""Vision evidence scoring helpers for agent cull study runs."""

from __future__ import annotations

from typing import Any


def score_vision_evidence(
    probe: dict[str, Any],
    smoke: dict[str, Any] | None,
    live: dict[str, Any] | None,
) -> dict[str, Any]:
    score = {
        "manifest_ok": bool(probe.get("ok")),
        "smoke_ok": bool((smoke or {}).get("ok")),
        "smoke_visual": bool((smoke or {}).get("has_visual_language")),
        "vision_used": bool((live or {}).get("vision_used")),
        "viewed_count": len((live or {}).get("viewed_image_ids") or []),
    }
    score["verified"] = score["manifest_ok"] and (
        score["smoke_visual"] or score["vision_used"] or score["viewed_count"] > 0
    )
    return score
