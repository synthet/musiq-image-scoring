#!/usr/bin/env python
"""One-shot backfill: recompute leaf sub-stacks + two-level pick/reject
decisions for every existing root stack.

Root stacks already exist from the clustering (culling) phase
(``images.stack_id`` -> ``stacks.id``). Sub-stacks (``sub_stacks`` +
``images.sub_stack_id``) are normally written only when Selection runs with
``culling.two_level`` enabled. This script applies the same two-level logic to
historical data WITHOUT re-clustering (``stack_id`` assignments are preserved)
and WITHOUT requiring ``culling.two_level.enabled: true`` in config.

It is idempotent: each stack's sub_stacks are cleared and rebuilt, so a crash
or rerun just recomputes. Decisions are written with policy version
``TWO_LEVEL_POLICY_VERSION`` (2.0).

Usage examples
--------------

    # Dry run on the first 10 stacks (no DB writes)
    python -m scripts.backfill_sub_stacks --dry-run --limit 10

    # Live run, restrict to a folder subtree
    python -m scripts.backfill_sub_stacks --folder /mnt/d/Photos/2024

    # Live run, whole library, log to a file
    python -u -m scripts.backfill_sub_stacks > reports/clip-culling/backfill_sub_stacks.log 2>&1

The level2 embedding space + threshold default to ``culling.two_level.level2``
from config.json; override with ``--embedding-space`` / ``--threshold``. If the
level2 space is a culling tower (e.g. ``openclip_l14_laion2b_image``), complete
the embedding backfill first or stacks collapse to a single fallback leaf.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from typing import Iterable

# Allow running directly from a checkout without a package install.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import db  # noqa: E402
from modules.embedding_spaces import DEFAULT_EMBEDDING_SPACE_CODE  # noqa: E402
from modules.indexing_policy import filter_image_rows_for_nef_policy  # noqa: E402
from modules.quality_ranking import quality_tiebreak_sort_key_best_first  # noqa: E402
from modules.selection import SelectionConfig, _load_two_level_config  # noqa: E402
from modules.two_level_culling import (  # noqa: E402
    TWO_LEVEL_POLICY_VERSION,
    TwoLevelConfig,
    TwoLevelLevelConfig,
    process_stack_two_level,
)

logger = logging.getLogger("backfill_sub_stacks")

# Below this fraction of images carrying a level2 vector, a stack will mostly
# collapse to one leaf (whole-stack cap). Warn so the operator can stop and
# finish the embedding backfill first.
_LOW_COVERAGE_WARN = 0.90


def _resolve_folder_ids(folder_path: str) -> set[int]:
    """Return folder_ids matching ``folder_path`` or nested under it."""
    norm = os.path.normpath(folder_path).rstrip(os.sep).replace("\\", "/")
    if not norm:
        return set()
    paths = db.list_folder_paths_under_scope(folder_path)
    if not paths:
        return set()
    out: set[int] = set()
    for p in paths:
        fid = db.get_or_create_folder(p)
        if fid:
            out.add(int(fid))
    return out


def _manual_override_image_ids() -> set[int]:
    """Return image_ids whose ``cull_decision`` is set but
    ``cull_policy_version`` is NULL (presumed manual edits — don't trample)."""
    try:
        rows = db.get_connector().query(
            "SELECT id FROM images "
            "WHERE cull_decision IS NOT NULL "
            "  AND TRIM(CAST(cull_decision AS VARCHAR(20))) <> '' "
            "  AND cull_policy_version IS NULL"
        )
    except Exception as e:
        logger.warning(
            "Could not enumerate manual cull_decision overrides (%s) — "
            "proceeding without the preservation guard.", e,
        )
        return set()
    return {int(r["id"]) for r in rows if r.get("id") is not None}


def _stack_ids_to_process(folder_filter: set[int] | None) -> list[int]:
    stacks = db.get_stacks()
    if not stacks:
        return []
    if folder_filter is None:
        return [int(s["id"]) for s in stacks if s.get("id") is not None]

    keep: list[int] = []
    for s in stacks:
        sid = s.get("id")
        if sid is None:
            continue
        rows = db.get_images_in_stack(int(sid))
        if any((r.get("folder_id") in folder_filter) for r in rows):
            keep.append(int(sid))
    return keep


def _make_sort_key(score_field: str):
    def sort_key(img):
        s = img.get(score_field) or 0
        c = img.get("created_at") or ""
        i = img.get("id") or 0
        return (
            -float(s) if s else 0,
            quality_tiebreak_sort_key_best_first(img),
            str(c),
            int(i),
        )

    return sort_key


def _prepare_images(images: list[dict]) -> list[dict]:
    """Filter to NEF policy and enrich with EXIF fields for the tiebreak,
    mirroring SelectionService.run()."""
    images = filter_image_rows_for_nef_policy(images)
    if not images:
        return []
    ids = [img["id"] for img in images if img.get("id") is not None]
    try:
        exif_map = db.get_exif_fields_for_quality_tiebreak(ids)
    except Exception as e:
        logger.debug("EXIF tiebreak fields unavailable (%s) — using score only.", e)
        exif_map = {}
    for im in images:
        ex = exif_map.get(im.get("id"))
        if ex:
            im["iso"] = ex.get("iso")
            im["exposure_time"] = ex.get("exposure_time")
            im["date_time_original"] = ex.get("date_time_original")
    return images


def _iter_stack_results(
    stack_ids: Iterable[int],
    tl_cfg: TwoLevelConfig,
    sort_key,
    *,
    dry_run: bool,
    coverage_tracker: list[int],
) -> Iterable[tuple[int, list[dict], list[tuple], int]]:
    """Yield ``(stack_id, persist_rows, decisions, leaf_count)`` per stack.

    Clears existing sub_stacks for the stack (live runs only) before rebuild.
    """
    space = tl_cfg.level2.embedding_space
    for sid in stack_ids:
        images = _prepare_images(db.get_images_in_stack(int(sid)))
        if len(images) < 2:
            yield int(sid), [], [], 0
            continue

        ids = [int(im["id"]) for im in images if im.get("id") is not None]
        emb_map = db.get_image_embeddings_batch_for_space(space, ids) if ids else {}

        # Track coverage so we can warn if a culling tower is under-populated.
        coverage_tracker[0] += len(ids)
        coverage_tracker[1] += sum(1 for i in ids if i in emb_map)

        if not dry_run:
            db.clear_sub_stacks_for_stack_ids([int(sid)])

        persist_rows, decisions, leaf_count = process_stack_two_level(
            int(sid), images, emb_map, tl_cfg, sort_key,
        )
        yield int(sid), persist_rows, decisions, leaf_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--folder",
        help="Limit to stacks containing images under this folder path. "
             "Omit to process every stack in the database.",
    )
    parser.add_argument(
        "--embedding-space",
        default=None,
        help="Override the level2 embedding space (default: "
             "culling.two_level.level2.embedding_space from config).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the level2 cosine distance threshold (default: "
             "culling.two_level.level2.distance_threshold from config).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N stacks (0 = unlimited). Useful for smoke tests.",
    )
    parser.add_argument(
        "--write-sidecars",
        action="store_true",
        help="Also rewrite XMP sidecars for every changed image.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute sub-stacks/decisions but do NOT persist to DB or sidecars.",
    )
    parser.add_argument(
        "--no-preserve-manual",
        dest="preserve_manual",
        action="store_false",
        default=True,
        help="Disable the guard that skips rows whose cull_decision is set but "
             "cull_policy_version is NULL (presumed manual overrides).",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Resolve two-level config + overrides.
    tl_cfg = _load_two_level_config(SelectionConfig())
    space = args.embedding_space or tl_cfg.level2.embedding_space
    threshold = args.threshold if args.threshold is not None else tl_cfg.level2.distance_threshold
    tl_cfg.level2 = TwoLevelLevelConfig(embedding_space=space, distance_threshold=float(threshold))
    sort_key = _make_sort_key(tl_cfg.score_field)

    folder_filter: set[int] | None = None
    if args.folder:
        folder_filter = _resolve_folder_ids(args.folder)
        if not folder_filter:
            logger.error("No folders matched %r — aborting.", args.folder)
            return 2
        logger.info("Folder filter resolved to %d folder_ids", len(folder_filter))

    stack_ids = _stack_ids_to_process(folder_filter)
    if not stack_ids:
        logger.info("No stacks found to process.")
        return 0
    if args.limit > 0:
        stack_ids = stack_ids[: args.limit]

    skip_ids: set[int] = set()
    if args.preserve_manual:
        skip_ids = _manual_override_image_ids()
        if skip_ids:
            logger.info(
                "Manual-override guard: %d image(s) with NULL cull_policy_version "
                "will be skipped.", len(skip_ids),
            )

    logger.info(
        "Backfill plan: stacks=%d space=%s threshold=%.4f picks/substack=%d "
        "max/stack=%d dry_run=%s write_sidecars=%s preserve_manual=%s",
        len(stack_ids), space, tl_cfg.level2.distance_threshold,
        tl_cfg.picks_per_substack, tl_cfg.max_picks_per_stack,
        args.dry_run, args.write_sidecars, args.preserve_manual,
    )

    counts: Counter = Counter()
    leaves_total = 0
    substacks_total = 0
    side_ok = 0
    side_err = 0
    skipped_manual = 0
    coverage_tracker = [0, 0]  # [total_ids, ids_with_embedding]

    pending_decisions: list[tuple] = []
    BATCH = 5_000

    def _flush(buf: list[tuple]) -> None:
        if not buf or args.dry_run:
            buf.clear()
            return
        db.batch_update_cull_decisions(buf, policy_version=TWO_LEVEL_POLICY_VERSION)
        buf.clear()

    for sid, persist_rows, decisions, leaf_count in _iter_stack_results(
        stack_ids, tl_cfg, sort_key, dry_run=args.dry_run, coverage_tracker=coverage_tracker,
    ):
        leaves_total += leaf_count
        if persist_rows and not args.dry_run:
            db.create_sub_stacks_batch(persist_rows)
        substacks_total += len(persist_rows)

        if skip_ids:
            kept = []
            for d in decisions:
                if d[0] in skip_ids:
                    skipped_manual += 1
                else:
                    kept.append(d)
            decisions = kept
        for _, decision, _ in decisions:
            counts[decision] += 1

        if args.write_sidecars and decisions and not args.dry_run:
            ok, err = _write_sidecars(decisions, sid)
            side_ok += ok
            side_err += err

        if args.verbose:
            logger.debug(
                "stack=%d leaves=%d substacks=%d picks=%d",
                sid, leaf_count, len(persist_rows),
                sum(1 for _, d, _ in decisions if d == "pick"),
            )

        pending_decisions.extend(decisions)
        if len(pending_decisions) >= BATCH:
            logger.info(
                "Flushing %d decisions (totals: pick=%d reject=%d neutral=%d)",
                len(pending_decisions), counts["pick"], counts["reject"], counts["neutral"],
            )
            _flush(pending_decisions)

    _flush(pending_decisions)

    total_ids, with_emb = coverage_tracker
    coverage = (with_emb / total_ids) if total_ids else 1.0
    if space != DEFAULT_EMBEDDING_SPACE_CODE and coverage < _LOW_COVERAGE_WARN:
        logger.warning(
            "LOW EMBEDDING COVERAGE: only %.1f%% of images in processed stacks have a "
            "%r vector. Stacks without vectors collapsed to a single leaf (whole-stack "
            "cap). Finish the embedding backfill before a full sub_stacks run.",
            coverage * 100.0, space,
        )

    logger.info(
        "Backfill done. stacks=%d leaves=%d substacks_written=%d coverage=%.1f%% "
        "picks=%d rejects=%d neutrals=%d skipped_manual=%d sidecar_ok=%d sidecar_err=%d "
        "dry_run=%s",
        len(stack_ids), leaves_total, substacks_total, coverage * 100.0,
        counts["pick"], counts["reject"], counts["neutral"],
        skipped_manual, side_ok, side_err, args.dry_run,
    )
    return 0


def _write_sidecars(decisions: list[tuple], stack_id: int) -> tuple[int, int]:
    try:
        from modules.selection_metadata import write_selection_metadata
    except Exception as e:  # pragma: no cover - env-dependent
        logger.warning("Sidecar writer unavailable: %s", e)
        return 0, len(decisions)
    ok = 0
    err = 0
    for img_id, decision, file_path in decisions:
        if not file_path:
            continue
        try:
            stack_ok, pr_ok = write_selection_metadata(file_path, stack_id, decision)
            if stack_ok and pr_ok:
                ok += 1
            else:
                err += 1
        except Exception as e:
            logger.warning("Sidecar write failed for %s: %s", file_path, e)
            err += 1
    return ok, err


if __name__ == "__main__":
    sys.exit(main())
