#!/usr/bin/env python3
"""
Export image scores for a folder to CSV.

Primary match: images.file_path or file_paths.path prefix (WSL + Windows variants).
When that yields zero rows and --source-folder is set, lists files on disk under
--folder and joins DB rows by basename (stem) under the source folder prefix
(export JPEGs often share names with indexed NEFs).

Run from repo root (WSL + ~/.venvs/tf):

    python scripts/export_folder_scores_csv.py \\
        --folder "D:\\Photos\\Export\\2026\\A23" \\
        --source-folder "D:\\Photos\\Z8\\180-600mm\\2026\\2026-04-09" \\
        --output output/A23_export_scores.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from modules import paths as pathutil

# Columns requested by export plan (filtered to existing DB columns at runtime).
_IMAGE_COLS = [
    "id",
    "file_name",
    "file_path",
    "file_type",
    "image_hash",
    "hash_version",
    "image_uuid",
    "score",
    "score_general",
    "score_technical",
    "score_aesthetic",
    "score_spaq",
    "score_ava",
    "score_koniq",
    "score_paq2piq",
    "score_liqe",
    "rating",
    "label",
    "keywords",
    "stack_id",
    "burst_uuid",
    "created_at",
    "updated_at",
    "model_version",
]

_EDITORIAL_COLS = [
    "editorial_batch_label",
    "editorial_subject",
    "editorial_overall_verdict",
    "editorial_carousel_title",
    "editorial_carousel_hook",
    "editorial_carousel_slide",
    "editorial_carousel_role",
    "editorial_top_pick_rank",
    "editorial_reject_priority",
    "editorial_reject_reason",
    "editorial_verdict",
    "editorial_strengths",
    "editorial_critique",
    "editorial_improvements",
    "editorial_left_out_summary",
    "editorial_strongest_keep",
]

_DEFAULT_REVIEWS = Path(_REPO_ROOT) / "data" / "editorial" / "a32_anhinga_reviews.json"


def _stem_from_row(row: dict[str, Any]) -> str:
    export_path = row.get("export_disk_path") or ""
    if export_path:
        return Path(str(export_path)).stem
    fname = row.get("file_name") or ""
    return Path(str(fname)).stem


def _load_editorial_reviews(path: Optional[Path]) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _editorial_fields_for_stem(stem: str, reviews: dict[str, Any]) -> dict[str, Any]:
    if not reviews:
        return {}
    images = reviews.get("images") or {}
    entry = images.get(stem)
    if not entry:
        return {}
    batch_key = entry.get("batch") or ""
    batch = (reviews.get("batches") or {}).get(batch_key) or {}
    out: dict[str, Any] = {
        "editorial_batch_label": batch.get("folder_label"),
        "editorial_subject": batch.get("subject"),
        "editorial_overall_verdict": batch.get("overall_verdict"),
        "editorial_carousel_title": batch.get("carousel_title"),
        "editorial_carousel_hook": batch.get("carousel_hook"),
        "editorial_left_out_summary": batch.get("left_out_summary"),
        "editorial_carousel_slide": entry.get("carousel_slide"),
        "editorial_carousel_role": entry.get("carousel_role"),
        "editorial_top_pick_rank": entry.get("top_pick_rank"),
        "editorial_reject_priority": entry.get("reject_priority"),
        "editorial_reject_reason": entry.get("reject_reason"),
        "editorial_verdict": entry.get("verdict"),
        "editorial_strengths": entry.get("strengths"),
        "editorial_critique": entry.get("critique"),
        "editorial_improvements": entry.get("improvements"),
        "editorial_strongest_keep": (
            "yes" if entry.get("strongest_keep") else ("no" if entry.get("strongest_keep") is False else "")
        ),
    }
    if out.get("editorial_reject_priority") is True:
        out["editorial_reject_priority"] = "yes"
    elif out.get("editorial_reject_priority") is False:
        out["editorial_reject_priority"] = "no"
    return out


def _folder_prefixes(folder: str) -> list[str]:
    """Build LIKE prefixes for WSL and Windows path forms."""
    wsl = pathutil.to_wsl(folder).rstrip("/")
    win = pathutil.normalize(folder).rstrip("/")
    prefixes: list[str] = []
    for p in (wsl, win):
        if p and p not in prefixes:
            prefixes.append(p)
    return prefixes


def _local_folder(folder: str) -> str:
    """Resolve folder to a path usable for os.listdir on this host."""
    wsl = pathutil.to_wsl(folder)
    if pathutil.is_wsl_path(wsl) and os.name != "nt":
        return wsl
    win = pathutil.to_windows(folder)
    if win and os.path.isdir(win):
        return win
    if os.path.isdir(wsl):
        return wsl
    return folder


def _path_match_where(prefixes: list[str]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for prefix in prefixes:
        like = f"{prefix}%"
        clauses.append("i.file_path LIKE ?")
        params.append(like)
        clauses.append("fp.path LIKE ?")
        params.append(like)
    return "(" + " OR ".join(clauses) + ")", params


def _discover_ids_by_path(conn, prefixes: list[str]) -> list[int]:
    where, params = _path_match_where(prefixes)
    rows = conn.query(
        f"""
        SELECT DISTINCT i.id AS id
        FROM images i
        LEFT JOIN file_paths fp ON fp.image_id = i.id
        WHERE {where}
        ORDER BY i.id
        """,
        tuple(params),
    )
    return [int(r["id"]) for r in rows]


def _discover_ids_by_basename(
    conn, export_folder: str, source_prefixes: list[str]
) -> list[tuple[int, str]]:
    """Return (image_id, export_disk_path) for each file in export folder."""
    local = _local_folder(export_folder)
    if not os.path.isdir(local):
        raise SystemExit(f"Export folder not found on disk: {local}")

    out: list[tuple[int, str]] = []
    seen: set[int] = set()

    for name in sorted(os.listdir(local)):
        full = os.path.join(local, name)
        if not os.path.isfile(full):
            continue
        stem, _ext = os.path.splitext(name)
        if not stem:
            continue
        src_clauses = " OR ".join(["i.file_path LIKE ?"] * len(source_prefixes))
        rows = conn.query(
            f"""
            SELECT i.id AS id
            FROM images i
            WHERE ({src_clauses})
              AND lower(regexp_replace(i.file_name, '\\.[^.]*$', '')) = lower(?)
            ORDER BY i.id
            """,
            tuple([f"{p}%" for p in source_prefixes] + [stem]),
        )
        if not rows:
            continue
        image_id = int(rows[0]["id"])
        if image_id in seen:
            continue
        seen.add(image_id)
        out.append((image_id, full))
    return out


def _existing_image_columns(conn) -> list[str]:
    from modules import db

    avail = set(db.get_available_columns())
    return [c for c in _IMAGE_COLS if c in avail]


def _fetch_images(conn, image_ids: list[int], cols: list[str]) -> dict[int, dict[str, Any]]:
    if not image_ids:
        return {}
    placeholders = ",".join(["?"] * len(image_ids))
    col_sql = ", ".join(f"i.{c}" for c in cols)
    rows = conn.query(
        f"""
        SELECT {col_sql},
               COALESCE((
                   SELECT string_agg(fp.path, '; ' ORDER BY fp.path)
                   FROM file_paths fp
                   WHERE fp.image_id = i.id
               ), '') AS all_file_paths
        FROM images i
        WHERE i.id IN ({placeholders})
        ORDER BY i.id
        """,
        tuple(image_ids),
    )
    return {int(r["id"]): dict(r) for r in rows}


def _fetch_model_scores_pivot(conn, image_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not image_ids:
        return {}
    try:
        conn.query("SELECT 1 FROM image_model_scores LIMIT 1", ())
    except Exception:
        return {}

    placeholders = ",".join(["?"] * len(image_ids))
    rows = conn.query(
        f"""
        SELECT image_id, model_name, normalized, raw_score, status, is_shadow
        FROM image_model_scores
        WHERE image_id IN ({placeholders})
          AND (is_shadow IS NULL OR is_shadow = FALSE)
        ORDER BY image_id, model_name
        """,
        tuple(image_ids),
    )
    by_id: dict[int, dict[str, Any]] = {}
    for r in rows:
        iid = int(r["image_id"])
        name = re.sub(r"[^a-zA-Z0-9_]+", "_", str(r["model_name"] or "").strip()).strip("_")
        if not name:
            continue
        col = f"ims_{name}"
        val = r.get("normalized")
        if val is None:
            val = r.get("raw_score")
        by_id.setdefault(iid, {})[col] = val
    return by_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Export folder image scores to CSV")
    parser.add_argument("--folder", required=True, help="Export folder (Windows or WSL path)")
    parser.add_argument(
        "--source-folder",
        default=None,
        help="When path match finds 0 rows, match export files on disk to DB by basename under this folder",
    )
    parser.add_argument("--output", required=True, help="Output CSV path")
    parser.add_argument(
        "--reviews",
        default=str(_DEFAULT_REVIEWS),
        help="JSON file with editorial reviews keyed by DSC stem (use '' to disable)",
    )
    args = parser.parse_args()

    os.chdir(_REPO_ROOT)
    from modules import db

    conn = db.get_connector()
    export_prefixes = _folder_prefixes(args.folder)
    image_ids = _discover_ids_by_path(conn, export_prefixes)
    export_disk_paths: dict[int, str] = {}
    match_mode = "path_prefix"

    if not image_ids and args.source_folder:
        source_prefixes = _folder_prefixes(args.source_folder)
        basename_pairs = _discover_ids_by_basename(conn, args.folder, source_prefixes)
        image_ids = [p[0] for p in basename_pairs]
        export_disk_paths = {p[0]: p[1] for p in basename_pairs}
        match_mode = "basename_source_folder"

    cols = _existing_image_columns(conn)
    rows_by_id = _fetch_images(conn, image_ids, cols)
    ims_by_id = _fetch_model_scores_pivot(conn, image_ids)

    all_ims_cols: set[str] = set()
    for d in ims_by_id.values():
        all_ims_cols.update(d.keys())
    ims_cols_sorted = sorted(all_ims_cols)

    reviews_path = Path(args.reviews) if args.reviews else None
    reviews_data = _load_editorial_reviews(reviews_path)
    editorial_cols = _EDITORIAL_COLS if reviews_data else []

    fieldnames = (
        ["export_disk_path", "match_mode"]
        + cols
        + ["all_file_paths"]
        + ims_cols_sorted
        + editorial_cols
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for iid in image_ids:
            base = rows_by_id.get(iid, {})
            row = {k: base.get(k) for k in fieldnames}
            row["match_mode"] = match_mode
            row["export_disk_path"] = export_disk_paths.get(iid, "")
            for k, v in ims_by_id.get(iid, {}).items():
                row[k] = v
            if reviews_data:
                stem = _stem_from_row(row)
                for k, v in _editorial_fields_for_stem(stem, reviews_data).items():
                    row[k] = v
            writer.writerow(row)

    if reviews_data:
        matched = sum(
            1
            for iid in image_ids
            if _stem_from_row(
                {"export_disk_path": export_disk_paths.get(iid, ""), **rows_by_id.get(iid, {})}
            )
            in (reviews_data.get("images") or {})
        )
        print(f"Editorial reviews matched: {matched}/{len(image_ids)}")

    print(f"Match mode: {match_mode}")
    print(f"Export prefixes: {export_prefixes}")
    print(f"Rows written: {len(image_ids)}")
    print(f"Output: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
