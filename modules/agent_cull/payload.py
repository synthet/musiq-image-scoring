"""Build compact agent review packets from stack member rows."""

from __future__ import annotations

import hashlib
import logging
import math
import os
from statistics import mean, pstdev
from typing import Any

from modules.agent_cull.config import (
    PROMPT_TEMPLATE_VERSION,
    REQUEST_SCHEMA_VERSION,
    AgentCullConfig,
)
from modules.agent_cull.discovery import ReviewUnit, classify_image_status

try:  # Pillow is a core dep; guard so packet build never hard-fails on import
    from PIL import Image
except Exception:  # pragma: no cover - environment without Pillow
    Image = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

SCORE_FIELDS = ("score_general", "score_technical", "score_aesthetic", "score")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _z_scores(values: list[float | None]) -> list[float | None]:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return [None if v is None else 0.0 for v in values]
    mu = mean(clean)
    try:
        sigma = pstdev(clean)
    except Exception:
        sigma = 0.0
    if sigma == 0:
        return [0.0 if v is not None else None for v in values]
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            out.append((v - mu) / sigma)
    return out


def _display_path(file_path: str | None) -> str | None:
    if not file_path:
        return None
    return os.path.basename(str(file_path))


def _keywords_list(row: dict[str, Any]) -> list[str]:
    raw = row.get("keywords") or []
    if isinstance(raw, str):
        return [k.strip() for k in raw.split(",") if k.strip()]
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]
    return []


def _downscale_cache_dir(max_edge: int) -> str:
    """Deterministic cache dir for agent-review downscaled thumbnails."""
    try:
        from modules.thumbnails import canonical_thumbnails_dir

        base = canonical_thumbnails_dir()
    except Exception:  # pragma: no cover - fallback if thumbnails module unavailable
        from modules.config import BASE_DIR

        base = os.path.join(str(BASE_DIR), "thumbnails")
    return os.path.join(base, "agent_review", str(int(max_edge)))


def _prepare_thumbnail(
    thumb_path: str, max_edge: int
) -> tuple[str, int | None, int | None, bool]:
    """Return ``(path, width, height, downscaled)`` for an agent-review thumbnail.

    When ``max_edge > 0`` and the source's longest edge exceeds it, a downscaled
    JPEG is written into a deterministic cache dir (idempotent across runs) and
    that path is returned so the agent loads a smaller image. Smaller sources are
    passed through untouched. On any failure (or Pillow unavailable) the original
    path is returned with no dimensions so the packet is never broken.
    """
    if Image is None or max_edge <= 0:
        return thumb_path, None, None, False
    try:
        with Image.open(thumb_path) as img:
            width, height = img.size
            if max(width, height) <= max_edge:
                return thumb_path, int(width), int(height), False
            digest = hashlib.sha1(
                f"{os.path.abspath(thumb_path)}|{int(max_edge)}".encode()
            ).hexdigest()
            cache_dir = _downscale_cache_dir(max_edge)
            out_path = os.path.join(cache_dir, f"{digest}.jpg")
            if not os.path.isfile(out_path):
                os.makedirs(cache_dir, exist_ok=True)
                resized = img.convert("RGB")
                resized.thumbnail((max_edge, max_edge))
                tmp_path = f"{out_path}.tmp"
                resized.save(tmp_path, "JPEG", quality=85)
                os.replace(tmp_path, out_path)
            with Image.open(out_path) as out_img:
                out_w, out_h = out_img.size
            return out_path, int(out_w), int(out_h), True
    except Exception:
        logger.debug(
            "agent cull thumbnail downscale failed for %s", thumb_path, exc_info=True
        )
        return thumb_path, None, None, False


def build_review_packet(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    cfg: AgentCullConfig,
) -> dict[str, Any]:
    images_payload: list[dict[str, Any]] = []
    thumbnail_manifest: list[dict[str, Any]] = []

    for image_id in unit.image_ids:
        row = dict(rows_by_id.get(image_id) or {})
        row["id"] = image_id
        scores_raw = {field: _safe_float(row.get(field)) for field in SCORE_FIELDS}
        general_vals = [_safe_float(rows_by_id.get(i, {}).get("score_general")) for i in unit.image_ids]
        z_general = _z_scores(general_vals)
        idx = list(unit.image_ids).index(image_id)
        normalized = {
            "score_general_z": z_general[idx] if idx < len(z_general) else None,
        }
        effective = classify_image_status(row, decision_source=cfg.decision_source)
        thumb_path = row.get("thumbnail_path") or row.get("thumbnail_path_win")
        entry = {
            "id": image_id,
            "file_name": row.get("file_name") or _display_path(row.get("file_path")),
            "display_path": _display_path(row.get("file_path")),
            "stack_id": unit.stack_id,
            "sub_stack_id": unit.sub_stack_id,
            "pick_status": row.get("pick_status"),
            "cull_decision": row.get("cull_decision"),
            "effective_status": effective,
            "scores": scores_raw,
            "scores_normalized": normalized,
            "keywords": _keywords_list(row),
            "species_tags": [k for k in _keywords_list(row) if k.lower().startswith("species:")],
            "exif": {
                "make": row.get("make"),
                "model": row.get("model"),
                "lens_model": row.get("lens_model"),
                "date_time_original": row.get("date_time_original"),
                "orientation": row.get("orientation"),
            },
            "file_type": row.get("file_type"),
            "technical": {
                "blur": _safe_float(row.get("blur")),
                "overexposed": _safe_float(row.get("overexposed")),
                "underexposed": _safe_float(row.get("underexposed")),
            },
            "similarity": {
                "embedding_outlier_z": _safe_float(row.get("embedding_outlier_z")),
            },
            "usable": bool(row.get("usable", True)),
        }
        images_payload.append(entry)
        if cfg.agent.include_thumbnails and thumb_path and os.path.isfile(str(thumb_path)):
            max_edge = int(cfg.agent.max_thumbnail_edge_px)
            prepared_path, thumb_w, thumb_h, downscaled = _prepare_thumbnail(
                str(thumb_path), max_edge
            )
            manifest_entry: dict[str, Any] = {
                "image_id": image_id,
                "path": prepared_path,
                "mode": cfg.agent.thumbnail_mode,
                "max_edge_px": max_edge,
                "width": thumb_w,
                "height": thumb_h,
                "downscaled": downscaled,
            }
            if downscaled:
                manifest_entry["source_path"] = str(thumb_path)
            thumbnail_manifest.append(manifest_entry)

    return {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "review_unit": {
            "stack_id": unit.stack_id,
            "sub_stack_id": unit.sub_stack_id,
            "review_unit_key": unit.review_unit_key,
            "image_count": len(unit.image_ids),
            "picked_count": len(unit.picked_ids),
            "rejected_count": len(unit.rejected_ids),
            "neutral_count": len(unit.neutral_ids),
            "usable_count": len(unit.usable_ids),
            "hierarchy_tier": unit.hierarchy_tier,
        },
        "policy": {
            "max_group_size": cfg.max_group_size,
            "min_agent_confidence": cfg.min_agent_confidence,
            "min_group_confidence": cfg.min_group_confidence,
            "decision_source": cfg.decision_source,
            "never_remove_rules": [
                "no_picked_images",
                "picked_lt_rejected",
                "low_confidence",
                "uncertain",
                "unique_subject_or_species",
                "higher_technical_quality",
                "unreadable_preview",
            ],
        },
        "images": images_payload,
        "picked_image_ids": list(unit.picked_ids),
        "rejected_image_ids": list(unit.rejected_ids),
        "thumbnail_manifest": thumbnail_manifest,
        "scores_normalized": True,
    }
