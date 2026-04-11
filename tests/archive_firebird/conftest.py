"""Archive Firebird integration tests — require local Firebird client/tools."""

from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    root = Path(config.rootpath) / "tests" / "archive_firebird"
    for item in items:
        path = getattr(item, "path", None)
        if path is None:
            continue
        try:
            path.relative_to(root)
        except ValueError:
            continue
        item.add_marker(pytest.mark.firebird)
