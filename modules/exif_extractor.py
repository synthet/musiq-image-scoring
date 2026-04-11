"""
EXIF metadata extraction for caching in IMAGE_EXIF table.

Uses exiftool -j (JSON output) to extract standard tags. Maps ExifTool tag names
to IMAGE_EXIF column names. Requires exiftool in PATH.
"""

import json
import logging
import os
import subprocess
from pathlib import Path

from modules import utils

logger = logging.getLogger(__name__)

_EXIFTOOL_PATH = None


def _get_exiftool_path():
    global _EXIFTOOL_PATH
    if _EXIFTOOL_PATH is None:
        _EXIFTOOL_PATH = __import__("shutil").which("exiftool")
    return _EXIFTOOL_PATH


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
    ]

    try:
        cmd = [exiftool, "-j", "-s"] + [f"-{t}" for t in tags_to_fetch] + [resolved]
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
            # Only set if not already set (first wins for lens fallbacks)
            if our_col not in out:
                out[our_col] = val

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
    return db.upsert_image_exif(image_id, data)


def backfill_exif_dates(limit: int | None = None) -> dict:
    """
    Re-extract EXIF dates for image_exif rows where date_time_original IS NULL.

    This repairs rows affected by the _parse_exif_timestamp truncation bug
    (s[:len(fmt)] instead of s[:min_len]). Only touches date columns —
    all other EXIF fields are left untouched via a full upsert.

    Args:
        limit: Optional max number of rows to process (for staged rollouts).

    Returns:
        dict with keys: checked, updated, skipped, errors.
    """
    from modules import db

    limit_clause = f" LIMIT {int(limit)}" if limit else ""
    rows = db.get_connector().query(
        f"""SELECT ex.image_id, i.file_path
            FROM image_exif ex
            JOIN images i ON i.id = ex.image_id
            WHERE ex.date_time_original IS NULL
            ORDER BY ex.image_id{limit_clause}"""
    )

    stats = {"checked": 0, "updated": 0, "skipped": 0, "errors": 0}
    for row in rows:
        stats["checked"] += 1
        image_id = row["image_id"]
        file_path = row["file_path"]
        try:
            data = extract_exif(file_path, image_id)
            if not data or ("date_time_original" not in data and "create_date" not in data):
                stats["skipped"] += 1
                continue
            if db.upsert_image_exif(image_id, data):
                stats["updated"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            logger.warning("backfill_exif_dates failed for image_id %s: %s", image_id, e)
            stats["errors"] += 1

    logger.info("backfill_exif_dates: %s", stats)
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
