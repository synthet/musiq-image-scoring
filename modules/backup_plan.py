"""
Backup selection planning for gallery export.

Returns ranked image IDs using score floor, per-date embedding dedup, and optional MMR
multi-keep — mirrors gallery electron/backupSelection.ts semantics.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from modules import db
from modules.diversity import reorder_with_mmr

logger = logging.getLogger(__name__)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PATH_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass
class BackupPlanItem:
    image_id: int
    score: float
    reason: str


@dataclass
class BackupPlanResult:
    items: list[BackupPlanItem]
    deduplicated_count: int
    warnings: list[str]


def _backup_date_key(row: dict[str, Any]) -> str:
    cd = (row.get("capture_date") or "").strip()
    if _ISO_DATE.match(cd):
        return cd
    path = row.get("file_path") or row.get("path") or ""
    m = _PATH_DATE.search(path)
    return m.group(1) if m else "unknown"


def _compute_folder_threshold(group_len: int, stacked_count: int, rough_fill_ratio: float) -> float:
    burst_ratio = stacked_count / group_len if group_len else 0.0
    base = 0.85 + 0.13 * min(1.0, max(0.0, rough_fill_ratio))
    return max(0.80, min(0.99, base - burst_ratio * 0.05))


def _stack_prefilter(group: list[dict], max_keep: int = 2) -> tuple[list[dict], int]:
    by_stack: dict[Any, list[dict]] = defaultdict(list)
    candidates: list[dict] = []
    for row in group:
        sid = row.get("stack_id")
        if sid is None:
            # Unstacked images are distinct photos the culling phase did NOT find
            # near-duplicates for — keep each as its own singleton, never trim them
            # against one another.
            candidates.append(row)
            continue
        by_stack[sid].append(row)
    rejected = 0
    for members in by_stack.values():
        if len(members) <= max_keep:
            candidates.extend(members)
            continue
        sorted_m = sorted(members, key=lambda r: float(r.get("score_general") or 0), reverse=True)
        candidates.extend(sorted_m[:max_keep])
        rejected += len(sorted_m) - max_keep
    return candidates, rejected


def _find_clusters(group: list[dict], pairs: list[dict]) -> list[list[dict]]:
    by_id = {int(r["id"]): r for r in group}
    adj: dict[int, set[int]] = defaultdict(set)
    for p in pairs:
        a, b = int(p["id_a"]), int(p["id_b"])
        if a in by_id and b in by_id:
            adj[a].add(b)
            adj[b].add(a)
    visited: set[int] = set()
    clusters: list[list[dict]] = []
    for row in group:
        iid = int(row["id"])
        if iid in visited:
            continue
        queue = [iid]
        cluster_ids: list[int] = []
        visited.add(iid)
        while queue:
            cur = queue.pop(0)
            cluster_ids.append(cur)
            for nxt in adj.get(cur, ()):
                if nxt not in visited and nxt in by_id:
                    visited.add(nxt)
                    queue.append(nxt)
        clusters.append([by_id[cid] for cid in cluster_ids])
    return clusters


def _pick_cluster(
    cluster: list[dict],
    max_keep: int,
    diversity_lambda: float,
    embeddings: dict[int, bytes],
) -> tuple[list[dict], list[dict]]:
    if not cluster:
        return [], []
    sorted_c = sorted(cluster, key=lambda r: float(r.get("score_general") or 0), reverse=True)
    k = min(max_keep, len(sorted_c))
    if k <= 1:
        return [sorted_c[0]], sorted_c[1:]
    reordered = reorder_with_mmr(
        sorted_images=sorted_c,
        k=k,
        embeddings_dict=embeddings,
        lambda_val=diversity_lambda,
        score_key="score_general",
    )
    kept = reordered[:k]
    kept_ids = {int(r["id"]) for r in kept}
    rejected = [r for r in sorted_c if int(r["id"]) not in kept_ids]
    return kept, rejected


def _query_similar_pairs(image_ids: list[int], threshold: float) -> tuple[list[dict], str | None]:
    """Run one pgvector self-join over the given IDs. Returns (pairs, error)."""
    if len(image_ids) < 2:
        return [], None
    try:
        from modules import db_postgres
        from modules.db import _get_db_engine

        if _get_db_engine() != "postgres":
            return [], "backup plan requires PostgreSQL"

        placeholders = ",".join(["%s"] * len(image_ids))
        rows = db_postgres.execute_select(
            f"""
            SELECT e1.image_id AS id_a, e2.image_id AS id_b,
                   (1 - (e1.embedding <=> e2.embedding)) AS similarity
            FROM image_embeddings e1
            JOIN image_embeddings e2 ON e1.image_id < e2.image_id
            JOIN embedding_spaces es ON es.id = e1.embedding_space_id AND es.id = e2.embedding_space_id
            WHERE es.code = 'mobilenet_v2_imagenet_gap'
              AND e1.image_id IN ({placeholders})
              AND e2.image_id IN ({placeholders})
              AND (1 - (e1.embedding <=> e2.embedding)) >= %s
            """,
            tuple(image_ids) + tuple(image_ids) + (threshold,),
        )
        return [dict(r) for r in rows], None
    except Exception as e:
        logger.exception("backup plan similarity query failed")
        return [], str(e)


def _dedupe_pairs(pairs: list[dict]) -> list[dict]:
    seen: set[tuple[int, int]] = set()
    out: list[dict] = []
    for p in pairs:
        a, b = int(p["id_a"]), int(p["id_b"])
        key = (min(a, b), max(a, b))
        if key in seen:
            continue
        seen.add(key)
        out.append({"id_a": key[0], "id_b": key[1], "similarity": p.get("similarity")})
    return out


def _similar_pairs_in_group(
    image_ids: list[int], threshold: float, batch_size: int = 500
) -> tuple[list[dict], str | None]:
    """Batched similarity-pair lookup. Mirrors gallery fetchSimilarPairsBatched: per-batch
    queries plus pairwise cross-batch combination, then dedup — avoids one oversized self-join
    that can time out (and silently disable dedup) on large date groups."""
    if len(image_ids) < 2:
        return [], None

    batches = [image_ids[i : i + batch_size] for i in range(0, len(image_ids), batch_size)]
    batches = [b for b in batches if len(b) >= 2]
    if len(batches) <= 1:
        return _query_similar_pairs(image_ids, threshold)

    all_pairs: list[dict] = []
    first_err: str | None = None
    for batch in batches:
        rows, err = _query_similar_pairs(batch, threshold)
        all_pairs.extend(rows)
        if err and first_err is None:
            first_err = err
    for i in range(len(batches)):
        for j in range(i + 1, len(batches)):
            rows, err = _query_similar_pairs(batches[i] + batches[j], threshold)
            all_pairs.extend(rows)
            if err and first_err is None:
                first_err = err

    return _dedupe_pairs(all_pairs), first_err


def _fetch_scored_images(min_score: float, folder_path: str | None) -> list[dict]:
    clauses = ["i.score_general >= %s"]
    params: list[Any] = [min_score]
    if folder_path:
        clauses.append("i.file_path LIKE %s")
        prefix = folder_path.rstrip("/\\")
        params.append(f"{prefix}%")
    where = " AND ".join(clauses)
    from modules import db_postgres
    from modules.db import _get_db_engine

    if _get_db_engine() != "postgres":
        return []

    rows = db_postgres.execute_select(
        f"""
        SELECT i.id, i.file_path, i.score_general, i.stack_id,
               (COALESCE(e.date_time_original, e.create_date, i.created_at))::date::text AS capture_date
        FROM images i
        LEFT JOIN image_exif e ON e.image_id = i.id
        WHERE {where}
        ORDER BY i.score_general DESC NULLS LAST
        """,
        tuple(params),
    )
    return [dict(r) for r in rows]


def plan_backup_selection(
    *,
    min_score: float = 0.7,
    diversity_lambda: float = 0.7,
    max_per_cluster: int = 2,
    folder_path: str | None = None,
    rough_fill_ratio: float = 1.0,
    pair_batch_size: int = 500,
) -> BackupPlanResult:
    """Build backup candidate list (image IDs + scores)."""
    warnings: list[str] = []
    all_rows = _fetch_scored_images(min_score, folder_path)
    if not all_rows:
        return BackupPlanResult(items=[], deduplicated_count=0, warnings=warnings)

    if rough_fill_ratio >= 0.9:
        eff_max = max_per_cluster
    elif rough_fill_ratio >= 0.5:
        eff_max = min(max_per_cluster, 2)
    else:
        eff_max = 1

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        groups[_backup_date_key(row)].append(row)

    selected: list[dict] = []
    dedup_count = 0

    for date_key, group in groups.items():
        stacked = sum(1 for r in group if r.get("stack_id") is not None)
        threshold = _compute_folder_threshold(len(group), stacked, rough_fill_ratio)
        candidates, stack_rej = _stack_prefilter(group, 2)
        dedup_count += stack_rej

        ids = [int(r["id"]) for r in candidates]
        pairs, err = _similar_pairs_in_group(ids, threshold, pair_batch_size)
        if err:
            warnings.append(f"Similarity query failed for {date_key}: {err}")
            pairs = []

        clusters = _find_clusters(candidates, pairs)
        cluster_ids = [int(r["id"]) for c in clusters for r in c]
        embeddings = db.get_image_embeddings_batch(cluster_ids)

        for cluster in clusters:
            kept, rejected = _pick_cluster(cluster, eff_max, diversity_lambda, embeddings)
            selected.extend(kept)
            dedup_count += len(rejected)

    items = [
        BackupPlanItem(
            image_id=int(r["id"]),
            score=float(r.get("score_general") or 0),
            reason="selected",
        )
        for r in selected
    ]
    items.sort(key=lambda x: (-x.score, x.image_id))
    return BackupPlanResult(items=items, deduplicated_count=dedup_count, warnings=warnings)
