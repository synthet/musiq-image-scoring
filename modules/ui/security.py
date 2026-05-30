"""Lightweight security helpers (rate limiting, path validation, SQL guards).

Extracted from app.py so tests and api.py can import these without pulling in
the full UI/ML dependency chain.
"""

import os
import re
import time
from collections import defaultdict

# --- Rate limiting ---
_rate_limits: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 10


def _check_rate_limit(endpoint: str):
    """Simple in-memory rate limiter per endpoint."""
    from fastapi import HTTPException
    now = time.time()
    _rate_limits[endpoint] = [t for t in _rate_limits[endpoint] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limits[endpoint]) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_limits[endpoint].append(now)

# --- Path validation ---
_ALLOWED_IMAGE_ROOTS = None


def _validate_file_path(file_path: str) -> str:
    """Validate and resolve a file path, rejecting traversal attempts."""
    from fastapi import HTTPException
    from modules import config
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    resolved = os.path.realpath(file_path)

    global _ALLOWED_IMAGE_ROOTS
    if _ALLOWED_IMAGE_ROOTS is None:
        _ALLOWED_IMAGE_ROOTS = config.get_allowed_paths_from_config()
        _ALLOWED_IMAGE_ROOTS.extend(config.get_default_allowed_paths())

    if _ALLOWED_IMAGE_ROOTS and not any(
        resolved.startswith(os.path.realpath(root)) for root in _ALLOWED_IMAGE_ROOTS
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    return resolved

# --- API authentication ---
_API_KEY_ENABLED = False
_API_KEY_VALUE = None

def _init_api_auth():
    """Initialize API key authentication from environment or config."""
    global _API_KEY_ENABLED, _API_KEY_VALUE
    # Check environment first, then config.json
    api_key_env = os.environ.get("API_KEY", "").strip()
    if api_key_env:
        _API_KEY_ENABLED = True
        _API_KEY_VALUE = api_key_env
    else:
        from modules import config
        try:
            api_key_config = config.get_config_value("api.key", "").strip()
            if api_key_config:
                _API_KEY_ENABLED = True
                _API_KEY_VALUE = api_key_config
        except Exception:
            pass


def _check_api_key(request) -> None:
    """Validate API key from X-API-Key header (for mutating endpoints).

    Required only if API_KEY environment variable or config.api.key is set.
    Raises HTTPException 401 if key is missing or invalid.
    """
    from fastapi import HTTPException
    if not _API_KEY_ENABLED:
        return  # No authentication required

    # Get key from header
    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key or api_key != _API_KEY_VALUE:
        raise HTTPException(status_code=401, detail="Missing or invalid API key (X-API-Key header)")


# --- SQL query validation ---
_SQL_FORBIDDEN_PATTERNS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXECUTE|INTO|GRANT|REVOKE)\b',
    re.IGNORECASE
)
