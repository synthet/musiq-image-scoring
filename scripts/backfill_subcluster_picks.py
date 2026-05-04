#!/usr/bin/env python
"""One-shot backfill: re-classify pick/reject decisions for every existing
stack using two-level sub-clustering.

Use this after enabling ``culling.sub_cluster_distance_threshold`` if you
want to roll the new logic over historical data without re-running the
whole Selection pipeline folder by folder. The script does NOT re-cluster
images (``stack_id`` assignments are preserved); it only rewrites the
``cull_decision`` column.

Usage examples
--------------

    # Dry run across the whole DB, default threshold from config
    python scripts/backfill_subcluster_picks.py --dry-run

    # Live run, restrict to a folder subtree, custom threshold
    python scripts/backfill_subcluster_picks.py \\
        --folder /mnt/d/Photos/2024 --threshold 0.05

    # Live run, also rewrite XMP sidecars
    python scripts/backfill_subcluster_picks.py --write-sidecars

The script overwrites ``IMAGES.cull_decision`` and (optionally) XMP
sidecars in place. Manual user picks stored in the same column WILL be
replaced — coordinate with users before running.
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
from modules.config import get_config_value  # noqa: E402
from modules.sub_clustering import assign_decisions_in_stack  # noqa: E402
from modules.selection_policy import POLICY_VERSION, DEFAULT_PICK_FRACTION  # noqa: E402
from modules.indexing_policy import filter_image_rows_for_nef_policy  # noqa: E402

logger = logging.getLogger("backfill_subcluster_picks")


def _resolve_folder_ids(folder_path: str) -> set[int]:
    """Return the set of folder_ids whose path matches ``folder_path`` or
    is nested under it. Empty set means "no match → process nothing"."""
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
    """Return image_ids whose ``cull_decision`` is set but whose
    ``cull_policy_version`` is NULL — the convention for "this value did NOT
    come from an automated policy run, so don't trample it."

    No automated path in the current codebase writes ``cull_decision`` without
    ``cull_policy_version``; the guard exists so a future manual-edit feature
    that writes the column directly is forward-compatible with the backfill.
    """
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

    # Filter: include a stack if any of its images live in the folder filter.
    keep: list[int] = []
    for s in stacks:
        sid = s.get("id")
        if sid is None:
            continue
        rows = db.get_images_in_stack(int(sid))
        if any((r.get("folder_id") in folder_filter) for r in rows):
            keep.append(int(sid))
    return keep


def _iter_stack_decisions(
    stack_ids: Iterable[int],
    threshold: float,
    frac: float,
    score_field: str,
) -> Iterable[tuple[int, list[tuple], int]]:
    """Yield ``(stack_id, decisions, sub_cluster_count)`` per stack."""
    from modules.sub_clustering import compute_sub_clusters

    for sid in stack_ids:
        images = filter_image_rows_for_nef_policy(db.get_images_in_stack(int(sid)))
        if not images:
            yield sid, [], 0
            continue

        ids = [int(im["id"]) for im in images if im.get("id") is not None]
        emb_map = db.get_image_embeddings_batch(ids) if ids else {}

        decisions = assign_decisions_in_stack(
            images,
            emb_map,
            distance_threshold=threshold,
            score_field=score_field,
            frac=frac,
            id_key="id",
        )
        # Count sub-clusters separately so we can log it; cheap because we
        # just re-run compute_sub_clusters with the same inputs.
        sub_groups = compute_sub_clusters(images, emb_map, distance_threshold=threshold)
        yield sid, decisions, len(sub_groups) if sub_groups else 1


def _maybe_write_sidecars(
    decisions: list[tuple], stack_id: int, dry_run: bool
) -> tuple[int, int]:
    """Write XMP sidecars for the given decisions. Returns (ok, errors)."""
    if dry_run:
        return 0, 0
    try:
        from modules.selection_metadata import write_selection_metadata
    except Exception as e:  # pragma: no cover - env-dependent
        logger.warning("Sidecar writer unavailable: %s", e)
        return 0, len(decisions)

    ok = 0
    errors = 0
    for img_id, decision, file_path in decisions:
        if not file_path:
            continue
        try:
            stack_ok, pr_ok = write_selection_metadata(file_path, stack_id, decision)
            if stack_ok and pr_ok:
                ok += 1
            else:
                errors += 1
        except Exception as e:
            logger.warning("Sidecar write failed for %s: %s", file_path, e)
            errors += 1
    return ok, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "--folder",
        help="Limit to stacks containing images under this folder path. "
             "Omit to process every stack in the database.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Cosine distance threshold for sub-clustering. Defaults to "
             "culling.sub_cluster_distance_threshold from config.",
    )
    parser.add_argument(
        "--pick-fraction",
        type=float,
        default=DEFAULT_PICK_FRACTION,
        help=f"Fraction for pick/reject bands (default: {DEFAULT_PICK_FRACTION}).",
    )
    parser.add_argument(
        "--score-field",
        default="score_general",
        help="Score column used for sorting (default: score_general).",
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
        help="Compute decisions but do NOT persist to the DB or sidecars.",
    )
    parser.add_argument(
        "--no-preserve-manual",
        dest="preserve_manual",
        action="store_false",
        default=True,
        help="Disable the safety guard that skips rows whose cull_decision is "
             "set but cull_policy_version is NULL (i.e. presumed manual "
             "overrides). Default: guard is ON.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    threshold = args.threshold
    if threshold is None:
        threshold = get_config_value("culling.sub_cluster_distance_threshold", default=None)
    try:
        threshold = float(threshold) if threshold is not None else None
    except (TypeError, ValueError):
        threshold = None
    if threshold is None or threshold <= 0.0:
        logger.error(
            "sub_cluster_distance_threshold is unset/non-positive; nothing to do. "
            "Pass --threshold or set culling.sub_cluster_distance_threshold in config.json."
        )
        return 2

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
                "Manual-override guard: %d image(s) with NULL "
                "cull_policy_version will be skipped.",
                len(skip_ids),
            )

    logger.info(
        "Backfill plan: stacks=%d threshold=%.4f pick_fraction=%.2f score_field=%s "
        "dry_run=%s write_sidecars=%s preserve_manual=%s",
        len(stack_ids), threshold, args.pick_fraction, args.score_field,
        args.dry_run, args.write_sidecars, args.preserve_manual,
    )

    counts = Counter()
    sub_clusters_total = 0
    side_ok = 0
    side_err = 0
    skipped_manual = 0

    pending_decisions: list[tuple] = []
    BATCH = 5_000

    def _flush(buf: list[tuple]) -> None:
        if not buf or args.dry_run:
            buf.clear()
            return
        db.batch_update_cull_decisions(buf, policy_version=POLICY_VERSION)
        buf.clear()

    for sid, decisions, sub_clusters in _iter_stack_decisions(
        stack_ids, threshold, args.pick_fraction, args.score_field,
    ):
        sub_clusters_total += sub_clusters
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
        pending_decisions.extend(decisions)
        if args.write_sidecars and decisions:
            ok, err = _maybe_write_sidecars(decisions, sid, args.dry_run)
            side_ok += ok
            side_err += err
        if len(pending_decisions) >= BATCH:
            logger.info(
                "Flushing %d decisions (running totals: pick=%d reject=%d neutral=%d)",
                len(pending_decisions),
                counts["pick"], counts["reject"], counts["neutral"],
            )
            _flush(pending_decisions)

    _flush(pending_decisions)

    logger.info(
        "Backfill done. stacks=%d sub_clusters=%d picks=%d rejects=%d neutrals=%d "
        "skipped_manual=%d sidecar_ok=%d sidecar_err=%d dry_run=%s",
        len(stack_ids), sub_clusters_total,
        counts["pick"], counts["reject"], counts["neutral"],
        skipped_manual, side_ok, side_err, args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
