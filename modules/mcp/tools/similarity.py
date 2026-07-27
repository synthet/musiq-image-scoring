"""MCP tool implementations — similarity (extracted from modules.mcp_server)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

def search_similar_images(
    example_path: str | None = None,
    example_image_id: int | None = None,
    limit: int = 20,
    folder_path: str | None = None,
    min_similarity: float | None = None,
    embedding_space: str | None = None,
) -> dict:
    """Find images visually similar to an example image using stored embeddings and cosine similarity.

    Provide either ``example_path`` or ``example_image_id``. By default this uses
    the MobileNetV2 ``mobilenet_v2_imagenet_gap`` space. Pass ``embedding_space``
    (e.g. ``clip_vit_b32_image``, ``bioclip_2_image``, ``blip_vit_b16_image``) to
    search a different per-dim table; non-default spaces are Postgres-only.
    """
    from modules import similar_search
    return similar_search.search_similar_images(
        example_path=example_path,
        example_image_id=example_image_id,
        limit=limit,
        folder_path=folder_path,
        min_similarity=min_similarity,
        embedding_space=embedding_space,
    )


def search_images_by_text(
    query: str,
    limit: int = 20,
    folder_path: str | None = None,
    folder_ids: list[int] | None = None,
    min_similarity: float | None = None,
    min_rating: int | None = None,
    color_label: str | None = None,
    keyword: str | None = None,
    captured_date: str | None = None,
    sort_by: str | None = None,
    order: str | None = None,
) -> dict:
    """Search images by free-text query using CLIP text-to-image similarity.

    Encodes the query with the CLIP ViT-B/32 text tower and searches against
    stored ``clip_vit_b32_image`` embeddings via pgvector cosine distance.
    Requires PostgreSQL and images with CLIP embeddings (produced during tagging).

    Examples: ``"sunset over mountains"``, ``"a bird on a branch"``,
    ``"portrait with dramatic lighting"``.
    """
    from modules import similar_search
    result = similar_search.search_by_text(
        query=query,
        limit=limit,
        folder_path=folder_path,
        folder_ids=folder_ids,
        min_similarity=min_similarity,
        min_rating=min_rating,
        color_label=color_label,
        keyword=keyword,
        captured_date=captured_date,
        sort_by=sort_by,
        order=order,
    )
    if isinstance(result, dict) and "error" in result:
        return result
    return {
        "query": query,
        "results": result,
        "count": len(result),
        "embedding_space": "clip_vit_b32_image",
    }


def find_near_duplicates(
    threshold: float | None = None,
    folder_path: str | None = None,
    limit: int | None = None
) -> dict:
    """Detect visually duplicate or near-duplicate images even when file hashes differ. Returns a list of near-duplicate image pairs."""
    from modules import similar_search
    return similar_search.find_near_duplicates(
        threshold=threshold,
        folder_path=folder_path,
        limit=limit
    )


def propagate_tags(
    folder_path: str | None = None,
    dry_run: bool = True,
    k: int | None = None,
    min_similarity: float | None = None,
    min_keyword_confidence: float | None = None
) -> dict:
    """Propagate keywords from tagged images to untagged neighbors using embedding cosine similarity. Uses weighted voting with configurable thresholds. Defaults to dry_run=true for safe preview."""
    from modules.tagging import propagate_tags as _propagate_tags
    return _propagate_tags(
        folder_path=folder_path,
        dry_run=dry_run,
        k=k,
        min_similarity=min_similarity,
        min_keyword_confidence=min_keyword_confidence,
    )


def find_outliers(
    folder_path: str = "",
    z_threshold: float | None = None,
    k: int | None = None,
    limit: int | None = None
) -> dict:
    """Identify visually atypical images in a folder using embedding similarity analysis. Computes top-K mean cosine similarity per image and flags statistical outliers via z-score. Returns flagged images with explainability (nearest neighbors, folder stats)."""
    from modules import similar_search
    return similar_search.find_outliers(
        folder_path=folder_path,
        z_threshold=z_threshold,
        k=k,
        limit=limit,
    )

