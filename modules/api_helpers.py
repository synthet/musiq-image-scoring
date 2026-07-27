"""API serialization and query payload helpers (extracted from modules.api)."""

import json
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import Response

from modules import db

logger = logging.getLogger(__name__)

def _jobs_recent_json_default(o: Any) -> Any:
    """json.dumps default=... for GET /api/jobs/recent (driver-native / odd nested values)."""
    if o is None:
        return None
    if isinstance(o, (bytes, memoryview, bytearray)):
        return bytes(o).decode("utf-8", errors="replace")
    if isinstance(o, bool):
        return o
    if isinstance(o, int) and not isinstance(o, bool):
        return o
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return o
    if isinstance(o, str):
        return o
    if isinstance(o, Decimal):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, (datetime, date)):
        try:
            return o.isoformat()
        except Exception:
            pass
    if hasattr(o, "isoformat") and callable(getattr(o, "isoformat", None)):
        try:
            return o.isoformat()
        except Exception:
            pass
    try:
        return str(o)
    except Exception:
        return "<non-stringifiable>"


def _decode_db_row_blobs(d: dict) -> dict:
    """Shallow decode of BLOB / buffer columns from Firebird rows."""
    out = {}
    for k, v in dict(d).items():
        if isinstance(v, (bytes, memoryview, bytearray)):
            out[k] = bytes(v).decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


def _normalize_jobs_table_row(d: dict) -> dict:
    """jobs row: decode BLOBs, parse scope_paths / queue_payload JSON (API contract)."""
    out = _decode_db_row_blobs(d)
    if isinstance(out.get("scope_paths"), str):
        try:
            out["scope_paths"] = json.loads(out["scope_paths"]) if out["scope_paths"] else []
        except (json.JSONDecodeError, TypeError):
            logger.warning("_normalize_jobs_table_row: bad scope_paths JSON on row id=%s", out.get("id"))
            out["scope_paths"] = []
    if out.get("scope_paths") is None:
        out["scope_paths"] = []
    if out.get("scope_type") is None and out.get("input_path"):
        out["scope_type"] = "folder_recursive"
        out["scope_paths"] = out["scope_paths"] or [out["input_path"]]
    qp = out.get("queue_payload")
    if isinstance(qp, str) and qp.strip():
        try:
            out["queue_payload"] = json.loads(qp)
        except (json.JSONDecodeError, TypeError):
            pass
    # Normalize cancelled (UK) → canceled (US) in API contract
    if isinstance(out.get("status"), str) and out["status"] == "cancelled":
        out["status"] = "canceled"
    out["capabilities"] = {
        "execution_report": _job_supports_execution_report(out),
    }
    qp_obj = out.get("queue_payload")
    if isinstance(qp_obj, dict):
        pra = qp_obj.get("post_run_audit")
        if isinstance(pra, dict):
            out["post_run_audit_status"] = pra.get("status")
            out["post_run_audit_severity"] = pra.get("severity")
    return out


def _job_supports_execution_report(job: dict[str, Any] | None, phase_codes: list[str] | None = None) -> bool:
    """Whether a job type/phase plan is expected to produce ``report_json``."""
    if not isinstance(job, dict):
        return False
    jt = str(job.get("job_type") or "").strip().lower()
    if jt in ("indexing", "metadata", "scoring"):
        return True
    if jt in ("tagging", "keywords", "selection", "culling", "clustering", "bird_species", "maintenance"):
        return False

    codes = {
        str(c).strip().lower()
        for c in (phase_codes or [])
        if isinstance(c, str) and str(c).strip()
    }
    if codes:
        return bool(codes.intersection({"indexing", "metadata", "scoring"}))

    if jt in ("pipeline", "ui_pipeline"):
        return True
    return False


def _normalize_incident_row(d: dict) -> dict:
    """image_incidents row: decode blobs; ensure ``detail`` is dict or None."""
    out = _decode_db_row_blobs(d)
    det = out.get("detail")
    if isinstance(det, str) and det.strip():
        try:
            out["detail"] = json.loads(det)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def _json_response_db(data: Any, log_label: str) -> Response:
    """Encode DB-backed payloads without Pydantic Dict[str,Any] serialization (avoids pydantic_core URL bugs)."""
    try:
        body = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=_jobs_recent_json_default,
        )
    except (TypeError, ValueError) as e:
        logger.exception("%s: JSON serialization failed", log_label)
        raise HTTPException(
            status_code=500,
            detail=f"JSON serialization failed: {e!r}",
        ) from e
    return Response(content=body.encode("utf-8"), media_type="application/json")


def _synthetic_bird_species_job_phases(job: dict[str, Any]) -> list[dict[str, Any]]:
    """One job_phases row for bird_species jobs when DB rows are missing or wrong template."""
    st = (job.get("status") or "queued").strip().lower()
    if st in ("pending", "queued"):
        pstate = "queued"
    elif st == "running":
        pstate = "running"
    elif st == "completed":
        pstate = "completed"
    elif st in ("failed", "interrupted"):
        pstate = st
    elif st in ("canceled", "cancelled"):
        pstate = "cancelled"
    elif st == "paused":
        pstate = "paused"
    else:
        pstate = "pending"
    return [
        {
            "phase_order": 0,
            "phase_code": "bird_species",
            "state": pstate,
            "started_at": job.get("started_at"),
            "completed_at": job.get("finished_at") or job.get("completed_at"),
            "error_message": None,
        }
    ]


def _job_phases_for_run_display(
    job: dict[str, Any] | None, phases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Use real job_phases when they include bird_species; else synthesize for bird-only jobs."""
    if not job:
        return phases
    jt = (job.get("job_type") or "").strip().lower()
    if jt not in ("bird_species", "bird-species"):
        return phases
    codes = {(p.get("phase_code") or "").strip().lower() for p in (phases or [])}
    if "bird_species" in codes:
        return phases or []
    return _synthetic_bird_species_job_phases(job)


# Per-model values that historically lived in dedicated ``images.score_*`` columns.
# After migration 0016 these live in ``image_model_scores``; the typed columns
# are scheduled for removal. While they still exist on the row we overlay the
# IMS value when the column is NULL so callers see one consistent shape.
_LEGACY_SCORE_COLUMN_MODELS: tuple[str, ...] = ("spaq", "ava", "koniq", "paq2piq", "liqe")


def _merge_model_scores_into(data: dict, ims: dict) -> None:
    """Attach per-model scores from `image_model_scores` to an image payload.

    Adds a structured ``model_scores`` block (all rows, including shadow, with
    `is_shadow`) plus flat ``{name}_score`` fields for production (non-shadow)
    models that lack a legacy ``score_{name}`` column. Production scores for the
    five legacy-column models also overlay the ``score_{name}`` field when it is
    NULL so the response contract stays stable once dual-writes are disabled.
    Shadow engines (cursor, claude) surface only in the structured block, never
    as flat scores.
    """
    if not ims:
        return
    data["model_scores"] = ims
    for name, info in ims.items():
        if info.get("is_shadow"):
            continue
        val = info.get("normalized")
        if val is None:
            val = info.get("raw_score")
        if val is None:
            continue
        legacy_key = f"score_{name}"
        if name in _LEGACY_SCORE_COLUMN_MODELS:
            if data.get(legacy_key) is None:
                data[legacy_key] = val
            continue
        key = f"{name}_score"
        if key not in data and legacy_key not in data:
            data[key] = val


def _parse_json_object_column(value) -> dict | None:
    """Parse a TEXT/JSON column into a dict for image detail enrichments."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _image_detail_payload(image_id: int) -> dict:
    """Full JSON for GET /api/images/{id} and uuid/hash lookups."""
    conn = db.get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM images WHERE id = ?", (image_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")

        data = _row_to_dict(row, exclude_keys={"image_embedding"})
        legacy_kw = (data.get("keywords") or "").strip()
        resolved_kw = db.get_resolved_image_keywords(image_id, legacy_fallback=legacy_kw).strip()
        data["keywords"] = resolved_kw or None
        data["file_paths"] = db.get_all_paths(image_id)
        data["resolved_path"] = db.get_resolved_path(image_id, verified_only=False)
        data["phase_statuses"] = db.get_image_phase_statuses(image_id)
        try:
            data["data_quality_flags"] = db.compute_image_data_quality_flags(image_id)
        except Exception:
            data["data_quality_flags"] = {}
        tf_det = db.get_image_technical_failure(image_id)
        if tf_det is not None:
            data["technical_failure_detection"] = tf_det
        try:
            emb_map = db.get_batch_image_embedding_presence([image_id])
            data["embeddings_present"] = emb_map.get(image_id, {})
        except Exception as exc:
            logger.debug("embeddings_present merge failed for image %s: %s", image_id, exc)
            data["embeddings_present"] = {}
        indexing_meta = _parse_json_object_column(data.get("metadata"))
        if indexing_meta is not None:
            data["indexing_metadata"] = indexing_meta
        scores_parsed = _parse_json_object_column(data.get("scores_json"))
        if scores_parsed is not None:
            data["scores_json_parsed"] = scores_parsed
        try:
            _merge_model_scores_into(data, db.get_image_model_scores(image_id, include_shadow=True))
        except Exception as exc:
            logger.debug("model_scores merge failed for image %s: %s", image_id, exc)
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _json_safe_metadata_row(row: dict | None) -> dict:
    """Serialize image_exif / image_xmp row dicts for JSON (omit binary columns)."""
    if not row:
        return {}
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, bytes):
            continue
        if hasattr(v, "isoformat") and callable(getattr(v, "isoformat", None)):
            try:
                out[k] = v.isoformat()
            except Exception:
                out[k] = str(v)
        else:
            out[k] = v
    return out


def _row_to_dict(row, exclude_keys=None):
    """Normalize a RowWrapper or plain dict to a JSON-serializable dict."""
    if hasattr(row, "to_dict"):
        return row.to_dict(exclude_keys=exclude_keys)
    # Plain dict from db_connector — apply same filtering as RowWrapper.to_dict
    exclude = exclude_keys or set()
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in exclude:
            continue
        if isinstance(v, bytes):
            continue
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _parse_rating_filter(rating: str | None) -> list | None:
    """Parse comma-separated rating integers; raise 400 on invalid tokens."""
    if not rating or not rating.strip():
        return None
    parts = [p.strip() for p in rating.split(",") if p.strip()]
    if not parts:
        return None
    try:
        return [int(p) for p in parts]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid rating parameter: expected comma-separated integers (e.g. 3,4,5).",
        )


def _images_list_payload(
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
    rating: str | None,
    label: str | None,
    keyword: str | None,
    min_score_general: float,
    min_score_aesthetic: float,
    min_score_technical: float,
    min_clip_quality_v0: float,
    folder_path: str | None,
    stack_id: int | None,
    phase_status_filter: str | None = None,
    unscored_only: bool = False,
    data_gap: str | None = None,
    keyword_exact: bool = False,
) -> dict:
    """Paginated image rows as JSON (embeddings excluded). Used by /api/images and /public/api/images."""
    rating_filter = _parse_rating_filter(rating)
    label_filter = label.split(",") if label else None
    try:
        images, total_count = db.get_images_paginated_with_count(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order,
            rating_filter=rating_filter,
            label_filter=label_filter,
            keyword_filter=keyword,
            keyword_exact=keyword_exact,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            min_clip_quality_v0=min_clip_quality_v0,
            folder_path=folder_path,
            stack_id=stack_id,
            phase_status_filter=phase_status_filter,
            unscored_only=unscored_only,
            data_gap=data_gap,
        )
        
        payload_images = []
        for img in images:
            d = _row_to_dict(img, exclude_keys={"image_embedding"})
            payload_images.append(d)

        img_ids = [d.get("id") or d.get("ID") for d in payload_images if (d.get("id") or d.get("ID"))]
        phase_map = db.get_batch_image_phase_statuses(img_ids)
        emb_map = db.get_batch_image_embedding_presence(img_ids)
        try:
            kw_ids = [int(i) for i in img_ids if i is not None]
            kw_map = db.get_batch_resolved_image_keywords(kw_ids) if kw_ids else {}
        except Exception as exc:
            logger.debug("batch resolved keywords failed: %s", exc)
            kw_map = {}
        try:
            ims_map = db.get_batch_image_model_scores(img_ids, include_shadow=True)
        except Exception as exc:
            logger.debug("batch model_scores merge failed: %s", exc)
            ims_map = {}
        for d in payload_images:
            img_id = d.get("id") or d.get("ID")
            img_id_int = int(img_id) if img_id is not None else None
            d["phase_statuses"] = phase_map.get(img_id_int, {}) if img_id_int else {}
            d["embeddings_present"] = emb_map.get(img_id_int, {}) if img_id_int else {}
            if img_id_int:
                _merge_model_scores_into(d, ims_map.get(img_id_int, {}))
                legacy_kw = (d.get("keywords") or "").strip()
                resolved_kw = (kw_map.get(img_id_int) or "").strip() or legacy_kw
                d["keywords"] = resolved_kw or None

        # Data-quality flags in one set-based query for the whole page (avoid N+1).
        try:
            dq_ids = [int(i) for i in img_ids if i is not None]
            dq_map = db.compute_image_data_quality_flags_batch(dq_ids) if dq_ids else {}
        except Exception as exc:
            logger.debug("batch data_quality_flags failed: %s", exc)
            dq_map = {}
        for d in payload_images:
            img_id = d.get("id") or d.get("ID")
            try:
                d["data_quality_flags"] = dq_map.get(int(img_id), {}) if img_id is not None else {}
            except (TypeError, ValueError):
                d["data_quality_flags"] = {}

        return {
            "images": payload_images,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 0,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _image_neighbors_payload(
    image_id: int,
    sort_by: str,
    order: str,
    rating: str | None,
    label: str | None,
    keyword: str | None,
    min_score_general: float,
    min_score_aesthetic: float,
    min_score_technical: float,
    min_clip_quality_v0: float,
    folder_path: str | None,
    stack_id: int | None,
) -> dict:
    """Find neighbor image IDs for navigation."""
    rating_filter = _parse_rating_filter(rating)
    label_filter = label.split(",") if label else None
    try:
        prev_id, next_id = db.get_image_neighbors(
            image_id=image_id,
            sort_by=sort_by,
            order=order,
            rating_filter=rating_filter,
            label_filter=label_filter,
            keyword_filter=keyword,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            min_clip_quality_v0=min_clip_quality_v0,
            folder_path=folder_path,
            stack_id=stack_id,
        )
        return {"prev_id": prev_id, "next_id": next_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _image_detail_for_uuid_str(image_uuid: str) -> dict:
    import uuid as uuid_stdlib

    key = (image_uuid or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="image_uuid is required")
    try:
        uuid_stdlib.UUID(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    image_id = db.find_image_id_by_uuid(key)
    if image_id is None:
        raise HTTPException(status_code=404, detail=f"Image not found: uuid={key}")
    return _image_detail_payload(image_id)


def _image_detail_for_hash_str(image_hash: str, hash_version: int | None = None) -> dict:
    import re

    key = (image_hash or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="image_hash is required")
    if not re.fullmatch(r"[0-9a-fA-F]{32,128}", key):
        raise HTTPException(
            status_code=400,
            detail="image_hash must be a hex string of length 32–128",
        )
    row = db.get_image_by_hash(key, hash_version=hash_version)
    if not row:
        raise HTTPException(status_code=404, detail=f"Image not found: hash={key}")
    image_id = row.get("id")
    if image_id is None:
        raise HTTPException(status_code=404, detail=f"Image not found: hash={key}")
    return _image_detail_payload(int(image_id))

