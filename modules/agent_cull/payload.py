"""Build compact agent review packets from stack member rows."""

from __future__ import annotations

import hashlib
import logging
import math
import os
from statistics import mean, pstdev
from typing import Any

from modules.agent_cull.config import REQUEST_SCHEMA_VERSION, AgentCullConfig
from modules.agent_cull.mode_profiles import resolve_prompt_template_version
from modules.agent_cull.discovery import ReviewUnit, classify_image_status
from modules import thumbnails
from modules.db_legacy import get_batch_image_model_scores

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


def _model_score_normalized(entry: Any) -> float | None:
    if not isinstance(entry, dict):
        return None
    val = entry.get("normalized")
    if val is None:
        val = entry.get("raw_score")
    return _safe_float(val)


def _row_has_model_score(row: dict[str, Any], model_name: str) -> bool:
    return _model_score_normalized((row.get("model_scores") or {}).get(model_name)) is not None


def _outlier_z_from_mean_sim(mean_sim_by_id: dict[int, float]) -> dict[int, float]:
    """Per-image embedding outlier z-score from per-image mean cosine similarity.

    Higher z = the image is *more dissimilar* to its unit siblings (i.e. more
    visually unique). The ``block_embedding_outliers`` safety gate blocks removal
    when ``z >= outlier_z_threshold``. Pure + side-effect-free for unit testing.
    Needs at least 3 members for a meaningful spread; returns ``{}`` otherwise.
    """
    if len(mean_sim_by_id) < 3:
        return {}
    ids = list(mean_sim_by_id)
    sims = [mean_sim_by_id[i] for i in ids]
    mu = mean(sims)
    sigma = pstdev(sims)
    if sigma == 0:
        return {i: 0.0 for i in ids}
    return {i: (mu - mean_sim_by_id[i]) / sigma for i in ids}


def _fetch_unit_mean_cosine(image_ids: list[int]) -> dict[int, float]:
    """Per-image mean cosine similarity to the other unit members (default space).

    Best-effort: returns ``{}`` when there is no Postgres connector, no default
    embedding space, fewer than 3 members, or any query error — so packet build
    never hard-fails and the outlier gate simply stays inert without data.
    """
    if len(image_ids) < 3:
        return {}
    try:
        from modules import db
        from modules.culling_analytics.embeddings import get_default_embedding_space_id

        space_id = get_default_embedding_space_id()
        if space_id is None:
            return {}
        placeholders = ",".join("?" * len(image_ids))
        rows = db.get_connector().query(
            f"""
            SELECT a.image_id AS image_id,
                   AVG(1 - (a.embedding <=> b.embedding)) AS mean_sim
            FROM image_embeddings a
            JOIN image_embeddings b
              ON a.embedding_space_id = b.embedding_space_id
             AND a.image_id <> b.image_id
            WHERE a.embedding_space_id = ?
              AND a.image_id IN ({placeholders})
              AND b.image_id IN ({placeholders})
            GROUP BY a.image_id
            """,
            (space_id, *image_ids, *image_ids),
        ) or []
        out: dict[int, float] = {}
        for r in rows:
            val = _safe_float(r.get("mean_sim"))
            if val is not None:
                out[int(r["image_id"])] = val
        return out
    except Exception:
        logger.debug("agent cull embedding outlier fetch failed", exc_info=True)
        return {}


def enrich_unit_rows(rows_by_id: dict[int, dict[str, Any]], cfg: AgentCullConfig) -> list[str]:
    """Attach model_scores to rows; optionally JIT clip_quality_v0. Returns advisory warnings."""
    warnings: list[str] = []
    if not rows_by_id:
        return warnings

    if cfg.agent.include_all_model_scores:
        ims = get_batch_image_model_scores(list(rows_by_id))
        for iid, row in rows_by_id.items():
            row["model_scores"] = ims.get(iid, {})

    if cfg.agent.jit_clip_quality and "clip_quality_v0" in cfg.agent.required_score_names:
        missing = [iid for iid, row in rows_by_id.items() if not _row_has_model_score(row, "clip_quality_v0")]
        if missing:
            try:
                from modules import clip_quality

                computed = clip_quality.compute_clip_quality(missing, persist=True, ensure=False)
                for iid, val in (computed or {}).items():
                    row = rows_by_id.get(int(iid))
                    if row is None:
                        continue
                    ms = row.setdefault("model_scores", {})
                    ms["clip_quality_v0"] = {
                        "normalized": float(val),
                        "raw_score": float(val),
                        "status": "success",
                        "is_shadow": False,
                    }
            except Exception as exc:
                logger.warning("agent cull jit clip_quality failed: %s", exc)
                warnings.append(f"jit_clip_quality_failed:{exc}")

    # Embedding outlier z-score (per-image dissimilarity vs unit siblings). Only
    # compute when not already supplied and the outlier gate is active, so packet
    # build stays cheap. Best-effort — leaves the field unset when unavailable.
    if cfg.local_gates.block_embedding_outliers and not any(
        row.get("embedding_outlier_z") is not None for row in rows_by_id.values()
    ):
        outlier_z = _outlier_z_from_mean_sim(_fetch_unit_mean_cosine(list(rows_by_id)))
        for iid, z in outlier_z.items():
            row = rows_by_id.get(iid)
            if row is not None:
                row["embedding_outlier_z"] = z

    for name in cfg.agent.required_score_names:
        for iid, row in rows_by_id.items():
            if not _row_has_model_score(row, name):
                warnings.append(f"missing_required_score:{name}:image_id:{iid}")

    return warnings


def _serialize_model_scores(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, entry in (row.get("model_scores") or {}).items():
        if not isinstance(entry, dict):
            continue
        out[str(name)] = {
            "normalized": _safe_float(entry.get("normalized")),
            "raw_score": _safe_float(entry.get("raw_score")),
            "status": entry.get("status"),
        }
    return out


def build_review_packet(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    cfg: AgentCullConfig,
    *,
    score_warnings: list[str] | None = None,
) -> dict[str, Any]:
    images_payload: list[dict[str, Any]] = []
    thumbnail_manifest: list[dict[str, Any]] = []

    for image_id in unit.image_ids:
        row = dict(rows_by_id.get(image_id) or {})
        row["id"] = image_id
        scores_raw = {field: _safe_float(row.get(field)) for field in SCORE_FIELDS}
        if cfg.agent.include_all_model_scores:
            for name in cfg.agent.flatten_model_scores:
                val = _model_score_normalized((row.get("model_scores") or {}).get(name))
                if val is not None:
                    scores_raw[name] = val
        general_vals = [_safe_float(rows_by_id.get(i, {}).get("score_general")) for i in unit.image_ids]
        z_general = _z_scores(general_vals)
        idx = list(unit.image_ids).index(image_id)
        normalized = {
            "score_general_z": z_general[idx] if idx < len(z_general) else None,
        }
        effective = classify_image_status(row, decision_source=cfg.decision_source)
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
        if cfg.agent.include_all_model_scores:
            entry["model_scores"] = _serialize_model_scores(row)
        images_payload.append(entry)
        fs_path = thumbnails._resolve_thumbnail_filesystem_path(
            row.get("thumbnail_path"), row.get("thumbnail_path_win")
        )
        if cfg.agent.include_thumbnails and fs_path and os.path.isfile(fs_path):
            max_edge = int(cfg.agent.max_thumbnail_edge_px)
            prepared_path, thumb_w, thumb_h, downscaled = _prepare_thumbnail(fs_path, max_edge)
            manifest_entry: dict[str, Any] = {
                "image_id": image_id,
                "path": prepared_path,
                "mode": cfg.agent.thumbnail_mode,
                "max_edge_px": max_edge,
                "width": thumb_w,
                "height": thumb_h,
                "downscaled": downscaled,
            }
            db_thumb = row.get("thumbnail_path") or row.get("thumbnail_path_win")
            if downscaled or (db_thumb and str(db_thumb) != prepared_path):
                manifest_entry["source_path"] = str(db_thumb) if db_thumb else fs_path
            thumbnail_manifest.append(manifest_entry)

    packet: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "prompt_template_version": resolve_prompt_template_version(cfg),
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
                "low_confidence",
                "uncertain",
                "unique_subject_or_species",
                "higher_technical_quality",
                "unreadable_preview",
            ],
            "conservative_when_picked_lt_rejected": True,
        },
        "images": images_payload,
        "picked_image_ids": list(unit.picked_ids),
        "rejected_image_ids": list(unit.rejected_ids),
        "thumbnail_manifest": thumbnail_manifest,
        "scores_normalized": True,
    }
    if score_warnings:
        packet["score_warnings"] = list(score_warnings)
    return packet
