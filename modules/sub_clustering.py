"""Two-level (sub-)clustering inside a single stack.

The primary clustering phase groups visually similar shots into stacks at a
loose distance threshold (``clustering.default_threshold``). When auto-picking,
applying a flat top-fraction across the *whole* stack systematically rejects
diverse-but-lower-scored frames that the photographer actually wants to keep
(e.g. the same family in three distinguishable poses).

This module performs a second, *tighter* agglomerative pass within each stack
so the caller can apply its pick/reject policy *per sub-cluster*. Each
sub-cluster represents a visually near-identical micro-group; the policy keeps
the best of each and rejects the duplicates inside that micro-group rather
than across the whole stack.

Pure compute. No I/O. The caller is responsible for fetching embeddings via
``db.get_image_embeddings_batch`` (or equivalent) and persisting decisions.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Mapping, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


def _decode_embedding(blob: object) -> Optional[np.ndarray]:
    """Decode a raw embedding payload to a 1D float32 vector."""
    if blob is None:
        return None
    try:
        if isinstance(blob, np.ndarray):
            arr = blob.astype(np.float32, copy=False)
        elif isinstance(blob, (bytes, bytearray, memoryview)):
            arr = np.frombuffer(bytes(blob), dtype=np.float32)
        elif isinstance(blob, (list, tuple)):
            arr = np.asarray(blob, dtype=np.float32)
        else:
            return None
    except Exception:
        return None
    if arr.size == 0 or not np.isfinite(arr).all():
        return None
    return arr


def compute_sub_clusters(
    images: Sequence[Mapping],
    embeddings_by_id: Mapping[int, object],
    distance_threshold: float,
    *,
    id_key: str = "id",
) -> List[List[dict]]:
    """Group ``images`` into sub-clusters using cosine AgglomerativeClustering.

    Args:
        images: Image rows for a single stack. Each row must expose ``id_key``.
        embeddings_by_id: Mapping from image id to a raw embedding payload
            (bytes, numpy array, or list). Missing entries are tolerated.
        distance_threshold: Cosine distance threshold for the secondary
            clustering. Should be **tighter** than the primary stack threshold
            (e.g. primary 0.15 → secondary 0.05).
        id_key: Key used to look up the image id on each row (default ``"id"``).

    Returns:
        A list of sub-clusters; each sub-cluster is a list of image dicts in
        the input order. Images whose embedding is missing or malformed are
        collected into a single fallback sub-cluster so the caller's policy
        still processes them.

    Trivial cases:
        * 0 images → ``[]``
        * 1 image  → ``[[that image]]``
        * any image without a usable embedding → joins the fallback bucket
          regardless of similarity to other images
    """
    if not images:
        return []
    if len(images) == 1:
        return [list(images)]

    valid_rows: List[dict] = []
    valid_vecs: List[np.ndarray] = []
    fallback_rows: List[dict] = []

    expected_dim: Optional[int] = None
    for row in images:
        try:
            img_id = int(row[id_key])
        except (KeyError, TypeError, ValueError):
            fallback_rows.append(dict(row))
            continue
        vec = _decode_embedding(embeddings_by_id.get(img_id))
        if vec is None:
            fallback_rows.append(dict(row))
            continue
        if expected_dim is None:
            expected_dim = vec.shape[0]
        elif vec.shape[0] != expected_dim:
            # Mismatched dim (mixed embedding spaces) — keep the image safe
            # via the fallback bucket rather than crashing the whole stack.
            fallback_rows.append(dict(row))
            continue
        valid_rows.append(dict(row))
        valid_vecs.append(vec)

    sub_clusters: List[List[dict]] = []

    if len(valid_rows) >= 2:
        try:
            from sklearn.cluster import AgglomerativeClustering
        except Exception as e:  # pragma: no cover - optional dep guard
            logger.warning(
                "sub-clustering unavailable (sklearn import failed: %s) — "
                "treating the whole stack as one sub-cluster.",
                e,
            )
            sub_clusters.append(valid_rows)
        else:
            X = np.vstack(valid_vecs).astype(np.float32, copy=False)
            try:
                model = AgglomerativeClustering(
                    n_clusters=None,
                    metric="cosine",
                    linkage="average",
                    distance_threshold=float(distance_threshold),
                )
                labels = model.fit_predict(X)
            except Exception as e:
                logger.warning(
                    "AgglomerativeClustering failed (%s) — treating the whole "
                    "stack as one sub-cluster.",
                    e,
                )
                sub_clusters.append(valid_rows)
            else:
                buckets: dict[int, List[dict]] = {}
                for label, row in zip(labels, valid_rows):
                    buckets.setdefault(int(label), []).append(row)
                # Stable ordering: by first appearance of each label.
                seen: List[int] = []
                for label in labels:
                    li = int(label)
                    if li not in seen:
                        seen.append(li)
                sub_clusters.extend(buckets[li] for li in seen)
    elif len(valid_rows) == 1:
        sub_clusters.append(valid_rows)

    if fallback_rows:
        logger.debug(
            "sub-clustering: %d image(s) routed to fallback bucket "
            "(missing/malformed embedding).",
            len(fallback_rows),
        )
        sub_clusters.append(fallback_rows)

    return sub_clusters


def assign_decisions_in_stack(
    images: Sequence[Mapping],
    embeddings_by_id: Mapping[int, object],
    distance_threshold: float,
    *,
    score_field: str = "score_general",
    frac: float = 0.33,
    id_key: str = "id",
) -> List[tuple]:
    """Two-level pick/reject classification for a single stack.

    Splits ``images`` into sub-clusters via :func:`compute_sub_clusters`, sorts
    each sub-cluster by ``score_field`` DESC, ``created_at`` ASC, ``id`` ASC,
    then runs :func:`modules.selection_policy.classify_sorted_ids` independently
    inside each sub-cluster. The aggregated decisions are returned as a list
    of ``(image_id, decision, file_path)`` tuples, the same shape consumed by
    :func:`db.batch_update_cull_decisions`.

    The function is pure — no DB calls, no logging side-effects beyond the
    debug line in :func:`compute_sub_clusters`. Singletons and stacks of size
    ≤1 short-circuit through ``classify_sorted_ids``'s small-stack rules.
    """
    from modules.selection_policy import classify_sorted_ids  # local to break cycles

    if not images:
        return []

    sub_groups = compute_sub_clusters(
        images, embeddings_by_id, distance_threshold, id_key=id_key
    )
    if not sub_groups:
        sub_groups = [list(images)]

    def _sort_key(img):
        s = img.get(score_field) or 0
        c = img.get("created_at") or ""
        try:
            i = int(img.get(id_key) or 0)
        except (TypeError, ValueError):
            i = 0
        return (-float(s) if s else 0, str(c), i)

    decisions: List[tuple] = []
    for sub in sub_groups:
        sorted_sub = sorted(sub, key=_sort_key)
        sorted_ids = [int(img[id_key]) for img in sorted_sub if id_key in img]
        path_by_id = {int(img[id_key]): (img.get("file_path") or "") for img in sorted_sub if id_key in img}
        cls = classify_sorted_ids(sorted_ids, frac=frac)
        for img_id, decision in cls.items():
            decisions.append((img_id, decision, path_by_id.get(img_id, "")))
    return decisions


def iter_sub_cluster_assignments(
    sub_clusters: Iterable[Sequence[Mapping]],
    *,
    id_key: str = "id",
) -> dict[int, int]:
    """Flatten ``compute_sub_clusters`` output into ``image_id -> sub_cluster_idx``.

    Convenience for logging / persistence; the index is the position of the
    sub-cluster in the returned list (deterministic for a given input).
    """
    out: dict[int, int] = {}
    for idx, group in enumerate(sub_clusters):
        for row in group:
            try:
                out[int(row[id_key])] = idx
            except (KeyError, TypeError, ValueError):
                continue
    return out
