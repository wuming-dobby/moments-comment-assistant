"""A8 配置页：人设问卷四字段与备用通道折叠区的回填/保存映射（offscreen 打桩）。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

import vision
from config_window import ConfigWindow


def _app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


FULL_CFG = {
    "VL_API_BASE": "https://main.test/v1",
    "VL_API_KEY": "main-key",
    "VL_MODEL": "main-vl",
    "VL_PERSONA_GENDER": "男",
    "VL_PERSONA_STYLE": "幽默调侃",
    "VL_PERSONA_CATCHPHRASE": "哈哈哈",
    "VL_PERSONA_CLOSENESS": "很熟",
    "VL_FALLBACK_API_BASE": "https://fb.test/v1",
    "VL_FALLBACK_KEY": "fb-key",
    "VL_FALLBACK_MODEL": "fb-vl",
}


def _window(monkeypatch, cfg):
    monkeypatch.setattr(vision, "load_config", lambda env=None, path=None: dict(cfg))
    return ConfigWindow()


def test_load_backfills_persona_and_fallback(monkeypatch):
    _app()
    win = _window(monkeypatch, FULL_CFG)
    try:
        assert win.gender_combo.currentData() == "男"
        assert win.style_combo.currentData() == "幽默调侃"
        assert win.catchphrase_edit.text() == "哈哈哈"
        assert win.closeness_combo.currentData() == "很熟"
        assert win.fallback_group.isChecked(), "配过备用通道时应自动勾选"
        assert win.fb_base_edit.text() == "https://fb.test/v1"
        assert win.fb_key_edit.text() == "fb-key"
        assert win.fb_model_edit.text() == "fb-vl"
    finally:
        win.close()


def test_defaults_when_config_empty(monkeypatch):
    _app()
    win = _window(monkeypatch, {})
    try:
        assert win.gender_combo.currentData() == ""          # 不填
        assert win.style_combo.currentData() == "温和真诚"    # 默认温和真诚
        assert win.closeness_combo.currentData() == "一般"    # 默认一般
        assert not win.fallback_group.isChecked(), "未配过备用通道时不该勾选"
    finally:
        win.close()


def test_fields_roundtrip_with_fallback_on(monkeypatch):
    _app()
    win = _window(monkeypatch, {})
    try:
        win.gender_combo.setCurrentIndex(win.gender_combo.findData("女"))
        win.style_combo.setCurrentIndex(win.style_combo.findData("简洁干脆"))
        win.catchphrase_edit.setText(" 好家伙 ")
        win.closeness_combo.setCurrentIndex(win.closeness_combo.findData("偏同事客户"))
        win.fallback_group.setChecked(True)
        win.fb_base_edit.setText("https://fb.test/v1")
        win.fb_key_edit.setText("fb-key")
        win.fb_model_edit.setText("fb-vl")

        fields = win._fields()

        assert fields["VL_PERSONA_GENDER"] == "女"
        assert fields["VL_PERSONA_STYLE"] == "简洁干脆"
        assert fields["VL_PERSONA_CATCHPHRASE"] == "好家伙", "口头禅应 strip 首尾空格"
        assert fields["VL_PERSONA_CLOSENESS"] == "偏同事客户"
        assert fields["VL_FALLBACK_API_BASE"] == "https://fb.test/v1"
        assert fields["VL_FALLBACK_KEY"] == "fb-key"
        assert fields["VL_FALLBACK_MODEL"] == "fb-vl"
    finally:
        win.close()


def test_fields_clears_fallback_when_unchecked(monkeypatch):
    _app()
    win = _window(monkeypatch, FULL_CFG)
    try:
        win.fallback_group.setChecked(False)
        fields = win._fields()
        for key in vision.FALLBACK_KEYS:
            assert fields[key] == "", "%s 未勾选备用时应存空串以关闭备用" % key
    finally:
        win.close()
