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


def _advisory_targets(advisories: list[dict[str, Any]], image_id: int) -> list[dict[str, Any]]:
    return [a for a in advisories if int(a.get("image_id") or 0) == image_id]


def score_picked_advisory_metrics(
    live: dict[str, Any] | None,
    *,
    watchlist: list[int] | None = None,
    target_image_id: int = 195193,
) -> dict[str, Any]:
    """Score picked-image advisory outcomes for study matrix runs."""
    live = live or {}
    advisories = list(live.get("picked_image_advisories") or [])
    pass2 = live.get("picked_audit_pass2") or {}
    if not advisories and pass2.get("picked_image_advisories"):
        advisories = list(pass2.get("picked_image_advisories") or [])

    watch = [int(x) for x in (watchlist or live.get("watchlist") or [])]
    advisory_ids = {int(a.get("image_id") or 0) for a in advisories if a.get("image_id") is not None}
    target_rows = _advisory_targets(advisories, target_image_id)
    target_misfocus = any(
        str(a.get("issue") or "").lower() in ("misfocus", "blur") for a in target_rows
    )

    return {
        "advisory_count": len(advisories),
        "watchlist": watch,
        "watchlist_hit": bool(watch and advisory_ids.intersection(watch)),
        "advisory_gap": bool(watch) and len(advisories) == 0,
        f"{target_image_id}_advised": bool(target_rows),
        f"{target_image_id}_misfocus": target_misfocus,
        "advisory_image_ids": sorted(advisory_ids),
    }
