"""Optional dependency guards for pytest module collection."""

from __future__ import annotations

import importlib.util

import pytest


def require_psycopg2() -> None:
    """Skip the module unless real psycopg2-binary is installed (not a test stub)."""
    try:
        available = importlib.util.find_spec("psycopg2.pool") is not None
    except ModuleNotFoundError:
        available = False
    if not available:
        pytest.skip("psycopg2-binary not installed", allow_module_level=True)


def require_sklearn() -> None:
    pytest.importorskip("sklearn")


def require_torch() -> None:
    pytest.importorskip("torch")


def require_exifread() -> None:
    pytest.importorskip("exifread")


def require_pandas() -> None:
    pytest.importorskip("pandas")


def require_gradio() -> None:
    pytest.importorskip("gradio")


def require_tensorflow() -> None:
    pytest.importorskip("tensorflow")


def require_mcp() -> None:
    pytest.importorskip("mcp")
