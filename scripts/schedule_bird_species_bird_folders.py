#!/usr/bin/env python3
"""
Schedule bird species classification jobs, one folder per API call.

Two operating modes (select with --only-needing-species):

  Legacy mode (default)
    List every folder that contains at least one image tagged with a birds-related
    keyword (keyword_norm LIKE '%birds%', or exact 'birds' with --exact-keyword),
    regardless of whether species classification has already run.

  Gap mode (--only-needing-species)
    List only folders that still have at least one image that has a birds keyword,
    lacks any 'species:*' keyword, and does not have bird_species IPS skipped/no_species_match —
    i.e. classification is genuinely pending (see bird_species_eligibility).
    In this mode --chunk-size defaults to 1 so every folder becomes its own queued
    job, keeping the queue granular and resumable.

Usage (WSL, project root, per CLAUDE.md):
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
  source ~/.venvs/tf/bin/activate

  # Inspect: which folders still need species ID?
  python scripts/schedule_bird_species_bird_folders.py --only-needing-species --dry-run

  # Enqueue each pending folder as a separate job (one-folder-per-run)
  python scripts/schedule_bird_species_bird_folders.py --only-needing-species

  # Legacy: enqueue all bird folders in batches of 80
  python scripts/schedule_bird_species_bird_folders.py --chunk-size 80 --overwrite

Requires the WebUI running for non-dry-run calls. Uses stdlib urllib only.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Legacy SQL: any folder with a birds-related keyword ──────────────────────

_SQL_LIKE = """
SELECT DISTINCT f.path
FROM images i
JOIN folders f ON i.folder_id = f.id
JOIN image_keywords ik ON ik.image_id = i.id
JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
WHERE kd.keyword_norm LIKE ?
ORDER BY 1
"""

_SQL_EXACT = """
SELECT DISTINCT f.path
FROM images i
JOIN folders f ON i.folder_id = f.id
JOIN image_keywords ik ON ik.image_id = i.id
JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
WHERE kd.keyword_norm = ?
ORDER BY 1
"""

# ── Gap SQL: folders with at least one image that needs species ID ────────────
# Pending = birds keyword, no species:*, and not IPS no_species_match skip
# (see modules/bird_species_eligibility.py). PostgreSQL prefix via LIKE.

_IPS_NOT_EXHAUSTED = """
AND NOT EXISTS (
    SELECT 1
    FROM image_phase_status ips_e
    JOIN pipeline_phases pp_e ON pp_e.id = ips_e.phase_id
    WHERE ips_e.image_id = i.id
      AND LOWER(TRIM(pp_e.code)) = 'bird_species'
      AND LOWER(TRIM(ips_e.status)) = 'skipped'
      AND LOWER(TRIM(COALESCE(ips_e.skip_reason, ''))) = 'no_species_match'
)
"""

_SQL_GAP_LIKE = f"""
SELECT DISTINCT f.path
FROM images i
JOIN folders f ON i.folder_id = f.id
WHERE EXISTS (
    SELECT 1
    FROM image_keywords ik
    JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
    WHERE ik.image_id = i.id
      AND kd.keyword_norm LIKE ?
)
AND NOT EXISTS (
    SELECT 1
    FROM image_keywords ik2
    JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
    WHERE ik2.image_id = i.id
      AND kd2.keyword_norm LIKE 'species:%'
)
{_IPS_NOT_EXHAUSTED}
ORDER BY 1
"""

_SQL_GAP_EXACT = f"""
SELECT DISTINCT f.path
FROM images i
JOIN folders f ON i.folder_id = f.id
WHERE EXISTS (
    SELECT 1
    FROM image_keywords ik
    JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
    WHERE ik.image_id = i.id
      AND kd.keyword_norm = ?
)
AND NOT EXISTS (
    SELECT 1
    FROM image_keywords ik2
    JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
    WHERE ik2.image_id = i.id
      AND kd2.keyword_norm LIKE 'species:%'
)
{_IPS_NOT_EXHAUSTED}
ORDER BY 1
"""


def fetch_folder_paths(*, exact_match: bool, gap_only: bool) -> List[str]:
    """Return distinct folder paths matching the chosen filter.

    gap_only=True  → only folders with pending species work (GAP-I)
    gap_only=False → all folders containing any bird-tagged image (legacy)
    """
    from modules import db

    conn = db.get_db()
    try:
        c = conn.cursor()
        if gap_only:
            if exact_match:
                c.execute(_SQL_GAP_EXACT, ("birds",))
            else:
                c.execute(_SQL_GAP_LIKE, ("%birds%",))
        else:
            if exact_match:
                c.execute(_SQL_EXACT, ("birds",))
            else:
                c.execute(_SQL_LIKE, ("%birds%",))
        rows = c.fetchall()
    finally:
        conn.close()

    paths: List[str] = []
    for row in rows:
        p = row[0]
        if p is not None and str(p).strip():
            paths.append(str(p).strip())
    return paths


def _post_bird_species_chunk(
    api_base: str,
    folder_paths: List[str],
    *,
    overwrite: bool,
    threshold: float,
    top_k: int,
    candidate_species: list[str] | None,
    timeout_sec: int,
) -> dict:
    url = api_base.rstrip("/") + "/api/bird-species/start"
    body: dict = {
        "folder_paths": folder_paths,
        "recursive": False,
        "overwrite": overwrite,
        "threshold": threshold,
        "top_k": top_k,
    }
    if candidate_species is not None:
        body["candidate_species"] = candidate_species

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--api-base",
        default=os.environ.get("IMGSCORE_API_BASE", "http://127.0.0.1:7860"),
        help="WebUI base URL (default: env IMGSCORE_API_BASE or http://127.0.0.1:7860)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only query DB and print folder paths; do not POST",
    )
    p.add_argument(
        "--only-needing-species",
        action="store_true",
        dest="gap_only",
        help=(
            "Gap mode: only include folders where at least one image has a birds "
            "keyword but no species: classification yet (analyzer GAP-I). "
            "Defaults chunk-size to 1 so each folder becomes its own queued job."
        ),
    )
    p.add_argument(
        "--exact-keyword",
        action="store_true",
        help="Match keyword_norm == 'birds' instead of LIKE '%%birds%%'",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Consider at most N folders after sort (0 = no limit)",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Max folder paths per POST. "
            "Defaults to 1 when --only-needing-species is set, 100 otherwise."
        ),
    )
    p.add_argument("--overwrite", action="store_true", help="Re-classify images that already have species: keywords")
    p.add_argument("--threshold", type=float, default=0.1, help="BioCLIP softmax threshold")
    p.add_argument("--top-k", type=int, default=3, dest="top_k", help="Max species keywords per image")
    p.add_argument(
        "--candidate-species-json",
        type=str,
        default="",
        metavar="PATH",
        help="JSON file: array of species name strings for candidate_species",
    )
    p.add_argument(
        "--output-json",
        type=str,
        default="",
        metavar="PATH",
        help="Write ordered folder path list as JSON array",
    )
    p.add_argument("--timeout", type=int, default=120, help="HTTP timeout seconds per request")
    args = p.parse_args()

    # Resolve chunk-size default based on mode
    if args.chunk_size is None:
        args.chunk_size = 1 if args.gap_only else 100

    if args.chunk_size < 1:
        logger.error("--chunk-size must be >= 1")
        return 2

    paths = fetch_folder_paths(exact_match=args.exact_keyword, gap_only=args.gap_only)
    if args.limit > 0:
        paths = paths[: args.limit]

    mode_label = "needing species classification" if args.gap_only else "with birds keyword"
    logger.info("Found %s distinct folder path(s) %s", len(paths), mode_label)

    if args.output_json:
        out_path = os.path.abspath(args.output_json)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(paths, f, indent=2)
        logger.info("Wrote folder list to %s", out_path)

    if args.dry_run:
        for fp in paths[:50]:
            print(fp)
        if len(paths) > 50:
            print(f"... and {len(paths) - 50} more", file=sys.stderr)
        if not paths:
            logger.warning("No folders matched; nothing to schedule.")
            return 1
        return 0

    if not paths:
        logger.error("No folders matched; aborting.")
        return 1

    candidate_species = None
    if args.candidate_species_json:
        with open(args.candidate_species_json, encoding="utf-8") as f:
            candidate_species = json.load(f)
        if not isinstance(candidate_species, list) or not all(isinstance(x, str) for x in candidate_species):
            logger.error("--candidate-species-json must be a JSON array of strings")
            return 2

    chunk_size = args.chunk_size
    ok_chunks = 0
    for start in range(0, len(paths), chunk_size):
        chunk = paths[start : start + chunk_size]
        try:
            resp = _post_bird_species_chunk(
                args.api_base,
                chunk,
                overwrite=args.overwrite,
                threshold=args.threshold,
                top_k=args.top_k,
                candidate_species=candidate_species,
                timeout_sec=args.timeout,
            )
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error("HTTP %s for chunk starting %s: %s", e.code, chunk[0], err_body)
            return 1
        except urllib.error.URLError as e:
            logger.error("Request failed for chunk starting %s: %s", chunk[0], e)
            return 1
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return 1

        if not resp.get("success"):
            logger.error("API error: %s", resp)
            return 1
        data = resp.get("data") or {}
        logger.info(
            "Queued job_id=%s queue_position=%s folders=%s resolved_count=%s",
            data.get("job_id"),
            data.get("queue_position"),
            len(chunk),
            data.get("resolved_count"),
        )
        ok_chunks += 1

    logger.info(
        "Submitted %s job(s) (%s folder path(s) total, chunk-size=%s).",
        ok_chunks,
        len(paths),
        chunk_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
