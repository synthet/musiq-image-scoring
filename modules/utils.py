import hashlib
import os
import platform
import re
import datetime
import shutil
import subprocess
import threading
from PIL import Image, ImageOps, ExifTags
import json
import time
try:
    import exifread
except ImportError:
    exifread = None
from modules import debug

# Cache exiftool path to avoid repeated shutil.which checks
# Cache exiftool path to avoid repeated shutil.which checks
# Cache exiftool path to avoid repeated shutil.which checks
_EXIFTOOL_PATH = shutil.which("exiftool")

# Thread-local storage for request-scoped caching
_thread_local = threading.local()

def set_batch_path_cache(cache):
    """Set the batch path cache for the current thread."""
    _thread_local.path_cache = cache

def clear_batch_path_cache():
    """Clear the batch path cache for the current thread."""
    if hasattr(_thread_local, 'path_cache'):
        del _thread_local.path_cache


def read_burst_uuid(image_path: str, metadata_json: str = None) -> str | None:
    """
    Read BurstUUID from image EXIF (Apple burst photos).
    
    BurstUUID is used by Apple devices to group burst photos together.
    This allows pre-grouping burst images before visual clustering.
    
    Args:
        image_path: Path to the image file
        metadata_json: Optional cached metadata JSON from database
        
    Returns:
        BurstUUID string if present, None otherwise
    """
    # 1. Check cached metadata first (fastest)
    if metadata_json:
        try:
            meta = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
            burst_uuid = meta.get('BurstUUID') or meta.get('Apple:BurstUUID')
            if burst_uuid:
                return burst_uuid
        except (json.JSONDecodeError, TypeError):
            pass
    
    # 2. Try exiftool if available (for RAW/NEF/iPhone files)
    if _EXIFTOOL_PATH:
        resolved = resolve_file_path(image_path)
        if resolved and os.path.exists(resolved):
            try:
                cmd = [_EXIFTOOL_PATH, '-s', '-S', '-BurstUUID', resolved]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    burst_uuid = result.stdout.strip()
                    if burst_uuid and burst_uuid != '-':
                        return burst_uuid
            except (subprocess.TimeoutExpired, Exception):
                pass
    
    return None


def get_debug_log_path():
    """
    Returns the absolute path to the debug log file, handling Windows/WSL differences.
    """
    # Base filename
    log_filename = "debug.log"
    
    # Determine project root (where modules folder functions as anchor)
    # utils.py is in <root>/modules/utils.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # Construct path: <root>/<log_dir>/debug.log
    from modules import config
    log_dir_name = config.get_config_value('system.log_dir', ".cursor")
    log_dir = os.path.join(project_root, log_dir_name)
    
    # Ensure directory exists
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass # Might fail on permissions, but we try
        
    return os.path.join(log_dir, log_filename)

_DEBUG_LOG_PATH = get_debug_log_path()

def add_border_to_image(image_path, color='gray', border=10):
    """
    Loads an image (or path) and adds a colored border.
    Returns a PIL Image object.
    """
    try:
        if isinstance(image_path, str):
            # Resolve path if needed
            local_path = convert_path_to_local(image_path)
            if not os.path.exists(local_path):
                # Placeholder or error
                return None
            img = Image.open(local_path)
        else:
            img = image_path
            
        # Add border
        # ImageOps.expand adds border, but we want it inside or outside?
        # Outside is safer to preserve content.
        img_with_border = ImageOps.expand(img, border=border, fill=color)
        return img_with_border
    except Exception as e:
        print(f"Error adding border to {image_path}: {e}")
        return None

def _remap_host_project_path(path: str) -> str | None:
    """Remap a host-side project path to the local project root.

    When running inside Docker, paths stored in the database refer to the
    host filesystem (e.g. `/mnt/d/Projects/image-scoring-backend/thumbnails/...`
    or `D:\\Projects\\image-scoring-backend\\thumbnails\\...`) and do not exist
    inside the container. The container project root (e.g. `/app`) is computed
    from `BASE_DIR`, and the host-side equivalents come from environment
    variables `IMAGE_SCORING_HOST_PROJECT_WSL` / `IMAGE_SCORING_HOST_PROJECT_WIN`.

    Returns the remapped path, or None when no env vars are set or no prefix matches.
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
        # Skip when the host root already matches the local root — nothing to remap.
        if prefix_norm == local_root.replace("\\", "/").rstrip("/"):
            continue
        if p_norm == prefix_norm:
            return local_root
        prefix_with_sep = prefix_norm + "/"
        if p_norm.startswith(prefix_with_sep):
            tail = p_norm[len(prefix_with_sep):]
            return os.path.join(local_root, *tail.split("/"))

    return None


def convert_path_to_local(path):
    """
    Converts a path to the local OS format.
    Specifically handles WSL paths (/mnt/c/...) when running on Windows.
    """
    remapped = _remap_host_project_path(path)
    if remapped is not None:
        path = remapped

    system = platform.system()

    if system == "Windows":
        # Handle WSL paths (forward and backslashes)
        # Normalize to forward slashes for checking
        p_str = path.replace('\\', '/')
        if p_str.startswith("/mnt/"):
            # Collapse duplicate slashes (e.g. /mnt//d/foo) so drive letter parses correctly
            p_str = re.sub(r"/+", "/", p_str)
            # /mnt/d/Description -> D:/Description
            parts = p_str.split('/')
            if len(parts) > 2 and len(parts[2]) == 1:
                drive = parts[2].upper()
                rest = "/".join(parts[3:])
                return f"{drive}:/{rest}"
    elif system == "Linux":
         # Handle Windows paths on WSL
         # D:\Foo -> /mnt/d/Foo
         # Check for D:\ or D:/
         match = re.match(r'^([a-zA-Z]):[\\\/](.*)', path)
         if match:
             drive = match.group(1).lower()
             rest = match.group(2).replace('\\', '/')
             return f"/mnt/{drive}/{rest}"
         
         # Fallback: maintain forward slashes for Linux
         if '\\' in path:
             path = path.replace('\\', '/')
    
    return path


def resolve_scope_input_path(raw: str) -> tuple[str, list[str]]:
    """
    Resolve a user-entered folder/file path for scope preview and validation.

    Tries several canonical forms (WSL /mnt/..., Windows D:\\..., duplicate slashes)
    and returns the first path that exists on the current OS.

    Returns:
        (existing_path, candidates_tried) when found; (None, candidates_tried) when not found.
    """
    s = (raw or "").strip()
    while len(s) > 1 and s[-1] in "/\\":
        prev = s[:-1]
        if len(prev) == 2 and prev[1] == ":":
            break
        s = prev
    if not s:
        return None, []

    sl = s.replace("\\", "/")
    collapsed_mnt = re.sub(r"/+", "/", sl) if sl.startswith("/mnt/") else sl

    candidates: list[str] = []
    seen: set[str] = set()

    def add(p: str | None) -> None:
        if p is None:
            return
        q = str(p).strip()
        if not q or q in seen:
            return
        seen.add(q)
        candidates.append(q)

    system = platform.system()
    if system == "Windows":
        # Prefer WSL-style → Windows drive mapping first (raw /mnt/d/... does not exist on NTFS)
        add(convert_path_to_local(collapsed_mnt))
        add(convert_path_to_local(s))
        add(collapsed_mnt)
        add(s)
    else:
        add(collapsed_mnt)
        add(s)
        if re.match(r"^[a-zA-Z]:/", sl):
            add(convert_path_to_wsl(sl))
        add(convert_path_to_local(s))
        add(convert_path_to_local(collapsed_mnt))

    for cand in candidates:
        expanded = os.path.expanduser(os.path.expandvars(cand))
        try:
            norm = os.path.normpath(expanded)
        except (OSError, ValueError):
            norm = expanded
        if os.path.exists(norm):
            return norm, candidates

    return None, candidates


def is_docker_runtime() -> bool:
    """True when the process is expected to run with a container filesystem (compose sets DOCKER_CONTAINER=1)."""
    flag = os.environ.get("DOCKER_CONTAINER", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    try:
        return os.path.exists("/.dockerenv")
    except OSError:
        return False


def convert_path_to_wsl(path):
    """
    Converts a Windows path to WSL format.
    D:/Photos/... -> /mnt/d/Photos/...
    """
    # Check for D:\ or D:/
    match = re.match(r'^([a-zA-Z]):[\\\/](.*)', path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return path

def compute_file_hash(file_path, algorithm='sha256', chunk_size=8192):
    """
    Computes the hash of a file using the specified algorithm (default: sha256).
    Reads the file in chunks to handle large files efficiently.
    """
    # Try resolving path using the new unified resolver
    resolved = resolve_file_path(file_path)
    if resolved:
        file_path = resolved
    elif not os.path.exists(file_path):
        return None

    try:
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        elif algorithm == 'md5':
            hasher = hashlib.md5()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error computing hash for {file_path}: {e}")
        return None


# Alias used by indexing_runner and any callers expecting the older name
calculate_image_hash = compute_file_hash


def resolve_file_path(db_path, image_id=None):
    """
    Unified path resolution: resolved_path first, then WSL conversion fallback.
    
    This is the PRIMARY function to use when resolving image paths across the app.
    
    Resolution order:
    1. If image_id provided: check resolved_paths table for cached Windows path
    2. Convert path using convert_path_to_local()
    3. Verify file exists, return the working path or None
    
    Args:
        db_path: The path stored in the database (may be WSL or Windows format)
        image_id: Optional image ID to check resolved_paths table first
    
    Returns:
        A path that exists on the local filesystem, or None if not found
    """
    # Local imports make this resilient even if module globals get into a bad state
    import time
    t0 = time.perf_counter()
    strat = None
    resolved_len = None
    converted_len = None
    db_ms = 0.0
    out = None

    # Strategy 0: Check thread-local batch cache (Performance Optimization)
    if image_id and hasattr(_thread_local, 'path_cache'):
        # Batch cache is populated by gallery.py using get_resolved_paths_batch
        # It contains only verified paths, so we can return immediately
        cached = _thread_local.path_cache.get(image_id)
        if cached:
            return cached

    # Strategy 1: Check resolved_paths table if image_id is provided
    if image_id:
        try:
            from modules import db
            t_db0 = time.perf_counter()
            resolved = db.get_resolved_path(image_id, verified_only=True)
            t_db1 = time.perf_counter()
            db_ms += (t_db1 - t_db0) * 1000
            if resolved and os.path.exists(resolved):
                strat = "resolved_verified"
                resolved_len = len(resolved) if isinstance(resolved, str) else None
                out = resolved
        except Exception:
            pass  # Fall through to conversion
    
    # Strategy 2: Try the path as-is first
    if out is None and os.path.exists(db_path):
        strat = "as_is"
        out = db_path
        # Cache this success if we have an ID
        if image_id:
             try:
                 from modules import db
                 db.add_resolved_path(image_id, out)
             except Exception: pass
    
    # Strategy 3: Convert using platform-aware conversion
    converted = convert_path_to_local(db_path)
    if out is None and converted != db_path and os.path.exists(converted):
        strat = "converted"
        converted_len = len(converted) if isinstance(converted, str) else None
        out = converted
        # Cache this success if we have an ID
        if image_id:
             try:
                 from modules import db
                 db.add_resolved_path(image_id, out)
             except Exception: pass
    
    # Strategy 4: If we have image_id, try unverified resolved path
    if out is None and image_id:
        try:
            from modules import db
            t_db0 = time.perf_counter()
            resolved = db.get_resolved_path(image_id, verified_only=False)
            t_db1 = time.perf_counter()
            db_ms += (t_db1 - t_db0) * 1000
            if resolved and os.path.exists(resolved):
                # Update verification status since we found it
                db.verify_resolved_path(image_id)
                strat = "resolved_unverified"
                resolved_len = len(resolved) if isinstance(resolved, str) else None
                out = resolved
        except Exception:
            pass
    

    # File not found anywhere
    if out is None:
        strat = strat or "not_found"

    total_ms = (time.perf_counter() - t0) * 1000

    if total_ms > 100: # Log only if slow (>100ms)
        debug.log_metric(f"Slow Resolve ({strat})", f"{total_ms:.2f}", "ms")

    return out

def get_image_creation_time(image_path):
    """
    Attempts to get the actual creation time of the image from metadata.
    Prioritizes:
    1. EXIF DateTimeOriginal (via PIL for JPG/TIFF)
    2. ExifTool (via subprocess for RAW/NEF - if available)
    3. Filesystem Creation Time (fallback)
    
    Returns datetime object.
    """
    # Try resolving first
    resolved = resolve_file_path(image_path)
    if resolved:
        image_path = resolved
        
    if not os.path.exists(image_path):
        return datetime.datetime.now()

    # 1. Try ExifTool first for RAW/NEF files or if PIL fails
    # User specifically mentioned NEF files which PIL often doesn't handle well for EXIF
    ext = os.path.splitext(image_path)[1].lower()
    is_raw = ext in ['.nef', '.nrw', '.cr2', '.arw', '.dng', '.orf', '.rw2']
    
    if is_raw and _EXIFTOOL_PATH:
        try:
            # -T: Table output (tab separated)
            # -DateTimeOriginal
            # -CreateDate (backup)
            cmd = [_EXIFTOOL_PATH, '-T', '-DateTimeOriginal', '-CreateDate', '-d', '%Y:%m:%d %H:%M:%S', image_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Output might be "2025:11:18 10:20:30\t-"
                parts = result.stdout.strip().split('\t')
                date_str = parts[0]
                if not date_str or date_str == "-":
                    if len(parts) > 1: date_str = parts[1]
                
                if date_str and date_str != "-":
                    try:
                        return datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        pass
        except Exception as e:
            print(f"ExifTool extraction failed: {e}")

    # 2. Try PIL for all images (standard and RAW fallbacks)
    # PIL can often read EXIF from TIFF-based RAWs (NEF, etc.)
    try:
        with Image.open(image_path) as img:
            exif = img.getexif() # Use getexif() for efficiency (no load) or _getexif()
            # _getexif is 'private' but returns decoded dict. getexif returns Image.Exif object
            
            # Helper to extract from decoded or raw
            dt_str = None
            if exif:
                 # 36867 = DateTimeOriginal
                 # 306 = DateTime
                 # ExifTags.TAGS can help, but we know the IDs
                 dt_str = exif.get(36867) or exif.get(306)
                 
                 # If not found, try _getexif() which sometimes has more? 
                 # Or iterating tags.
            
            if not dt_str and hasattr(img, '_getexif'):
                 exif_dict = img._getexif()
                 if exif_dict:
                     dt_str = exif_dict.get(36867) or exif_dict.get(306)

            if dt_str:
                # Format "YYYY:MM:DD HH:MM:SS"
                return datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
            
    except Exception:
        pass

    # 3. Try exifread (for RAW/NEF where PIL fails)
    if is_raw and exifread:
        try:
            with open(image_path, 'rb') as f:
                # details=False stops reading thumbnails etc.
                tags = exifread.process_file(f, details=False)
                
                dt_tag = tags.get('EXIF DateTimeOriginal') or tags.get('Image DateTime') or tags.get('EXIF DateTimeDigitized')
                dt_str = str(dt_tag)
                
                # Format "YYYY:MM:DD HH:MM:SS"
                if dt_str and ':' in dt_str:
                     return datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        except Exception as e:
            # print(f"exifread error {image_path}: {e}")
            pass
            
    # 4. Fallback to Filesystem
    try:
        # Windows: creation time, Unix: last modification (often best proxy if ctime is metadata change)
        if platform.system() == "Windows":
             ts = os.path.getctime(image_path)
        else:
             # Unix ctime is metadata change, mtime is content modification. 
             # mtime is usually closer to creation for files copied.
             ts = os.path.getmtime(image_path)
        return datetime.datetime.fromtimestamp(ts)
    except Exception:
        return datetime.datetime.now()

