"""
Remove DB image rows under a Photos root whose first subfolder does not match
allowed camera-style names (default: Nikon D* / Z* top-level folders).

Used by ``scripts/maintenance/prune_photos_keep_camera_folders.py``.
"""

from __future__ import annotations

import os
import posixpath
import re
from typing import Any

# Default: D + digit + optional suffix (D850, D7500), or Z + digits / Zf / Zfc (Z6, Z6 III, Z30, …).
# Compiled with re.IGNORECASE (inline (?i) is not valid after ``^`` in stdlib ``re``).
DEFAULT_ALLOW_PATTERN = r"^(D\d[\w .-]*|Z((fc|f)|\d[\w .-]*))$"


def photos_prune_whitelist_from_config() -> frozenset[str]:
    """Lowercased first-segment names from ``indexing.photos_prune_top_segment_whitelist``."""
    from modules import config

    raw = config.get_config_value("indexing.photos_prune_top_segment_whitelist", default=[]) or []
    if not isinstance(raw, list):
        return frozenset()
    out: set[str] = set()
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.add(x.strip().lower())
    return frozenset(out)


def photos_prune_allow_regex_from_config(cli_allow_pattern: str | None) -> str:
    """CLI pattern wins; else ``indexing.photos_prune_top_segment_allow_regex``; else default."""
    from modules import config

    if cli_allow_pattern is not None and str(cli_allow_pattern).strip():
        return str(cli_allow_pattern).strip()
    cfg = config.get_config_value("indexing.photos_prune_top_segment_allow_regex", default=None)
    if isinstance(cfg, str) and cfg.strip():
        return cfg.strip()
    return DEFAULT_ALLOW_PATTERN


def photos_prune_root_from_config(cli_root: str | None) -> str:
    """Non-empty CLI root wins; else ``indexing.photos_prune_root``; else ``D:\\Photos``."""
    from modules import config

    if cli_root is not None and str(cli_root).strip():
        return str(cli_root).strip()
    cfg = config.get_config_value("indexing.photos_prune_root", default="") or ""
    if isinstance(cfg, str) and cfg.strip():
        return cfg.strip()
    return r"D:\Photos"


def top_segment_allowed(
    seg_raw: str,
    *,
    whitelist_lower: frozenset[str],
    allow_re: re.Pattern[str],
) -> bool:
    """Keep folder if it is on the whitelist (case-insensitive) or matches ``allow_re`` (fullmatch)."""
    if seg_raw.lower() in whitelist_lower:
        return True
    return bool(allow_re.fullmatch(seg_raw))


def _canonical_logical_path(p: str) -> str:
    s = str(p).strip().replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s.lower()


def _nonempty_path_parts(path: str) -> list[str]:
    return [p for p in str(path).replace("\\", "/").split("/") if p != ""]


def first_segment_under_logical_roots(file_path: str, roots: frozenset[str]) -> str | None:
    """
    Return the first path segment under the longest matching logical root (lowercase),
    or None if the file lies directly under a root or under none of them.
    """
    raw = first_segment_raw_under_logical_roots(file_path, roots)
    return raw.lower() if raw is not None else None


def first_segment_raw_under_logical_roots(file_path: str, roots: frozenset[str]) -> str | None:
    """
    Same as ``first_segment_under_logical_roots`` but preserves the segment spelling from
    ``file_path`` (needed for ``folders`` cache paths and Windows/WSL consistency).
    """
    k = _canonical_logical_path(file_path)
    if not k or not roots:
        return None
    best: str | None = None
    for r in sorted(roots, key=len, reverse=True):
        if not r:
            continue
        if k == r:
            return None
        if k.startswith(r + "/"):
            best = r
            break
    if not best:
        return None
    root_parts = _nonempty_path_parts(best)
    fp_parts = _nonempty_path_parts(file_path)
    if len(fp_parts) <= len(root_parts):
        return None
    for i, rp in enumerate(root_parts):
        if i >= len(fp_parts) or fp_parts[i].lower() != rp.lower():
            return None
    return fp_parts[len(root_parts)]


def run_prune_keep_top_segment_pattern(
    *,
    root: str | None = None,
    allow_pattern: str | None = None,
    extra_whitelist: list[str] | None = None,
    dry_run: bool = True,
    limit_images: int = 0,
) -> dict[str, Any]:
    """
    Under ``root`` (Windows, WSL, or mixed DB paths), delete images whose first
    directory segment under ``root`` is not allowed.

    Allow if the segment is in ``indexing.photos_prune_top_segment_whitelist`` (config),
    plus any ``extra_whitelist`` names, **or** it full-matches the effective allow regex
    (CLI ``allow_pattern``, else ``indexing.photos_prune_top_segment_allow_regex``, else
    Nikon D/Z default).

    Returns a JSON-friendly dict.
    """
    from modules.db import delete_folder_cache_entry, delete_image, get_connector
    from modules.indexing_policy import (
        _expand_path_variants_for_exclusion,
        logical_roots_from_user_prefixes,
        path_is_under_logical_roots,
        sql_like_prefixes_for_path_purge,
    )

    raw_root = photos_prune_root_from_config(root)
    if not raw_root:
        return {"success": False, "message": "No root path.", "matched": 0}

    pat_str = photos_prune_allow_regex_from_config(allow_pattern)
    try:
        allow_re = re.compile(pat_str, re.IGNORECASE)
    except re.error as e:
        return {"success": False, "message": f"Invalid regex: {e}", "matched": 0}

    wl = set(photos_prune_whitelist_from_config())
    if extra_whitelist:
        for x in extra_whitelist:
            if isinstance(x, str) and x.strip():
                wl.add(x.strip().lower())
    whitelist_lower = frozenset(wl)

    roots = logical_roots_from_user_prefixes([raw_root])
    if not roots:
        return {"success": False, "message": "Could not resolve root path.", "matched": 0}

    patterns = sql_like_prefixes_for_path_purge([raw_root])
    if not patterns:
        return {"success": False, "message": "No LIKE patterns for root.", "matched": 0}

    placeholders = " OR ".join(["file_path LIKE ?"] * len(patterns))
    sql = f"SELECT file_path FROM images WHERE {placeholders}"
    conn = get_connector()
    try:
        rows = conn.query(sql, tuple(patterns))
    except Exception as exc:
        return {"success": False, "message": str(exc), "matched": 0}

    to_remove: list[str] = []
    seen: set[str] = set()
    bad_segments: set[str] = set()
    examples_bad: list[str] = []
    examples_keep: list[str] = []

    for row in rows or []:
        fp = row.get("file_path") if isinstance(row, dict) else None
        if not fp or fp in seen:
            continue
        if not path_is_under_logical_roots(str(fp), roots):
            continue
        seen.add(str(fp))
        seg = first_segment_raw_under_logical_roots(str(fp), roots)
        if seg is None:
            to_remove.append(str(fp))
            if len(examples_bad) < 12:
                examples_bad.append(str(fp))
            continue
        if top_segment_allowed(seg, whitelist_lower=whitelist_lower, allow_re=allow_re):
            if len(examples_keep) < 8:
                examples_keep.append(str(fp))
            continue
        to_remove.append(str(fp))
        bad_segments.add(seg)
        if len(examples_bad) < 12:
            examples_bad.append(str(fp))

    lim = int(limit_images or 0)
    if lim > 0:
        to_remove = to_remove[:lim]

    out: dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        "logical_roots": sorted(roots),
        "root": raw_root,
        "allow_pattern": pat_str,
        "whitelist_lower": sorted(whitelist_lower),
        "matched": len(to_remove),
        "deleted": 0,
        "bad_top_segments_sample": sorted(bad_segments)[:40],
        "examples_remove": examples_bad,
        "examples_keep": examples_keep,
        "folder_cache": [],
    }

    if dry_run:
        out["message"] = f"Dry-run: {len(to_remove)} image path(s) would be removed."
        return out

    deleted = 0
    errors: list[str] = []
    for fp in to_remove:
        ok, msg = delete_image(fp, delete_related=True)
        if ok:
            deleted += 1
        else:
            errors.append(f"{fp}: {msg}")

    out["deleted"] = deleted
    out["errors"] = errors[:30]
    if errors:
        out["success"] = False
        out["message"] = f"Removed {deleted} image(s); {len(errors)} error(s)."
    else:
        out["message"] = f"Removed {deleted} image(s)."

    def _join_root_segment(root: str, seg: str) -> str:
        r = str(root).strip()
        s = str(seg).strip().replace("\\", "/")
        if r.startswith("/"):
            return posixpath.normpath(f"{r.rstrip('/')}/{s}")
        return os.path.normpath(os.path.join(r, s.replace("/", os.sep)))

    fc_results: list[dict[str, Any]] = []
    try:
        for seg in sorted(bad_segments):
            for root_var in _expand_path_variants_for_exclusion(raw_root):
                sub = _join_root_segment(root_var, seg)
                fc_results.append(delete_folder_cache_entry(sub, delete_descendants=True))
    except Exception as exc:
        fc_results.append({"success": False, "message": str(exc)})
    out["folder_cache"] = fc_results[:80]

    return out
