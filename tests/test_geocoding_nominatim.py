"""Unit tests for Nominatim geocoding (HTTP mocked; no network)."""

from __future__ import annotations

import json
from unittest import mock

import httpx
import pytest

from modules.geocoding import nominatim as nominatim_mod
from modules.geocoding.nominatim import NominatimProvider


@pytest.fixture
def fake_config(monkeypatch):
    monkeypatch.setattr(
        nominatim_mod,
        "get_config_value",
        lambda key, default=None: {
            "geocoding.nominatim_base_url": "https://nominatim.openstreetmap.org/",
            "geocoding.user_agent": "image-scoring-tests/0",
            "geocoding.min_interval_seconds": 0.01,
            "geocoding.http_timeout_seconds": 5,
        }.get(key, default),
    )


def test_nominatim_reverse_parses(fake_config):
    sample = {
        "display_name": "Test City, TS, Exampleland",
        "address": {
            "city": "Test City",
            "state": "Test State",
            "country": "Exampleland",
            "country_code": "ex",
            "postcode": "12345",
        },
    }
    with mock.patch.object(httpx.Client, "get") as m_get:
        m_get.return_value.status_code = 200
        m_get.return_value.text = json.dumps(sample)
        m_get.return_value.json = lambda: sample
        p = NominatimProvider()
        loc = p.reverse(40.0, -74.0)
    assert loc is not None
    assert loc.get("display_name")
    assert loc.get("country") == "Exampleland"
    m_get.assert_called_once()


def test_nominatim_forward_returns_coords(fake_config):
    sample = [
        {
            "lat": "37.0",
            "lon": "-122.0",
            "display_name": "Somewhere",
            "address": {"country": "United States"},
        }
    ]
    with mock.patch.object(httpx.Client, "get") as m_get:
        m_get.return_value.status_code = 200
        m_get.return_value.text = json.dumps(sample)
        m_get.return_value.json = lambda: sample
        p = NominatimProvider()
        out = p.forward("Some Place")
    assert out is not None
    lat, lon, parts = out
    assert abs(lat - 37.0) < 0.01
    assert abs(lon - (-122.0)) < 0.01
    assert parts is not None
