import json
import logging
import os
import platform
import string
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
ENVIRONMENT_FILE = BASE_DIR / "environment.json"

_config_cache: dict | None = None
_config_cache_mtime: tuple[float, float] | None = None


def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    last_err = None
    for attempt in range(3):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except OSError as exc:
            last_err = exc
            if getattr(exc, "errno", None) == 5 and attempt < 2:
                time.sleep(0.05 * (attempt + 1))
                continue
            logging.error("Failed to load JSON from %s: %s", path, exc)
            return {}
        except Exception as e:
            logging.error("Failed to load JSON from %s: %s", path, e)
            return {}
    if last_err is not None:
        logging.error("Failed to load JSON from %s after retries: %s", path, last_err)
    return {}


def _deep_merge_dict(base: dict, override: dict) -> dict:
    """Recursively merge override into base; override wins. Lists and scalars replace."""
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge_dict(out[key], val)
        else:
            out[key] = val
    return out


def _load_config_file_only() -> dict:
    """config.json only (no environment merge). Used when persisting changes."""
    return _read_json_file(CONFIG_FILE)


def _load_environment_file_only() -> dict:
    return _read_json_file(ENVIRONMENT_FILE)


def load_config():
    """
    Loads configuration from config.json merged with environment.json (when present).
    environment.json overrides overlapping keys.
    """
    global _config_cache, _config_cache_mtime

    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            return 0.0

    # Key on BOTH files: environment.json is merged in, so an edit there must
    # invalidate the cache even when config.json is untouched.
    key = (_mtime(CONFIG_FILE), _mtime(ENVIRONMENT_FILE))
    if _config_cache is not None and _config_cache_mtime == key:
        return _config_cache
    merged = _deep_merge_dict(_load_config_file_only(), _load_environment_file_only())
    _config_cache = merged
    _config_cache_mtime = key
    return merged


def invalidate_config_cache() -> None:
    """Clear in-process config cache (e.g. after save_config_value)."""
    global _config_cache, _config_cache_mtime
    _config_cache = None
    _config_cache_mtime = None

def save_config_value(key, value):
    """
    Updates a single key in the config and saves it.
    Supports nested keys using dot notation (e.g., 'scoring.force_rescore_default').
    """
    data = _load_config_file_only()
    if '.' in key:
        parts = key.split('.')
        target = data
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
    else:
        data[key] = value

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        invalidate_config_cache()
    except Exception as e:
        logging.error(f"Failed to save config: {e}")

def get_config_value(key, default=None):
    """
    Get a config value with fallback to default.
    Supports nested keys using dot notation (e.g., 'scoring.force_rescore_default').
    """
    data = load_config()
    if '.' in key:
        # Handle nested keys
        parts = key.split('.')
        value = data
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value
    else:
        return data.get(key, default)

def get_config_section(section):
    """
    Get all keys in a section (for organization).
    Returns a dictionary of all keys under the given section.
    """
    data = load_config()
    if section in data and isinstance(data[section], dict):
        return data[section]
    return {}


def get_database_engine() -> str:
    """Resolve ``database.engine`` from ``config.json``.

    Returns ``postgres`` in all cases unless explicitly overridden.

    Resolution order:

    1. Explicit ``engine`` value in ``config.json`` ``database`` section (any valid
       engine: ``postgres``, ``firebird``, ``api``).
    2. ``IMAGE_SCORING_DB_ENGINE_DEFAULT`` env var (``firebird`` or ``postgres``).
    3. ``IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP`` env var — returns ``firebird``
       (legacy escape hatch for ``scripts/setup_test_db.py``).
    4. Default: ``postgres`` (for both production and pytest).

    .. deprecated:: 6.4
       Firebird support is deprecated and will be removed in v7.0 (July 2026).
       The default is now ``postgres`` for all environments including pytest.
    """
    # 1. Explicit config.json engine (highest priority)
    sec = get_config_section("database") or {}
    raw = sec.get("engine")
    if raw is not None and str(raw).strip():
        return str(raw).strip().lower()

    # 2. Environment override
    forced = os.environ.get("IMAGE_SCORING_DB_ENGINE_DEFAULT", "").strip().lower()
    if forced in ("firebird", "postgres", "api"):
        return forced

    # 3. Legacy escape hatch for Firebird test setup script
    if os.environ.get("IMAGE_SCORING_FORCE_FIREBIRD_TEST_SETUP", "").strip().lower() in ("1", "true", "yes"):
        return "firebird"

    # 4. Default: postgres (production, Docker, pytest — all environments)
    return "postgres"

def save_config_section(section, section_data):
    """
    Save an entire section of configuration.
    """
    data = _load_config_file_only()
    data[section] = section_data
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        invalidate_config_cache()
    except Exception as e:
        logging.error(f"Failed to save config section: {e}")


def merge_and_save_config_section(section: str, patch: dict) -> None:
    """Deep-merge ``patch`` into an existing config section, then persist to config.json."""
    existing = get_config_section(section) or {}
    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(patch, dict):
        patch = {}
    save_config_section(section, _deep_merge_dict(existing, patch))


def get_allowed_paths_from_config() -> list:
    """Resolve image path allowlist: ``system.allowed_paths`` with legacy top-level fallback."""
    data = load_config()
    system_paths = (data.get("system") or {}).get("allowed_paths")
    if isinstance(system_paths, list) and system_paths:
        return list(system_paths)
    legacy = data.get("allowed_paths")
    if isinstance(legacy, list) and legacy:
        return list(legacy)
    return []


def get_export_templates():
    """
    Get all export templates.
    Returns a dictionary of template_name -> template_config.
    """
    data = load_config()
    return data.get('export_templates', {})


def save_export_template(template_name, template_config):
    """
    Save an export template.
    
    Args:
        template_name: Name of the template
        template_config: Dictionary with export configuration:
            - format: export format (csv/xlsx/json)
            - columns_basic: list
            - columns_scores: list
            - columns_metadata: list
            - columns_other: list
            - filter_rating: list
            - filter_label: list
            - filter_keyword: str
            - filter_folder: str
            - filter_min_gen: float
            - filter_min_aes: float
            - filter_min_tech: float
            - filter_date_start: str
            - filter_date_end: str
    """
    data = _load_config_file_only()
    if 'export_templates' not in data:
        data['export_templates'] = {}
    
    data['export_templates'][template_name] = template_config
    
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Failed to save export template: {e}")
        return False


def delete_export_template(template_name):
    """
    Delete an export template.
    """
    data = _load_config_file_only()
    if 'export_templates' in data and template_name in data['export_templates']:
        del data['export_templates'][template_name]
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logging.error(f"Failed to delete export template: {e}")
            return False
    return False


def get_export_template(template_name):
    """
    Get a specific export template by name.
    Returns None if not found.
    """
    templates = get_export_templates()
    return templates.get(template_name)


def get_system_drives():
    """
    Get a list of available system drives/root paths.
    
    Returns:
        List of strings (e.g. ['C:/', 'D:/'] on Windows, ['/'] on Linux)
    """
    drives = []
    system = platform.system()
    
    if system == "Windows":
        # Get logical drives
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:/")
            bitmask >>= 1
    else:
        # Linux/Unix/MacOS
        drives.append("/")
        # Add WSL mounts if applicable
        if os.path.isdir("/mnt"):
            try:
                for item in os.listdir("/mnt"):
                    mount_point = f"/mnt/{item}"
                    if os.path.isdir(mount_point):
                        drives.append(mount_point + "/")
            except OSError:
                pass
                
    return drives


_SECRETS_FILE = BASE_DIR / "secrets.json"

def get_secret(service_name: str):
    """Load API credentials from secrets.json for a specific service.

    Returns:
        dict or None: Credentials dict for the service, or None if not found.
    """
    try:
        if not _SECRETS_FILE.exists():
            return None
        with open(_SECRETS_FILE, 'r') as f:
            secrets = json.load(f)
        return secrets.get(service_name)
    except Exception as e:
        logging.warning("Failed to load secret for '%s': %s", service_name, e)
        return None


def get_default_allowed_paths():
    """
    Get default allowed paths based on system configuration.
    
    Returns:
        List of paths safe to allow by default.
    """
    allowed = [os.path.abspath("."), str(BASE_DIR / "thumbnails")]
    
    # Add all detected system drives
    drives = get_system_drives()
    allowed.extend(drives)
    
    return allowed


def validate_config() -> dict:
    """
    Structural validation of config.json (no DB connection).
    Returns dict with ok (bool), issues (list of str), and optional warnings.
    """
    issues = []
    warnings = []

    if not CONFIG_FILE.exists() and not ENVIRONMENT_FILE.exists():
        return {
            "ok": False,
            "issues": [
                f"No configuration files found: {CONFIG_FILE} or {ENVIRONMENT_FILE}",
            ],
            "warnings": warnings,
        }

    data = load_config()
    if not data:
        issues.append("config.json and environment.json are missing, empty, or failed to parse")

    proc = data.get("processing") or {}
    for key in ("prep_queue_size", "scoring_queue_size", "result_queue_size"):
        v = proc.get(key)
        if v is not None and (not isinstance(v, int) or v <= 0):
            issues.append(f"processing.{key} must be a positive integer (got {v!r})")

    cb = proc.get("clustering_batch_size")
    if cb is not None and (not isinstance(cb, int) or cb <= 0):
        issues.append(f"processing.clustering_batch_size must be a positive integer (got {cb!r})")

    sjv = proc.get("strict_job_completion_verify")
    if sjv is not None and not isinstance(sjv, bool):
        issues.append(f"processing.strict_job_completion_verify must be a boolean when set (got {sjv!r})")

    prd = proc.get("post_run_data_quality_audit")
    if prd is not None and not isinstance(prd, bool):
        issues.append(f"processing.post_run_data_quality_audit must be a boolean when set (got {prd!r})")

    prf = proc.get("post_run_audit_fail_job_on_issues")
    if prf is not None and not isinstance(prf, bool):
        issues.append(f"processing.post_run_audit_fail_job_on_issues must be a boolean when set (got {prf!r})")

    db_sec = data.get("database") or {}
    engine = get_database_engine()

    if engine == "firebird":
        if not str(db_sec.get("filename") or "").strip():
            issues.append("database.filename should be set to the Firebird database file name")
    elif engine == "postgres":
        for k in ["host", "port", "dbname", "user"]:
            if not db_sec.get("postgres", {}).get(k):
                issues.append(f"database.postgres.{k} is required when engine is postgres")
    elif engine == "api":
        api_url = str(db_sec.get("api_url") or (db_sec.get("api") or {}).get("url") or "").strip()
        if not api_url:
            issues.append("database.api_url (or database.api.url) is required when engine is api")
    else:
        issues.append(
            f"database.engine must be 'firebird', 'postgres', or 'api' (got {engine!r})"
        )

    for path_key in ("scoring_input_path", "tagging_input_path", "stacks_input_path", "culling_input_path", "selection_input_path"):
        p = data.get(path_key)
        if isinstance(p, str) and p.strip() and not os.path.exists(p):
            warnings.append(f"{path_key} path does not exist on this machine: {p}")

    log_dir = (data.get("system") or {}).get("log_dir")
    if log_dir and not os.path.isdir(os.path.abspath(log_dir)):
        warnings.append(f"system.log_dir is not an existing directory: {log_dir}")

    idx = data.get("indexing") or {}
    if idx.get("nikon_nef_only") is not None and not isinstance(idx.get("nikon_nef_only"), bool):
        issues.append("indexing.nikon_nef_only must be a boolean when set")
    excl = idx.get("excluded_paths")
    if excl is not None:
        if not isinstance(excl, list) or any(not isinstance(x, str) for x in excl):
            issues.append("indexing.excluded_paths must be a list of strings when set")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }