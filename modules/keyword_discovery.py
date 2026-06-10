"""
Keyword Discovery Helpers — Phase 4 Optimization

Optimized queries for keyword discovery, autocomplete, and clouds.
Uses KEYWORDS_DIM + IMAGE_KEYWORDS instead of scanning IMAGES table.
"""

import logging
from typing import List, Dict, Tuple, Optional
from modules import db, db_postgres
from modules.db_connector import get_connector

logger = logging.getLogger(__name__)


def get_top_keywords(limit: int = 50, folder_path: Optional[str] = None) -> List[Dict]:
    """
    Get top N keywords by usage count.

    Args:
        limit: Number of keywords to return (default 50)
        folder_path: Optional folder path to filter keywords to that folder

    Returns:
        List of dicts with keys: keyword_norm, keyword_display, count
    """
    conn = get_connector()

    try:
        if conn.type == 'postgres':
            if folder_path:
                folder_id = db.get_or_create_folder(folder_path)
                if not folder_id:
                    return []

                sql = f"""
                    SELECT
                        kd.keyword_norm,
                        kd.keyword_display,
                        COUNT(DISTINCT ik.image_id) AS count
                    FROM keywords_dim kd
                    JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                    JOIN images i ON ik.image_id = i.id
                    WHERE i.folder_id = %s
                    GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                    ORDER BY count DESC
                    LIMIT %s
                """
                rows = conn.query(sql, (folder_id, limit))
            else:
                sql = f"""
                    SELECT
                        kd.keyword_norm,
                        kd.keyword_display,
                        COUNT(DISTINCT ik.image_id) AS count
                    FROM keywords_dim kd
                    JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                    GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                    ORDER BY count DESC
                    LIMIT %s
                """
                rows = conn.query(sql, (limit,))
        else:
            # Firebird
            if folder_path:
                folder_id = db.get_or_create_folder(folder_path)
                if not folder_id:
                    return []

                sql = f"""
                    SELECT
                        kd.keyword_norm,
                        kd.keyword_display,
                        COUNT(DISTINCT ik.image_id) AS count
                    FROM keywords_dim kd
                    JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                    JOIN images i ON ik.image_id = i.id
                    WHERE i.folder_id = ?
                    GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                    ORDER BY count DESC
                    ROWS 1 TO ?
                """
                rows = conn.query(sql, (folder_id, limit))
            else:
                sql = f"""
                    SELECT
                        kd.keyword_norm,
                        kd.keyword_display,
                        COUNT(DISTINCT ik.image_id) AS count
                    FROM keywords_dim kd
                    JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                    GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                    ORDER BY count DESC
                    ROWS 1 TO ?
                """
                rows = conn.query(sql, (limit,))

        return [{"keyword_norm": r.get("keyword_norm"),
                 "keyword_display": r.get("keyword_display"),
                 "count": r.get("count")} for r in (rows or [])]
    except Exception as e:
        logger.error(f"Failed to get top keywords: {e}")
        return []


SPECIES_PREFIX = "species:"


def get_keyword_cloud(
    kind: str = "general",
    limit: int = 200,
    folder_path: Optional[str] = None,
) -> List[Dict]:
    """Top keywords by usage count, split by whether they are ``species:`` tags.

    Args:
        kind: ``"species"`` returns only ``species:*`` keywords (for the Birds
            tag cloud); ``"general"`` returns everything else (the Keywords cloud).
        limit: Number of keywords to return (default 200).
        folder_path: Optional folder path to scope the cloud to one folder.

    Returns:
        List of dicts with keys: keyword_norm, keyword_display, count — ordered by
        count descending. Empty list on failure or empty catalog.
    """
    conn = get_connector()
    is_species = str(kind).strip().lower() == "species"
    # keyword_norm is stored lowercased, so the prefix match is case-stable.
    species_pred = "kd.keyword_norm LIKE ?" if is_species else "kd.keyword_norm NOT LIKE ?"
    species_arg = f"{SPECIES_PREFIX}%"

    try:
        ph = "%s" if conn.type == "postgres" else "?"
        species_pred_db = species_pred.replace("?", ph)
        folder_id = None
        if folder_path:
            folder_id = db.get_or_create_folder(folder_path)
            if not folder_id:
                return []

        where = [species_pred_db]
        params: List = [species_arg]
        join_images = ""
        if folder_id:
            join_images = "JOIN images i ON ik.image_id = i.id"
            where.append(f"i.folder_id = {ph}")
            params.append(folder_id)
        where_sql = " AND ".join(where)

        if conn.type == "postgres":
            sql = f"""
                SELECT kd.keyword_norm, kd.keyword_display,
                       COUNT(DISTINCT ik.image_id) AS count
                FROM keywords_dim kd
                JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                {join_images}
                WHERE {where_sql}
                GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                ORDER BY count DESC
                LIMIT {ph}
            """
            params.append(limit)
        else:
            sql = f"""
                SELECT kd.keyword_norm, kd.keyword_display,
                       COUNT(DISTINCT ik.image_id) AS count
                FROM keywords_dim kd
                JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                {join_images}
                WHERE {where_sql}
                GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                ORDER BY count DESC
                ROWS 1 TO {ph}
            """
            params.append(limit)

        rows = conn.query(sql, tuple(params))
        return [{"keyword_norm": r.get("keyword_norm"),
                 "keyword_display": r.get("keyword_display"),
                 "count": r.get("count")} for r in (rows or [])]
    except Exception as e:
        logger.error(f"Failed to get keyword cloud (kind={kind}): {e}")
        return []


def search_keywords(search_term: str, limit: int = 20) -> List[Dict]:
    """
    Keyword autocomplete/search.

    Args:
        search_term: Partial keyword to search for (case-insensitive)
        limit: Maximum results (default 20)

    Returns:
        List of dicts with keys: keyword_norm, keyword_display, count
    """
    conn = get_connector()
    search_pattern = f"%{search_term}%"

    try:
        if conn.type == 'postgres':
            sql = f"""
                SELECT
                    kd.keyword_norm,
                    kd.keyword_display,
                    COUNT(DISTINCT ik.image_id) AS count
                FROM keywords_dim kd
                JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                WHERE kd.keyword_norm ILIKE %s OR kd.keyword_display ILIKE %s
                GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                ORDER BY count DESC
                LIMIT %s
            """
            rows = conn.query(sql, (search_pattern, search_pattern, limit))
        else:
            # Firebird
            sql = f"""
                SELECT
                    kd.keyword_norm,
                    kd.keyword_display,
                    COUNT(DISTINCT ik.image_id) AS count
                FROM keywords_dim kd
                JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
                WHERE UPPER(kd.keyword_norm) LIKE UPPER(?) OR UPPER(kd.keyword_display) LIKE UPPER(?)
                GROUP BY kd.keyword_id, kd.keyword_norm, kd.keyword_display
                ORDER BY count DESC
                ROWS 1 TO ?
            """
            rows = conn.query(sql, (search_pattern, search_pattern, limit))

        return [{"keyword_norm": r.get("keyword_norm"),
                 "keyword_display": r.get("keyword_display"),
                 "count": r.get("count")} for r in (rows or [])]
    except Exception as e:
        logger.error(f"Failed to search keywords: {e}")
        return []


def get_keywords_for_folder(folder_path: str, limit: int = 100) -> List[Dict]:
    """
    Get all keywords used in a folder, ordered by frequency.

    Args:
        folder_path: Folder path to get keywords for
        limit: Maximum keywords to return

    Returns:
        List of dicts with keys: keyword_norm, keyword_display, count
    """
    return get_top_keywords(limit=limit, folder_path=folder_path)


def get_keyword_cooccurrence(keyword: str, limit: int = 20) -> List[Dict]:
    """
    Get keywords that frequently co-occur with a given keyword.

    Args:
        keyword: Base keyword to find co-occurrences for
        limit: Maximum co-occurring keywords to return

    Returns:
        List of dicts with keys: keyword_norm, keyword_display, count
    """
    conn = get_connector()

    try:
        if conn.type == 'postgres':
            sql = f"""
                SELECT
                    kd2.keyword_norm,
                    kd2.keyword_display,
                    COUNT(DISTINCT ik2.image_id) AS count
                FROM keywords_dim kd1
                JOIN image_keywords ik1 ON kd1.keyword_id = ik1.keyword_id
                JOIN image_keywords ik2 ON ik1.image_id = ik2.image_id
                JOIN keywords_dim kd2 ON ik2.keyword_id = kd2.keyword_id
                WHERE LOWER(kd1.keyword_norm) = LOWER(%s)
                  AND kd2.keyword_id != kd1.keyword_id
                GROUP BY kd2.keyword_id, kd2.keyword_norm, kd2.keyword_display
                ORDER BY count DESC
                LIMIT %s
            """
            rows = conn.query(sql, (keyword, limit))
        else:
            # Firebird
            sql = f"""
                SELECT
                    kd2.keyword_norm,
                    kd2.keyword_display,
                    COUNT(DISTINCT ik2.image_id) AS count
                FROM keywords_dim kd1
                JOIN image_keywords ik1 ON kd1.keyword_id = ik1.keyword_id
                JOIN image_keywords ik2 ON ik1.image_id = ik2.image_id
                JOIN keywords_dim kd2 ON ik2.keyword_id = kd2.keyword_id
                WHERE UPPER(kd1.keyword_norm) = UPPER(?)
                  AND kd2.keyword_id != kd1.keyword_id
                GROUP BY kd2.keyword_id, kd2.keyword_norm, kd2.keyword_display
                ORDER BY count DESC
                ROWS 1 TO ?
            """
            rows = conn.query(sql, (keyword, limit))

        return [{"keyword_norm": r.get("keyword_norm"),
                 "keyword_display": r.get("keyword_display"),
                 "count": r.get("count")} for r in (rows or [])]
    except Exception as e:
        logger.error(f"Failed to get keyword cooccurrence for '{keyword}': {e}")
        return []


def get_keyword_stats() -> Dict:
    """
    Get overall keyword statistics.

    Returns:
        Dict with keys: total_keywords, total_links, avg_keywords_per_image, etc.
    """
    conn = get_connector()

    try:
        if conn.type == 'postgres':
            stats = conn.query("""
                SELECT
                    (SELECT COUNT(*) FROM keywords_dim) AS total_keywords,
                    (SELECT COUNT(*) FROM image_keywords) AS total_links,
                    (SELECT COUNT(DISTINCT image_id) FROM image_keywords) AS images_with_keywords,
                    (SELECT COUNT(*) FROM images) AS total_images
            """)
        else:
            # Firebird
            stats = conn.query("""
                SELECT
                    (SELECT COUNT(*) FROM keywords_dim) AS total_keywords,
                    (SELECT COUNT(*) FROM image_keywords) AS total_links,
                    (SELECT COUNT(DISTINCT image_id) FROM image_keywords) AS images_with_keywords,
                    (SELECT COUNT(*) FROM images) AS total_images
            """)

        if stats:
            row = stats[0]
            total_kw = row.get("total_keywords", 0)
            total_links = row.get("total_links", 0)
            images_with_kw = row.get("images_with_keywords", 0)
            total_imgs = row.get("total_images", 0)

            avg_per_image = total_links / images_with_kw if images_with_kw > 0 else 0
            coverage = (images_with_kw / total_imgs * 100) if total_imgs > 0 else 0

            return {
                "total_keywords": total_kw,
                "total_keyword_links": total_links,
                "images_with_keywords": images_with_kw,
                "total_images": total_imgs,
                "avg_keywords_per_image": avg_per_image,
                "keyword_coverage_percent": coverage
            }
    except Exception as e:
        logger.error(f"Failed to get keyword stats: {e}")

    return {}
