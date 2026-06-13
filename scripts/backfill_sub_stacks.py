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

    # Sidecar sync with progress bar + checkpoint (resume after interrupt)
    python -u -m scripts.backfill_sub_stacks --write-sidecars \\
        --checkpoint reports/clip-culling/backfill_sub_stacks.checkpoint.json
    python -u -m scripts.backfill_sub_stacks --write-sidecars --resume \\
        --checkpoint reports/clip-culling/backfill_sub_stacks.checkpoint.json

    # Explicit resume after stack id 42000 (stable ascending stack_id order)
    python -u -m scripts.backfill_sub_stacks --write-sidecars --resume-after-stack-id 42000

The level2 embedding space + threshold default to ``culling.two_level.level2``
from config.json; override with ``--embedding-space`` / ``--threshold``. If the
level2 space is a culling tower (e.g. ``openclip_l14_laion2b_image``), complete
the embedding backfill first or stacks collapse to a single fallback leaf.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path
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
_DEFAULT_CHECKPOINT = "reports/clip-culling/backfill_sub_stacks.checkpoint.json"
_PROGRESS_LOG_EVERY = 100


def _load_checkpoint(path: str) -> dict | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read checkpoint %s: %s", path, e)
        return None


def _save_checkpoint(path: str, payload: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(p)


def _format_progress_line(
    done: int,
    total: int,
    *,
    counts: Counter,
    side_ok: int,
    side_err: int,
    elapsed_s: float,
) -> str:
    pct = 100.0 * done / total if total else 100.0
    rate = done / elapsed_s if elapsed_s > 0 else 0.0
    remaining = total - done
    eta_s = remaining / rate if rate > 0 else 0.0
    bar_w = 32
    filled = int(bar_w * done / total) if total else bar_w
    bar = "#" * filled + "-" * (bar_w - filled)
    return (
        f"[{bar}] {done}/{total} ({pct:.1f}%) "
        f"pick={counts['pick']} reject={counts['reject']} neutral={counts['neutral']} "
        f"sidecar_ok={side_ok} sidecar_err={side_err} "
        f"rate={rate:.1f} stacks/s eta={eta_s:.0f}s"
    )


class _StackProgress:
    """Visual progress on TTY (tqdm) or periodic log lines otherwise."""

    def __init__(self, total: int, *, log_every: int = _PROGRESS_LOG_EVERY):
        self.total = total
        self.log_every = max(1, log_every)
        self.done = 0
        self.started = time.monotonic()
        self._tqdm = None
        self._use_tqdm = sys.stderr.isatty()
        if self._use_tqdm:
            try:
                from tqdm import tqdm

                self._tqdm = tqdm(
                    total=total,
                    unit="stack",
                    file=sys.stderr,
                    dynamic_ncols=True,
                    mininterval=0.5,
                )
            except ImportError:
                self._use_tqdm = False

    def update(
        self,
        stack_id: int,
        *,
        counts: Counter,
        side_ok: int,
        side_err: int,
    ) -> None:
        self.done += 1
        elapsed = time.monotonic() - self.started
        if self._tqdm is not None:
            self._tqdm.set_postfix(
                stack=stack_id,
                pick=counts["pick"],
                reject=counts["reject"],
                side_ok=side_ok,
                refresh=False,
            )
            self._tqdm.update(1)
            return
        if self.done == 1 or self.done >= self.total or self.done % self.log_every == 0:
            line = _format_progress_line(
                self.done,
                self.total,
                counts=counts,
                side_ok=side_ok,
                side_err=side_err,
                elapsed_s=elapsed,
            )
            logger.info("%s (last_stack_id=%d)", line, stack_id)

    def close(self) -> None:
        if self._tqdm is not None:
            self._tqdm.close()
        elif self.total and self.done:
            elapsed = time.monotonic() - self.started
            sys.stderr.write("\n")
            sys.stderr.flush()
            logger.info(
                "Progress complete: %d/%d stacks in %.1fs",
                self.done,
                self.total,
                elapsed,
            )


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


def _stack_ids_to_process(
    folder_filter: set[int] | None,
    *,
    only_policy_version: str | None = None,
) -> list[int]:
    stacks = db.get_stacks()
    if not stacks:
        return []

    policy_stack_ids: set[int] | None = None
    if only_policy_version:
        try:
            rows = db.get_connector().query(
                """
                SELECT DISTINCT stack_id FROM images
                WHERE stack_id IS NOT NULL
                  AND cull_policy_version = ?
                """,
                (only_policy_version,),
            )
        except Exception as e:
            logger.error("Could not filter by cull_policy_version=%r: %s", only_policy_version, e)
            return []
        policy_stack_ids = {
            int(r["stack_id"]) for r in rows if r.get("stack_id") is not None
        }
        if not policy_stack_ids:
            logger.info(
                "No stacks with cull_policy_version=%r — nothing to process.",
                only_policy_version,
            )
            return []

    keep: list[int] = []
    for s in stacks:
        sid = s.get("id")
        if sid is None:
            continue
        sid_int = int(sid)
        if policy_stack_ids is not None and sid_int not in policy_stack_ids:
            continue
        if folder_filter is None:
            keep.append(sid_int)
            continue
        rows = db.get_images_in_stack(sid_int)
        if any((r.get("folder_id") in folder_filter) for r in rows):
            keep.append(sid_int)
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
            # Singleton stacks: two-level culling uses legacy classify (n=1 → neutral).
            singleton_decisions = [
                (int(im["id"]), "neutral", im.get("file_path") or "")
                for im in images
                if im.get("id") is not None
            ]
            yield int(sid), [], singleton_decisions, 0
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
        "--only-policy-version",
        default=None,
        help="Process only stacks that have at least one image with this "
             "cull_policy_version (e.g. 1.0 for legacy stacked rows).",
    )
    parser.add_argument(
        "--resume-after-stack-id",
        type=int,
        default=None,
        help="Skip stacks with id <= N (stable ascending order). Use after "
             "interrupt or with --checkpoint --resume.",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        metavar="PATH",
        help=f"Write progress JSON after each stack (default when --resume: "
             f"{_DEFAULT_CHECKPOINT}).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from --checkpoint (or --resume-after-stack-id). "
             "Stacks at or before the saved last_stack_id are skipped.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=_PROGRESS_LOG_EVERY,
        help="When stderr is not a TTY, log a progress line every N stacks "
             f"(default {_PROGRESS_LOG_EVERY}).",
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

    stack_ids = _stack_ids_to_process(
        folder_filter,
        only_policy_version=args.only_policy_version,
    )
    if not stack_ids:
        logger.info("No stacks found to process.")
        return 0

    stack_ids = sorted(set(stack_ids))

    resume_after: int | None = args.resume_after_stack_id
    checkpoint_path: str | None = args.checkpoint
    if args.resume and checkpoint_path is None:
        checkpoint_path = _DEFAULT_CHECKPOINT
    if checkpoint_path is None and args.write_sidecars and not args.dry_run:
        checkpoint_path = _DEFAULT_CHECKPOINT

    if args.resume:
        ckpt = _load_checkpoint(checkpoint_path) if checkpoint_path else None
        if ckpt and ckpt.get("last_stack_id") is not None:
            ckpt_id = int(ckpt["last_stack_id"])
            resume_after = max(resume_after or 0, ckpt_id)
            logger.info(
                "Resuming from checkpoint %s (last_stack_id=%d, done=%s/%s)",
                checkpoint_path,
                ckpt_id,
                ckpt.get("stacks_done"),
                ckpt.get("stacks_total"),
            )
        elif resume_after is None:
            logger.warning(
                "No checkpoint at %r and no --resume-after-stack-id — starting from beginning.",
                checkpoint_path,
            )

    if resume_after is not None:
        before = len(stack_ids)
        stack_ids = [sid for sid in stack_ids if sid > resume_after]
        logger.info(
            "Resume filter: stack_id > %d — %d of %d stacks remaining",
            resume_after,
            len(stack_ids),
            before,
        )
        if not stack_ids:
            logger.info("All stacks already processed.")
            return 0

    if args.limit > 0:
        stack_ids = stack_ids[: args.limit]

    total_planned = len(stack_ids)

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
        "max/stack=%d dry_run=%s write_sidecars=%s preserve_manual=%s "
        "only_policy_version=%s resume_after_stack_id=%s checkpoint=%s",
        total_planned, space, tl_cfg.level2.distance_threshold,
        tl_cfg.picks_per_substack, tl_cfg.max_picks_per_stack,
        args.dry_run, args.write_sidecars, args.preserve_manual,
        args.only_policy_version, resume_after, checkpoint_path,
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

    progress = _StackProgress(total_planned, log_every=args.progress_every)

    def _flush(buf: list[tuple]) -> None:
        if not buf or args.dry_run:
            buf.clear()
            return
        db.batch_update_cull_decisions(buf, policy_version=TWO_LEVEL_POLICY_VERSION)
        buf.clear()

    stacks_done = 0
    try:
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

            stacks_done += 1
            progress.update(
                sid,
                counts=counts,
                side_ok=side_ok,
                side_err=side_err,
            )

            if checkpoint_path and not args.dry_run:
                _save_checkpoint(
                    checkpoint_path,
                    {
                        "last_stack_id": int(sid),
                        "stacks_done": stacks_done,
                        "stacks_total": total_planned,
                        "resume_after_stack_id": int(sid),
                        "write_sidecars": bool(args.write_sidecars),
                        "only_policy_version": args.only_policy_version,
                        "folder": args.folder,
                        "counts": dict(counts),
                        "sidecar_ok": side_ok,
                        "sidecar_err": side_err,
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                )
    finally:
        progress.close()

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
        "dry_run=%s checkpoint=%s",
        stacks_done, leaves_total, substacks_total, coverage * 100.0,
        counts["pick"], counts["reject"], counts["neutral"],
        skipped_manual, side_ok, side_err, args.dry_run, checkpoint_path,
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
