"""Read-only public image API routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from modules.api_helpers import (
    _image_detail_for_hash_str,
    _image_detail_for_uuid_str,
    _image_detail_payload,
    _image_neighbors_payload,
    _images_list_payload,
)


def create_public_api_router() -> APIRouter:
    """Read-only JSON API for image records (no job control or mutations).

    Mounted at ``/public/api``. Intended for integrations and scripts that only
    need database-backed image metadata and scores.
    """
    router = APIRouter(
        prefix="/public/api",
        tags=["Public Image API"],
        responses={
            400: {"description": "Bad Request"},
            404: {"description": "Not Found"},
            500: {"description": "Internal Server Error"},
        },
    )

    @router.get(
        "/images",
        summary="List images (public)",
        description="Read-only paginated image rows from the database; same filters as /api/images. "
        "page_size is capped at 200.",
    )
    async def public_list_images(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        sort_by: str = Query(
            "score",
            description="score, date, name, rating, score_general, score_aesthetic, score_technical",
        ),
        order: str = Query("desc", description="asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings"),
        label: Optional[str] = Query(None, description="Comma-separated labels"),
        keyword: Optional[str] = Query(None),
        keyword_exact: bool = Query(False, description="When true, match the keyword exactly instead of a substring"),
        min_score_general: float = Query(0, ge=0, le=1),
        min_score_aesthetic: float = Query(0, ge=0, le=1),
        min_score_technical: float = Query(0, ge=0, le=1),
        min_clip_quality_v0: float = Query(0, ge=0, le=1),
        folder_path: Optional[str] = Query(None),
        stack_id: Optional[int] = Query(None),
    ):
        return _images_list_payload(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            order=order,
            rating=rating,
            label=label,
            keyword=keyword,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            min_clip_quality_v0=min_clip_quality_v0,
            folder_path=folder_path,
            stack_id=stack_id,
            keyword_exact=keyword_exact,
        )

    @router.get(
        "/images/by-uuid/{image_uuid}",
        summary="Image by UUID (public)",
        description="Same JSON as GET /api/images/by-uuid/{image_uuid}.",
    )
    async def public_get_image_by_uuid(image_uuid: str):
        return _image_detail_for_uuid_str(image_uuid)

    @router.get(
        "/images/by-hash/{image_hash}",
        summary="Image by content hash (public)",
        description="Same JSON as GET /api/images/by-hash/{image_hash}. Optional hash_version disambiguates.",
    )
    async def public_get_image_by_hash(
        image_hash: str,
        hash_version: Optional[int] = Query(None, description="images.hash_version (1=full file, 2=preview)"),
    ):
        return _image_detail_for_hash_str(image_hash, hash_version=hash_version)

    @router.get(
        "/images/{image_id}",
        summary="Image by numeric id (public)",
        description="Same JSON as GET /api/images/{image_id}.",
    )
    async def public_get_image_by_id(image_id: int):
        return _image_detail_payload(image_id)

    @router.get(
        "/images/{image_id}/neighbors",
        summary="Image neighbors (public)",
        description="Find previous and next image IDs for navigation within a sorted/filtered sequence.",
    )
    async def public_get_image_neighbors(
        image_id: int,
        sort_by: str = Query("score", description="Same sort as /public/api/images"),
        order: str = Query("desc", description="asc or desc"),
        rating: Optional[str] = Query(None, description="Comma-separated ratings"),
        label: Optional[str] = Query(None, description="Comma-separated labels"),
        keyword: Optional[str] = Query(None),
        min_score_general: float = Query(0, ge=0, le=1),
        min_score_aesthetic: float = Query(0, ge=0, le=1),
        min_score_technical: float = Query(0, ge=0, le=1),
        min_clip_quality_v0: float = Query(0, ge=0, le=1),
        folder_path: Optional[str] = Query(None),
        stack_id: Optional[int] = Query(None),
    ):
        return _image_neighbors_payload(
            image_id=image_id,
            sort_by=sort_by,
            order=order,
            rating=rating,
            label=label,
            keyword=keyword,
            min_score_general=min_score_general,
            min_score_aesthetic=min_score_aesthetic,
            min_score_technical=min_score_technical,
            min_clip_quality_v0=min_clip_quality_v0,
            folder_path=folder_path,
            stack_id=stack_id,
        )

    return router
