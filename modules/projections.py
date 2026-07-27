"""
2D Embedding Map — Application #05

Projects stored MobileNetV2 image embeddings to 2D coordinates using UMAP
(with t-SNE as a fallback when umap-learn is not installed).  Results are
cached on disk as JSON so repeated calls are cheap.

Public API
----------
compute_embedding_map(folder_path, method, refresh, sample_limit, ...) -> dict
invalidate_embedding_map_cache(folder_path) -> int   # returns files deleted
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

import numpy as np

from modules.config import BASE_DIR, get_config_value
from modules.embedding_spaces import DEFAULT_EMBEDDING_SPACE_CODE, SPACE_DIMS

logger = logging.getLogger(__name__)

_CACHE_DIR = BASE_DIR / ".cache" / "embedding_map"
MIN_POINTS = 3  # UMAP / t-SNE require at least 3 samples
PCA_AUTO_THRESHOLD = 1280  # PCA pre-step on by default for dims >= this


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_cache_dir():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _make_cache_key(
    folder_path,
    method,
    max_points,
    n_neighbors,
    min_dist,
    embedding_space=DEFAULT_EMBEDDING_SPACE_CODE,
    pca_dim=None,
):
    """
    Build a deterministic cache key for projection inputs.

    Method-specific params are normalised so non-relevant parameters do not
    perturb the cache key. ``embedding_space`` and ``pca_dim`` are part of
    the key so a CLIP-512 map and a MobileNet-1280 map (or with/without PCA)
    cannot collide.
    """
    normalized_method = (method or "umap").lower()
    method_params = {"n_neighbors": n_neighbors}
    if normalized_method == "umap":
        method_params["min_dist"] = min_dist

    payload = json.dumps(
        {
            "folder_path": folder_path,
            "method": normalized_method,
            "max_points": max_points,
            "method_params": method_params,
            "embedding_space": embedding_space or DEFAULT_EMBEDDING_SPACE_CODE,
            "pca_dim": int(pca_dim) if pca_dim else 0,
            "output_v": 4,
        },
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()


def _resolve_pca_dim(pca_dim, source_dim):
    """Decide effective PCA target dimension for a given source dim.

    - ``pca_dim is None`` (caller did not pass): auto — 50 for source >= 1280,
      else off (0).
    - ``pca_dim == 0``: explicit off.
    - ``pca_dim > 0``: clamp to ``min(pca_dim, source_dim - 1)``; values
      ``>= source_dim`` are no-ops (return 0).
    """
    if pca_dim is None:
        return 50 if source_dim >= PCA_AUTO_THRESHOLD else 0
    n = int(pca_dim)
    if n <= 0 or n >= source_dim:
        return 0
    return n


def _project_pca(vecs, n_components):
    """Deterministic PCA pre-step. Returns ``vecs`` unchanged when disabled."""
    if not n_components or n_components <= 0 or n_components >= vecs.shape[1]:
        return vecs
    # n_components must also be <= n_samples
    n = min(n_components, max(1, vecs.shape[0] - 1))
    if n >= vecs.shape[1]:
        return vecs
    from sklearn.decomposition import PCA

    return PCA(n_components=n, random_state=42).fit_transform(vecs)


def _cache_path(cache_key):
    return _CACHE_DIR / f"{cache_key}.json"


def _load_cache(cache_key):
    path = _cache_path(cache_key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read embedding map cache %s: %s", path, exc)
    return None


def _save_cache(cache_key, data):
    _ensure_cache_dir()
    path = _cache_path(cache_key)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write embedding map cache %s: %s", path, exc)


def _normalize(matrix):
    """Row-wise L2 normalisation."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _effective_umap_n_neighbors(n_neighbors: int, n_samples: int) -> int:
    """UMAP requires ``2 <= n_neighbors < n_samples`` (strict upper bound)."""
    if n_samples <= MIN_POINTS:
        return max(2, int(n_neighbors))
    return max(2, min(int(n_neighbors), n_samples - 1))


def _project_umap(vecs, n_neighbors, min_dist):
    import umap  # optional dependency
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        n_components=2,
        metric="cosine",
        random_state=42,
    )
    return reducer.fit_transform(vecs)


def _project_tsne(vecs, n_neighbors):
    from sklearn.manifold import TSNE

    n = len(vecs)
    # sklearn: perplexity must be less than n_samples
    perplexity = float(min(max(1.0, float(n_neighbors)), max(1.0, n - 1.0001)))
    reducer = TSNE(
        n_components=2,
        metric="cosine",
        perplexity=perplexity,
        random_state=42,
        init="random",
    )
    return reducer.fit_transform(vecs)


def _scale_to_unit(coords):
    """Min-max scale both axes to [0.0, 1.0]."""
    result = coords.astype(float).copy()
    for axis in range(result.shape[1]):
        col = result[:, axis]
        lo, hi = col.min(), col.max()
        span = hi - lo
        result[:, axis] = (col - lo) / span if span > 0 else col * 0.0 + 0.5
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_embedding_map(
    folder_path=None,
    method=None,
    refresh=False,
    sample_limit=None,
    n_neighbors=None,
    min_dist=None,
    embedding_space=None,
    pca_dim=None,
):
    """
    Project image embeddings to 2D coordinates.

    Parameters
    ----------
    folder_path : str or None
        Scope to a specific folder; None means all images.
    method : {'umap', 'tsne'} or None
        Projection method.  Falls back to config, then 'umap'.
    refresh : bool
        If True, ignore cached result and recompute.
    sample_limit : int or None
        Maximum number of images to include; None means config default.
    n_neighbors : int or None
        UMAP/t-SNE neighbourhood size.  Falls back to config, then 30.
    min_dist : float or None
        UMAP min_dist parameter.  Falls back to config, then 0.1.
    embedding_space : str or None
        Embedding-space code (see ``modules.embedding_spaces.SPACE_DIMS``).
        Defaults to the 1280-d MobileNet space. Non-default spaces are
        Postgres-only and read straight from the per-dim fact table.
    pca_dim : int or None
        Target dimension for an optional PCA pre-step (sklearn).
        ``None`` = auto (50 when source dim >= 1280, off otherwise).
        ``0`` = explicitly off. Other values clamp to ``< source_dim``.

    Returns
    -------
    dict
        {
            "points": [{image_id, x, y, file_path, thumbnail_path,
                        label, rating, score_general, score_technical,
                        score_aesthetic, score_spaq, score_ava, score_koniq,
                        score_paq2piq, score_liqe}, ...],
            "meta":   {count, method, computed_at, cache_key,
                       embedding_space, pca_dim}
        }
        On error: "meta" contains an "error" key and "points" is [].
    """
    method = method or get_config_value("embedding_map.method", "umap")
    n_neighbors = n_neighbors if n_neighbors is not None else get_config_value(
        "embedding_map.n_neighbors", 30
    )
    min_dist = min_dist if min_dist is not None else get_config_value(
        "embedding_map.min_dist", 0.1
    )
    # Default cap keeps first UMAP/t-SNE interactive load responsive; raise in
    # config.json (`embedding_map.max_points`) for full-library projections.
    max_points = sample_limit or get_config_value("embedding_map.max_points", 15000)

    space_code = embedding_space or DEFAULT_EMBEDDING_SPACE_CODE
    if space_code not in SPACE_DIMS:
        return {
            "points": [],
            "meta": {
                "count": 0,
                "method": method,
                "embedding_space": space_code,
                "error": "unknown_embedding_space",
            },
        }

    cache_key = _make_cache_key(
        folder_path=folder_path,
        method=method,
        max_points=max_points,
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        embedding_space=space_code,
        pca_dim=pca_dim,
    )
    if not refresh:
        cached = _load_cache(cache_key)
        if cached:
            logger.debug("Embedding map: cache hit %s", cache_key)
            return cached

    from modules import projections_db

    rows = projections_db.get_embeddings_with_metadata_for_space(
        space_code=space_code,
        folder_path=folder_path,
        limit=max_points,
    )
    count = len(rows)

    meta_base = {
        "count": count,
        "method": method,
        "embedding_space": space_code,
    }

    if count < MIN_POINTS:
        logger.info("Embedding map: only %d images — too few to project", count)
        return {
            "points": [],
            "meta": {**meta_base, "error": "too_few_points"},
        }

    # Build embedding matrix
    vecs = np.array(
        [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows],
        dtype=np.float32,
    )
    vecs = _normalize(vecs)

    # Optional PCA pre-step (deterministic: random_state=42)
    effective_pca_dim = _resolve_pca_dim(pca_dim, vecs.shape[1])
    if effective_pca_dim:
        try:
            vecs = _project_pca(vecs, effective_pca_dim)
        except ImportError:
            logger.warning("sklearn.decomposition.PCA unavailable, skipping PCA pre-step")
            effective_pca_dim = 0

    umap_neighbors = _effective_umap_n_neighbors(n_neighbors, count)
    if umap_neighbors != n_neighbors:
        logger.debug(
            "Embedding map: clamped n_neighbors %s -> %s for n=%d",
            n_neighbors,
            umap_neighbors,
            count,
        )

    # Project to 2D
    actual_method = method
    try:
        if method == "umap":
            coords = _project_umap(vecs, umap_neighbors, min_dist)
        else:
            coords = _project_tsne(vecs, n_neighbors)
    except ImportError:
        logger.warning("umap-learn not available, falling back to t-SNE")
        actual_method = "tsne"
        coords = _project_tsne(vecs, n_neighbors)

    coords = _scale_to_unit(np.array(coords))

    points = [
        {
            "image_id": r["image_id"],
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "file_path": r["file_path"],
            "thumbnail_path": r["thumbnail_path"],
            "label": r["label"],
            "rating": r["rating"],
            "score_general": r["score_general"],
            "score_technical": r.get("score_technical"),
            "score_aesthetic": r.get("score_aesthetic"),
            "score_spaq": r.get("score_spaq"),
            "score_ava": r.get("score_ava"),
            "score_koniq": r.get("score_koniq"),
            "score_paq2piq": r.get("score_paq2piq"),
            "score_liqe": r.get("score_liqe"),
        }
        for i, r in enumerate(rows)
    ]

    meta = {
        "count": count,
        "method": actual_method,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "cache_key": cache_key,
        "embedding_space": space_code,
        "pca_dim": effective_pca_dim,
    }
    if actual_method == "umap":
        meta["n_neighbors_effective"] = umap_neighbors

    result = {
        "points": points,
        "meta": meta,
    }

    _save_cache(cache_key, result)
    logger.info(
        "Embedding map: projected %d images via %s (space=%s, pca=%s)",
        count,
        actual_method,
        space_code,
        effective_pca_dim or "off",
    )
    return result


def invalidate_embedding_map_cache(folder_path=None):
    """
    Delete cached projection files.  Pass folder_path to limit scope (best-effort
    prefix match on the cache filename is not possible; this always clears all
    cached files when folder_path is None, or all files when folder_path is given).

    Returns the number of files deleted.
    """
    if not _CACHE_DIR.exists():
        return 0
    deleted = 0
    for f in _CACHE_DIR.glob("*.json"):
        try:
            f.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Could not delete cache file %s: %s", f, exc)
    return deleted
