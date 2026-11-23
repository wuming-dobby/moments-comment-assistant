# -*- coding: utf-8 -*-
"""v0.3.1 单测：max_tokens=512 / 浮球新锚点常量 / VL_SHOW_OVERLAY 备用浮窗开关。"""
import json

import capture
import vision
from config_window import ConfigWindow
from overlay import CommentOverlay


# ---------- 1. max_tokens 512（阻断 bug：推理模型 40 被思考烧光） ----------

def test_max_tokens_is_512():
    import test_vision_prompt  # 复用其打桩基建
    # 直接查常量语义：调用参数在 generate_comment 里写死，用打桩 client 抓
    import types

    calls = {}

    class FakeClient:
        def __init__(self, api_key=None, base_url=None):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create))

        def _create(self, model=None, messages=None, **kwargs):
            calls.update(kwargs)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content="好评论"))])

    saved = vision.OpenAI
    vision.OpenAI = FakeClient
    try:
        import os
        png = os.path.join(os.path.dirname(__file__), "_t512.png")
        from PIL import Image
        Image.new("RGB", (64, 64), "white").save(png)
        vision.generate_comment(png, cfg={"VL_API_KEY": "k", "VL_MODEL": "m"})
        os.unlink(png)
    finally:
        vision.OpenAI = saved
    assert calls["max_tokens"] == 512


# ---------- 2. 浮球缩小＋新锚点 ----------

def test_ball_size_and_margins():
    import ball
    assert ball.SIZE == 36
    assert ball.RIGHT_MARGIN == 48
    assert ball.TOP_MARGIN == 64


# ---------- 3. 备用浮窗默认隐藏，VL_SHOW_OVERLAY 控制 ----------

def _overlay(monkeypatch, foreground=True):
    monkeypatch.setattr(capture, "wechat_in_foreground", lambda **kw: foreground)
    return CommentOverlay()


def test_overlay_hidden_by_default_even_wechat_foreground(monkeypatch):
    o = _overlay(monkeypatch, foreground=True)
    assert o.auto_show is False, "v0.3.1 默认关"
    assert o.want_visible() is False, "微信前台也不自动显示右下角浮窗"


def test_overlay_auto_show_on(monkeypatch):
    o = _overlay(monkeypatch, foreground=True)
    o.auto_show = True
    assert o.want_visible() is True


def test_overlay_auto_show_ignored_when_wechat_background(monkeypatch):
    o = _overlay(monkeypatch, foreground=False)
    o.auto_show = True
    assert o.want_visible() is False


def test_overlay_pinned_unaffected_by_auto_show(monkeypatch):
    o = _overlay(monkeypatch, foreground=False)
    o.pinned = True
    assert o.want_visible() is True, "托盘唤起不受开关影响"


def test_config_show_overlay_roundtrip(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.json"
    monkeypatch.setattr(vision, "load_config", lambda env=None, path=None: {"VL_SHOW_OVERLAY": "1"})
    win = ConfigWindow()
    try:
        assert win.show_overlay_check.isChecked(), "VL_SHOW_OVERLAY=1 应回显勾选"
        assert win._fields()["VL_SHOW_OVERLAY"] == "1"
        win.show_overlay_check.setChecked(False)
        assert win._fields()["VL_SHOW_OVERLAY"] == "0"
    finally:
        win.close()


def test_config_show_overlay_default_off(monkeypatch):
    monkeypatch.setattr(vision, "load_config", lambda env=None, path=None: {})
    win = ConfigWindow()
    try:
        assert not win.show_overlay_check.isChecked(), "默认不勾选"
        assert win._fields()["VL_SHOW_OVERLAY"] == "0"
    finally:
        win.close()
