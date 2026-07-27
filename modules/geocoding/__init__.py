"""
Pluggable geocoding (Nominatim by default). Config under ``geocoding.*`` in config.json.
"""

from modules.geocoding.provider import GeocodingProvider, get_geocoding_provider
from modules.geocoding.types import LocationParts, location_parts_to_dict

__all__ = [
    "GeocodingProvider",
    "LocationParts",
    "get_geocoding_provider",
    "location_parts_to_dict",
]
