#!/usr/bin/env python3
"""Backfill ARNIQA shadow scores into ``image_model_scores`` for images missing ``arniqa``.

Uses ``ArniqaModelWrapper`` (pyiqa ``arniqa`` metric). Resolves JPEG/thumbnail paths
for RAW files when the DB file_path is not directly readable. Rows are written with
``is_shadow`` per ``scoring.models.arniqa`` config (default true).

Requires pyiqa and PyTorch. Run from WSL with the app venv (``~/.venvs/tf``)::

    source ~/.venvs/tf/bin/activate
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
    python scripts/maintenance/backfill_arniqa.py --dry-run
    python scripts/maintenance/backfill_arniqa.py --device cuda
    python scripts/maintenance/backfill_arniqa.py --folder /mnt/d/Photos/2024-03-26
    python scripts/maintenance/backfill_arniqa.py --limit 100 --resume-after-id 500
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db, db_legacy, utils  # noqa: E402
from modules.engines.arniqa_model import ArniqaModelWrapper  # noqa: E402
from modules.engines.registry import get_registry  # noqa: E402
from modules.thumbnails import get_local_thumb, get_thumb_wsl  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_MODEL_NAME = "arniqa"


def _row_get(row: Any, key: str, index: int = 0) -> Any:
    try:
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
    except Exception:
        pass
    try:
        return row[index]
    except (KeyError, IndexError, TypeError):
        return None


def _resolve_scoring_path(row: Any) -> Optional[str]:
    """Prefer thumbnail / readable JPEG over RAW DB path."""
    if os.name == "nt":
        thumb = get_local_thumb(row)
        if thumb and os.path.exists(thumb):
            return thumb
        fp = _row_get(row, "file_path", 1)
        if not fp:
            return None
        local_fp = utils.convert_path_to_local(fp) if hasattr(utils, "convert_path_to_local") else fp
        return local_fp if local_fp and os.path.exists(local_fp) else None

    thumb = get_thumb_wsl(row)
    if thumb and os.path.exists(thumb):
        return thumb
    fp = _row_get(row, "file_path", 1)
    if not fp:
        return None
    wsl_fp = utils.convert_path_to_wsl(fp) if hasattr(utils, "convert_path_to_wsl") else fp
    if wsl_fp and os.path.exists(wsl_fp):
        ext = os.path.splitext(wsl_fp)[1].lower()
        if ext not in (".nef", ".nrw", ".cr2", ".cr3", ".arw", ".dng", ".orf", ".raf", ".rw2"):
            return wsl_fp
    return thumb if thumb and os.path.exists(thumb) else None


def _fetch_candidates(
    *,
    folder: Optional[str],
    limit: Optional[int],
    resume_after_id: Optional[int],
    force: bool,
) -> list:
    conn = db.get_connector()
    clauses = ["1=1"]
    params: list[Any] = []

    if not force:
        clauses.append(
            "NOT EXISTS ("
            "SELECT 1 FROM image_model_scores ims "
            "WHERE ims.image_id = i.id AND ims.model_name = ?"
            ")"
        )
        params.append(_MODEL_NAME)

    if folder:
        folder_norm = folder.replace("\\", "/").rstrip("/")
        clauses.append("(i.file_path LIKE ? OR i.file_path LIKE ?)")
        params.extend([f"{folder_norm}/%", f"{folder_norm}\\%"])

    if resume_after_id is not None:
        clauses.append("i.id > ?")
        params.append(int(resume_after_id))

    sql = (
        "SELECT i.id, i.file_path, i.thumbnail_path "
        f"FROM images i WHERE {' AND '.join(clauses)} "
        "ORDER BY i.id"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))

    return conn.query(sql, tuple(params))


def _is_shadow_from_config() -> bool:
    try:
        return get_registry().is_shadow(_MODEL_NAME)
    except Exception:
        return True


def _build_write_result(wrapper: ArniqaModelWrapper, raw: float, *, is_shadow: bool) -> dict:
    norm = wrapper.normalize(raw)
    return {
        "models": {
            _MODEL_NAME: {
                "score": round(raw, 4),
                "normalized_score": round(norm, 4),
                "status": "success",
                "is_shadow": is_shadow,
            }
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill ARNIQA into image_model_scores")
    parser.add_argument("--folder", type=str, default=None, help="Restrict to images under this folder path")
    parser.add_argument("--limit", type=int, default=None, help="Max images to process")
    parser.add_argument(
        "--resume-after-id",
        type=int,
        default=None,
        metavar="ID",
        help="Only rows with id > ID (stable resume after interruption)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rescore even when an arniqa row already exists",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report candidates only; do not score or write")
    parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        choices=("cuda", "cpu"),
        help="Torch device for ARNIQA (default: cuda)",
    )
    args = parser.parse_args()

    db.init_db()
    conn = db.get_connector()
    if getattr(conn, "type", None) != "postgres":
        logger.error("Backfill is Postgres-only (current engine: %s).", getattr(conn, "type", "?"))
        return 1

    rows = _fetch_candidates(
        folder=args.folder,
        limit=args.limit,
        resume_after_id=args.resume_after_id,
        force=args.force,
    )
    total = len(rows)
    logger.info("Found %d image(s) to %s.", total, "inspect" if args.dry_run else "score")

    if total == 0:
        return 0

    if args.dry_run:
        for i, row in enumerate(rows[:15]):
            img_id = _row_get(row, "id", 0)
            path = _resolve_scoring_path(row)
            logger.info(
                "  [%d] id=%s file_path=%s resolved=%s exists=%s",
                i + 1,
                img_id,
                _row_get(row, "file_path", 1),
                path,
                bool(path and os.path.exists(path)),
            )
        if total > 15:
            logger.info("  ... and %d more", total - 15)
        return 0

    is_shadow = _is_shadow_from_config()
    logger.info("Writing with is_shadow=%s (from scoring.models.arniqa)", is_shadow)

    wrapper = ArniqaModelWrapper(device=args.device)
    if not wrapper.load():
        logger.error("ARNIQA model failed to load (check pyiqa/torch/CUDA).")
        return 1

    version = wrapper.version or "arniqa-1"
    ok = 0
    skipped = 0
    failed = 0
    t0 = time.time()

    for idx, row in enumerate(rows, start=1):
        img_id = int(_row_get(row, "id", 0))
        path = _resolve_scoring_path(row)
        if not path or not os.path.exists(path):
            skipped += 1
            logger.warning("Skip id=%s — no readable path", img_id)
            continue

        payload = wrapper.predict(path)
        if payload.get("status") != "success" or payload.get("score") is None:
            failed += 1
            logger.warning(
                "Fail id=%s path=%s: %s",
                img_id,
                path,
                payload.get("error") or payload.get("status"),
            )
            continue

        raw = float(payload["score"])
        result = _build_write_result(wrapper, raw, is_shadow=is_shadow)
        db_legacy._write_image_model_scores(img_id, result, version)
        ok += 1

        if idx % 50 == 0 or idx == total:
            elapsed = time.time() - t0
            rate = ok / elapsed if elapsed > 0 else 0.0
            logger.info(
                "Progress %d/%d — ok=%d skipped=%d failed=%d (%.1f img/s)",
                idx,
                total,
                ok,
                skipped,
                failed,
                rate,
            )

    logger.info(
        "Done. ok=%d skipped=%d failed=%d elapsed=%.1fs",
        ok,
        skipped,
        failed,
        time.time() - t0,
    )
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
