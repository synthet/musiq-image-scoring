"""Geocoding provider protocol and factory."""

from __future__ import annotations

import logging
from typing import Protocol

from modules.geocoding.types import LocationParts

logger = logging.getLogger(__name__)


class GeocodingProvider(Protocol):
    """Pluggable forward / reverse geocoding."""

    name: str

    def reverse(self, lat: float, lon: float) -> LocationParts | None:
        """Coordinates to structured location."""
        ...

    def forward(self, query: str) -> tuple[float, float, LocationParts | None] | None:
        """Address text to (lat, lon, optional structured parts)."""
        ...


def get_geocoding_provider() -> GeocodingProvider | None:
    """
    Return configured provider, or None if geocoding is disabled or misconfigured.
    """
    from modules.config import get_config_value
    from modules.geocoding.nominatim import NominatimProvider

    if not get_config_value("geocoding.enabled", default=False):
        return None
    which = (get_config_value("geocoding.provider", default="nominatim") or "nominatim").strip().lower()
    if which == "nominatim":
        try:
            return NominatimProvider()
        except Exception as e:
            logger.warning("Nominatim geocoder init failed: %s", e)
            return None
    logger.warning("Unknown geocoding.provider: %s", which)
    return None
