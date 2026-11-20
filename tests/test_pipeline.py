"""自检：python tests/test_pipeline.py

1) 没有微信窗口 / 微信最小化 → 浮窗不显示；微信在前台 → 浮窗显示
2) 配好 API（接口打桩）→ 返回非空评论草稿；没配 API → 明确报错
"""
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import win32gui  # noqa: E402
from PyQt5 import QtWidgets  # noqa: E402

import capture  # noqa: E402
import overlay as overlay_mod  # noqa: E402
import vision  # noqa: E402

FAKE_HWND = 0x1234


def check_overlay():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    saved = (capture.find_wechat_window, win32gui.GetForegroundWindow, win32gui.IsIconic)
    win = overlay_mod.CommentOverlay()
    try:
        capture.find_wechat_window = lambda: None
        win.poll()
        assert not win.isVisible(), "没有微信窗口时浮窗不该显示"

        capture.find_wechat_window = lambda: FAKE_HWND
        win32gui.GetForegroundWindow = lambda: FAKE_HWND
        win32gui.IsIconic = lambda hwnd: False
        win.poll()
        assert win.isVisible(), "微信在前台时浮窗该显示"

        win32gui.IsIconic = lambda hwnd: True
        win.poll()
        assert not win.isVisible(), "微信最小化时浮窗该藏起来"
    finally:
        capture.find_wechat_window, win32gui.GetForegroundWindow, win32gui.IsIconic = saved
        win.close()
    print("PASS 浮窗跟随微信窗口（无窗口 / 前台 / 最小化）")


def check_vision_with_stub():
    calls = {}

    class FakeClient:
        def __init__(self, api_key=None, base_url=None):
            calls["api_key"], calls["base_url"] = api_key, base_url
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create)
            )

        def _create(self, model=None, messages=None, **kwargs):
            calls["model"], calls["messages"] = model, messages
            reply = "周末的日落真好看，下次叫上我一起。"
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=" " + reply + " "))]
            )

    png = ROOT / "tests" / "_stub_shot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n stub-bytes-not-a-real-png")
    saved = vision.OpenAI
    vision.OpenAI = FakeClient
    try:
        draft = vision.generate_comment(
            str(png),
            cfg={"VL_API_KEY": "test-key", "VL_MODEL": "test-vl", "VL_API_BASE": "https://example.test/v1"},
        )
    finally:
        vision.OpenAI = saved
        png.unlink()

    assert draft == "周末的日落真好看，下次叫上我一起。", "返回值应是被裁掉首尾空格的评论文本，实际：%r" % draft
    assert calls["api_key"] == "test-key" and calls["model"] == "test-vl"
    assert calls["base_url"] == "https://example.test/v1"
    sent = calls["messages"][1]["content"][1]["image_url"]["url"]
    assert sent.startswith("data:image/png;base64,"), "截图应随请求一起发出"
    print("PASS 配置齐全时 VL 返回非空评论：%s" % draft)


def check_vision_needs_config():
    saved_path, saved_env = vision.CONFIG_PATH, dict(os.environ)
    vision.CONFIG_PATH = ROOT / "_no_such_config.json"
    for key in [k for k in os.environ if k.startswith("VL_")]:
        del os.environ[key]
    try:
        vision.generate_comment("unused.png", cfg={})
    except RuntimeError as exc:
        assert "VL_API_KEY" in str(exc)
        print("PASS 未配置 API 时明确报错：%s" % exc)
    else:
        raise AssertionError("缺配置该报错，不该静默发出请求")
    finally:
        vision.CONFIG_PATH = saved_path
        os.environ.clear()
        os.environ.update(saved_env)


if __name__ == "__main__":
    for step in (check_overlay, check_vision_with_stub, check_vision_needs_config):
        step()
    print("三项自检全部通过")
