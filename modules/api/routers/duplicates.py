"""API routes: duplicates (extracted from modules.api)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, Query

from modules.api.handler_registry import get_handler
from modules.api_models import (
    ApiResponse,
    FindDuplicatesRequest,
    OutlierResponse,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_duplicates_router() -> APIRouter:
    router = APIRouter()
    # ========== Find Duplicates Endpoints ==========

    @router.post(
        "/duplicates/find", 
        response_model=ApiResponse,
        summary="[DEPRECATED] Find near-duplicate images",
        description="DEPRECATED: Use POST /api/similarity/duplicates instead.",
        deprecated=True,
    )
    def find_duplicates_legacy(req: FindDuplicatesRequest = Body(...)):
        """Deprecated legacy duplicate detection."""
        return post_duplicates_similarity_namespace(req)

    @router.post(
        "/similarity/duplicates", 
        response_model=ApiResponse,
        summary="Find near-duplicate images",
        description="Detect likely duplicate image pairs using embedding cosine similarity.",
        tags=["Similarity"]
    )
    def post_duplicates_similarity_namespace(req: FindDuplicatesRequest = Body(...)):
        """Find near-duplicate image pairs in the database (similarity namespace)."""
        try:
            from modules import similar_search
            results = similar_search.find_near_duplicates(
                threshold=req.threshold,
                folder_path=req.folder_path,
                limit=req.limit
            )
            return ApiResponse(
                success=True, 
                message=f"Found {len(results)} near-duplicate pairs",
                data={"duplicates": results}
            )
        except Exception as e:
            return ApiResponse(success=False, message=str(e))

    @router.get(
        "/similarity/similar",
        summary="[DEPRECATED] Find similar images",
        description="DEPRECATED: Use GET /api/similarity/search instead.",
        deprecated=True,
    )
    def get_similar_images_alias(
        image_id: int = Query(..., description="ID of the query image"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        folder_path: str | None = Query(None, description="Scope search to folder"),
        min_similarity: float | None = Query(0.80, ge=0.0, le=1.0, description="Minimum similarity threshold"),
        embedding_space: str | None = Query(
            None, description="Embedding-space code (default: mobilenet_v2_imagenet_gap)"
        ),
    ):
        """Deprecated alias for similarity search."""
        return get_handler("get_similar_images_similarity_namespace")(
            image_id=image_id,
            limit=limit,
            folder_path=folder_path,
            min_similarity=min_similarity,
            embedding_space=embedding_space,
        )

    @router.get(
        "/similarity/duplicates",
        summary="Find near-duplicate images (similarity namespace)",
        description="Detect likely duplicate image pairs using embedding cosine similarity.",
    )
    def get_duplicates_similarity_namespace(
        threshold: float | None = Query(
            None,
            ge=0.0,
            le=1.0,
            description="Similarity threshold. Uses config default when omitted.",
        ),
        folder_path: str | None = Query(None, description="Restrict duplicate detection to a folder"),
        limit: int = Query(1000, ge=1, le=10000, description="Maximum duplicate pairs to return"),
    ):
        """GET alias for duplicate detection under /api/similarity namespace."""
        from modules import similar_search

        try:
            duplicates = similar_search.find_near_duplicates(
                threshold=threshold,
                folder_path=folder_path,
                limit=limit,
            )
            return {
                "duplicates": duplicates,
                "count": len(duplicates),
            }
        except Exception as exc:
            logger.error("Error in get_duplicates_similarity_namespace: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get(
        "/outliers",
        response_model=OutlierResponse,
        summary="[DEPRECATED] Find visual outliers in a folder",
        description="DEPRECATED: Use GET /api/similarity/outliers instead.",
        deprecated=True,
    )
    def get_outliers_legacy(
        folder_path: str = Query(..., description="Folder path to analyze"),
        z_threshold: float | None = Query(None, ge=0.0, description="Outlier z-score threshold"),
        k: int | None = Query(None, ge=1, description="Top-K neighbors used for local density"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum outlier results to return"),
    ):
        """Deprecated legacy outlier search."""
        return get_outliers_similarity_namespace(
            folder_path=folder_path,
            z_threshold=z_threshold,
            k=k,
            limit=limit,
        )

    @router.get(
        "/similarity/outliers",
        response_model=OutlierResponse,
        summary="Find visual outliers",
        description="""
        Identify visually atypical images inside a folder using embedding-based similarity analysis.

        **Query Parameters:**
        - folder_path: Required. Restrict analysis to this folder.
        - z_threshold: Optional z-score cutoff (default from config).
        - k: Optional number of nearest neighbors used per image (default from config).
        - limit: Maximum number of outliers to return (default: 100).

        **Returns:**
        - outliers: List of flagged images with outlier scores, z-scores, and nearest-neighbor explainability.
        - stats: Folder-level summary statistics used during detection.
        - skipped: Images skipped due to missing embeddings.
        """,
        tags=["Similarity"]
    )
    def get_outliers_similarity_namespace(
        folder_path: str = Query(..., description="Folder path to analyze"),
        z_threshold: float | None = Query(None, ge=0.0, description="Outlier z-score threshold"),
        k: int | None = Query(None, ge=1, description="Top-K neighbors used for local density"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum outlier results to return"),
    ):
        """Find statistically atypical images based on embedding similarity (similarity namespace)."""
        from modules import similar_search
        try:
            result = similar_search.find_outliers(
                folder_path=folder_path,
                z_threshold=z_threshold,
                k=k,
                limit=limit,
            )
            if isinstance(result, dict) and "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Error in get_outliers for %s: %s", folder_path, exc)
            raise HTTPException(status_code=500, detail=str(exc))



    return router
