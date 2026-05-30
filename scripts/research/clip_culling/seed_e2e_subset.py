#!/usr/bin/env python3
"""Phase 0 seed: copy a representative subset from prod @5432 into E2E @5433.

Read-only on production; all writes go to ``image_scoring_test``. IDs are
preserved so on-disk RAW/thumbnail paths still resolve and so embeddings keyed
by ``image_id`` line up. Idempotent (ON CONFLICT upserts).

    python -m scripts.research.clip_culling.seed_e2e_subset --folders 62,44,45,676

Default folders are bird (``species:*``) telephoto folders that include
multi-image stacks and the full Red/Yellow/Green/Blue/Purple human label range.
"""

from __future__ import annotations

import argparse
import logging

import psycopg2.extras

from scripts.research.clip_culling import common
from modules import db_postgres

logger = logging.getLogger("clip_culling.seed")

DEFAULT_FOLDERS = [62, 44, 45, 676]


def _prod_columns(prod, table: str) -> list[str]:
    with prod.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=%s ORDER BY ordinal_position",
            (table,),
        )
        return [r[0] for r in cur.fetchall()]


def _e2e_columns(table: str) -> set[str]:
    rows = db_postgres.execute_select(
        "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
        (table,),
    )
    return {r["column_name"] for r in rows}


def _copy_rows(prod, table: str, where_sql: str, params: tuple, *,
               conflict_cols: str, overrides: dict | None = None,
               skip_cols: set | None = None) -> int:
    """Generic prod->E2E copy for ``table`` rows matching ``where_sql``."""
    prod_cols = _prod_columns(prod, table)
    e2e_cols = _e2e_columns(table)
    cols = [c for c in prod_cols if c in e2e_cols and (not skip_cols or c not in skip_cols)]
    overrides = overrides or {}

    with prod.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE {where_sql}", params)
        rows = cur.fetchall()
    if not rows:
        logger.info("  %s: 0 rows", table)
        return 0

    placeholders = ", ".join(["%s"] * len(cols))
    update_set = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict_cols)
    conflict_action = f"DO UPDATE SET {update_set}" if update_set else "DO NOTHING"
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_cols}) {conflict_action}"
    )
    written = 0
    with db_postgres.PGConnectionManager(commit=True) as conn:
        with conn.cursor() as wcur:
            for r in rows:
                vals = [overrides.get(c, r[c]) if c in overrides else r[c] for c in cols]
                wcur.execute(sql, vals)
                written += 1
    logger.info("  %s: %d rows", table, written)
    return written


def seed(folders: list[int]) -> dict:
    common.assert_e2e()
    common.register_l14_spaces()
    prod = common.prod_connection()
    stats: dict[str, int] = {}
    folder_csv = ",".join(str(f) for f in folders)

    # Resolve target image_ids and stack_ids on prod (read-only).
    with prod.cursor() as cur:
        cur.execute(
            f"SELECT id, stack_id FROM images WHERE folder_id IN ({folder_csv})"
        )
        rows = cur.fetchall()
    image_ids = [r[0] for r in rows]
    stack_ids = sorted({r[1] for r in rows if r[1] is not None})
    logger.info("Seeding %d images, %d stacks from folders %s", len(image_ids), len(stack_ids), folders)
    if not image_ids:
        raise SystemExit("No images found for the requested folders.")
    img_csv = ",".join(str(i) for i in image_ids)
    stk_csv = ",".join(str(s) for s in stack_ids) if stack_ids else "NULL"

    # 1. folders
    logger.info("Copying folders...")
    stats["folders"] = _copy_rows(prod, "folders", f"id IN ({folder_csv})", (),
                                  conflict_cols="id")

    # 2. keywords_dim (all keywords referenced by seeded images)
    logger.info("Copying keywords_dim...")
    with prod.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT keyword_id FROM image_keywords WHERE image_id IN ({img_csv})"
        )
        kw_ids = [r[0] for r in cur.fetchall()]
    if kw_ids:
        kw_csv = ",".join(str(k) for k in kw_ids)
        stats["keywords_dim"] = _copy_rows(prod, "keywords_dim",
                                           f"keyword_id IN ({kw_csv})", (),
                                           conflict_cols="keyword_id")

    # 3. stacks WITHOUT best_image_id (satisfy images.stack_id FK first)
    if stack_ids:
        logger.info("Copying stacks (best_image_id deferred)...")
        stats["stacks"] = _copy_rows(prod, "stacks", f"id IN ({stk_csv})", (),
                                     conflict_cols="id", skip_cols={"best_image_id"})

    # 4. images (job_id -> NULL to avoid seeding jobs)
    logger.info("Copying images (job_id nulled)...")
    stats["images"] = _copy_rows(prod, "images", f"id IN ({img_csv})", (),
                                 conflict_cols="id", overrides={"job_id": None})

    # 5. backfill stacks.best_image_id where the target image is in the seed set
    if stack_ids:
        logger.info("Backfilling stacks.best_image_id...")
        with prod.cursor() as cur:
            cur.execute(
                f"SELECT id, best_image_id FROM stacks WHERE id IN ({stk_csv}) "
                f"AND best_image_id IN ({img_csv})"
            )
            pairs = cur.fetchall()
        with db_postgres.PGConnectionManager(commit=True) as conn:
            with conn.cursor() as wcur:
                for sid, bid in pairs:
                    wcur.execute("UPDATE stacks SET best_image_id=%s WHERE id=%s", (bid, sid))
        stats["stacks_best_backfilled"] = len(pairs)

    # 6. dependent tables
    logger.info("Copying image_keywords / image_model_scores / image_exif...")
    stats["image_keywords"] = _copy_rows(prod, "image_keywords", f"image_id IN ({img_csv})", (),
                                         conflict_cols="image_id, keyword_id")
    stats["image_model_scores"] = _copy_rows(prod, "image_model_scores", f"image_id IN ({img_csv})", (),
                                             conflict_cols="image_id, model_name")
    stats["image_exif"] = _copy_rows(prod, "image_exif", f"image_id IN ({img_csv})", (),
                                     conflict_cols="image_id")

    # 7. baseline embeddings (map prod space code -> E2E space id)
    logger.info("Copying baseline embeddings...")
    _ensure_bioclip_768()
    stats["embeddings"] = _copy_embeddings(prod, image_ids)

    prod.close()
    logger.info("Seed complete: %s", stats)
    common.write_json("phase0_seed_stats.json", {"folders": folders, "stats": stats})
    return stats


def _ensure_bioclip_768() -> None:
    """Prod BioCLIP is 768-d; align the E2E registry row so vectors validate."""
    with db_postgres.PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE embedding_spaces SET dim=768 WHERE code='bioclip_2_image' AND dim<>768")
    from modules import embedding_spaces as es
    es.SPACE_DIMS["bioclip_2_image"] = 768
    es.invalidate_default_embedding_space_cache()


def _coerce_vector(emb):
    """Normalize a pgvector value (text ``[..]`` / bytes / list) to a float list."""
    if emb is None:
        return None
    if isinstance(emb, str):
        s = emb.strip().lstrip("[").rstrip("]")
        if not s:
            return None
        return [float(x) for x in s.split(",")]
    if isinstance(emb, (bytes, bytearray, memoryview)):
        return bytes(emb)
    return list(emb)


def _copy_embeddings(prod, image_ids: list[int]) -> int:
    """Copy mobilenet (1280), clip_b32 (512), bioclip (768) vectors from prod.

    Reads prod fact tables joined to prod ``embedding_spaces`` for the code,
    then upserts into the matching E2E per-dim table under the E2E space id.
    """
    img_csv = ",".join(str(i) for i in image_ids)
    total = 0
    fact_tables = {
        "image_embeddings": 1280,
        "image_embeddings_512": 512,
        "image_embeddings_768": 768,
    }
    for table, _dim in fact_tables.items():
        with prod.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT e.image_id, e.embedding, e.model_version, s.code "
                f"FROM {table} e JOIN embedding_spaces s ON s.id=e.embedding_space_id "
                f"WHERE e.image_id IN ({img_csv})"
            )
            rows = cur.fetchall()
        if not rows:
            continue
        # group by code -> use db.update_image_embeddings_batch_for_space
        from modules import db
        from modules import embedding_spaces as es
        by_code: dict[str, list] = {}
        for r in rows:
            vec = _coerce_vector(r["embedding"])
            if vec is None:
                continue
            by_code.setdefault(r["code"], []).append((r["image_id"], vec, r["model_version"]))
        for code, batch in by_code.items():
            if code not in es.SPACE_DIMS:
                logger.warning("  skip embeddings for unregistered space %s", code)
                continue
            # ensure E2E registry has the space row
            with db_postgres.PGConnectionManager(commit=True) as conn:
                with conn.cursor() as wcur:
                    wcur.execute(
                        "INSERT INTO embedding_spaces (code, dim, description, active) "
                        "VALUES (%s,%s,%s,1) ON CONFLICT (code) DO NOTHING",
                        (code, es.SPACE_DIMS[code], f"{code} (seeded baseline)"),
                    )
            es.invalidate_default_embedding_space_cache()
            n = db.update_image_embeddings_batch_for_space(code, batch)
            logger.info("  embeddings[%s]: %d", code, n)
            total += n
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folders", default=",".join(str(f) for f in DEFAULT_FOLDERS),
                    help="comma-separated prod folder ids")
    args = ap.parse_args()
    folders = [int(x) for x in args.folders.split(",") if x.strip()]
    seed(folders)


if __name__ == "__main__":
    main()
