"""
DB + file operations for per-image forward / reverse geocoding.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

from modules import db
from modules import exif_extractor
from modules import utils
from modules import xmp
from modules.geocoding.provider import get_geocoding_provider
from modules.geocoding.types import LocationParts

logger = logging.getLogger(__name__)


def _slim_location_parts(parts: LocationParts) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k, v in parts.items():
        if k == "raw":
            continue
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        d[k] = v
    return d


def _merge_exif_with_location(
    image_id: int, updates: dict[str, Any]
) -> bool:
    ex = db.get_image_exif(image_id) or {}
    merged = exif_extractor._merge_exif_for_upsert(ex, updates)  # noqa: SLF001
    return db.upsert_image_exif(image_id, merged)


def _file_path_for_image(image_id: int) -> str | None:
    row = db.get_connector().query_one("SELECT file_path FROM images WHERE id = ?", (image_id,))
    if not row:
        return None
    fp = row.get("file_path")
    return str(fp) if fp else None


def ensure_gps_for_image(image_id: int) -> tuple[Optional[float], Optional[float], str | None]:
    """
    Return (lat, lon, file_path) from cache or exiftool. Path is DB file_path.
    """
    file_path = _file_path_for_image(image_id)
    if not file_path:
        return None, None, None
    ex = db.get_image_exif(image_id) or {}
    lat, lon = ex.get("gps_latitude"), ex.get("gps_longitude")
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), str(file_path)
        except (TypeError, ValueError):
            pass
    if not file_path:
        return None, None, None
    resolved = utils.resolve_file_path(str(file_path), image_id) or utils.convert_path_to_local(
        str(file_path)
    )
    if not resolved or not __import__("os").path.exists(resolved):
        return None, None, str(file_path)
    data = exif_extractor.extract_exif(resolved, image_id)
    if not data:
        return None, None, str(file_path)
    ex2 = db.get_image_exif(image_id) or {}
    merged = exif_extractor._merge_exif_for_upsert(ex2, data)  # noqa: SLF001  # merge helper
    db.upsert_image_exif(image_id, merged)
    ex3 = db.get_image_exif(image_id) or {}
    gla, glo = ex3.get("gps_latitude"), ex3.get("gps_longitude")
    if gla is None or glo is None:
        return None, None, str(file_path)
    try:
        return float(gla), float(glo), str(file_path)
    except (TypeError, ValueError):
        return None, None, str(file_path)


def geocode_image_reverse(
    image_id: int,
    *,
    force: bool = False,
    dry_run: bool = False,
    write_embedded: bool = False,
    write_sidecar: bool = False,
) -> dict[str, Any]:
    prov = get_geocoding_provider()
    if not prov:
        return {"ok": False, "error": "geocoding disabled or not configured (geocoding.enabled, user_agent)"}

    lat, lon, path = ensure_gps_for_image(image_id)
    if lat is None or lon is None or not path:
        return {"ok": False, "error": "no GPS coordinates for this image; add GPS in EXIF first"}

    ex = db.get_image_exif(image_id) or {}
    if (
        not force
        and ex.get("location_resolved")
        and ex.get("geocoded_at")
    ):
        return {
            "ok": True,
            "cached": True,
            "location_resolved": ex.get("location_resolved"),
            "geocoded_at": ex.get("geocoded_at"),
            "geocode_provider": ex.get("geocode_provider"),
        }

    parts = prov.reverse(lat, lon)
    if not parts:
        return {"ok": False, "error": "reverse geocoding returned no result"}

    stored = _slim_location_parts(parts)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "location_resolved": stored,
            "geocode_provider": prov.name,
        }

    now = datetime.datetime.now()
    ok = _merge_exif_with_location(
        image_id,
        {
            "location_resolved": stored,
            "geocoded_at": now,
            "geocode_provider": prov.name,
        },
    )
    if not ok:
        return {"ok": False, "error": "failed to save image_exif"}

    loc_label = (parts.get("display_name") or stored.get("city") or "") if parts else None
    wrote = False
    if write_embedded or write_sidecar:
        wrote = xmp.write_gps_and_location_to_files(
            path,
            float(lat),
            float(lon),
            city=stored.get("city") or None,
            state=stored.get("state") or None,
            country=stored.get("country") or None,
            location_label=loc_label if isinstance(loc_label, str) and loc_label else None,
            write_embedded=write_embedded,
            write_sidecar=write_sidecar,
        )
    ex_out = db.get_image_exif(image_id) or {}
    return {
        "ok": True,
        "cached": False,
        "location_resolved": ex_out.get("location_resolved"),
        "geocoded_at": ex_out.get("geocoded_at"),
        "geocode_provider": ex_out.get("geocode_provider"),
        "wrote_to_files": wrote,
    }


def geocode_image_forward(
    image_id: int,
    address_query: str,
    *,
    dry_run: bool = False,
    write_embedded: bool = True,
    write_sidecar: bool = True,
) -> dict[str, Any]:
    prov = get_geocoding_provider()
    if not prov:
        return {"ok": False, "error": "geocoding disabled or not configured (geocoding.enabled, user_agent)"}
    q = (address_query or "").strip()
    if not q:
        return {"ok": False, "error": "empty address query"}

    out = prov.forward(q)
    if not out:
        return {"ok": False, "error": "no geocoding result for that address"}
    lat, lon, parts = out

    file_path = _file_path_for_image(image_id)
    if not file_path:
        return {"ok": False, "error": f"image not found: {image_id}"}

    stored = _slim_location_parts(parts) if parts else {}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "gps_latitude": lat,
            "gps_longitude": lon,
            "location_resolved": stored,
            "geocode_provider": prov.name,
        }

    now = datetime.datetime.now()
    ok = _merge_exif_with_location(
        image_id,
        {
            "gps_latitude": float(lat),
            "gps_longitude": float(lon),
            "gps_position_source": "geocode",
            "location_resolved": stored,
            "geocoded_at": now,
            "geocode_provider": prov.name,
        },
    )
    if not ok:
        return {"ok": False, "error": "failed to save image_exif"}

    loc_label = (parts.get("display_name") if parts else None) or q
    wrote = False
    if write_embedded or write_sidecar:
        city = (stored.get("city") if stored else None) or None
        state = (stored.get("state") if stored else None) or None
        country = (stored.get("country") if stored else None) or None
        wrote = xmp.write_gps_and_location_to_files(
            file_path,
            float(lat),
            float(lon),
            city=city,
            state=state,
            country=country,
            location_label=loc_label if loc_label else None,
            write_embedded=write_embedded,
            write_sidecar=write_sidecar,
        )
    ex_out = db.get_image_exif(image_id) or {}
    return {
        "ok": True,
        "gps_latitude": ex_out.get("gps_latitude"),
        "gps_longitude": ex_out.get("gps_longitude"),
        "location_resolved": ex_out.get("location_resolved"),
        "geocoded_at": ex_out.get("geocoded_at"),
        "geocode_provider": ex_out.get("geocode_provider"),
        "wrote_to_files": wrote,
    }
