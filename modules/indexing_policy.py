"""
Policy for which files are discovered, indexed, and processed.

When ``indexing.nikon_nef_only`` is true in config.json:

- Indexing and scope preview count only ``.nef`` files (case-insensitive).
- Scoring disk walks use the same extension set.
- Metadata, tagging, clustering, and selection skip non-NEF rows already in the DB.

``indexing.excluded_paths`` (list of directory prefixes in config or environment.json):
those subtrees are skipped during indexing, scope disk preview counts, and scoring
directory walks (paths still in the DB are unchanged until explicitly purged).

XMP sidecars and JPEG previews are not registered as separate ``images`` rows; they
remain on disk and are read by metadata/thumbnail code for NEF paths.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

# When policy is off, match ``indexing_runner.SUPPORTED_EXTENSIONS``.
DEFAULT_INDEXING_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".tiff",
        ".tif",
        ".nef",
        ".nrw",
        ".arw",
        ".cr2",
        ".cr3",
        ".dng",
    }
)


def nikon_nef_only_enabled() -> bool:
    from modules import config

    return bool(config.get_config_value("indexing.nikon_nef_only", default=False))


def discovery_extensions() -> frozenset[str]:
    """Extensions for filesystem walks (indexing, scoring batch, scope preview)."""
    if nikon_nef_only_enabled():
        return frozenset({".nef"})
    return DEFAULT_INDEXING_EXTENSIONS


def passes_nikon_nef_policy(file_path: str | None, file_type: str | None = None) -> bool:
    """Whether a DB row or path should be processed when NEF-only mode is on."""
    if not nikon_nef_only_enabled():
        return True
    ft = (file_type or "").strip().lower()
    if ft == "nef":
        return True
    fp = (file_path or "").lower()
    return fp.endswith(".nef")


def _row_file_path_type(row: Any) -> tuple[str | None, str | None]:
    try:
        fp = row["file_path"]
    except Exception:
        fp = getattr(row, "file_path", None) if row is not None else None
    try:
        ft = row["file_type"]
    except Exception:
        ft = getattr(row, "file_type", None) if row is not None else None
    return fp, ft


def filter_image_rows_for_nef_policy(rows: Sequence[Any] | None) -> list[Any]:
    """Drop non-NEF rows when ``indexing.nikon_nef_only`` is enabled."""
    if not rows:
        return []
    if not nikon_nef_only_enabled():
        return list(rows)
    out: list[Any] = []
    for r in rows:
        fp, ft = _row_file_path_type(r)
        if passes_nikon_nef_policy(fp, ft):
            out.append(r)
    return out


def indexing_excluded_paths_raw() -> list[str]:
    """Raw ``indexing.excluded_paths`` entries from merged config."""
    from modules import config

    raw = config.get_config_value("indexing.excluded_paths", default=[]) or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def _expand_path_variants_for_exclusion(path: str) -> list[str]:
    """Normpath variants (as-given, local OS, WSL) for one configured root."""
    from modules import utils

    p = os.path.normpath(os.path.expanduser(os.path.expandvars(path.strip())))
    seen: set[str] = set()
    variants: list[str] = []

    def add(q: str) -> None:
        try:
            n = os.path.normpath(q)
        except (OSError, ValueError):
            n = q
        if n not in seen:
            seen.add(n)
            variants.append(n)

    add(p)
    add(utils.convert_path_to_local(p))
    wsl = utils.convert_path_to_wsl(p)
    if wsl != p:
        add(wsl)
    add(p.replace("\\", "/"))
    return variants


def _canonical_logical_path(p: str) -> str:
    """Lowercase path with forward slashes for stable prefix tests (Windows + WSL + DB).

    Avoids ``os.path.normpath`` here so ``/mnt/d/...`` is not mangled on Windows.
    """
    s = str(p).strip().replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    while len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s.lower()


def indexing_excluded_logical_roots() -> frozenset[str]:
    """All exclusion roots as canonical logical paths."""
    out: set[str] = set()
    for raw in indexing_excluded_paths_raw():
        for v in _expand_path_variants_for_exclusion(raw):
            c = _canonical_logical_path(v)
            if c and c != ".":
                out.add(c)
    return frozenset(out)


def path_is_indexing_excluded(path: str | None) -> bool:
    """True if ``path`` is exactly an excluded root or inside an excluded subtree."""
    if not path or not str(path).strip():
        return False
    k = _canonical_logical_path(path)
    if not k or k == ".":
        return False
    for r in indexing_excluded_logical_roots():
        if k == r or k.startswith(r + "/"):
            return True
    return False


def prune_indexing_excluded_walk_dirs(root: str, dirs: list[str]) -> None:
    """Mutate ``dirs`` in place for ``os.walk``: drop children whose full path is excluded."""
    i = 0
    while i < len(dirs):
        full = os.path.join(root, dirs[i])
        if path_is_indexing_excluded(full):
            dirs.pop(i)
            continue
        i += 1


def sql_like_prefixes_for_path_purge(user_prefixes: list[str]) -> list[str]:
    """
    Build DISTINCT non-empty LIKE patterns (both slash styles) for DB path cleanup.

    Patterns are broad (``prefix%``); callers must refine with
    ``path_is_under_logical_roots`` so ``Lightroom`` does not match ``LightroomBackup``.
    """
    likes: set[str] = set()
    for raw in user_prefixes:
        if not isinstance(raw, str) or not raw.strip():
            continue
        for v in _expand_path_variants_for_exclusion(raw.strip()):
            for sep_style in (v.replace("\\", "/"), v.replace("/", "\\")):
                p = sep_style.rstrip("/\\")
                if not p:
                    continue
                likes.add(p + "%")
    return sorted(likes)


def logical_roots_from_user_prefixes(user_prefixes: list[str]) -> frozenset[str]:
    """Canonical logical roots for strict subtree membership (purge / reports)."""
    roots: set[str] = set()
    for raw in user_prefixes:
        if isinstance(raw, str) and raw.strip():
            for v in _expand_path_variants_for_exclusion(raw.strip()):
                c = _canonical_logical_path(v)
                if c and c != ".":
                    roots.add(c)
    return frozenset(roots)


def path_is_under_logical_roots(path: str | None, logical_roots: frozenset[str]) -> bool:
    """True if ``path`` is exactly one of the roots or strictly under it (path segment boundary)."""
    if not path or not logical_roots:
        return False
    k = _canonical_logical_path(path)
    if not k or k == ".":
        return False
    for r in logical_roots:
        if not r:
            continue
        if k == r or k.startswith(r + "/"):
            return True
    return False
