"""Types for geocoding results (coordinates ↔ address)."""

from __future__ import annotations

from typing import Any, TypedDict


class LocationParts(TypedDict, total=False):
    display_name: str
    city: str
    state: str
    county: str
    country: str
    country_code: str
    postcode: str
    raw: dict[str, Any]


def location_parts_to_dict(loc: LocationParts | None) -> dict[str, Any] | None:
    if loc is None:
        return None
    return dict(loc)
