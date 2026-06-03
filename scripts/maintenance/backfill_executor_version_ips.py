#!/usr/bin/env python3
"""
Back-fill ``image_phase_status.executor_version`` on ``done`` rows where data is complete.

Legacy rows often have ``executor_version = NULL`` while status is ``done``. The planner
policy fix treats NULL as unknown; this script removes audit noise and aligns stored
versions with the current phase registry constants.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    export PYTHONPATH=/mnt/d/Projects/image-scoring-backend
    python scripts/maintenance/backfill_executor_version_ips.py --dry-run
    python scripts/maintenance/backfill_executor_version_ips.py --folder-path '/mnt/d/Photos/...' --limit 5000
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db  # noqa: E402
from modules.phases import SCORING_EXECUTOR_VERSION  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_PHASE_VERSION: dict[str, str] = {
    "indexing": "1.0.0",
    "metadata": "1.0.0",
    "scoring": SCORING_EXECUTOR_VERSION,
    "culling": "1.0.0",
    "keywords": "1.0.0",
}


def _wsl_path(path: str) -> str:
    p = path.replace("\\", "/")
    if len(p) >= 3 and p[1] == ":" and p[0].isalpha():
        return f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    return p


def _complete_check(phase_code: str) -> Callable[[int], bool]:
    checks: dict[str, Callable[[int], bool]] = {
        "indexing": db.is_image_indexing_complete,
        "metadata": db.is_image_metadata_complete,
        "scoring": db.is_image_scoring_complete,
        "culling": db.is_image_culling_complete,
        "keywords": db.is_image_keywords_complete,
        "bird_species": db.is_image_bird_species_complete,
    }
    fn = checks.get(phase_code)
    if fn is None:
        raise ValueError(f"unsupported phase_code: {phase_code}")
    return fn


def _bird_version() -> str:
    from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

    return str(BIRD_SPECIES_RUNNER_VERSION)


def _target_version(phase_code: str) -> str:
    if phase_code == "bird_species":
        return _bird_version()
    return _PHASE_VERSION[phase_code]


def _fetch_candidates(
    phase_code: str,
    *,
    folder_path: Optional[str],
    limit: int,
    offset: int,
) -> list[int]:
    folder_sql = ""
    params: list[object] = [phase_code]
    if folder_path:
        target = _wsl_path(folder_path)
        folder_sql = (
            " AND EXISTS ("
            "SELECT 1 FROM images i JOIN folders f ON f.id = i.folder_id "
            "WHERE i.id = ips.image_id AND (f.path = ? OR f.path LIKE ?)"
            ")"
        )
        params.extend([target, f"{target.rstrip('/')}/%"])
    params.append(limit)
    params.append(offset)
    query = (
        "SELECT ips.image_id AS image_id "
        "FROM image_phase_status ips "
        "JOIN pipeline_phases pp ON pp.id = ips.phase_id "
        "WHERE LOWER(TRIM(ips.status)) = 'done' "
        "AND (ips.executor_version IS NULL OR TRIM(COALESCE(ips.executor_version, '')) = '') "
        "AND pp.code = ?"
        f"{folder_sql} "
        "ORDER BY ips.image_id "
        "LIMIT ? OFFSET ?"
    )
    rows = db.get_connector().query(query, tuple(params))
    out: list[int] = []
    for row in rows or []:
        try:
            out.append(int(row["image_id"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _apply_version(image_id: int, phase_code: str, version: str) -> None:
    db.set_image_phase_status(
        image_id,
        phase_code,
        "done",
        executor_version=version,
    )


def backfill(
    *,
    dry_run: bool,
    folder_path: Optional[str],
    phases: Optional[list[str]],
    limit: int,
    batch_size: int,
) -> dict[str, int]:
    db.init_db()
    phase_list = phases or list(_PHASE_VERSION.keys()) + ["bird_species"]
    stats = {"candidates": 0, "backfilled": 0, "skipped_incomplete": 0}

    for phase_code in phase_list:
        if phase_code not in _PHASE_VERSION and phase_code != "bird_species":
            log.warning("skip unknown phase %s", phase_code)
            continue
        version = _target_version(phase_code)
        is_complete = _complete_check(phase_code)
        offset = 0
        phase_backfilled = 0
        while phase_backfilled < limit:
            page_limit = min(batch_size, limit - phase_backfilled)
            image_ids = _fetch_candidates(
                phase_code,
                folder_path=folder_path,
                limit=page_limit,
                offset=offset,
            )
            if not image_ids:
                break
            offset += len(image_ids)
            stats["candidates"] += len(image_ids)
            for image_id in image_ids:
                if not is_complete(image_id):
                    stats["skipped_incomplete"] += 1
                    continue
                stats["backfilled"] += 1
                phase_backfilled += 1
                if dry_run:
                    log.debug("would set image %s %s -> %s", image_id, phase_code, version)
                else:
                    _apply_version(image_id, phase_code, version)
            if len(image_ids) < page_limit:
                break
        log.info(
            "phase %s: backfilled %s (dry_run=%s)",
            phase_code,
            phase_backfilled,
            dry_run,
        )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Back-fill executor_version on done image_phase_status rows when data is complete.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Count only; do not write")
    parser.add_argument("--folder-path", type=str, default=None, help="Limit to folder subtree")
    parser.add_argument(
        "--phases",
        type=str,
        default=None,
        help="Comma-separated phase codes (default: all standard phases)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100_000,
        help="Max rows to backfill per phase (default 100000)",
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Fetch page size")
    args = parser.parse_args()
    phases = [p.strip() for p in args.phases.split(",") if p.strip()] if args.phases else None
    stats = backfill(
        dry_run=args.dry_run,
        folder_path=args.folder_path,
        phases=phases,
        limit=max(1, args.limit),
        batch_size=max(50, args.batch_size),
    )
    log.info(
        "done: candidates=%s backfilled=%s skipped_incomplete=%s dry_run=%s",
        stats["candidates"],
        stats["backfilled"],
        stats["skipped_incomplete"],
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
