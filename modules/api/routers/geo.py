"""API routes: geo (extracted from modules.api)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from modules import db

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_geo_router() -> APIRouter:
    router = APIRouter()
    # ========== Geo Map Endpoint ==========

    @router.get(
        "/geo/images",
        summary="Get geotagged images for map display",
        description="""
        Return images that have GPS coordinates stored in image_exif,
        suitable for rendering on an interactive map.

        **Query Parameters:**
        - folder_path: Optional. Restrict to images under this folder.
        - keyword: Optional. Filter by keyword (substring match on image_keywords).
        - min_score: Optional. Minimum score_general threshold.
        - label: Optional. Filter by label (e.g. 'Green', 'Yellow', 'Red').
        - rating: Optional. Filter by star rating (1-5).
        - semantic: Optional. If true, perform semantic search via CLIP.
        - limit: Maximum number of results (default: 50000, max: 100000).

        **Returns:**
        - images: List of geotagged image objects with lat/lng and metadata.
        - count: Number of results.
        - bounds: Bounding box {sw: [lat, lng], ne: [lat, lng]} or null.
        """,
        tags=["Geo"],
    )
    async def get_geo_images(
        folder_path: str | None = Query(None, description="Restrict to folder path"),
        keyword: str | None = Query(None, description="Filter by keyword substring"),
        min_score: float | None = Query(None, ge=0.0, le=100.0, description="Minimum score_general"),
        label: str | None = Query(None, description="Filter by label"),
        rating: int | None = Query(None, ge=1, le=5, description="Filter by star rating"),
        semantic: bool = Query(False, description="Perform semantic search via CLIP"),
        limit: int = Query(50000, ge=1, le=100000, description="Maximum results"),
    ):
        """Return images with GPS coordinates for map display."""
        semantic_ids: list[int] | None = None
        if semantic and keyword:
            from modules import similar_search
            try:
                semantic_results = await asyncio.wait_for(
                    asyncio.to_thread(
                        similar_search.search_by_text,
                        query=keyword,
                        limit=limit,
                        folder_path=folder_path
                    ),
                    timeout=30.0
                )
                if isinstance(semantic_results, list):
                    semantic_ids = [r["image_id"] for r in semantic_results]
                    if not semantic_ids:
                        return {"images": [], "count": 0, "bounds": None}
            except Exception as e:
                logger.error(f"Semantic search failed in geo endpoint: {e}")
                # Fallback to empty or keyword? Let's return empty to be consistent
                return {"images": [], "count": 0, "bounds": None}

        def _fetch():
            conn = db.get_db()
            try:
                c = conn.cursor()
                clauses = [
                    "e.gps_latitude IS NOT NULL",
                    "e.gps_longitude IS NOT NULL",
                ]
                params: list = []

                if folder_path:
                    clauses.append("f.path = ?")
                    params.append(folder_path)
                
                if semantic_ids is not None:
                    placeholders = ",".join(["?"] * len(semantic_ids))
                    clauses.append(f"i.id IN ({placeholders})")
                    params.extend(semantic_ids)
                elif keyword:
                    clauses.append(
                        "EXISTS ("
                        " SELECT 1"
                        " FROM image_keywords ik"
                        " JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id"
                        " WHERE ik.image_id = i.id AND COALESCE(kd.keyword_display, kd.keyword_norm) ILIKE ?"
                        ")"
                    )
                    params.append(f"%{keyword}%")

                if min_score is not None:
                    clauses.append("i.score_general >= ?")
                    params.append(min_score)
                if label:
                    clauses.append("i.label = ?")
                    params.append(label)
                if rating is not None:
                    clauses.append("i.rating = ?")
                    params.append(rating)

                where = " AND ".join(clauses)
                sql = f"""
                    SELECT
                        i.id AS image_id,
                        i.file_path,
                        e.gps_latitude AS latitude,
                        e.gps_longitude AS longitude,
                        e.date_time_original AS date_taken,
                        i.label,
                        i.rating,
                        COALESCE(e.make, '') || ' ' || COALESCE(e.model, '') AS camera,
                        i.score_general
                    FROM images i
                    JOIN image_exif e ON e.image_id = i.id
                    LEFT JOIN folders f ON f.id = i.folder_id
                    WHERE {where}
                    ORDER BY e.date_time_original DESC NULLS LAST
                    LIMIT ?
                """
                params.append(limit)
                c.execute(sql, params)
                cols = [d[0] for d in c.description]
                res = c.fetchall()
                if res and isinstance(res[0], dict):
                    rows = res
                else:
                    rows = []
                    for row in res:
                        seq = list(row)
                        # Some DB adapters return rows as sequences of (key, value) pairs.
                        if (
                            seq
                            and isinstance(seq[0], (list, tuple))
                            and len(seq[0]) == 2
                            and isinstance(seq[0][0], str)
                        ):
                            rows.append(dict(seq))
                        else:
                            rows.append(dict(zip(cols, seq)))

                # Normalize adapters that return dict values like (key, value).
                norm_rows = []
                for r in rows:
                    if not isinstance(r, dict):
                        norm_rows.append(r)
                        continue
                    r2 = {}
                    for k, v in r.items():
                        if isinstance(v, (list, tuple)) and len(v) == 2 and v[0] == k:
                            r2[k] = v[1]
                        else:
                            r2[k] = v
                    norm_rows.append(r2)
                rows = norm_rows
                return rows
            finally:
                conn.close()

        try:
            rows = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=30.0)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Geo query timed out.")


        # Build response with computed bounds
        images = []
        lats, lngs = [], []
        for r in rows:
            lat, lng = r["latitude"], r["longitude"]
            lats.append(lat)
            lngs.append(lng)
            dt = r.get("date_taken")
            if isinstance(dt, datetime):
                dt = dt.isoformat()
            elif dt is not None:
                dt = str(dt)
            images.append({
                "image_id": r["image_id"],
                "file_path": r["file_path"],
                "latitude": lat,
                "longitude": lng,
                "date_taken": dt,
                "label": r.get("label"),
                "rating": r.get("rating"),
                "camera": str(r.get("camera") or "").strip(),
                "score_general": r.get("score_general"),
            })

        bounds = None
        if lats:
            bounds = {
                "sw": [min(lats), min(lngs)],
                "ne": [max(lats), max(lngs)],
            }

        return {"images": images, "count": len(images), "bounds": bounds}


    return router
