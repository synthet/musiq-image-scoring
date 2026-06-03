"""MCP /mcp HTTP client IP allowlist (localhost + Docker/WSL private nets)."""

import os

import pytest

from modules.mcp_server import _mcp_allowed_networks, is_mcp_client_ip_allowed


@pytest.fixture(autouse=True)
def _clear_allowlist_cache():
    _mcp_allowed_networks.cache_clear()
    yield
    _mcp_allowed_networks.cache_clear()


def test_loopback_allowed():
    assert is_mcp_client_ip_allowed("127.0.0.1")
    assert is_mcp_client_ip_allowed("127.0.0.2")
    assert is_mcp_client_ip_allowed("::1")


def test_docker_and_private_ranges_allowed():
    assert is_mcp_client_ip_allowed("172.17.0.1")
    assert is_mcp_client_ip_allowed("192.168.65.1")
    assert is_mcp_client_ip_allowed("10.0.0.5")
    assert is_mcp_client_ip_allowed("169.254.1.1")


def test_public_ips_rejected():
    assert not is_mcp_client_ip_allowed("8.8.8.8")
    assert not is_mcp_client_ip_allowed("203.0.113.1")
    assert not is_mcp_client_ip_allowed(None)
    assert not is_mcp_client_ip_allowed("")


def test_extra_cidr_from_env(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_CIDRS", "100.64.0.0/10")
    _mcp_allowed_networks.cache_clear()
    assert is_mcp_client_ip_allowed("100.64.0.1")
    assert not is_mcp_client_ip_allowed("8.8.8.8")
