"""
WSL-only smoke test for Firebird client library availability.

Historically this file executed code at import time; this version provides
an actual pytest test and skips on Windows.
"""

import sys
import ctypes
import pytest
import os

pytestmark = [pytest.mark.wsl, pytest.mark.firebird]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (Firebird libfbclient.so check)", allow_module_level=True)


def test_firebird_client_library_present():
    firebird = pytest.importorskip("firebird.driver")

    # We don't require a running Firebird server here; we only want to know the
    # client library can be resolved/loaded inside WSL.
    #
    # Prefer an explicit override if provided, otherwise try common loader names.
    candidates = []
    override = os.environ.get("FIREBIRD_CLIENT_LIBRARY") or os.environ.get("FB_CLIENT_LIBRARY")
    if override:
        candidates.append(override)

    # Common names (Firebird 3-5 typically expose SONAME as libfbclient.so.2).
    candidates.extend(["libfbclient.so", "libfbclient.so.2"])

    # Repo-extracted Firebird 5 client (matches project conventions).
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidates.append(
        os.path.join(
            repo_root,
            "FirebirdLinux",
            "Firebird-5.0.0.1306-0-linux-x64",
            "opt",
            "firebird",
            "lib",
            "libfbclient.so",
        )
    )

    last_err = None
    for c in candidates:
        try:
            ctypes.CDLL(c)
            last_err = None
            break
        except OSError as e:
            last_err = e

    if last_err is not None:
        pytest.skip(
            f"Firebird client library not loadable here (bundle or system FB client missing). "
            f"Tried {candidates!r}. Last error: {last_err}"
        )

    # Basic sanity: module import succeeded.
    assert hasattr(firebird, "connect")
