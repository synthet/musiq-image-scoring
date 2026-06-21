"""Deterministic picked-image quality hints for agent cull packets (research)."""

from __future__ import annotations

from typing import Any


def _score_val(row: dict[str, Any], key: str) -> float | None:
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    val = scores.get(key)
    if val is None:
        val = row.get(key)
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def build_picked_quality_hints(
    *,
    picked_ids: list[int],
    rows_by_id: dict[int, dict[str, Any]],
    images_payload: list[dict[str, Any]],
    score_technical_threshold: float = 0.75,
    clip_mid_low: float = 0.45,
    clip_mid_high: float = 0.60,
) -> dict[str, Any] | None:
    """Build watchlist + pairwise context for high-scoring picks needing vision audit."""
    if not picked_ids:
        return None

    payload_by_id = {int(img["id"]): img for img in images_payload if img.get("id") is not None}
    watchlist: list[int] = []
    watch_reasons: dict[str, str] = {}

    for iid in picked_ids:
        row = rows_by_id.get(iid) or {}
        img = payload_by_id.get(iid) or {}
        scores = img.get("scores") or {}
        st = scores.get("score_technical")
        if st is None:
            st = row.get("score_technical")
        clip = scores.get("clip_quality_v0")
        if clip is None and isinstance(img.get("model_scores"), dict):
            clip = img["model_scores"].get("clip_quality_v0")
        reasons: list[str] = []
        try:
            if st is not None and float(st) >= score_technical_threshold:
                reasons.append(f"score_technical={float(st):.3f}>={score_technical_threshold}")
        except (TypeError, ValueError):
            pass
        try:
            if clip is not None and clip_mid_low <= float(clip) <= clip_mid_high:
                reasons.append(f"clip_quality_v0={float(clip):.3f} mid-band")
        except (TypeError, ValueError):
            pass
        if reasons:
            watchlist.append(iid)
            watch_reasons[str(iid)] = "; ".join(reasons)

    if not watchlist:
        return None

    pairwise: dict[str, list[dict[str, Any]]] = {}
    compare_keys = ("topiq", "liqe", "spaq", "score_technical", "clip_quality_v0")
    for wid in watchlist:
        wimg = payload_by_id.get(wid) or {}
        wscores = wimg.get("scores") or {}
        alts: list[dict[str, Any]] = []
        for oid in picked_ids:
            if oid == wid:
                continue
            oimg = payload_by_id.get(oid) or {}
            oscores = oimg.get("scores") or {}
            better_on: list[str] = []
            for key in compare_keys:
                wv = wscores.get(key)
                ov = oscores.get(key)
                if wv is None or ov is None:
                    continue
                try:
                    if float(ov) > float(wv) + 0.02:
                        better_on.append(key)
                except (TypeError, ValueError):
                    continue
            if better_on:
                alts.append(
                    {
                        "image_id": oid,
                        "file_name": oimg.get("file_name"),
                        "better_on": better_on,
                    }
                )
        if alts:
            pairwise[str(wid)] = alts

    return {
        "score_technical_watchlist": watchlist,
        "watch_reasons": watch_reasons,
        "pairwise_sharper_picked": pairwise,
        "note": (
            "These picked ids have high score_technical and/or mid-band clip_quality_v0; "
            "verify subject focus in each thumbnail before returning picked_image_advisories: []."
        ),
    }
