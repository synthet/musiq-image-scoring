#!/usr/bin/env python3
"""
Backfill ``images.bird_bbox`` for bird-tagged images that have never been scanned.

Detector-only: runs YOLO ``synthet/bird-detect-v0`` (via ``BirdDetector``) without
BioCLIP, so species keywords and embeddings are not rewritten. Writes a real box
when a bird is found, or the ``BBOX_NOT_DETECTED`` sentinel (``{"detected": false}``)
when the detector runs and finds nothing. Rows that stay NULL (file missing /
decode failure) are retried on the next run because selection filters on
``bird_bbox IS NULL``.

Usage (WSL, project root, per CLAUDE.md):
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
  source ~/.venvs/tf/bin/activate

  # Inspect how many rows would be processed
  python scripts/backfill_bird_bbox.py --dry-run

  # Pilot one folder
  python scripts/backfill_bird_bbox.py --folder "/path/to/folder"

  # Full library (detach with setsid/nohup for long runs)
  python scripts/backfill_bird_bbox.py --workers 4
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Optional, Tuple

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SQL_MISSING_BBOX = """
SELECT i.id, i.file_path, i.thumbnail_path, i.thumbnail_path_win
FROM images i
JOIN folders f ON i.folder_id = f.id
WHERE i.bird_bbox IS NULL
  AND EXISTS (
    SELECT 1 FROM image_keywords ik
    JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
    WHERE ik.image_id = i.id AND kd.keyword_norm LIKE ?
  )
  AND (? = '' OR f.path = ?)
ORDER BY f.path, i.id
"""

# Set by SIGINT handler; main loop finishes the in-flight chunk then stops.
_stop_requested = False


def _on_sigint(signum, frame) -> None:  # noqa: ARG001
    global _stop_requested
    if _stop_requested:
        logger.warning("Second interrupt — exiting immediately.")
        raise SystemExit(130)
    _stop_requested = True
    logger.warning("Interrupt received — finishing in-flight chunk then stopping.")


def fetch_candidates(*, folder: str = "", limit: int = 0) -> List[dict]:
    """Return bird-tagged images with ``bird_bbox IS NULL``."""
    from modules import db

    conn = db.get_db()
    try:
        c = conn.cursor()
        folder_arg = (folder or "").strip()
        c.execute(_SQL_MISSING_BBOX, ("%birds%", folder_arg, folder_arg))
        rows = c.fetchall()
    finally:
        conn.close()

    out: List[dict] = []
    for row in rows:
        # Cursor may return tuple or dict-like depending on connector.
        if hasattr(row, "keys"):
            item = {
                "id": int(row["id"]),
                "file_path": row["file_path"],
                "thumbnail_path": row.get("thumbnail_path") if hasattr(row, "get") else row["thumbnail_path"],
                "thumbnail_path_win": (
                    row.get("thumbnail_path_win") if hasattr(row, "get") else row["thumbnail_path_win"]
                ),
            }
        else:
            item = {
                "id": int(row[0]),
                "file_path": row[1],
                "thumbnail_path": row[2] if len(row) > 2 else None,
                "thumbnail_path_win": row[3] if len(row) > 3 else None,
            }
        out.append(item)
        if limit > 0 and len(out) >= limit:
            break
    return out


def _decode_oriented(row: dict) -> Tuple[int, Optional[Any], Optional[str]]:
    """Decode + bake orientation. Returns (image_id, pil_image_or_None, error_or_None)."""
    from modules.bird_species import _resolve_inference_path
    from modules.thumbnails import bake_orientation, open_image_for_ml

    image_id = int(row["id"])
    file_path = row.get("file_path") or ""
    try:
        inference_path = _resolve_inference_path(row, file_path)
        if not inference_path or not os.path.exists(inference_path):
            return image_id, None, "file_missing"
        img = open_image_for_ml(inference_path).convert("RGB")
        try:
            img = bake_orientation(img, inference_path)
        except Exception as orient_err:  # noqa: BLE001 — orientation is best-effort
            logger.debug("bake_orientation failed for image_id=%s: %s", image_id, orient_err)
        return image_id, img, None
    except Exception as exc:  # noqa: BLE001 — continue batch
        return image_id, None, f"decode_error: {exc}"


def apply_detection_result(
    image_id: int,
    box: Optional[dict],
    *,
    dry_run: bool,
    update_fn=None,
) -> str:
    """Persist a box or the not-detected sentinel. Returns 'detected'|'not_detected'|'write_error'."""
    from modules.bird_detection import BBOX_NOT_DETECTED

    if update_fn is None:
        from modules import db

        update_fn = db.update_image_bird_bbox

    payload = box if box is not None else BBOX_NOT_DETECTED
    outcome = "detected" if box is not None else "not_detected"
    if dry_run:
        return outcome
    if update_fn(image_id, payload):
        return outcome
    return "write_error"


def process_batch(
    rows: List[dict],
    *,
    detector,
    dry_run: bool,
    workers: int,
    progress_every: int,
    decode_fn=_decode_oriented,
    update_fn=None,
) -> dict:
    """Decode in a pool, run YOLO serially, write boxes/sentinels. Returns counters."""
    detected = 0
    not_detected = 0
    skipped = 0
    errors = 0
    written = 0
    t0 = time.monotonic()
    total = len(rows)
    chunk_size = max(workers * 4, workers)
    processed = 0

    for start in range(0, total, chunk_size):
        if _stop_requested:
            break
        chunk = rows[start : start + chunk_size]
        decoded: List[Tuple[int, Optional[Any], Optional[str]]] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(decode_fn, row) for row in chunk]
            for fut in as_completed(futures):
                decoded.append(fut.result())

        by_id = {image_id: (img, err) for image_id, img, err in decoded}

        for row in chunk:
            image_id = int(row["id"])
            img, err = by_id.get(image_id, (None, "missing_decode_result"))
            processed += 1

            if err or img is None:
                skipped += 1
                if err and err != "file_missing":
                    errors += 1
                    logger.warning("Skip image_id=%s: %s", image_id, err)
                continue

            try:
                box = detector.detect_best_box(img)
            except Exception as det_err:  # noqa: BLE001
                errors += 1
                logger.warning("Detect failed image_id=%s: %s", image_id, det_err)
                continue
            finally:
                try:
                    img.close()
                except Exception:  # noqa: BLE001
                    pass

            outcome = apply_detection_result(
                image_id, box, dry_run=dry_run, update_fn=update_fn
            )
            if outcome == "detected":
                detected += 1
                if not dry_run:
                    written += 1
            elif outcome == "not_detected":
                not_detected += 1
                if not dry_run:
                    written += 1
            else:
                errors += 1
                logger.error("Failed to write bird_bbox for image_id=%s", image_id)

            if progress_every > 0 and processed % progress_every == 0:
                elapsed = max(time.monotonic() - t0, 1e-6)
                rate = processed / elapsed
                remaining = max(total - processed, 0)
                eta = remaining / rate if rate > 0 else 0
                logger.info(
                    "Progress %s/%s (%.1f img/s, ETA %.0fs) — detected=%s none=%s skipped=%s",
                    processed,
                    total,
                    rate,
                    eta,
                    detected,
                    not_detected,
                    skipped,
                )

    return {
        "total": total,
        "detected": detected,
        "not_detected": not_detected,
        "skipped": skipped,
        "errors": errors,
        "written": written,
        "elapsed_sec": round(time.monotonic() - t0, 1),
        "stopped_early": _stop_requested,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Query and print candidates; run detection but do not write to DB",
    )
    p.add_argument(
        "--folder",
        type=str,
        default="",
        metavar="PATH",
        help="Limit to one folder path (exact match on folders.path)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Process at most N images (0 = no limit)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        metavar="N",
        help="Decode worker threads (default 4); YOLO stays single-threaded",
    )
    p.add_argument(
        "--progress-every",
        type=int,
        default=100,
        metavar="N",
        help="Log progress every N processed images (default 100; 0 = silent)",
    )
    p.add_argument(
        "--device",
        type=str,
        default=None,
        help="Override detector device (cpu|cuda|auto); default from config",
    )
    args = p.parse_args()

    if args.workers < 1:
        logger.error("--workers must be >= 1")
        return 2

    signal.signal(signal.SIGINT, _on_sigint)

    rows = fetch_candidates(folder=args.folder, limit=args.limit)
    logger.info(
        "Found %s bird-tagged image(s) with bird_bbox IS NULL%s",
        len(rows),
        f" in folder {args.folder!r}" if args.folder else "",
    )

    if not rows:
        logger.warning("Nothing to process.")
        return 1

    if args.dry_run:
        for row in rows[:50]:
            print(f"{row['id']}\t{row['file_path']}")
        if len(rows) > 50:
            print(f"... and {len(rows) - 50} more", file=sys.stderr)
        logger.info("Dry-run: %s candidate(s); no detection or writes.", len(rows))
        return 0

    from modules.bird_detection import BirdDetector

    detector = BirdDetector(device=args.device)
    if not detector.enabled:
        logger.error("bird_detection.enabled is false in config; aborting.")
        return 1
    try:
        detector.load_model()
    except Exception as exc:
        logger.error("Failed to load bird detector: %s", exc)
        return 1
    logger.info("Bird detector loaded (device=%s).", detector.device)

    summary = process_batch(
        rows,
        detector=detector,
        dry_run=False,
        workers=args.workers,
        progress_every=args.progress_every,
    )
    logger.info(
        "Done: total=%s detected=%s not_detected=%s skipped=%s errors=%s written=%s elapsed=%ss",
        summary["total"],
        summary["detected"],
        summary["not_detected"],
        summary["skipped"],
        summary["errors"],
        summary["written"],
        summary["elapsed_sec"],
    )
    if summary["stopped_early"]:
        return 130
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
