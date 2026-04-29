"""
EXIF metadata extraction for caching in IMAGE_EXIF table.

Uses exiftool -j (JSON output) to extract standard tags. Maps ExifTool tag names
to IMAGE_EXIF column names. Requires exiftool in PATH.
"""

import json
import logging
import os
import subprocess

from modules import utils

logger = logging.getLogger(__name__)

_EXIFTOOL_PATH = None


def _get_exiftool_path():
    global _EXIFTOOL_PATH
    if _EXIFTOOL_PATH is None:
        _EXIFTOOL_PATH = __import__("shutil").which("exiftool")
    return _EXIFTOOL_PATH


def get_exiftool_path():
    """Return path to exiftool binary, or None if not on PATH."""
    return _get_exiftool_path()


def get_exiftool_timeout_seconds(*, write: bool = False) -> int:
    """
    Subprocess timeout for exiftool. Writes (especially large RAW on slow mounts)
    need more time than read-only JSON extraction.
    Override via config: exif.exiftool_read_timeout_seconds / exif.exiftool_write_timeout_seconds.
    """
    from modules.config import get_config_value

    key = "exif.exiftool_write_timeout_seconds" if write else "exif.exiftool_read_timeout_seconds"
    default = 120 if write else 30
    raw = get_config_value(key, default)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(5, min(n, 3600))


# ExifTool tag names -> our IMAGE_EXIF column names
_EXIF_TAG_MAP = {
    "Make": "make",
    "Model": "model",
    "LensModel": "lens_model",
    "Lens": "lens_model",  # fallback
    "LensID": "lens_model",
    "LensType": "lens_model",
    "FocalLength": "focal_length",
    "FocalLengthIn35mmFormat": "focal_length_35mm",
    "DateTimeOriginal": "date_time_original",
    "CreateDate": "create_date",
    "ExposureTime": "exposure_time",
    "FNumber": "f_number",
    "ISO": "iso",
    "ExposureCompensation": "exposure_compensation",
    "ImageWidth": "image_width",
    "ImageHeight": "image_height",
    "Orientation": "orientation",
    "Flash": "flash",
    "ImageUniqueID": "image_unique_id",
    "ShutterCount": "shutter_count",
    "SubSecTimeOriginal": "sub_sec_time_original",
    "GPSLatitude": "gps_latitude",
    "GPSLongitude": "gps_longitude",
    "GPSAltitude": "gps_altitude",
}


def extract_exif(image_path: str, image_id: int = None) -> dict | None:
    """
    Extract EXIF metadata from an image file using exiftool.

    Args:
        image_path: Path to the image file (or XMP sidecar's base path)
        image_id: Optional image_id for resolve_file_path batch cache

    Returns:
        Dict with keys matching IMAGE_EXIF columns, or None on failure.
        Lens fallback: LensModel > Lens > LensID > LensType
    """
    exiftool = _get_exiftool_path()
    if not exiftool:
        logger.debug("exiftool not found in PATH")
        return None

    resolved = utils.resolve_file_path(image_path, image_id)
    if not resolved:
        resolved = utils.convert_path_to_local(image_path)
    if not resolved or not os.path.exists(resolved):
        logger.debug("File not found: %s", image_path)
        return None

    tags_to_fetch = [
        "Make", "Model", "LensModel", "Lens", "LensID", "LensType",
        "FocalLength", "FocalLengthIn35mmFormat",
        "DateTimeOriginal", "CreateDate",
        "ExposureTime", "FNumber", "ISO", "ExposureCompensation",
        "ImageWidth", "ImageHeight", "Orientation", "Flash",
        "ImageUniqueID", "ShutterCount", "SubSecTimeOriginal",
        "GPSLatitude", "GPSLongitude", "GPSAltitude",
    ]

    try:
        # -n: print numeric values (e.g. decimal degrees for GPS)
        cmd = [exiftool, "-j", "-s", "-n", "-ee"] + [f"-{t}" for t in tags_to_fetch] + [resolved]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=get_exiftool_timeout_seconds(write=False)
        )
        if result.returncode != 0:
            logger.debug("exiftool failed for %s: %s", image_path, result.stderr)
            return None

        data = json.loads(result.stdout)
        if not data or not isinstance(data, list):
            return None

        raw = data[0]
        out = {}

        for exif_tag, our_col in _EXIF_TAG_MAP.items():
            val = raw.get(exif_tag)
            if val is None or (isinstance(val, str) and val.strip() in ("-", "")):
                continue
            if our_col in ("gps_latitude", "gps_longitude", "gps_altitude"):
                if isinstance(val, (int, float)):
                    if our_col not in out:
                        out[our_col] = float(val)
                else:
                    try:
                        f = float(str(val).replace(",", ".").strip())
                        if our_col not in out:
                            out[our_col] = f
                    except (ValueError, TypeError):
                        pass
            else:
                # Only set if not already set (first wins for lens fallbacks)
                if our_col not in out:
                    out[our_col] = val

        if any(k in out for k in ("gps_latitude", "gps_longitude")):
            out["gps_position_source"] = "exif"

        # Lens fallback order: LensModel > Lens > LensID > LensType
        if "lens_model" not in out:
            for tag in ("LensModel", "Lens", "LensID", "LensType"):
                v = raw.get(tag)
                if v and str(v).strip() not in ("-", ""):
                    out["lens_model"] = v
                    break

        return out if out else None

    except subprocess.TimeoutExpired:
        logger.warning("exiftool timeout for %s", image_path)
        return None
    except json.JSONDecodeError as e:
        logger.warning("exiftool JSON parse error for %s: %s", image_path, e)
        return None
    except Exception as e:
        logger.warning("extract_exif failed for %s: %s", image_path, e)
        return None


def extract_and_upsert_exif(image_path: str, image_id: int) -> bool:
    """
    Extract EXIF from image and upsert into IMAGE_EXIF.

    Returns True if extraction and upsert succeeded.
    """
    from modules import db

    data = extract_exif(image_path, image_id)
    if not data:
        return False
    existing = db.get_image_exif(image_id) or {}
    merged = _merge_exif_for_upsert(existing, data)
    return db.upsert_image_exif(image_id, merged)


def backfill_exif_dates(limit: int | None = None) -> dict:
    """
    Refresh EXIF + XMP caches for images that still have no effective capture date.

    Selects rows where COALESCE(ex.date_time_original, ex.create_date, xm.create_date)
    is NULL, then re-reads XMP sidecar and exiftool (-ee for embedded RAW metadata).

    Args:
        limit: Optional max rows per call (use for batching large libraries).

    Returns:
        dict: checked, updated, skipped_no_file, skipped_no_date, errors.
    """
    from modules import db
    from modules import xmp as xmp_mod

    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    rows = db.get_connector().query(
        f"""SELECT i.id AS image_id, i.file_path
            FROM images i
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            LEFT JOIN image_xmp xm ON xm.image_id = i.id
            WHERE COALESCE(ex.date_time_original, ex.create_date, xm.create_date) IS NULL
            ORDER BY i.id{limit_clause}"""
    )

    stats = {"checked": 0, "updated": 0, "skipped_no_file": 0, "skipped_no_date": 0, "errors": 0}
    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                resolved = utils.convert_path_to_local(file_path)
            if not resolved or not os.path.exists(resolved):
                stats["skipped_no_file"] += 1
                logger.debug("backfill skip image_id=%s: file not found (%s)", image_id, file_path)
                continue
            xmp_mod.extract_and_upsert_xmp(resolved, image_id)
            data = extract_exif(resolved, image_id)
            if data:
                existing = db.get_image_exif(image_id) or {}
                merged = _merge_exif_for_upsert(existing, data)
                if not db.upsert_image_exif(image_id, merged):
                    stats["errors"] += 1
                    continue
            exif_row = db.get_image_exif(image_id) or {}
            xmp_row = db.get_image_xmp(image_id) or {}
            if (
                exif_row.get("date_time_original")
                or exif_row.get("create_date")
                or xmp_row.get("create_date")
            ):
                stats["updated"] += 1
            else:
                stats["skipped_no_date"] += 1
                logger.debug(
                    "backfill skip image_id=%s: no capture date in EXIF or XMP (%s)",
                    image_id,
                    file_path,
                )
        except Exception as e:
            logger.warning("backfill_exif_dates failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1

    logger.info("backfill_exif_dates: %s", stats)
    return stats


# Keys accepted by db.upsert_image_exif (excluding image_id / extracted_at).
_IMAGE_EXIF_UPSERT_KEYS = (
    "make",
    "model",
    "lens_model",
    "focal_length",
    "focal_length_35mm",
    "date_time_original",
    "create_date",
    "exposure_time",
    "f_number",
    "iso",
    "exposure_compensation",
    "image_width",
    "image_height",
    "orientation",
    "flash",
    "image_unique_id",
    "shutter_count",
    "sub_sec_time_original",
    "gps_latitude",
    "gps_longitude",
    "gps_altitude",
    "gps_position_source",
    "location_resolved",
    "geocoded_at",
    "geocode_provider",
)


def _merge_exif_for_upsert(existing: dict | None, fresh: dict) -> dict:
    """Merge a full EXIF row with a fresh exiftool dict so partial extractions do not wipe columns."""
    merged: dict = {}
    if existing:
        for k in _IMAGE_EXIF_UPSERT_KEYS:
            if k in existing:
                merged[k] = existing[k]
    merged.update(fresh)
    return merged


def _exif_row_has_camera_and_lens(ex_row: dict | None) -> bool:
    if not ex_row:
        return False
    cam = (str(ex_row.get("model") or "").strip() or str(ex_row.get("make") or "").strip())
    lens = str(ex_row.get("lens_model") or "").strip()
    return bool(cam and lens)


def _exif_row_has_gps_coords(ex_row: dict | None) -> bool:
    if not ex_row:
        return False
    lat, lon = ex_row.get("gps_latitude"), ex_row.get("gps_longitude")
    if lat is None or lon is None:
        return False
    try:
        float(lat)
        float(lon)
    except (TypeError, ValueError):
        return False
    return True


def backfill_exif_camera_lens(
    limit: int | None = None,
    *,
    path_like: str | None = None,
) -> dict:
    """
    Re-extract EXIF from disk for rows missing camera and/or lens (image_exif.make/model or lens_model).

    Used when gallery backup/sync skips files because ``exif_model`` / ``exif_lens_model`` are empty.
    Requires ``exiftool`` on PATH. Merges with existing ``image_exif`` so partial tags do not NULL out
    other cached columns.

    Args:
        limit: Optional max rows per call.
        path_like: Optional SQL ``LIKE`` pattern on ``images.file_path`` (e.g. ``%/Photos/Z6ii/%``).

    Returns:
        dict: checked, updated, skipped_no_file, skipped_no_exif, skipped_still_missing, errors.
    """
    from modules import db

    path_clause = ""
    sql_params: tuple | None = None
    if path_like:
        path_clause = " AND i.file_path LIKE ?"
        sql_params = (path_like,)

    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    rows = db.get_connector().query(
        f"""SELECT i.id AS image_id, i.file_path
            FROM images i
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            WHERE (
                ex.image_id IS NULL
                OR COALESCE(
                    NULLIF(TRIM(COALESCE(ex.model, '')), ''),
                    NULLIF(TRIM(COALESCE(ex.make, '')), '')
                ) IS NULL
                OR NULLIF(TRIM(COALESCE(ex.lens_model, '')), '') IS NULL
            ){path_clause}
            ORDER BY i.id{limit_clause}""",
        sql_params,
    )

    stats = {
        "checked": 0,
        "updated": 0,
        "skipped_no_file": 0,
        "skipped_no_exif": 0,
        "skipped_still_missing": 0,
        "errors": 0,
    }
    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                resolved = utils.convert_path_to_local(file_path)
            if not resolved or not os.path.exists(resolved):
                stats["skipped_no_file"] += 1
                logger.debug("backfill_exif_camera_lens skip image_id=%s: file not found (%s)", image_id, file_path)
                continue

            existing = db.get_image_exif(image_id)
            fresh = extract_exif(resolved, image_id)
            if not fresh:
                stats["skipped_no_exif"] += 1
                logger.debug(
                    "backfill_exif_camera_lens skip image_id=%s: no EXIF from exiftool (%s)",
                    image_id,
                    file_path,
                )
                continue

            merged = _merge_exif_for_upsert(existing, fresh)
            if not db.upsert_image_exif(image_id, merged):
                stats["errors"] += 1
                continue

            exif_row = db.get_image_exif(image_id) or {}
            if _exif_row_has_camera_and_lens(exif_row):
                stats["updated"] += 1
            else:
                stats["skipped_still_missing"] += 1
                logger.debug(
                    "backfill_exif_camera_lens still missing camera/lens after upsert image_id=%s (%s)",
                    image_id,
                    file_path,
                )
        except Exception as e:
            logger.warning("backfill_exif_camera_lens failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1

    logger.info("backfill_exif_camera_lens: %s", stats)
    return stats


def backfill_exif_gps(
    limit: int | None = None,
    *,
    path_like: str | None = None,
) -> dict:
    """
    Re-extract EXIF from disk for rows missing ``gps_latitude`` / ``gps_longitude`` in ``image_exif``.

    Fills GPS from embedded/sidecar metadata where present. Requires ``exiftool`` on PATH.
    Merges with existing ``image_exif`` so reverse-geocode fields are not wiped when fresh EXIF lacks them.

    Args:
        limit: Optional max rows per call.
        path_like: Optional SQL ``LIKE`` pattern on ``images.file_path``.
    """
    from modules import db

    path_clause = ""
    sql_params: tuple | None = None
    if path_like:
        path_clause = " AND i.file_path LIKE ?"
        sql_params = (path_like,)

    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    rows = db.get_connector().query(
        f"""SELECT i.id AS image_id, i.file_path
            FROM images i
            LEFT JOIN image_exif ex ON ex.image_id = i.id
            WHERE (
                ex.image_id IS NULL
                OR ex.gps_latitude IS NULL
                OR ex.gps_longitude IS NULL
            ){path_clause}
            ORDER BY i.id{limit_clause}""",
        sql_params,
    )

    stats = {
        "checked": 0,
        "updated": 0,
        "skipped_no_file": 0,
        "skipped_no_exif": 0,
        "skipped_still_missing": 0,
        "errors": 0,
    }
    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            resolved = utils.resolve_file_path(file_path, image_id)
            if not resolved:
                resolved = utils.convert_path_to_local(file_path)
            if not resolved or not os.path.exists(resolved):
                stats["skipped_no_file"] += 1
                logger.debug("backfill_exif_gps skip image_id=%s: file not found (%s)", image_id, file_path)
                continue

            existing = db.get_image_exif(image_id)
            fresh = extract_exif(resolved, image_id)
            if not fresh:
                stats["skipped_no_exif"] += 1
                logger.debug(
                    "backfill_exif_gps skip image_id=%s: no EXIF from exiftool (%s)",
                    image_id,
                    file_path,
                )
                continue

            merged = _merge_exif_for_upsert(existing, fresh)
            if not db.upsert_image_exif(image_id, merged):
                stats["errors"] += 1
                continue

            exif_row = db.get_image_exif(image_id) or {}
            if _exif_row_has_gps_coords(exif_row):
                stats["updated"] += 1
            else:
                stats["skipped_still_missing"] += 1
                logger.debug(
                    "backfill_exif_gps still no GPS after upsert image_id=%s (%s)",
                    image_id,
                    file_path,
                )
        except Exception as e:
            logger.warning("backfill_exif_gps failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1

    logger.info("backfill_exif_gps: %s", stats)
    return stats


def write_image_unique_id(image_path: str, uuid_str: str) -> bool:
    """
    Write ImageUniqueID to EXIF using exiftool.
    This modifies the original file.
    """
    exiftool = _get_exiftool_path()
    if not exiftool:
        return False

    local_path = utils.convert_path_to_local(image_path)
    if not os.path.exists(local_path):
        return False

    try:
        # -overwrite_original avoids creating .original backup files
        # ImageUniqueID is a standard EXIF tag
        cmd = [exiftool, "-overwrite_original", f"-ImageUniqueID={uuid_str}", local_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=get_exiftool_timeout_seconds(write=True)
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to write ImageUniqueID to {image_path}: {e}")
        return False


def ensure_image_unique_id(image_path: str, provided_uuid: str = None) -> str | None:
    """
    Check if image has an ImageUniqueID. If not, write the provided one or generate a new one.
    
    Args:
        image_path: Local or remote path to image
        provided_uuid: Optional UUID to write if missing
        
    Returns:
        The existing or newly written UUID, or None on failure.
    """
    # 1. Check existing
    data = extract_exif(image_path)
    if data and data.get("image_unique_id"):
        return data["image_unique_id"]

    # 2. Need to write
    if not provided_uuid:
        from modules import db
        # We need some context for deterministic UUID if possible, but extract_exif 
        # already gave us most of it or we can just use random fallback via db utility
        provided_uuid = db.generate_image_uuid(data)

    if write_image_unique_id(image_path, provided_uuid):
        return provided_uuid

    return None
