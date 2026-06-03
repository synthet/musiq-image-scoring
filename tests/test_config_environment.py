"""Tests for config.json + environment.json merge."""

import json

import modules.config as cfg


def test_load_config_caches_until_mtime_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")
    cfg.invalidate_config_cache()
    (tmp_path / "config.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    first = cfg.load_config()
    second = cfg.load_config()
    assert first is second
    (tmp_path / "config.json").write_text(json.dumps({"a": 2}), encoding="utf-8")
    cfg.invalidate_config_cache()
    third = cfg.load_config()
    assert third["a"] == 2


def test_environment_json_mtime_invalidates_cache(monkeypatch, tmp_path):
    """An environment.json edit must bust the cache even if config.json is untouched."""
    import os

    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")
    cfg.invalidate_config_cache()
    (tmp_path / "config.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (tmp_path / "environment.json").write_text(json.dumps({"a": 2}), encoding="utf-8")
    os.utime(tmp_path / "config.json", (1000, 1000))
    os.utime(tmp_path / "environment.json", (1000, 1000))
    first = cfg.load_config()
    assert first["a"] == 2  # environment overrides config

    # Change environment.json only (new mtime); no explicit invalidate.
    (tmp_path / "environment.json").write_text(json.dumps({"a": 3}), encoding="utf-8")
    os.utime(tmp_path / "environment.json", (2000, 2000))
    second = cfg.load_config()
    assert second["a"] == 3


def test_deep_merge_nested_and_scalar_override(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "scoring_input_path": "/from/config",
                "database": {"postgres": {"host": "h1", "port": 5432}},
                "system": {"allowed_paths": ["C:/"]},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps(
            {
                "scoring_input_path": "/from/env",
                "database": {"postgres": {"host": "h2"}},
            }
        ),
        encoding="utf-8",
    )

    merged = cfg.load_config()
    assert merged["scoring_input_path"] == "/from/env"
    assert merged["database"]["postgres"]["host"] == "h2"
    assert merged["database"]["postgres"]["port"] == 5432
    assert merged["system"]["allowed_paths"] == ["C:/"]


def test_environment_replaces_list(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps({"system": {"allowed_paths": ["C:/"]}}),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps({"system": {"allowed_paths": ["/mnt/d/"]}}),
        encoding="utf-8",
    )

    merged = cfg.load_config()
    assert merged["system"]["allowed_paths"] == ["/mnt/d/"]


def test_save_config_value_writes_config_only_not_merged_env(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps({"foo": 1, "bar": {"x": 1}}),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps({"bar": {"x": 99}}),
        encoding="utf-8",
    )

    cfg.save_config_value("foo", 2)
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["foo"] == 2
    assert raw["bar"]["x"] == 1


def test_validate_config_accepts_environment_only(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "environment.json").write_text(
        json.dumps(
            {
                "database": {
                    "engine": "postgres",
                    "postgres": {
                        "host": "127.0.0.1",
                        "port": 5432,
                        "dbname": "image_scoring",
                        "user": "postgres",
                        "password": "postgres",
                    },
                },
                "processing": {
                    "prep_queue_size": 50,
                    "scoring_queue_size": 10,
                    "result_queue_size": 50,
                },
            }
        ),
        encoding="utf-8",
    )

    out = cfg.validate_config()
    assert out["ok"] is True


def test_merge_and_save_preserves_scoring_models(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "scoring": {
                    "models": {"liqe": {"enabled": True, "shadow": False}},
                    "fusion": {"general": {"liqe": 1.0}},
                    "force_rescore_default": True,
                }
            }
        ),
        encoding="utf-8",
    )

    cfg.merge_and_save_config_section(
        "scoring",
        {"force_rescore_default": False, "default_sort_by": "score_general"},
    )
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    scoring = raw["scoring"]
    assert scoring["force_rescore_default"] is False
    assert scoring["default_sort_by"] == "score_general"
    assert scoring["models"]["liqe"]["enabled"] is True
    assert scoring["fusion"]["general"]["liqe"] == 1.0


def test_get_allowed_paths_prefers_system(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps({"system": {"allowed_paths": ["C:/Photos/"]}, "allowed_paths": ["D:/"]}),
        encoding="utf-8",
    )
    assert cfg.get_allowed_paths_from_config() == ["C:/Photos/"]


def test_get_allowed_paths_legacy_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(json.dumps({"allowed_paths": ["D:/"]}), encoding="utf-8")
    assert cfg.get_allowed_paths_from_config() == ["D:/"]


def test_validate_config_accepts_api_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "database": {
                    "engine": "api",
                    "api_url": "http://127.0.0.1:7860",
                },
                "processing": {
                    "prep_queue_size": 50,
                    "scoring_queue_size": 10,
                    "result_queue_size": 50,
                },
            }
        ),
        encoding="utf-8",
    )
    out = cfg.validate_config()
    assert out["ok"] is True


def test_validate_config_api_engine_requires_url(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")

    (tmp_path / "config.json").write_text(
        json.dumps({"database": {"engine": "api"}, "processing": {"prep_queue_size": 50}}),
        encoding="utf-8",
    )
    out = cfg.validate_config()
    assert out["ok"] is False
    assert any("api_url" in issue for issue in out["issues"])
