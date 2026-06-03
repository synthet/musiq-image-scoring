"""EXIF exposure consistency metrics (stack-level heuristics)."""

from __future__ import annotations

import re
from typing import Any

from modules import db
from modules.culling_analytics._common import STACK_MEMBER_CAP, images_folder_filter

_BURST_SECONDS = 2.0


def _parse_exposure_time(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).strip()
    if "/" in s:
        parts = s.split("/")
        try:
            num, den = float(parts[0]), float(parts[1])
            return num / den if den else None
        except (ValueError, IndexError):
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_f_number(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).strip().lower().lstrip("f")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"([\d.]+)", s)
        return float(m.group(1)) if m else None


def _exposure_similarity_score(rows: list[dict[str, Any]]) -> float:
    """Heuristic 0–1 score from EXIF field agreement."""
    if len(rows) < 2:
        return 1.0
    same_make = len({r.get("make") for r in rows if r.get("make")}) <= 1
    same_lens = len({r.get("lens_model") for r in rows if r.get("lens_model")}) <= 1
    iso_vals = [r.get("iso") for r in rows if r.get("iso") is not None]
    iso_range = (max(iso_vals) - min(iso_vals)) if iso_vals else 0
    fn_vals = [_parse_f_number(r.get("f_number")) for r in rows]
    fn_vals = [v for v in fn_vals if v is not None]
    fn_spread = (max(fn_vals) - min(fn_vals)) if len(fn_vals) >= 2 else 0.0
    score = 0.0
    score += 0.35 if same_make else 0.0
    score += 0.25 if same_lens else 0.0
    score += 0.20 if iso_range <= 400 else max(0.0, 0.20 - iso_range / 4000.0)
    score += 0.20 if fn_spread <= 1.0 else max(0.0, 0.20 - fn_spread / 5.0)
    return min(1.0, max(0.0, score))


def compute_library_exposure(folder_id: int | None) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id, alias="i")
    conn = db.get_connector()
    cov = conn.query_one(
        f"""
        SELECT
            COUNT(*)::int AS total_images,
            COUNT(e.image_id)::int AS with_exif
        FROM images i
        LEFT JOIN image_exif e ON e.image_id = i.id
        WHERE 1=1{folder_clause}
        """,
        tuple(params),
    )
    total = int((cov or {}).get("total_images") or 0)
    with_exif = int((cov or {}).get("with_exif") or 0)
    coverage_pct = round(100.0 * with_exif / total, 2) if total else 0.0

    stack_ids = conn.query(
        f"""
        SELECT DISTINCT i.stack_id
        FROM images i
        WHERE i.stack_id IS NOT NULL{folder_clause}
        LIMIT 100
        """,
        tuple(params),
    )
    warnings: list[str] = []
    burst_like = bracket_like = mixed_camera = 0
    for sid_row in stack_ids:
        sid = int(sid_row["stack_id"])
        detail = compute_stack_exposure(sid)
        if detail.get("likely_burst"):
            burst_like += 1
        if detail.get("likely_bracket"):
            bracket_like += 1
        for w in detail.get("warnings") or []:
            warnings.append(f"stack:{sid}:{w}")
            if "mixed_camera" in w:
                mixed_camera += 1

    return {
        "coverage_pct": coverage_pct,
        "images_with_exif": with_exif,
        "total_images": total,
        "stacks_sampled": len(stack_ids),
        "likely_burst_stacks": burst_like,
        "likely_bracket_stacks": bracket_like,
        "mixed_camera_lens_stacks": mixed_camera,
        "warnings_sample": warnings[:30],
        "missing_fields_note": "metering_mode, white_balance, exposure_mode not in image_exif schema",
    }


def compute_stack_exposure(stack_id: int) -> dict[str, Any]:
    conn = db.get_connector()
    rows = conn.query(
        """
        SELECT
            e.make, e.model, e.lens_model, e.focal_length, e.f_number,
            e.exposure_time, e.iso, e.exposure_compensation,
            e.date_time_original, e.orientation, e.flash
        FROM images i
        JOIN image_exif e ON e.image_id = i.id
        WHERE i.stack_id = ?
        ORDER BY i.id
        LIMIT ?
        """,
        (stack_id, STACK_MEMBER_CAP),
    )
    truncated = len(rows) >= STACK_MEMBER_CAP
    if len(rows) < 2:
        return {
            "member_count": len(rows),
            "truncated": truncated,
            "exposure_similarity_score": 1.0 if rows else None,
            "likely_burst": False,
            "likely_bracket": False,
            "warnings": [],
        }

    makes = {r.get("make") for r in rows if r.get("make")}
    lenses = {r.get("lens_model") for r in rows if r.get("lens_model")}
    iso_vals = [int(r["iso"]) for r in rows if r.get("iso") is not None]
    exp_times = [_parse_exposure_time(r.get("exposure_time")) for r in rows]
    exp_times = [t for t in exp_times if t is not None]
    fn_vals = [_parse_f_number(r.get("f_number")) for r in rows]
    fn_vals = [v for v in fn_vals if v is not None]

    warnings: list[str] = []
    if len(makes) > 1:
        warnings.append("mixed_camera")
    if len(lenses) > 1:
        warnings.append("mixed_lens")

    likely_burst = False
    dates = [r.get("date_time_original") for r in rows if r.get("date_time_original")]
    if len(dates) >= 2:
        try:
            from datetime import datetime

            parsed = []
            for d in dates:
                if isinstance(d, datetime):
                    parsed.append(d)
                else:
                    parsed.append(datetime.fromisoformat(str(d).replace("Z", "+00:00")))
            span = (max(parsed) - min(parsed)).total_seconds()
            likely_burst = span <= _BURST_SECONDS and len(makes) <= 1
        except (TypeError, ValueError):
            likely_burst = False

    likely_bracket = False
    if iso_vals and fn_vals:
        iso_spread = max(iso_vals) - min(iso_vals)
        fn_spread = max(fn_vals) - min(fn_vals) if len(fn_vals) >= 2 else 0.0
        likely_bracket = iso_spread > 0 and fn_spread < 0.2 and len(makes) <= 1

    sim = _exposure_similarity_score(rows)
    return {
        "member_count": len(rows),
        "truncated": truncated,
        "same_camera_pct": round(100.0 / len(rows) * sum(1 for r in rows if r.get("make") == next(iter(makes))), 2) if len(makes) == 1 else 0.0,
        "same_lens_pct": round(100.0 / len(rows) * sum(1 for r in rows if r.get("lens_model") == next(iter(lenses))), 2) if len(lenses) == 1 else 0.0,
        "iso_min": min(iso_vals) if iso_vals else None,
        "iso_max": max(iso_vals) if iso_vals else None,
        "f_number_min": min(fn_vals) if fn_vals else None,
        "f_number_max": max(fn_vals) if fn_vals else None,
        "exposure_similarity_score": round(sim, 4),
        "likely_burst": likely_burst,
        "likely_bracket": likely_bracket,
        "warnings": warnings,
    }
