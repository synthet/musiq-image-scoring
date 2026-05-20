"""GPS / geolocation consistency metrics."""

from __future__ import annotations

import math
from typing import Any

from modules import db
from modules.culling_analytics._common import STACK_MEMBER_CAP, images_folder_filter

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def compute_library_gps(folder_id: int | None) -> dict[str, Any]:
    folder_clause, params = images_folder_filter(folder_id, alias="i")
    conn = db.get_connector()
    row = conn.query_one(
        f"""
        SELECT
            COUNT(*)::int AS total,
            COUNT(*) FILTER (
                WHERE e.gps_latitude IS NOT NULL AND e.gps_longitude IS NOT NULL
            )::int AS with_gps
        FROM images i
        LEFT JOIN image_exif e ON e.image_id = i.id
        WHERE 1=1{folder_clause}
        """,
        tuple(params),
    )
    total = int((row or {}).get("total") or 0)
    with_gps = int((row or {}).get("with_gps") or 0)
    missing = total - with_gps

    stack_row = conn.query_one(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE gps_cnt = stack_size AND stack_size > 0)::int AS all_gps,
            COUNT(*) FILTER (WHERE gps_cnt > 0 AND gps_cnt < stack_size)::int AS partial_gps,
            COUNT(*)::int AS stacks
        FROM (
            SELECT
                i.stack_id,
                COUNT(*)::int AS stack_size,
                COUNT(*) FILTER (
                    WHERE e.gps_latitude IS NOT NULL AND e.gps_longitude IS NOT NULL
                )::int AS gps_cnt
            FROM images i
            LEFT JOIN image_exif e ON e.image_id = i.id
            WHERE i.stack_id IS NOT NULL{folder_clause}
            GROUP BY i.stack_id
        ) s
        """,
        tuple(params),
    )

    return {
        "total_images": total,
        "with_gps": with_gps,
        "missing_gps": missing,
        "with_gps_pct": round(100.0 * with_gps / total, 2) if total else 0.0,
        "stacks_all_gps": int((stack_row or {}).get("all_gps") or 0),
        "stacks_partial_gps": int((stack_row or {}).get("partial_gps") or 0),
        "privacy_note": "Responses include coordinates only; no reverse geocode in API.",
    }


def compute_stack_gps(stack_id: int) -> dict[str, Any]:
    conn = db.get_connector()
    rows = conn.query(
        """
        SELECT e.gps_latitude AS lat, e.gps_longitude AS lon
        FROM images i
        JOIN image_exif e ON e.image_id = i.id
        WHERE i.stack_id = ?
          AND e.gps_latitude IS NOT NULL
          AND e.gps_longitude IS NOT NULL
        LIMIT ?
        """,
        (stack_id, STACK_MEMBER_CAP),
    )
    if not rows:
        return {"with_gps": 0, "centroid": None, "max_distance_m": None, "bbox": None}

    lats = [float(r["lat"]) for r in rows]
    lons = [float(r["lon"]) for r in rows]
    centroid = {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)}
    max_d = 0.0
    for i in range(len(lats)):
        for j in range(i + 1, len(lats)):
            max_d = max(max_d, haversine_m(lats[i], lons[i], lats[j], lons[j]))

    return {
        "with_gps": len(rows),
        "centroid": centroid,
        "max_distance_m": round(max_d, 2),
        "bbox": {
            "sw": [min(lats), min(lons)],
            "ne": [max(lats), max(lons)],
        },
    }
