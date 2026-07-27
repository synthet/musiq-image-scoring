"""
Unified path conversion for Windows ↔ WSL ↔ Docker environments.

This module is the **single source of truth** for path format translation.
Other modules should import from here rather than re-implementing /mnt/ ↔ D:\\ logic.

API layers (bottom → top, each adds I/O):

1. **Pure converters** — no I/O, no imports beyond stdlib:
   ``to_windows``, ``to_wsl``, ``to_local``, ``normalize``,
   ``is_wsl_path``, ``is_windows_path``, ``all_variants``.

2. **Docker remap** — reads env vars once at import:
   ``remap_docker_project``.

3. **Filesystem resolver** — calls ``os.path.exists``:
   ``resolve_to_existing``.
"""

from __future__ import annotations

import os
import platform
import re

# ---------------------------------------------------------------------------
# Environment detection (cached at import time)
# ---------------------------------------------------------------------------

RUNTIME_OS: str = platform.system()  # "Windows", "Linux", "Darwin"

_WSL_MNT_RE = re.compile(r"^/mnt/([a-zA-Z])(?:/|$)")
_WIN_DRIVE_RE = re.compile(r"^([a-zA-Z]):[/\\]")
# Hybrid: D:/mnt/d/Photos/... — drive letter prefixed to a /mnt/ tail.
# After normalize() the path uses forward slashes only.
_HYBRID_RE = re.compile(r"^([A-Za-z]):/mnt/([A-Za-z])(?:/(.*))?$")
# Bare drive (no separator yet): "D:" or "d:"
_BARE_DRIVE_RE = re.compile(r"^([a-zA-Z]):$")
# Drive prefix optionally followed by tail. Matches "d:Photos" too (DOS
# drive-relative) — but we treat that the same as "d:/Photos" since the
# DB never stores drive-relative paths.
_DRIVE_PREFIX_RE = re.compile(r"^([a-zA-Z]):/?(.*)$")


# ---------------------------------------------------------------------------
# Private helpers — input tolerance
# ---------------------------------------------------------------------------

def _normalize_internal(path: object) -> str:
    """Bulletproof normalization to forward-slash canonical form.

    Handles arbitrary input:
    - ``None`` / non-strings → ``""``
    - Leading/trailing whitespace → stripped
    - All ``\\`` → ``/``
    - Runs of slashes (``//``, ``///``, …) → single ``/``
    - Trailing slash stripped, except for filesystem root ``/`` and drive
      root ``D:/``
    - Bare drive ``D:`` → ``D:/`` (canonical drive root)

    UNC paths (``\\\\server\\share``) lose the UNC marker after slash
    collapse — UNC is out of scope for this codebase.
    """
    if path is None:
        return ""
    s = str(path).strip()
    if not s:
        return ""
    s = s.replace("\\", "/")
    s = re.sub(r"/{2,}", "/", s)
    # Bare drive → drive root
    if _BARE_DRIVE_RE.match(s):
        return f"{s[0]}:/"
    # Strip trailing slash (preserve "/" root and "D:/" drive root)
    while len(s) > 1 and s.endswith("/"):
        if len(s) == 3 and s[1] == ":":
            break
        s = s[:-1]
    return s


def _strip_hybrid(path: str) -> str:
    """Collapse a hybrid ``D:/mnt/d/Photos`` to its WSL tail ``/mnt/d/Photos``.

    Assumes input is already normalized (forward slashes, collapsed runs).
    The WSL drive letter wins — the leading ``D:`` is treated as noise.
    """
    m = _HYBRID_RE.match(path)
    if not m:
        return path
    drive = m.group(2).lower()
    rest = m.group(3) or ""
    return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"


# ---------------------------------------------------------------------------
# 1. Pure converters (no I/O, no DB)
# ---------------------------------------------------------------------------

def is_wsl_path(path: str) -> bool:
    """True for ``/mnt/<letter>/...`` paths (any separator style)."""
    return bool(_WSL_MNT_RE.match(_normalize_internal(path)))


def is_windows_path(path: str) -> bool:
    """True for ``D:\\...`` / ``D:/...`` / ``D:`` paths."""
    n = _normalize_internal(path)
    return bool(_WIN_DRIVE_RE.match(n) or _BARE_DRIVE_RE.match(n))


def normalize(path: str) -> str:
    """Canonical forward-slash form for any input separator style.

    - Strips whitespace
    - Converts ``\\`` → ``/``
    - Collapses runs of ``/`` → single ``/``
    - Strips trailing ``/`` (preserves ``/`` and ``D:/``)
    - ``D:`` (bare drive) → ``D:/``

    Does **not** translate between Windows and WSL — use :func:`to_local`,
    :func:`to_windows`, or :func:`to_wsl` for that.
    """
    return _normalize_internal(path)


def to_windows(path: str) -> str | None:
    r"""Convert any path format to Windows backslash form (``D:\...``).

    Tolerant of arbitrary input: ``/``, ``\\``, ``//``, ``\\\\``, mixed
    separators, ``d:``, ``d:/``, ``d://``, ``D:\\Photos\\``,
    ``/mnt/d/Photos``, hybrid ``D:/mnt/d/Photos``.

    Returns ``None`` for empty / unparseable input.
    """
    if path is None or (isinstance(path, str) and not path.strip()):
        return None

    n = _strip_hybrid(_normalize_internal(path))
    if not n:
        return None

    # WSL form: /mnt/<letter>[/rest]
    if _WSL_MNT_RE.match(n):
        parts = n.split("/")
        # parts[0]="" parts[1]="mnt" parts[2]=<drive> parts[3:]=rest
        drive = parts[2].upper()
        rest = "\\".join(parts[3:])
        return f"{drive}:\\{rest}" if rest else f"{drive}:\\"

    # Drive-letter form: D:/... or D: or D:Photos (DOS drive-relative)
    m = _DRIVE_PREFIX_RE.match(n)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).lstrip("/")
        return f"{drive}:\\{rest.replace('/', chr(92))}" if rest else f"{drive}:\\"

    # No drive letter — Linux-style or relative; can't reach a Windows
    # filesystem root. Return with backslash separators for cosmetic
    # consistency, but the caller is probably misusing the API.
    return n.replace("/", "\\")


def to_wsl(path: str) -> str:
    """Convert any path format to WSL form (``/mnt/<lower>/...``).

    Tolerant of arbitrary input: ``D:\\Photos``, ``D:/Photos``, ``d:``,
    ``d://Photos``, hybrid ``D:/mnt/d/Photos``, already-WSL paths.

    Linux-style paths without a drive letter (``/home/user/...``) are
    returned normalized but otherwise unchanged.
    """
    if path is None:
        return ""

    n = _strip_hybrid(_normalize_internal(path))
    if not n:
        return ""

    # Already WSL → return normalized form
    if _WSL_MNT_RE.match(n) or n == "/mnt":
        return n

    # Drive-letter form → /mnt/<lower>/rest
    m = _DRIVE_PREFIX_RE.match(n)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).lstrip("/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"

    return n


def to_local(path: str) -> str:
    """Convert any path to the local OS format (forward-slash on Windows).

    - On Windows: returns drive-letter form with forward slashes
      (``/mnt/d/Photos`` → ``D:/Photos``).
    - On Linux: returns WSL form (``D:\\Photos`` → ``/mnt/d/Photos``).
    - Other OS: returns the normalized form.

    Paths that don't carry a convertible drive letter are returned in
    normalized form unchanged.
    """
    if path is None:
        return ""
    n = _strip_hybrid(_normalize_internal(path))
    if not n:
        return ""

    if RUNTIME_OS == "Windows":
        if _WSL_MNT_RE.match(n):
            parts = n.split("/")
            drive = parts[2].upper()
            rest = "/".join(parts[3:])
            return f"{drive}:/{rest}" if rest else f"{drive}:/"
        return n  # already drive-letter or Linux-style
    if RUNTIME_OS == "Linux":
        return to_wsl(n)
    return n


def db_form(path: str) -> str:
    """Return the canonical DB-storage form (WSL) for any input.

    The pipeline historically registers folders from WSL/Linux, so the
    DB stores ``/mnt/<lower>/...``. Use this before any
    ``WHERE path = ?`` lookup or insert.
    """
    return to_wsl(path)


def db_lookup_variants(path: str) -> list[str]:
    """De-duplicated list of forms suitable for ``WHERE path IN (?, ?, …)``.

    Covers the common storage formats: WSL canonical, drive-letter forward,
    drive-letter backslash. Use this when the storage format is uncertain
    (e.g. a folder registered on Windows alongside ones registered in WSL).
    """
    if path is None or (isinstance(path, str) and not path.strip()):
        return []
    seen: set[str] = set()
    out: list[str] = []

    def _add(p: str | None) -> None:
        if not p:
            return
        if p in seen:
            return
        seen.add(p)
        out.append(p)

    _add(to_wsl(path))
    w = to_windows(path)
    _add(w)
    if w:
        _add(w.replace("\\", "/"))  # forward-slash drive form
    return out


def all_variants(path: str) -> list[str]:
    """Return de-duplicated list of path variants (normalized, Windows, WSL).

    Useful for SQL ``LIKE`` matching or scope resolution where the storage
    format is unknown.
    """
    if not path:
        return []
    seen: set[str] = set()
    out: list[str] = []

    def _add(p: str | None) -> None:
        if p and p not in seen:
            seen.add(p)
            out.append(p)

    n = normalize(path)
    _add(n)
    _add(to_windows(path))
    w = to_wsl(path)
    _add(w)
    return out


# ---------------------------------------------------------------------------
# 2. Docker remap (reads env vars; no filesystem I/O beyond that)
# ---------------------------------------------------------------------------

def remap_docker_project(path: str) -> str | None:
    """Remap a host-side project path to the local (container) project root.

    When running inside Docker, paths stored in the database refer to the host
    filesystem (e.g. ``/mnt/d/Projects/image-scoring-backend/thumbnails/...``
    or ``D:\\Projects\\image-scoring-backend\\thumbnails\\...``) and do not exist
    inside the container.

    Returns the remapped path, or ``None`` when no env vars are set or no
    prefix matches.
    """
    host_wsl = os.environ.get("IMAGE_SCORING_HOST_PROJECT_WSL", "").strip()
    host_win = os.environ.get("IMAGE_SCORING_HOST_PROJECT_WIN", "").strip()
    if not host_wsl and not host_win:
        return None

    from modules.config import BASE_DIR
    local_root = str(BASE_DIR)

    p_norm = path.replace("\\", "/").rstrip("/")
    for prefix in (host_wsl, host_win):
        if not prefix:
            continue
        prefix_norm = prefix.replace("\\", "/").rstrip("/")
        if not prefix_norm:
            continue
        # Skip when the host root already matches the local root
        if prefix_norm == local_root.replace("\\", "/").rstrip("/"):
            continue
        if p_norm == prefix_norm:
            return local_root
        prefix_with_sep = prefix_norm + "/"
        if p_norm.startswith(prefix_with_sep):
            tail = p_norm[len(prefix_with_sep):]
            return os.path.join(local_root, *tail.split("/"))

    return None


# ---------------------------------------------------------------------------
# 3. Filesystem resolver (calls os.path.exists)
# ---------------------------------------------------------------------------

def resolve_to_existing(path: str) -> str | None:
    """Try path variants and return the first that exists on disk, or ``None``.

    Resolution order depends on the runtime OS:
    - **Windows**: tries ``to_local()`` (drive-letter) first, then raw, then WSL
    - **Linux**: tries raw/WSL first, then ``to_local()``

    Also applies Docker project remap when env vars are set.
    """
    if not path:
        return None

    s = str(path).strip()
    if not s:
        return None

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(p: str | None) -> None:
        if p is None:
            return
        q = str(p).strip()
        if not q or q in seen:
            return
        seen.add(q)
        candidates.append(q)

    n = normalize(s)

    # Docker remap gets highest priority
    _add(remap_docker_project(s))
    _add(remap_docker_project(n))

    if RUNTIME_OS == "Windows":
        # On Windows, WSL /mnt/ paths don't exist on NTFS — convert first
        _add(to_local(n))
        _add(to_local(s))
        _add(n)
        _add(s)
    else:
        _add(n)
        _add(s)
        # Try Windows→WSL conversion if input looks like a Windows path
        if is_windows_path(s):
            _add(to_wsl(s))
        _add(to_local(s))
        _add(to_local(n))

    for cand in candidates:
        expanded = os.path.expanduser(os.path.expandvars(cand))
        try:
            norm = os.path.normpath(expanded)
        except (OSError, ValueError):
            norm = expanded
        if os.path.exists(norm):
            return norm

    return None
