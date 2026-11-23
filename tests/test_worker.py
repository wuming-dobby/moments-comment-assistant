"""GenerateWorker 单测：生成在子线程执行，空结果/异常走 fail 信号，_run_generate 全链路打桩。"""
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

logging.getLogger("MomentsAssistant").addHandler(logging.NullHandler())


def _spin_until(pred, timeout_ms=5000):
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        QtWidgets.QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.005)
    return False


class FakeOverlay:
    def __init__(self):
        self.hidden = 0
        self.resets = 0
        self.polled = 0
        self.toasts = []

    def hide(self):
        self.hidden += 1

    def show_toast(self, text):
        self.toasts.append(text)

    def reset_button(self):
        self.resets += 1

    def poll(self):
        self.polled += 1


def test_w4_generation_runs_off_ui_thread(monkeypatch):
    def slow_gen(path):
        time.sleep(0.3)
        return "周末的日落真好看"

    monkeypatch.setattr(main.vision, "generate_comment", slow_gen)
    results = []
    w = main.GenerateWorker("shot.png")
    w.ok.connect(lambda d: results.append(d))
    w.start()
    assert w.isRunning(), "start() 返回时线程该已在跑"
    assert _spin_until(lambda: results), "ok 信号超时"
    assert results == ["周末的日落真好看"]
    assert w.wait(1000)  # 测试里没连 deleteLater，wait 安全


def test_w4_empty_draft_reports_fail(monkeypatch):
    monkeypatch.setattr(main.vision, "generate_comment", lambda path: "")
    errors = []
    w = main.GenerateWorker("shot.png")
    w.fail.connect(lambda e: errors.append(e))
    w.start()
    assert _spin_until(lambda: errors), "fail 信号超时"
    assert errors == ["模型返回空内容"]
    assert w.wait(1000)


def test_w4_exception_reports_fail(monkeypatch):
    def boom(path):
        raise RuntimeError("VL 调用失败：429")

    monkeypatch.setattr(main.vision, "generate_comment", boom)
    errors = []
    w = main.GenerateWorker("shot.png")
    w.fail.connect(lambda e: errors.append(e))
    w.start()
    assert _spin_until(lambda: errors), "fail 信号超时"
    assert errors == ["VL 调用失败：429"]
    assert w.wait(1000)


def test_r4_overlay_happy_path(monkeypatch):
    copied = []
    monkeypatch.setattr(main.capture, "capture_wechat", lambda: "shot.png")
    monkeypatch.setattr(main.vision, "generate_comment", lambda path: "周末的日落真好看")
    monkeypatch.setattr(main.pyperclip, "copy", copied.append)
    ov = FakeOverlay()
    main._run_generate(ov)
    assert _spin_until(lambda: copied), "生成回调超时"
    assert copied == ["周末的日落真好看"]
    assert "草稿已复制到剪贴板，去微信里粘贴" in ov.toasts
    assert ov.hidden == 1 and ov.resets == 1 and ov.polled == 1
    assert getattr(ov, "_worker", None) is not None


def test_r4_capture_failure_no_worker(monkeypatch):
    def boom():
        raise RuntimeError("微信窗口已最小化")

    monkeypatch.setattr(main.capture, "capture_wechat", boom)
    ov = FakeOverlay()
    main._run_generate(ov)
    assert ov.toasts == ["失败：微信窗口已最小化"]
    assert ov.resets == 1 and ov.polled == 1
    assert getattr(ov, "_worker", None) is None


def test_r4_worker_failure_resets(monkeypatch):
    monkeypatch.setattr(main.capture, "capture_wechat", lambda: "shot.png")

    def boom(path):
        raise RuntimeError("VL 调用失败：超时")

    monkeypatch.setattr(main.vision, "generate_comment", boom)
    ov = FakeOverlay()
    main._run_generate(ov)
    assert _spin_until(lambda: ov.toasts), "fail 回调超时"
    assert ov.toasts == ["失败：VL 调用失败：超时"]
    assert ov.resets == 1 and ov.polled == 1
