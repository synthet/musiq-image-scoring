import hashlib
import io
import logging
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)
_HOST_THUMB_WARN_EMITTED = False

# Anchor to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
THUMB_DIR = str(PROJECT_ROOT / "thumbnails")
MAX_SIZE = (512, 512)

def ensure_thumb_dir():
    os.makedirs(THUMB_DIR, exist_ok=True)


def canonical_thumbnails_dir() -> str:
    """Absolute backend ``thumbnails/`` root. Use instead of ``os.path.abspath("thumbnails")`` (cwd-dependent)."""
    return THUMB_DIR


def collapse_malformed_thumbnail_segments(path: str) -> str:
    """
    Remove erroneous ``.../thumbnails/app/thumbnails/...`` segments (static SPA / cwd-relative leaks).
    """
    if not path:
        return path
    s = str(path)
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"(?i)thumbnails[/\\](?:static[/\\])?app[/\\]thumbnails", "thumbnails", s)
    return s


def remap_container_thumbnail_path_to_host(path: str) -> str | None:
    """
    Map Docker / static-UI roots (``/app/thumbnails/...``, ``\\app\\thumbnails\\...``) to an absolute
    path under :data:`THUMB_DIR`. Returns None if *path* does not use those synthetic roots.

    This prevents persisting container-relative paths when the DB is used from WSL/Windows with a
    host-mounted repo (canonical: ``/mnt/<drive>/.../thumbnails/...`` + matching ``<Drive>:\\...``).
    """
    if not path or not str(path).strip():
        return None
    s = collapse_malformed_thumbnail_segments(str(path).strip()).replace("\\", "/")
    # Remove any extra leading slashes so logic handles //app/thumbnails/ safely
    s = re.sub(r"^/+", "/", s)
    m = re.search(r"(?i)(?:^|/)(?:static/)?app/thumbnails/(.+)$", s)
    if not m:
        return None
    rel = m.group(1).strip("/")
    if not rel:
        return None
    return os.path.normpath(os.path.join(THUMB_DIR, rel.replace("/", os.sep)))


def _path_is_under(child: str, parent: str) -> bool:
    """True if *child* is *parent* or a path beneath it (best-effort; drive/OS quirks)."""
    try:
        c = os.path.abspath(child)
        p = os.path.abspath(parent)
        c_n = os.path.normcase(c)
        p_n = os.path.normcase(p)
        if c_n == p_n:
            return True
        sep = os.sep
        if not p_n.endswith(sep):
            p_n = p_n + sep
        return c_n.startswith(p_n)
    except (OSError, ValueError):
        return False


def _thumbnail_db_use_host_project_remap(proj: str) -> bool:
    """
    ``paths.host_project_root_*`` / ``IMAGE_SCORING_HOST_PROJECT_*`` remap on-disk paths to host
    DB strings only in container-style layouts.

    Applying remap on a normal WSL/Windows checkout while those vars are set (e.g. leaked from
    ``.env``) would rewrite every thumbnail to the wrong project prefix.
    """
    p = os.path.normpath(str(proj)).replace("\\", "/")
    if p == "/app" or p.startswith("/app/"):
        return True
    v = (os.environ.get("DOCKER_CONTAINER") or "").strip().lower()
    return v in ("1", "true", "yes")


def _host_project_roots_for_db() -> tuple[str, str]:
    """
    Host-side project roots for DB thumbnail strings. Used together with
    :func:`_thumbnail_db_use_host_project_remap` so native WSL/Windows runs are not rewritten
    when these vars are set (e.g. from a Docker ``.env``).

    Env (override config): ``IMAGE_SCORING_HOST_PROJECT_WSL``, ``IMAGE_SCORING_HOST_PROJECT_WIN``
    Config: ``paths.host_project_root_wsl``, ``paths.host_project_root_win``
    """
    wsl_h = (os.environ.get("IMAGE_SCORING_HOST_PROJECT_WSL") or "").strip()
    win_h = (os.environ.get("IMAGE_SCORING_HOST_PROJECT_WIN") or "").strip()
    if not wsl_h or not win_h:
        from modules.config import get_config_value

        if not wsl_h:
            v = get_config_value("paths.host_project_root_wsl")
            wsl_h = (str(v).strip() if v is not None else "") or ""
        if not win_h:
            v = get_config_value("paths.host_project_root_win")
            win_h = (str(v).strip() if v is not None else "") or ""
    if wsl_h and not win_h:
        win_h = thumb_path_to_win(wsl_h) or ""
    if win_h and not wsl_h:
        wsl_h = thumb_path_to_wsl(win_h) or ""
    return wsl_h, win_h


def _db_pair_under_host_project(rel_posix: str) -> tuple[str, str]:
    """Build DB columns from a path relative to project root (POSIX slashes)."""
    rel_posix = rel_posix.replace("\\", "/").strip("/")
    wsl_h, win_h = _host_project_roots_for_db()
    wsl_base = wsl_h.rstrip("/").replace("\\", "/")
    win_base = win_h.rstrip("\\/")
    tp = f"{wsl_base}/{rel_posix}".replace("//", "/")
    tw = win_base + "\\" + rel_posix.replace("/", "\\")
    return tp, tw


def _rel_posix_under_project_root(path_any: str) -> str | None:
    """
    If *path_any* resolves under :data:`PROJECT_ROOT`, return the relative path with POSIX slashes.
    Used to map on-disk paths (including Docker ``/app/...`` when the repo root is ``/app``) to
    ``thumbnails/...`` for host DB columns — without hardcoding drive letters or ``/mnt/d/...``.
    """
    s = str(path_any).strip()
    if not s:
        return None
    try:
        root = os.path.abspath(str(PROJECT_ROOT))
        candidate = os.path.abspath(s)
        rel = os.path.relpath(candidate, root)
    except (OSError, ValueError):
        return None
    if rel.startswith(".."):
        return None
    return rel.replace("\\", "/")


def _synthetic_app_thumbnail_db_pair(
    tp: str | None, tw: str | None
) -> tuple[str | None, str | None]:
    """
    If columns still reference ``.../app/thumbnails/...`` and host project roots are configured,
    rewrite to canonical host WSL + Windows paths (thumbnail file may be missing on disk).
    """
    wsl_h, win_h = _host_project_roots_for_db()
    if not wsl_h or not win_h:
        return None, None
    rel = None
    for p in (tp, tw):
        if not p:
            continue
        s = collapse_malformed_thumbnail_segments(str(p).strip()).replace("\\", "/")
        s = re.sub(r"^/+", "/", s)
        m = re.search(r"(?i)(?:^|/)(?:static/)?app/thumbnails/(.+)$", s)
        if m:
            rel = m.group(1).strip("/")
            break
    if not rel:
        return None, None
    return _db_pair_under_host_project(f"thumbnails/{rel}")


def _resolve_thumbnail_filesystem_path(
    thumbnail_path: str | None,
    thumbnail_path_win: str | None,
) -> str | None:
    """Return absolute path to an existing thumbnail file, or None."""
    candidates: list[str] = []
    for raw in (thumbnail_path, thumbnail_path_win):
        if not raw or not str(raw).strip():
            continue
        c = collapse_malformed_thumbnail_segments(str(raw).strip())
        candidates.append(c)
        p = os.path.normpath(os.path.expanduser(c))
        if os.path.isabs(p) and os.path.isfile(p):
            return p

    for c in candidates:
        rel = c.replace("\\", "/").strip("/")
        for pref in (
            "../image-scoring-backend/thumbnails/",
            "../../image-scoring-backend/thumbnails/",
            "image-scoring-backend/thumbnails/",
            "static/app/thumbnails/",
            "app/thumbnails/",
            "thumbnails/",
        ):
            pl = rel.lower()
            p_low = pref.lower()
            if pl.startswith(p_low):
                rel = rel[len(pref) :].lstrip("/")
                break
        joined = os.path.normpath(os.path.join(THUMB_DIR, rel.replace("/", os.sep)))
        if os.path.isfile(joined):
            return joined

    for c in candidates:
        m = re.search(r"([a-f0-9]{32}\.(?:jpg|jpeg))\s*$", c.replace("\\", "/"), re.IGNORECASE)
        if not m:
            continue
        name = m.group(1)
        pref = name[:2]
        nested = os.path.join(THUMB_DIR, pref, name)
        if os.path.isfile(nested):
            return nested
        flat = os.path.join(THUMB_DIR, name)
        if os.path.isfile(flat):
            return flat

    return None


def database_thumbnail_pair_from_fs_path(abs_path: str) -> tuple[str, str]:
    """Build (thumbnail_path, thumbnail_path_win) for DB columns from an on-disk thumbnail path."""
    raw = str(abs_path).strip()
    if not raw:
        return "", ""
    try:
        resolved = os.path.normpath(os.path.abspath(os.path.realpath(raw)))
    except OSError:
        resolved = os.path.normpath(os.path.abspath(raw))
    try:
        proj = os.path.normpath(os.path.abspath(os.path.realpath(str(PROJECT_ROOT))))
    except OSError:
        proj = os.path.normpath(os.path.abspath(str(PROJECT_ROOT)))

    wsl_h, win_h = _host_project_roots_for_db()
    if (
        wsl_h
        and win_h
        and _thumbnail_db_use_host_project_remap(proj)
        and _path_is_under(resolved, proj)
    ):
        try:
            rel = os.path.relpath(resolved, proj).replace("\\", "/")
        except ValueError:
            rel = ""
        if rel and not rel.startswith(".."):
            return _db_pair_under_host_project(rel)

    tp = thumb_path_to_wsl(resolved)
    tw = thumb_path_to_win(resolved)
    blob = ((tp or "") + (tw or "")).replace("\\", "/").lower()
    if "/app/thumbnails" in blob:
        global _HOST_THUMB_WARN_EMITTED
        if not _HOST_THUMB_WARN_EMITTED and not (wsl_h and win_h):
            _HOST_THUMB_WARN_EMITTED = True
            logger.warning(
                "Thumbnail DB paths resolve under /app/...; set IMAGE_SCORING_HOST_PROJECT_WSL and "
                "IMAGE_SCORING_HOST_PROJECT_WIN (or paths.host_project_root_wsl / paths.host_project_root_win "
                "in config.json) so the database stores host paths such as /mnt/d/... and D:\\..."
            )
    return tp, tw


def normalize_stored_thumbnail_pair(
    thumbnail_path: str | None,
    thumbnail_path_win: str | None,
) -> tuple[str | None, str | None]:
    """
    Sanitize thumbnail DB columns: collapse bad segments, remap Docker ``/app/thumbnails/...`` to
    :data:`THUMB_DIR`, resolve to a real file under THUMB_DIR when possible.

    When ``IMAGE_SCORING_HOST_PROJECT_*`` or ``paths.host_project_root_*`` is set, persisted paths
    use the host project root (e.g. ``/mnt/d/Projects/...`` and ``D:\\Projects\\...``) instead of
    ``/app/...`` inside the container.
    """
    def _prepare_column(val: str | None) -> str | None:
        if not val or not str(val).strip():
            return None
        v = collapse_malformed_thumbnail_segments(str(val).strip())
        host = remap_container_thumbnail_path_to_host(v)
        return host if host else v

    tp_p = _prepare_column(thumbnail_path)
    tw_p = _prepare_column(thumbnail_path_win)

    resolved = _resolve_thumbnail_filesystem_path(tp_p, tw_p)
    if resolved:
        return database_thumbnail_pair_from_fs_path(resolved)

    thumb_root = os.path.abspath(THUMB_DIR)
    for cand in (tp_p, tw_p):
        if not cand:
            continue
        try:
            abs_c = os.path.abspath(cand)
        except OSError:
            continue
        if _path_is_under(abs_c, thumb_root):
            return database_thumbnail_pair_from_fs_path(abs_c)

    if not tp_p and not tw_p:
        return None, None
    syn_tp, syn_tw = _synthetic_app_thumbnail_db_pair(tp_p, tw_p)
    if syn_tp and syn_tw:
        return syn_tp, syn_tw
    if tp_p and tw_p:
        return tp_p, tw_p
    if tp_p:
        return tp_p, thumb_path_to_win(tp_p)
    return thumb_path_to_wsl(tw_p), tw_p


def thumbnail_pair_needs_repair(
    thumbnail_path: str | None,
    thumbnail_path_win: str | None,
) -> bool:
    """
    True if DB columns should be rewritten via normalize_stored_thumbnail_pair.

    Canonical storage (host dev / WSL + Windows):
    - thumbnail_path: absolute WSL, e.g. /mnt/d/.../thumbnails/ab/abcdef....jpg
    - thumbnail_path_win: matching Windows path, e.g. D:\\...\\thumbnails\\ab\\....

    /app/thumbnails/... is container-relative (wrong in a host-mounted DB). Pairs should
    include both columns when possible.
    """
    tp = str(thumbnail_path).strip() if thumbnail_path else ""
    tw = str(thumbnail_path_win).strip() if thumbnail_path_win else ""

    if not tp and not tw:
        return False

    blob = f"{tp} {tw}".lower().replace("\\", "/")

    if "/app/thumbnails" in blob:
        return True
    if "thumbnails/app/thumbnails" in blob or "static/app/thumbnails" in blob:
        return True
    tp_n = tp.replace("\\", "/").lower()
    tw_n = tw.replace("\\", "/").lower()
    if "../image-scoring-backend/thumbnails" in tp_n or "../image-scoring/thumbnails" in tp_n:
        return True
    if "../image-scoring-backend/thumbnails" in tw_n or "../image-scoring/thumbnails" in tw_n:
        return True

    for p in (tp, tw):
        if not p:
            continue
        if collapse_malformed_thumbnail_segments(p) != p:
            return True

    if (tp and not tw) or (tw and not tp):
        return True

    return False


# EXIF Orientation tag (TIFF / EXIF IFD).
_EXIF_ORIENTATION = 0x0112


def read_orientation(path: str) -> int | None:
    """
    Read numeric EXIF Orientation from *path* via exiftool (``-n -Orientation -s3``).

    Returns an int in 1..8, or None if exiftool is missing, the tag is absent, or parsing fails.
    """
    if not path or not shutil.which("exiftool"):
        return None
    try:
        result = subprocess.run(
            ["exiftool", "-n", "-Orientation", "-s3", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        raw = (result.stdout or "").strip()
        if not raw:
            return None
        value = int(raw.splitlines()[0].strip())
        if 1 <= value <= 8:
            return value
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, OSError):
        return None
    return None


def bake_orientation(img: Image.Image, source_path: str) -> Image.Image:
    """
    Apply EXIF Orientation so returned pixels are upright (Orientation cleared).

    Prefer Orientation already on *img* (embedded JPEG). If missing or 1, fall back to
    Orientation from *source_path* (typically the RAW file — ``exiftool -b`` extracts often
    omit the tag). Mirrors gallery ``nefExtractor`` stamping NEF Orientation onto extracts.
    """
    from PIL import ImageOps

    image_exif = img.getexif()
    existing = image_exif.get(_EXIF_ORIENTATION)
    if existing in (None, 0, 1):
        source_orient = read_orientation(source_path)
        if source_orient is not None and source_orient >= 2:
            image_exif[_EXIF_ORIENTATION] = source_orient

    return ImageOps.exif_transpose(img)


def extract_embedded_jpeg(image_path: str, min_size: int = 100) -> Image.Image | None:
    """
    Extract embedded JPEG preview from RAW file.
    Tries ExifTool first (robust for modern formats like Z8/Z9 HE*), then dcraw (fast).
    Returns PIL Image or None if extraction fails.
    
    Args:
        image_path: Path to RAW file
        min_size: Minimum file size in bytes to accept (default 100 bytes)
    
    Returns:
        PIL Image if successful, None otherwise
    """
    image_path_str = str(image_path)
    
    # Try ExifTool first (most robust for modern Nikon formats)
    if shutil.which("exiftool"):
        try:
            # Try -JpgFromRaw first (full-size embedded JPEG)
            cmd = ['exiftool', '-b', '-JpgFromRaw', image_path_str]
            result = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            
            if result.returncode == 0 and len(result.stdout) > min_size:
                if result.stdout.startswith(b'\xff\xd8'):  # JPEG header
                    try:
                        img = Image.open(io.BytesIO(result.stdout))
                        img.load()  # Verify validity
                        return img
                    except Exception:
                        pass
            
            # Try -PreviewImage if JpgFromRaw fails or is missing
            cmd = ['exiftool', '-b', '-PreviewImage', image_path_str]
            result = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            
            if result.returncode == 0 and len(result.stdout) > min_size:
                if result.stdout.startswith(b'\xff\xd8'):  # JPEG header
                    try:
                        img = Image.open(io.BytesIO(result.stdout))
                        img.load()  # Verify validity
                        return img
                    except Exception:
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
    
    # Fallback to dcraw -e (fast embedded thumbnail extraction)
    if shutil.which("dcraw"):
        try:
            cmd = ["dcraw", "-e", "-c", image_path_str]
            res = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            if res.returncode == 0 and len(res.stdout) > min_size:
                if res.stdout.startswith(b'\xff\xd8'):  # JPEG header
                    try:
                        img = Image.open(io.BytesIO(res.stdout))
                        img.load()  # Verify validity
                        return img
                    except Exception:
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
    
    return None


# Extensions treated as camera RAW for ML inference (same set as generate_thumbnail).
_RAW_EXT_ML = frozenset({".nef", ".nrw", ".cr2", ".dng", ".arw", ".orf", ".cr3", ".rw2"})


def open_image_for_ml(read_path: str) -> Image.Image:
    """
    Open a file as PIL for ML inference (CLIP, BLIP, BioCLIP, etc.).

    Raster formats use :func:`PIL.Image.open` directly. RAW files use the same decode
    chain as thumbnail generation (embedded JPEG → rawpy → ImageMagick) so tagging
    and similar jobs work when no thumbnail row/path exists yet.
    """
    read_path = str(read_path)
    ext = Path(read_path).suffix.lower()
    if ext not in _RAW_EXT_ML:
        return Image.open(read_path)

    img = extract_embedded_jpeg(read_path, min_size=1000)
    if img is None:
        try:
            import rawpy

            with rawpy.imread(read_path) as raw:
                rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                img = Image.fromarray(rgb)
        except ImportError:
            pass
        except Exception:
            pass
    if img is None and shutil.which("magick"):
        try:
            cmd = ["magick", read_path, "-resize", "2048x2048>", "jpeg:-"]
            res = subprocess.run(cmd, capture_output=True, text=False, timeout=60)
            if res.returncode == 0 and len(res.stdout) > 100 and res.stdout.startswith(b"\xff\xd8"):
                img = Image.open(io.BytesIO(res.stdout))
                img.load()
        except Exception:
            pass
    if img is None:
        from PIL import UnidentifiedImageError

        raise UnidentifiedImageError(f"cannot identify or decode RAW image file {read_path!r}")
    return img


def _thumb_hash(image_path):
    return hashlib.md5(str(image_path).encode('utf-8')).hexdigest()


def get_thumb_path(image_path):
    """
    Returns the expected path of the thumbnail for a given image.
    Uses MD5 of the path with a 2-char prefix subdirectory (git-style).
    Layout: thumbnails/{hash[:2]}/{hash}.jpg
    Falls back to legacy flat path if it exists and nested does not.
    """
    path_hash = _thumb_hash(image_path)
    prefix = path_hash[:2]

    nested = os.path.join(THUMB_DIR, prefix, f"{path_hash}.jpg")
    if os.path.exists(nested):
        return nested

    legacy = os.path.join(THUMB_DIR, f"{path_hash}.jpg")
    if os.path.exists(legacy):
        return legacy

    subdir = os.path.join(THUMB_DIR, prefix)
    os.makedirs(subdir, exist_ok=True)
    return nested


def thumb_path_to_win(wsl_path):
    """Deterministic WSL-to-Windows conversion for thumbnail paths."""
    if not wsl_path:
        return None
    p = wsl_path.replace("\\", "/")

    wsl_h, win_h = _host_project_roots_for_db()
    try:
        proj = os.path.normpath(os.path.abspath(str(PROJECT_ROOT)))
    except OSError:
        proj = ""
    rel = _rel_posix_under_project_root(p)
    if (
        rel is not None
        and wsl_h
        and win_h
        and _thumbnail_db_use_host_project_remap(proj)
    ):
        _, tw = _db_pair_under_host_project(rel)
        return tw

    syn_tp, syn_tw = _synthetic_app_thumbnail_db_pair(p, None)
    if syn_tw:
        return syn_tw

    m = re.match(r"^/mnt/([a-zA-Z])/(.*)", p)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"
    return p.replace("/", "\\")


def thumb_path_to_wsl(win_path):
    """Deterministic Windows-to-WSL conversion for thumbnail paths."""
    if not win_path:
        return None

    p = win_path.replace("\\", "/")

    wsl_h, win_h = _host_project_roots_for_db()
    try:
        proj = os.path.normpath(os.path.abspath(str(PROJECT_ROOT)))
    except OSError:
        proj = ""
    rel = _rel_posix_under_project_root(p)
    if (
        rel is not None
        and wsl_h
        and win_h
        and _thumbnail_db_use_host_project_remap(proj)
    ):
        twp, _ = _db_pair_under_host_project(rel)
        return twp

    syn_tp, _ = _synthetic_app_thumbnail_db_pair(p, None)
    if syn_tp:
        return syn_tp

    m = re.match(r"^([a-zA-Z]):[\\/](.*)", p)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return win_path.replace("\\", "/")


def get_thumb_wsl(row):
    """
    Return the WSL/Linux thumbnail path from a DB row.
    Use this in code that runs inside WSL (Gradio server, ML inference, scoring).
    Falls back to converting thumbnail_path_win if thumbnail_path is empty.
    """
    wsl = _row_val(row, 'thumbnail_path')
    if wsl:
        return wsl
    win = _row_val(row, 'thumbnail_path_win')
    return thumb_path_to_wsl(win) if win else None


def get_thumb_win(row):
    """
    Return the native Windows thumbnail path from a DB row.
    Use this in code that runs on native Windows (Windows-only scripts, native UI).
    Falls back to converting thumbnail_path if thumbnail_path_win is empty.
    """
    win = _row_val(row, 'thumbnail_path_win')
    if win:
        return win
    wsl = _row_val(row, 'thumbnail_path')
    return thumb_path_to_win(wsl) if wsl else None


def get_local_thumb(row):
    """
    Auto-detect platform and return the appropriate thumbnail path.
    Prefer get_thumb_wsl() or get_thumb_win() for explicit intent.
    """
    if platform.system() == 'Windows':
        return get_thumb_win(row)
    return get_thumb_wsl(row)


def _row_val(row, col_name):
    """Read a column from a DB row (dict, Row, or keys()-supporting object)."""
    try:
        if hasattr(row, 'get'):
            return row.get(col_name)
        if hasattr(row, 'keys') and col_name in row.keys():
            return row[col_name]
    except Exception:
        pass
    return None

def generate_thumbnail(image_path, source_path=None):
    """
    Generates a thumbnail for the image if it doesn't exist.
    Returns the path to the thumbnail.

    For RAW files, prioritizes fast embedded JPEG extraction:
    ExifTool → dcraw (embedded) → rawpy (full decode) → ImageMagick

    Args:
        image_path: Logical path (e.g. DB ``file_path``) — used for thumbnail hash / layout.
        source_path: If set, read pixel data from this filesystem path; defaults to *image_path*.
          Use when *image_path* is a Windows path string but the script runs under WSL.
    """
    read_path = source_path if source_path is not None else image_path
    thumb_path = get_thumb_path(image_path)

    if os.path.exists(thumb_path):
        return thumb_path

    try:
        # Check if RAW file
        is_raw = Path(read_path).suffix.lower() in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']

        if is_raw:
            img = None

            # Priority 1: Extract embedded JPEG (fast - ExifTool or dcraw)
            img = extract_embedded_jpeg(read_path, min_size=1000)

            # Priority 2: Full RAW decode with rawpy (slow but high quality)
            if img is None:
                try:
                    import rawpy
                    with rawpy.imread(str(read_path)) as raw:
                        rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                        img = Image.fromarray(rgb)
                except ImportError:
                    pass  # rawpy not available
                except Exception:
                    pass  # rawpy failed (e.g., Z8 HE* files)

            # Priority 3: ImageMagick as last resort
            if img is None:
                if shutil.which("magick"):
                    # ImageMagick can write directly to output path
                    cmd = ["magick", str(read_path), "-resize", "512x512", "-quality", "85", thumb_path]
                    res = subprocess.run(cmd, capture_output=True, timeout=30)
                    if res.returncode == 0 and os.path.exists(thumb_path):
                        return thumb_path

                # All methods failed
                raise Exception("All RAW conversion methods failed for thumbnail generation")
        else:
            # Standard image handling (non-RAW)
            img = Image.open(read_path)

        # Process and save thumbnail
        with img:
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            img.thumbnail(MAX_SIZE)
            img.save(thumb_path, "JPEG", quality=85)

            # Copy EXIF orientation from original
            if is_raw and shutil.which("exiftool"):
                cmd = ["exiftool", "-TagsFromFile", str(read_path), "-Orientation", "-overwrite_original", thumb_path]
                subprocess.run(cmd, capture_output=True, timeout=10)

            return thumb_path

    except Exception as e:
        print(f"Error generating thumbnail for {image_path}: {e}")
        return None

PREVIEW_DIR = str(PROJECT_ROOT / "thumbnails" / "previews")

def ensure_preview_dir():
    if not os.path.exists(PREVIEW_DIR):
        try:
            os.makedirs(PREVIEW_DIR)
        except OSError:
            pass

def get_preview_filename(image_path):
    path_hash = hashlib.md5(str(image_path).encode('utf-8')).hexdigest()
    return os.path.join(PREVIEW_DIR, f"{path_hash}.jpg")

def generate_preview(image_path):
    """
    Generates or extracts a high-resolution preview for the image.
    Returns the path to the preview image (JPEG).
    
    For RAW files, prioritizes embedded JPEG extraction (ExifTool → dcraw),
    then falls back to full RAW decode if needed.
    """
    ensure_preview_dir()
    
    # If not raw, return original (assuming browser compatible)
    ext = Path(image_path).suffix.lower()
    if ext not in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']:
        return image_path
        
    preview_path = get_preview_filename(image_path)
    if os.path.exists(preview_path):
        return preview_path
        
    print(f"Generating preview for {image_path}...")
    
    img = None
    
    # Priority 1: Extract embedded JPEG via ExifTool or dcraw (fast, high quality)
    img = extract_embedded_jpeg(image_path, min_size=1000)
    
    if img:
        # Check if preview is large enough (reject tiny thumbnails)
        # Full HD is usually > 1600 width, but we accept > 1000 for previews
        if img.width > 1000:
            try:
                img.save(preview_path, "JPEG", quality=90)
                
                # Copy EXIF orientation from original
                if shutil.which("exiftool"):
                    cmd = ["exiftool", "-TagsFromFile", str(image_path), "-Orientation", "-overwrite_original", preview_path]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                
                return preview_path
            except Exception as e:
                print(f"Failed to save extracted preview: {e}")
                img = None
        else:
            print(f"Embedded preview too small: {img.size}, trying full decode...")
            img = None
    
    # Priority 2: Fallback to rawpy full decode (slow but best quality)
    if img is None:
        try:
            import rawpy
            with rawpy.imread(str(image_path)) as raw:
                # postprocess gives full size numpy array
                rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                img = Image.fromarray(rgb)
                img.save(preview_path, "JPEG", quality=90)
                
                # Copy EXIF orientation from original
                if shutil.which("exiftool"):
                    cmd = ["exiftool", "-TagsFromFile", str(image_path), "-Orientation", "-overwrite_original", preview_path]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                
                return preview_path
        except ImportError:
            print("rawpy not available for full decode")
        except Exception as e:
            print(f"rawpy decode failed: {e}")
        
    return None
