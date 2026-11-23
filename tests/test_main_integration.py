"""main 接线集成单测（离线打桩）：浮窗让位浮球、浮球生成链路（异步 worker）。"""
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets  # noqa: E402

import main  # noqa: E402
import overlay as overlay_mod  # noqa: E402

logging.getLogger("MomentsAssistant").addHandler(logging.NullHandler())


def _spin_until(pred, timeout_ms=5000):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        QtWidgets.QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.005)
    return False


class FakeTray:
    def __init__(self):
        self.messages = []

    def showMessage(self, title, text, icon=None, msecs=None):
        self.messages.append(text)


class FakeBall:
    def __init__(self, hwnd):
        self._hwnd = hwnd
        self.busy = []

    def moments_hwnd(self):
        return self._hwnd

    def set_busy(self, busy):
        self.busy.append(busy)


# ---------- 浮窗让位浮球 ----------

def test_m3_overlay_yields_to_ball(monkeypatch):
    monkeypatch.setattr(overlay_mod.capture, "wechat_in_foreground", lambda: True)
    ov = overlay_mod.CommentOverlay(moments_finder=lambda: 0x10)
    try:
        assert not ov.want_visible(), "朋友圈窗开着：浮球接管，浮窗让位"
    finally:
        ov.close()


def test_m3_overlay_shows_without_moments_window(monkeypatch):
    # v0.3.1: 微信前台不再自动显示浮窗，须 VL_SHOW_OVERLAY 开关（auto_show=True）
    monkeypatch.setattr(overlay_mod.capture, "wechat_in_foreground", lambda **kw: True)
    ov = overlay_mod.CommentOverlay(moments_finder=lambda: None)
    try:
        assert not ov.want_visible(), "默认隐藏"
        ov.auto_show = True
        assert ov.want_visible()
    finally:
        ov.close()


def test_m3_overlay_shows_without_finder(monkeypatch):
    monkeypatch.setattr(overlay_mod.capture, "wechat_in_foreground", lambda **kw: True)
    ov = overlay_mod.CommentOverlay()
    try:
        assert not ov.want_visible(), "v0.3.1 默认隐藏"
        ov.auto_show = True
        assert ov.want_visible()
    finally:
        ov.close()


# ---------- 浮球生成链路 ----------

def test_gb_happy_path(monkeypatch):
    seen, copied = [], []
    monkeypatch.setattr(main.capture, "find_moments_window", lambda: None)
    monkeypatch.setattr(main.capture, "capture_wechat", lambda hwnd: seen.append(hwnd) or "shot.png")
    monkeypatch.setattr(main.vision, "generate_comment", lambda path: "这色泽绝了")
    monkeypatch.setattr(main.pyperclip, "copy", copied.append)
    ball, tray = FakeBall(0x20), FakeTray()
    main.generate_from_ball(ball, tray)
    assert _spin_until(lambda: copied), "生成回调超时"
    assert seen == [0x20]
    assert copied == ["这色泽绝了"]
    assert tray.messages == ["草稿已复制到剪贴板，去微信里粘贴"]
    assert ball.busy == [True, False]


def test_gb_no_moments_window(monkeypatch):
    monkeypatch.setattr(main.capture, "find_moments_window", lambda: None)
    ball, tray = FakeBall(None), FakeTray()
    main.generate_from_ball(ball, tray)
    assert tray.messages == ["没找到微信窗口（先打开微信）"]
    assert ball.busy == []


def test_gb_capture_failure_no_copy(monkeypatch):
    copied = []

    def boom(hwnd):
        raise RuntimeError("微信窗口已最小化")

    monkeypatch.setattr(main.capture, "capture_wechat", boom)
    monkeypatch.setattr(main.pyperclip, "copy", copied.append)
    ball, tray = FakeBall(0x20), FakeTray()
    main.generate_from_ball(ball, tray)
    assert tray.messages == ["失败：微信窗口已最小化"]
    assert copied == []
    assert ball.busy == []


def test_gb_worker_failure_resets_busy(monkeypatch):
    monkeypatch.setattr(main.capture, "capture_wechat", lambda hwnd: "shot.png")

    def boom(path):
        raise RuntimeError("VL 调用失败：超时")

    monkeypatch.setattr(main.vision, "generate_comment", boom)
    ball, tray = FakeBall(0x20), FakeTray()
    main.generate_from_ball(ball, tray)
    assert _spin_until(lambda: tray.messages), "fail 回调超时"
    assert tray.messages == ["失败：VL 调用失败：超时"]
    assert ball.busy == [True, False]
