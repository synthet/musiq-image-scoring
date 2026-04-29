"""
OpenStreetMap Nominatim geocoding.

Comply with https://operations.osmfoundation.org/policies/nominatim/
(appropriate User-Agent, throttling, no bulk abuse).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional, Tuple
from urllib.parse import urljoin

import httpx

from modules.config import get_config_value
from modules.geocoding.types import LocationParts

logger = logging.getLogger(__name__)

_nominatim_lock = threading.Lock()
_nominatim_last_call: float = 0.0


def _nominatim_parsed_to_parts(data: dict[str, Any]) -> LocationParts:
    display_name = (data.get("display_name") or "").strip() or "unknown"
    addr: dict[str, str] = data.get("address") or {}
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("hamlet")
        or addr.get("suburb")
    )
    state = addr.get("state") or addr.get("region")
    country = addr.get("country")
    return LocationParts(
        display_name=display_name,
        city=(city or "").strip(),
        state=(state or "").strip(),
        county=(addr.get("county") or "").strip(),
        country=(country or "").strip(),
        country_code=(addr.get("country_code") or "").upper().strip(),
        postcode=(addr.get("postcode") or "").strip(),
        raw=data,
    )


def _throttle() -> None:
    global _nominatim_last_call
    min_interval = get_config_value("geocoding.min_interval_seconds", default=1.1)
    try:
        sec = float(min_interval)
    except (TypeError, ValueError):
        sec = 1.1
    sec = max(0.5, min(sec, 60.0))
    with _nominatim_lock:
        now = time.monotonic()
        wait = _nominatim_last_call + sec - now
        if wait > 0:
            time.sleep(wait)
        _nominatim_last_call = time.monotonic()


class NominatimProvider:
    name = "nominatim"

    def __init__(self) -> None:
        base = (get_config_value("geocoding.nominatim_base_url", default="https://nominatim.openstreetmap.org")
                or "https://nominatim.openstreetmap.org")
        if not base.rstrip("/").endswith("openstreetmap.org") and "localhost" not in base:
            # Allow self-hosted; log once if unusual
            logger.info("Nominatim base URL: %s", base)
        self._base = base if base.endswith("/") else base + "/"
        ua = get_config_value("geocoding.user_agent", default="")
        if not ua or not str(ua).strip():
            raise ValueError("geocoding.user_agent is required for Nominatim (set in config.json)")
        self._headers = {
            "User-Agent": str(ua).strip(),
            "Accept": "application/json",
        }
        try:
            t = int(get_config_value("geocoding.http_timeout_seconds", default=10))
        except (TypeError, ValueError):
            t = 10
        self._timeout = httpx.Timeout(max(3, min(t, 120)))

    def _get(self, path: str, params: dict[str, str]) -> Optional[dict | list]:
        _throttle()
        url = urljoin(self._base, path)
        with httpx.Client(follow_redirects=True, timeout=self._timeout) as client:
            r = client.get(url, params=params, headers=self._headers)
        if r.status_code != 200:
            logger.warning("Nominatim HTTP %s: %s", r.status_code, r.text[:200])
            return None
        try:
            return r.json()
        except json.JSONDecodeError as e:
            logger.warning("Nominatim JSON error: %s", e)
            return None

    def reverse(self, lat: float, lon: float) -> Optional[LocationParts]:
        data = self._get(
            "reverse",
            {
                "lat": f"{lat:.7f}",
                "lon": f"{lon:.7f}",
                "format": "jsonv2",
                "addressdetails": "1",
            },
        )
        if not data or not isinstance(data, dict):
            return None
        return _nominatim_parsed_to_parts(data)

    def forward(
        self, query: str
    ) -> Optional[Tuple[float, float, Optional[LocationParts]]]:
        q = (query or "").strip()
        if not q:
            return None
        data = self._get(
            "search",
            {
                "q": q,
                "format": "jsonv2",
                "limit": "1",
                "addressdetails": "1",
            },
        )
        if not data or not isinstance(data, list) or not data:
            return None
        first: dict[str, Any] = data[0] if isinstance(data[0], dict) else {}
        try:
            lat = float(first["lat"])
            lon = float(first["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        parts: Optional[LocationParts] = None
        if isinstance(first, dict):
            parts = _nominatim_parsed_to_parts(first)
        return (lat, lon, parts)
