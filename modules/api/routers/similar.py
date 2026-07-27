"""API routes: similar (extracted from modules.api)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from modules import db

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_similar_router() -> APIRouter:
    router = APIRouter()
    # ========== Similar Images Endpoint ==========

    @router.get(
        "/similar",
        summary="[DEPRECATED] Find similar images",
        description="DEPRECATED: Use GET /api/similarity/search instead.",
        deprecated=True,
    )
    def get_similar_images_legacy(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: str | None = Query(None, description="Scope search to folder"),
        min_similarity: float | None = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
    ):
        """Deprecated legacy similarity search."""
        return get_similar_images_similarity_namespace(
            image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
        )

    @router.get(
        "/similarity/search",
        summary="Find similar images",
        description="""
        Find images visually similar to a given image using embedding-based cosine similarity.

        **Query Parameters:**
        - image_id: Required. Integer ID of the query image.
        - limit: Maximum number of results (default: 20).
        - folder_path: Optional. Scope search to a specific folder path.
        - min_similarity: Minimum similarity threshold 0.0-1.0 (default: 0.80).
        - embedding_space: Optional embedding-space code. Defaults to the
          1280-d MobileNet space. Non-default codes (e.g.
          `clip_vit_b32_image`) require PostgreSQL.

        **Returns:**
        - query_image_id: ID of the query image
        - results: List of {image_id, file_path, similarity}
        - count: Number of results returned
        """,
        tags=["Similarity"]
    )
    def get_similar_images_similarity_namespace(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: str | None = Query(None, description="Scope search to folder"),
        min_similarity: float | None = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
        embedding_space: str | None = Query(
            None,
            description="Embedding-space code (default: mobilenet_v2_imagenet_gap)",
        ),
    ):
        """Find images similar to the given image by ID (new similarity namespace)."""
        from modules import similar_search
        # Verify image exists before searching
        conn = db.get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT id FROM images WHERE id = ?", (image_id,))
            if c.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"Image not found: id={image_id}")
        finally:
            conn.close()
        result = similar_search.search_similar_images(
            example_image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
            embedding_space=embedding_space,
        )
        if isinstance(result, dict) and "error" in result:
            if "not found" in result["error"].lower():
                raise HTTPException(status_code=404, detail=result["error"])
            if "no embeddings" in result["error"].lower() or "clustering" in result["error"].lower():
                raise HTTPException(status_code=400, detail=result["error"])
            raise HTTPException(status_code=400, detail=result["error"])
        payload = {
            "query_image_id": image_id,
            "results": result,
            "count": len(result),
        }
        if embedding_space is not None:
            payload["embedding_space"] = embedding_space
        return payload

    @router.get(
        "/similarity/text-search",
        summary="Search images by text query",
        description="""
        Find images semantically matching a free-text query using CLIP text-to-image
        similarity.

        Encodes the query with the CLIP ViT-B/32 text tower and searches against
        stored `clip_vit_b32_image` embeddings via pgvector cosine distance.
        Requires PostgreSQL and at least some images with CLIP embeddings
        (produced during tagging).

        **Query Parameters:**
        - query: Required. Free-text search query (e.g. "sunset over mountains").
        - limit: Maximum number of results (default: 20, max: 100).
        - folder_path: Optional. Scope search to a specific folder path.
        - min_similarity: Minimum similarity threshold 0.0-1.0 (default: none).

        **Returns:**
        - query: The original query string
        - results: List of {image_id, file_path, similarity}
        - count: Number of results returned
        - embedding_space: Always "clip_vit_b32_image"
        """,
        tags=["Similarity"],
    )
    async def search_images_by_text(
        query: str = Query(..., min_length=1, max_length=500, description="Free-text search query"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: str | None = Query(None, description="Scope search to folder (ignored if folder_ids set)"),
        folder_ids: list[int] | None = Query(None, description="Scope search to folder IDs (includes subfolders when expanded client-side)"),
        min_similarity: float | None = Query(None, ge=0.0, le=1.0, description="Minimum similarity threshold"),
        min_rating: int | None = Query(None, ge=0, le=5, description="Minimum star rating"),
        color_label: str | None = Query(None, description="Filter by color label (Red, Yellow, Green, Blue, Purple)"),
        keyword: str | None = Query(None, description="Also require normalized keyword match (AND filter)"),
        captured_date: str | None = Query(None, description="Filter by capture date (YYYY-MM-DD)"),
        sort_by: str | None = Query(None, description="Secondary sort after relevance (capture_date, created_at, rating, score_general, ...)"),
        order: str | None = Query("DESC", description="Secondary sort direction (ASC or DESC)"),
    ):
        """Search images by free-text query using CLIP text-to-image similarity."""
        from modules import similar_search

        def _run():
            return similar_search.search_by_text(
                query=query,
                limit=limit,
                folder_path=folder_path,
                min_similarity=min_similarity,
                folder_ids=folder_ids,
                min_rating=min_rating,
                color_label=color_label,
                keyword=keyword,
                captured_date=captured_date,
                sort_by=sort_by,
                order=order,
            )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_run),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Text search timed out (model loading may take a while on first call).",
            )
        except Exception as e:
            import traceback
            logger.error(f"Unexpected error in text search endpoint: {e!s}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

        if isinstance(result, dict):
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            raise HTTPException(status_code=500, detail="Unexpected text search result shape.")
        if not isinstance(result, list):
            raise HTTPException(status_code=500, detail="Unexpected text search result type.")

        return {
            "query": query,
            "results": result,
            "count": len(result),
            "embedding_space": "clip_vit_b32_image",
        }

    @router.get(
        "/similarity/example-queries",
        summary="Suggested text-search queries from library keywords",
        description="""
        Returns up to ``limit`` display strings derived from ranked keywords in the catalog
        (``keywords_dim`` / ``image_keywords``), optionally scoped to a folder path.
        Used by the Semantic Search UI for rotating example chips.

        Always returns HTTP 200; on failure or empty catalog, ``queries`` is an empty list.
        """,
        tags=["Similarity"],
    )
    def get_similarity_example_queries(
        limit: int = Query(48, ge=1, le=100, description="Maximum keyword phrases to return"),
        folder_path: str | None = Query(None, description="Scope keywords to images under this folder path"),
    ):
        """Top keywords from the catalog as suggestion strings for text search."""
        from modules.keyword_discovery import get_top_keywords

        def _min_display_len(val: str | None) -> bool:
            s = (val or "").strip()
            return len(s) >= 2

        try:
            rows = get_top_keywords(limit=limit, folder_path=folder_path) or []
        except Exception as e:
            logger.warning("example-queries failed: %s", e)
            return {"queries": [], "source": "keywords"}

        out: list[str] = []
        seen = set()
        for r in rows:
            disp = r.get("keyword_display")
            norm = r.get("keyword_norm")
            text = (disp if (disp and str(disp).strip()) else norm) or ""
            text = str(text).strip()
            if not _min_display_len(text):
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)

        return {"queries": out, "source": "keywords"}

    @router.get(
        "/keywords/cloud",
        summary="Keyword tag cloud (counts by keyword)",
        description="""
        Returns keywords with usage counts for a tag-cloud UI, ordered by count desc.

        ``kind=species`` returns only ``species:*`` keywords (Birds page); ``kind=general``
        returns all non-species keywords (Keywords page). Optionally scope to a folder path.

        Each entry: ``{keyword_norm, keyword_display, count}``. Always HTTP 200; on failure
        or empty catalog, ``keywords`` is an empty list.
        """,
        tags=["Keywords"],
    )
    def get_keyword_cloud_endpoint(
        kind: str = Query("general", description="species | general"),
        limit: int = Query(200, ge=1, le=1000, description="Maximum keywords to return"),
        folder_path: str | None = Query(None, description="Scope keywords to images under this folder path"),
    ):
        """Keyword usage counts for the Birds / Keywords tag clouds."""
        from modules.keyword_discovery import get_keyword_cloud

        kind_norm = (kind or "general").strip().lower()
        if kind_norm not in ("species", "general"):
            raise HTTPException(status_code=400, detail="kind must be 'species' or 'general'")
        try:
            rows = get_keyword_cloud(kind=kind_norm, limit=limit, folder_path=folder_path) or []
        except Exception as e:
            logger.warning("keyword cloud failed: %s", e)
            return {"keywords": [], "kind": kind_norm}
        return {"keywords": rows, "kind": kind_norm}

    from modules.api.handler_registry import register_handlers

    register_handlers(
        {"get_similar_images_similarity_namespace": get_similar_images_similarity_namespace}
    )

    return router
