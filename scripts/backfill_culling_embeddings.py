#!/usr/bin/env python3
"""Backfill an optional culling embedding space over existing images (Postgres).

Embeds images that lack a vector for the requested space and upserts them into
``image_embeddings_768`` so the space becomes selectable per two-level culling
level (``culling.two_level.level*.embedding_space``).

Run in WSL with the app/ML venv (GPU towers, fp16). Example::

    source ~/.venvs/tf/bin/activate
    python -m scripts.backfill_culling_embeddings \
        --space openclip_l14_laion2b_image --batch-size 32

Filter to one folder and dry-run the count first::

    python -m scripts.backfill_culling_embeddings \
        --space siglip2_base_image --folder-id 62 --dry-run

Supported spaces: see ``modules.embedding_extractors.SUPPORTED_CULLING_SPACES``.
Postgres-only — persistence is a no-op on other engines.
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger("backfill_culling_embeddings")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--space",
        action="append",
        default=None,
        help="Embedding space code to backfill (repeatable). "
        "Defaults to config embeddings.culling_spaces.",
    )
    parser.add_argument("--folder-id", type=int, default=None, help="Restrict to one folder")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of images")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default=None, help="cuda | cpu (default: auto)")
    parser.add_argument("--no-fp16", action="store_true", help="Disable fp16 on CUDA")
    parser.add_argument(
        "--no-thumbnails",
        action="store_true",
        help="Decode the original RAW/file instead of the on-disk thumbnail (slower).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count missing images only")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from modules import config, db
    from modules.culling_embeddings import ensure_embeddings_for_space
    from modules.embedding_extractors import SUPPORTED_CULLING_SPACES, is_supported
    from modules.embedding_spaces import get_embedding_space_id

    spaces = list(args.space or [])
    if not spaces:
        spaces = list(config.get_config_value("embeddings.culling_spaces", default=[]) or [])
    if not spaces:
        logger.error(
            "No spaces requested; pass --space or set embeddings.culling_spaces. "
            "Supported: %s",
            sorted(SUPPORTED_CULLING_SPACES),
        )
        return 2

    unknown = [s for s in spaces if not is_supported(s)]
    if unknown:
        logger.error(
            "Unknown culling space(s) %s; supported: %s",
            unknown,
            sorted(SUPPORTED_CULLING_SPACES),
        )
        return 2

    if db._get_db_engine() != "postgres":
        logger.error("Backfill requires database.engine = 'postgres' (got %s).", db._get_db_engine())
        return 2

    rc = 0
    for space in spaces:
        space_id = get_embedding_space_id(space)
        if space_id is None:
            logger.error(
                "Space %r not registered; run 'alembic upgrade head' (migration 0029).",
                space,
            )
            rc = 2
            continue

        kwargs = {"limit": args.limit}
        if args.folder_id is not None:
            from modules import db_postgres

            row = db_postgres.execute_select_one(
                "SELECT path FROM folders WHERE id = %s",
                (args.folder_id,),
            )
            if not row:
                logger.error("Unknown folder_id=%s", args.folder_id)
                rc = 2
                continue
            kwargs["folder_path"] = row["path"]

        missing_rows = db.get_images_missing_embedding_for_space(space, **kwargs)
        logger.info("Images missing %s: %d", space, len(missing_rows))
        if args.dry_run or not missing_rows:
            continue

        missing_ids = [int(r["id"]) for r in missing_rows]
        result = ensure_embeddings_for_space(
            space,
            missing_ids,
            batch_size=args.batch_size,
            use_thumbnails=not args.no_thumbnails,
            device=args.device,
            fp16=not args.no_fp16,
        )
        logger.info(
            "Persisted %d/%d embeddings for space %s",
            result.persisted,
            result.missing_before,
            space,
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
