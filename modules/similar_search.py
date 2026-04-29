"""
Similar Image Search

Finds visually similar images using stored MobileNetV2 embeddings
and cosine similarity ranking. Uses pgvector SQL operators for
search_similar_images() and find_near_duplicates() for efficiency.
find_outliers() remains in Python for complex statistical logic.

search_by_text() encodes free-text queries with the CLIP ViT-B/32
text tower and searches against stored CLIP image embeddings via
pgvector cosine distance (Postgres-only).
"""

import logging
import numpy as np
from modules import db

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1280  # MobileNetV2 global average pooling output


def _normalize(v):
    """L2-normalize a vector (or row-wise for a matrix)."""
    if v.ndim == 1:
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return v / norms


def _get_or_compute_embedding(image_id, file_path=None):
    """
    Return the embedding for an image as a numpy array, computing and persisting it
    on the fly if not already stored in the DB.
    """
    emb_bytes = db.get_image_embedding(image_id)
    if emb_bytes is not None:
        return np.frombuffer(emb_bytes, dtype=np.float32)

    if not file_path:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("SELECT file_path FROM images WHERE id = %s", (image_id,))
            row = c.fetchone()
            file_path = row[0] if row else None
        if not file_path:
            return None

    from modules.clustering import ClusteringEngine
    engine = ClusteringEngine()
    features, valid = engine.extract_features([file_path])
    if len(features) == 0:
        return None

    vec = features[0].astype(np.float32)
    db.update_image_embedding(image_id, vec.tobytes())
    return vec


def _search_similar_images_numpy(example_image_id, query_vec, limit, folder_path, min_similarity):
    """Firebird / non-pgvector: rank by cosine similarity in Python."""
    candidates = db.get_embeddings_for_search(folder_path=folder_path, limit=None)
    if not candidates:
        return {
            "error": "No embeddings available for similarity search; run culling/clustering or scripts/maintenance/populate_missing_embeddings.py (see docs/technical/EMBEDDINGS.md).",
        }
    q = query_vec.astype(np.float32, copy=False)
    q = _normalize(q.reshape(1, -1))[0]
    ranked = []
    for cid, cpath, cbytes in candidates:
        if cid == example_image_id:
            continue
        cv = np.frombuffer(cbytes, dtype=np.float32)
        cn = _normalize(cv.reshape(1, -1))[0]
        sim = float(np.dot(q, cn))
        ranked.append((sim, cid, cpath))
    ranked.sort(key=lambda x: -x[0])
    results = []
    for sim, cid, cpath in ranked[:limit]:
        if min_similarity is not None and sim < min_similarity:
            break
        results.append({
            "image_id": int(cid),
            "file_path": cpath,
            "similarity": round(sim, 6),
        })
    return results


def _search_similar_in_space_pg(example_image_id, embedding_space, limit, folder_path, min_similarity):
    """Postgres-only similarity search scoped to a specific embedding space.

    Unlike the default-space path, there is no legacy column to fall back on
    for non-MobileNet spaces — the image must have a row in the matching
    per-dim fact table (see ``image_embeddings_512`` / ``image_embeddings_768``).
    """
    from modules.embedding_spaces import SPACE_DIMS, get_embedding_space_id

    expected_dim = SPACE_DIMS.get(embedding_space)
    if expected_dim is None:
        return {"error": f"Unknown embedding_space: {embedding_space}"}
    space_id = get_embedding_space_id(embedding_space)
    if space_id is None:
        return {"error": f"Embedding space not registered: {embedding_space}"}
    table = db._pg_embedding_table_for_dim(expected_dim)

    with db.connection() as conn:
        c = conn.cursor()
        c.execute(
            f"SELECT embedding FROM {table} WHERE image_id = %s AND embedding_space_id = %s",
            (example_image_id, space_id),
        )
        row = c.fetchone()
        if not row or row[0] is None:
            return {
                "error": (
                    f"Example image {example_image_id} has no stored embedding for "
                    f"space {embedding_space}; re-run the phase that produces it."
                ),
            }
        import numpy as np

        raw = row[0]
        query_vec = np.asarray(raw, dtype=np.float32) if not isinstance(raw, np.ndarray) else raw.astype(np.float32)

        params: list = [query_vec, example_image_id, space_id]
        folder_clause = ""
        if folder_path:
            import os

            norm = os.path.normpath(folder_path)
            c.execute("SELECT id FROM folders WHERE path = %s", (norm,))
            frow = c.fetchone()
            if not frow:
                return []
            folder_clause = "AND i.folder_id = %s"
            params.insert(1, frow[0])

        sql = f"""
            SELECT i.id AS image_id,
                   i.file_path,
                   1 - (e.embedding <=> %s::vector) AS similarity
            FROM {table} e
            JOIN images i ON i.id = e.image_id
            WHERE e.image_id != %s
              AND e.embedding_space_id = %s
              {folder_clause}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
        """
        params.append(query_vec)
        params.append(limit)
        c.execute(sql, tuple(params))
        rows = c.fetchall()

    results = []
    for row in rows:
        sim = float(row['similarity'])
        if min_similarity is not None and sim < min_similarity:
            break
        results.append({
            "image_id": int(row['image_id']),
            "file_path": row['file_path'],
            "similarity": round(sim, 6),
            "embedding_space": embedding_space,
        })
    return results


def search_similar_images(example_path=None, example_image_id=None,
                          limit=20, folder_path=None, min_similarity=None,
                          embedding_space=None):
    """
    Find images most visually similar to a given example.
    Postgres uses pgvector cosine distance; Firebird ranks candidates in Python.

    Provide either example_path (file path string) or example_image_id (int).
    If ``embedding_space`` is given (e.g. ``clip_vit_b32_image``), search uses
    the matching per-dim table instead of the default MobileNet space. Non-default
    spaces are Postgres-only and do not fall back to a legacy column.

    Returns a list of dicts sorted by descending similarity.
    """
    if not example_path and example_image_id is None:
        return {"error": "Provide example_path or example_image_id"}

    # Resolve the example image
    if example_path:
        details = db.get_image_details(example_path)
        if not details or not details.get('id'):
            return {"error": f"Image not found in database: {example_path}"}
        example_image_id = details['id']
        file_path = example_path
    else:
        with db.connection() as conn:
            c = conn.cursor()
            ph = "%s" if db._get_db_engine() == "postgres" else "?"
            c.execute(f"SELECT file_path FROM images WHERE id = {ph}", (example_image_id,))
            row = c.fetchone()
            file_path = row[0] if row else None

    # Non-default space: delegate to the per-dim query path (Postgres only).
    from modules.embedding_spaces import DEFAULT_EMBEDDING_SPACE_CODE

    if embedding_space and embedding_space != DEFAULT_EMBEDDING_SPACE_CODE:
        if db._get_db_engine() != "postgres":
            return {"error": "Non-default embedding_space requires PostgreSQL (pgvector)."}
        return _search_similar_in_space_pg(
            example_image_id, embedding_space, limit, folder_path, min_similarity
        )

    query_vec = _get_or_compute_embedding(example_image_id, file_path)
    if query_vec is None:
        return {"error": "Could not obtain embedding for the example image"}

    if db._get_db_engine() != "postgres":
        return _search_similar_images_numpy(
            example_image_id, query_vec, limit, folder_path, min_similarity
        )

    # Postgres: pgvector cosine distance operator <=> for efficient ANN search
    with db.connection() as conn:
        c = conn.cursor()
        sub = db._pg_default_embedding_space_subquery_sql()
        has_e = db._postgres_has_default_embedding_sql("i")
        emb_expr = "COALESCE(ie.embedding, i.image_embedding)"

        params = [query_vec, example_image_id]
        folder_clause = ""

        if folder_path:
            import os
            norm = os.path.normpath(folder_path)
            c.execute("SELECT id FROM folders WHERE path = %s", (norm,))
            frow = c.fetchone()
            if not frow:
                return []
            folder_id = frow[0]
            folder_clause = "AND i.folder_id = %s"
            params.insert(1, folder_id)

        # <=> is cosine distance (0=identical, 2=opposite)
        # similarity = 1 - cosine_distance
        sql = f"""
            SELECT i.id AS image_id,
                   i.file_path,
                   1 - ({emb_expr} <=> %s::vector) AS similarity
            FROM images i
            LEFT JOIN image_embeddings ie ON ie.image_id = i.id AND ie.embedding_space_id = {sub}
            WHERE {has_e}
              AND i.id != %s
              {folder_clause}
            ORDER BY {emb_expr} <=> %s::vector
            LIMIT %s
        """
        params.extend([query_vec, limit])
        c.execute(sql, tuple(params))
        rows = c.fetchall()

    results = []
    for row in rows:
        sim = float(row['similarity'])
        if min_similarity is not None and sim < min_similarity:
            break
        results.append({
            "image_id": int(row['image_id']),
            "file_path": row['file_path'],
            "similarity": round(sim, 6),
        })

    return results


# ── Free-text (semantic) search via CLIP ───────────────────────────

# Module-level cache for the CLIP model / processor (loaded lazily once).
_clip_model_cache: dict = {}


def _get_clip_text_embedding(query: str) -> np.ndarray:
    """Encode *query* with the CLIP ViT-B/32 text tower → L2-normalized 512-d float32 vector.

    The model is lazy-loaded on first call and cached for the process lifetime
    (same ``openai/clip-vit-base-patch32`` weights used by ``KeywordScorer``).
    """
    import torch

    if "model" not in _clip_model_cache:
        from transformers import CLIPModel, CLIPProcessor
        from modules import config

        tagging_cfg = config.get_config_section("tagging")
        model_name = tagging_cfg.get("clip_model", "openai/clip-vit-base-patch32")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _clip_model_cache["model"] = CLIPModel.from_pretrained(model_name).to(device)
        _clip_model_cache["processor"] = CLIPProcessor.from_pretrained(model_name)
        _clip_model_cache["device"] = device
        logger.info("CLIP model loaded for text search (device=%s, model=%s)", device, model_name)

    model = _clip_model_cache["model"]
    processor = _clip_model_cache["processor"]
    device = _clip_model_cache["device"]

    inputs = processor(text=[query], return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.get_text_features(**inputs)

    # Handle different return types from get_text_features (tensor vs model output).
    text_features = outputs
    if not hasattr(text_features, "cpu"):
        # Some transformers versions return a ModelOutput from get_text_features.
        if hasattr(text_features, "text_embeds") and text_features.text_embeds is not None:
            text_features = text_features.text_embeds
        elif hasattr(text_features, "pooler_output") and text_features.pooler_output is not None:
            text_features = text_features.pooler_output
        elif hasattr(text_features, "last_hidden_state") and text_features.last_hidden_state is not None:
            # [batch, seq, dim] -> CLS / SOS token embedding
            text_features = text_features.last_hidden_state[:, 0, :]
        elif isinstance(text_features, (list, tuple)) and text_features:
            text_features = text_features[0]

    if not hasattr(text_features, "cpu"):
        raise TypeError(f"Unexpected CLIP text features type: {type(text_features)!r}")

    vec = text_features.detach().cpu().numpy().astype(np.float32)
    vec = np.asarray(vec, dtype=np.float32).reshape(-1)
    if vec.ndim != 1:
        raise ValueError(f"CLIP text embedding must be 1D, got shape={vec.shape!r}")

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec


def search_by_text(
    query: str,
    limit: int = 20,
    folder_path: str | None = None,
    min_similarity: float | None = None,
) -> dict | list:
    return _search_by_text_impl(query, limit, folder_path, min_similarity)

def _search_by_text_impl(
    query: str,
    limit: int = 20,
    folder_path: str | None = None,
    min_similarity: float | None = None,
) -> dict | list:
    """Find images semantically matching a free-text *query*.

    Encodes the query with the CLIP ViT-B/32 text tower (512-d) and runs a
    pgvector cosine-distance search against stored ``clip_vit_b32_image``
    embeddings in ``image_embeddings_512``.

    Requires PostgreSQL with pgvector; returns an error dict on other engines.

    Returns a list of ``{image_id, file_path, similarity}`` dicts sorted by
    descending similarity, or a dict with an ``error`` key on failure.
    """
    if not query or not query.strip():
        return {"error": "query must be a non-empty string"}

    if db._get_db_engine() != "postgres":
        return {"error": "Text search requires PostgreSQL with pgvector."}

    from modules.embedding_spaces import CLIP_IMAGE_SPACE_CODE, get_embedding_space_id

    space_id = get_embedding_space_id(CLIP_IMAGE_SPACE_CODE)
    if space_id is None:
        return {"error": f"Embedding space not registered: {CLIP_IMAGE_SPACE_CODE}"}

    table = db._pg_embedding_table_for_dim(512)

    try:
        query_vec = _get_clip_text_embedding(query.strip())
    except Exception as e:
        logger.error("Failed to encode text query: %s", e)
        return {"error": f"Failed to encode text query: {e}"}

    with db.connection() as conn:
        c = conn.cursor()

        params: list = [query_vec, space_id]
        folder_clause = ""
        if folder_path:
            import os

            norm = os.path.normpath(folder_path)
            c.execute("SELECT id FROM folders WHERE path = %s", (norm,))
            frow = c.fetchone()
            if not frow:
                return []
            folder_clause = "AND i.folder_id = %s"
            params.append(frow[0])

        sql = f"""
            SELECT i.id   AS image_id,
                   i.file_path,
                   1 - (e.embedding <=> %s::vector) AS similarity
            FROM {table} e
            JOIN images i ON i.id = e.image_id
            WHERE e.embedding_space_id = %s
              {folder_clause}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
        """
        params.append(query_vec)
        params.append(limit)
        c.execute(sql, tuple(params))
        rows = c.fetchall()

    results = []
    for row in rows:
        sim = float(row["similarity"])
        if min_similarity is not None and sim < min_similarity:
            break
        results.append({
            "image_id": int(row["image_id"]),
            "file_path": row["file_path"],
            "similarity": round(sim, 6),
        })

    return results


def find_near_duplicates(threshold=None, folder_path=None, limit=None):
    """
    Find near-duplicate image pairs in the database based on embedding cosine similarity.

    Postgres: SQL self-join with pgvector for smaller libraries; Python block-wise for large sets.
    Firebird: always uses Python over ``get_embeddings_for_search`` (mock-friendly in tests).

    Returns a list of dicts representing near-duplicate pairs, sorted by similarity descending:
        [{'image_id_a': int, 'image_id_b': int, 'file_path_a': str, 'file_path_b': str, 'similarity': float}, ...]
    """
    from modules import config

    if threshold is None:
        threshold = config.get_config_value("similarity.duplicate_threshold", 0.98)
    max_pairs = config.get_config_value("similarity.duplicate_max_pairs", 5000)

    if limit is None:
        limit = max_pairs
    else:
        limit = min(limit, max_pairs)

    if db._get_db_engine() != "postgres":
        return _find_near_duplicates_python(threshold, folder_path, limit)

    # Postgres: count embeddings to choose pgvector self-join vs Python block path
    with db.connection() as conn:
        c = conn.cursor()
        import os
        sub = db._pg_default_embedding_space_subquery_sql()
        has_e = db._postgres_has_default_embedding_sql("images")
        folder_clause = ""
        count_params = []
        if folder_path:
            norm = os.path.normpath(folder_path)
            c.execute("SELECT id FROM folders WHERE path = %s", (norm,))
            frow = c.fetchone()
            if not frow:
                return []
            folder_id = frow[0]
            folder_clause = "AND images.folder_id = %s"
            count_params = [folder_id]

        count_sql = f"""
            SELECT COUNT(*) FROM images
            LEFT JOIN image_embeddings ie ON ie.image_id = images.id AND ie.embedding_space_id = {sub}
            WHERE {has_e} {folder_clause}
        """
        c.execute(count_sql, tuple(count_params))
        count_row = c.fetchone()
        n_embeddings = count_row[0] if count_row else 0

    if n_embeddings < 2:
        return []

    PYTHON_THRESHOLD = 5000
    if n_embeddings > PYTHON_THRESHOLD:
        return _find_near_duplicates_python(threshold, folder_path, limit)

    # Postgres: SQL self-join using pgvector
    with db.connection() as conn:
        c = conn.cursor()
        sub = db._pg_default_embedding_space_subquery_sql()
        has_e_a = db._postgres_has_default_embedding_sql("a")
        has_e_b = db._postgres_has_default_embedding_sql("b")
        emb_expr = "COALESCE(ie_a.embedding, a.image_embedding)"
        emb_expr_b = "COALESCE(ie_b.embedding, b.image_embedding)"
        cosine_dist_threshold = 1.0 - threshold  # convert similarity → distance

        sql = f"""
            SELECT a.id AS image_id_a, b.id AS image_id_b,
                   a.file_path AS file_path_a, b.file_path AS file_path_b,
                   1 - ({emb_expr} <=> {emb_expr_b}) AS similarity
            FROM images a
            LEFT JOIN image_embeddings ie_a ON ie_a.image_id = a.id AND ie_a.embedding_space_id = {sub}
            JOIN images b ON b.id > a.id
            LEFT JOIN image_embeddings ie_b ON ie_b.image_id = b.id AND ie_b.embedding_space_id = {sub}
            WHERE {has_e_a}
              AND {has_e_b}
              AND ({emb_expr} <=> {emb_expr_b}) <= %s
              {folder_clause if folder_clause else ''}
            ORDER BY similarity DESC
            LIMIT %s
        """
        sql_params = [cosine_dist_threshold]
        if folder_clause and count_params:
            # need folder_id for both a and b
            sql_params = [cosine_dist_threshold, count_params[0], count_params[0], limit]
        else:
            sql_params = [cosine_dist_threshold, limit]

        c.execute(sql, tuple(sql_params))
        rows = c.fetchall()

    results = []
    for row in rows:
        results.append({
            "image_id_a": int(row['image_id_a']),
            "image_id_b": int(row['image_id_b']),
            "file_path_a": row['file_path_a'],
            "file_path_b": row['file_path_b'],
            "similarity": round(float(row['similarity']), 6),
        })
    return results


def _find_near_duplicates_python(threshold=0.98, folder_path=None, limit=5000):
    """
    Python block-wise near-duplicate detection (fallback for large libraries).
    Loads all embeddings and computes cosine similarity in numpy batches.
    """
    candidates = db.get_embeddings_for_search(folder_path=folder_path)
    if not candidates or len(candidates) < 2:
        return []

    ids = []
    paths = []
    vecs = []
    for cid, cpath, cbytes in candidates:
        ids.append(cid)
        paths.append(cpath)
        vecs.append(np.frombuffer(cbytes, dtype=np.float32))

    matrix = np.stack(vecs)
    matrix_norm = _normalize(matrix)

    n = len(ids)
    results = []
    block_size = 2000

    for i in range(0, n, block_size):
        end_i = min(i + block_size, n)
        block_a = matrix_norm[i:end_i]

        for j in range(i, n, block_size):
            end_j = min(j + block_size, n)
            block_b = matrix_norm[j:end_j]

            sims = block_a @ block_b.T

            rows_idx, cols_idx = np.where(sims >= threshold)

            for r, c in zip(rows_idx, cols_idx):
                global_i = i + r
                global_j = j + c

                if global_i < global_j:
                    results.append({
                        "image_id_a": int(ids[global_i]),
                        "image_id_b": int(ids[global_j]),
                        "file_path_a": paths[global_i],
                        "file_path_b": paths[global_j],
                        "similarity": round(float(sims[r, c]), 6)
                    })

    results.sort(key=lambda x: (-x['similarity'], x['image_id_a'], x['image_id_b']))
    return results[:limit]


def find_outliers(folder_path, z_threshold=None, k=None, limit=None):
    """
    Identify images that are visually atypical inside a folder.

    For each image, computes the mean cosine similarity to its top-K nearest
    neighbors, then z-scores the distribution and flags images whose z-score
    falls at or below -z_threshold.

    Returns a dict with:
        outliers  – list of flagged images (sorted by z_score ascending)
        stats     – folder-level summary (mean, std, total, z_threshold)
        skipped   – list of images missing embeddings (anomaly_class: embedding_missing)
    """
    from modules import config

    if z_threshold is None:
        z_threshold = config.get_config_value("similarity.outlier_z_threshold", 2.0)
    if k is None:
        k = config.get_config_value("similarity.outlier_k_neighbors", 10)
    min_folder_size = config.get_config_value("similarity.outlier_min_folder_size", 20)
    if limit is None:
        limit = 100

    if not folder_path:
        return {"error": "folder_path is required"}

    # Fetch all images in the folder (with and without embeddings)
    candidates = db.get_embeddings_for_search(folder_path=folder_path)

    # Also detect images that have no embedding at all
    skipped = []
    ids = []
    paths = []
    vecs = []

    if candidates:
        for cid, cpath, cbytes in candidates:
            if cbytes is None:
                skipped.append({
                    "image_id": int(cid),
                    "file_path": cpath,
                    "anomaly_class": "embedding_missing",
                })
                continue
            ids.append(cid)
            paths.append(cpath)
            vecs.append(np.frombuffer(cbytes, dtype=np.float32))

    n = len(ids)
    if n < min_folder_size:
        return {
            "outliers": [],
            "stats": {
                "total_with_embeddings": n,
                "min_folder_size": min_folder_size,
                "reason": "folder_too_small",
            },
            "skipped": skipped,
        }

    matrix = np.stack(vecs)
    matrix_norm = _normalize(matrix)

    # Compute mean of top-K similarities using block-wise processing to avoid huge sim_matrix
    effective_k = min(k, n - 1)
    scores = np.zeros(n, dtype=np.float64)
    block_size = 2000

    for i in range(0, n, block_size):
        end_i = min(i + block_size, n)
        block_a = matrix_norm[i:end_i]
        
        # We need pairwise similarity of block_a vs ALL images to find top-K
        # This still involves n * block_size similarities at a time.
        # For 38k images and block_size 2000: 38000 * 2000 * 8 bytes ~= 600MB. Very safe.
        sims_block = block_a @ matrix_norm.T
        
        for idx_in_block in range(end_i - i):
            global_idx = i + idx_in_block
            row = sims_block[idx_in_block].copy()
            row[global_idx] = -np.inf  # exclude self
            
            # Use argpartition to find top-K indices efficiently
            top_k_vals = np.partition(row, -effective_k)[-effective_k:]
            scores[global_idx] = float(np.mean(top_k_vals))

    # Z-score
    folder_mean = float(np.mean(scores))
    folder_std = float(np.std(scores))
    if folder_std == 0:
        z_scores = np.zeros(n, dtype=np.float64)
    else:
        z_scores = (scores - folder_mean) / folder_std

    # Flag outliers
    outlier_indices = np.where(z_scores <= -z_threshold)[0]

    # Sort by z_score ascending (worst outliers first)
    outlier_indices = outlier_indices[np.argsort(z_scores[outlier_indices])]

    outliers = []
    for idx in outlier_indices:
        if len(outliers) >= limit:
            break

        # Need the nearest neighbors for this specific outlier (small block here)
        vec_norm = matrix_norm[idx].reshape(1, -1)
        row = (vec_norm @ matrix_norm.T)[0].copy()
        row[idx] = -np.inf
        neighbor_k = min(3, n - 1)
        top_neighbor_indices = np.argpartition(row, -neighbor_k)[-neighbor_k:]
        top_neighbor_indices = top_neighbor_indices[np.argsort(-row[top_neighbor_indices])]

        nearest_neighbors = []
        for ni in top_neighbor_indices:
            nearest_neighbors.append({
                "image_id": int(ids[ni]),
                "file_path": paths[ni],
                "similarity": round(float(row[ni]), 6),
            })

        outliers.append({
            "image_id": int(ids[idx]),
            "file_path": paths[idx],
            "outlier_score": round(float(scores[idx]), 6),
            "z_score": round(float(z_scores[idx]), 4),
            "nearest_neighbors": nearest_neighbors,
        })

    return {
        "outliers": outliers,
        "stats": {
            "total_with_embeddings": n,
            "folder_mean": round(folder_mean, 6),
            "folder_std": round(folder_std, 6),
            "z_threshold": z_threshold,
            "k_neighbors": effective_k,
            "outliers_found": len(outliers),
        },
        "skipped": skipped,
    }
