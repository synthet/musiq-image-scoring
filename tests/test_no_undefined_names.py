"""Class-wide guard against NameError regressions in modules/.

Commit 4e2cac3 ("split modules/api into domain routers and extract runner batch
helpers") mechanically lifted code into new functions without carrying the names
those bodies referenced, leaving 57 undefined names across modules/. Two of them
broke indexing outright; the rest degraded silently behind broad `except
Exception` handlers.

Ruff's F821 catches the whole class statically. Scoped to modules/ — scripts/
has pre-existing F821 findings that are out of scope here.
"""
import shutil
import subprocess

import pytest

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_no_undefined_names_in_modules():
    ruff = shutil.which("ruff")
    if not ruff:
        pytest.skip("ruff not installed; CI enforces this via lint-f821 workflow")

    proc = subprocess.run(
        [ruff, "check", "--select", "F821", "--output-format=concise", "modules/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "Undefined names found in modules/ — these become NameError at runtime, "
        "often masked by broad except handlers:\n" + (proc.stdout or proc.stderr)
    )
