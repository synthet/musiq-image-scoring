"""Path allowlist resolution for modules.ui.security."""

import json
import os

import pytest

import modules.config as cfg
from modules.ui import security as ui_security


def test_validate_file_path_uses_system_allowed_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    image = allowed_root / "photo.jpg"
    image.write_text("x", encoding="utf-8")

    (tmp_path / "config.json").write_text(
        json.dumps({"system": {"allowed_paths": [str(allowed_root)]}}),
        encoding="utf-8",
    )

    ui_security._ALLOWED_IMAGE_ROOTS = None
    monkeypatch.setattr(cfg, "get_default_allowed_paths", lambda: [])

    resolved = ui_security._validate_file_path(str(image))
    assert resolved == os.path.realpath(str(image))
