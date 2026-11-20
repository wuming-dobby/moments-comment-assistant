"""A6 配置字段级合并 + 旧配置迁移。"""
import json

import paths
import vision


def test_env_overrides_only_same_field(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    target.write_text(json.dumps({"VL_API_KEY": "file-key", "VL_MODEL": "file-model"}),
                      encoding="utf-8")
    monkeypatch.setattr(paths, "LEGACY_CONFIG", tmp_path / "none.json")

    cfg = vision.load_config(env={"VL_API_KEY": "env-key"}, path=target)

    assert cfg["VL_API_KEY"] == "env-key"      # env 覆盖同名键
    assert cfg["VL_MODEL"] == "file-model"     # 其余字段仍取文件（v0.1 会丢）


def test_empty_env_value_ignored(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    target.write_text(json.dumps({"VL_MODEL": "m"}), encoding="utf-8")
    monkeypatch.setattr(paths, "LEGACY_CONFIG", tmp_path / "none.json")

    cfg = vision.load_config(env={"VL_MODEL": "", "VL_API_BASE": ""}, path=target)
    assert cfg["VL_MODEL"] == "m"
    assert "VL_API_BASE" not in cfg


def test_legacy_config_migrated_once(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy" / "config.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"VL_API_KEY": "k", "VL_MODEL": "m"}), encoding="utf-8")
    target = tmp_path / "appdata" / "config.json"
    monkeypatch.setattr(paths, "LEGACY_CONFIG", legacy)

    cfg = vision.load_config(env={}, path=target)

    assert cfg == {"VL_API_KEY": "k", "VL_MODEL": "m"}
    assert target.exists()
    assert not legacy.exists()
    assert legacy.with_name("config.json.migrated").exists()


def test_missing_everything_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LEGACY_CONFIG", tmp_path / "none.json")
    assert vision.load_config(env={}, path=tmp_path / "missing.json") == {}
