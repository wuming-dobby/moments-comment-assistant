"""v0.3.2 单测：ocr 封装（fake winsdk 链）+ 浮球 OCR 门控 + 配置回显 + UI 非阻塞。"""
import sys
import threading
import time
from pathlib import Path

from PyQt5 import QtWidgets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ball as ball_mod  # noqa: E402
import ocr  # noqa: E402
import vision  # noqa: E402
from config_window import ConfigWindow  # noqa: E402


# ---------- fake winsdk 链 ----------

class FakeStream:
    def __init__(self):
        self.written = b""

    def seek(self, pos):
        pass


class FakeWriter:
    def __init__(self, stream):
        self._stream = stream

    def write_bytes(self, data):
        self._stream.written = bytes(data)

    async def store_async(self):
        pass

    async def flush_async(self):
        pass


class FakeDecoder:
    @staticmethod
    async def create_async(stream):
        return FakeDecoder()

    async def get_software_bitmap_async(self):
        return object()


class FakeEngine:
    text = "朋友圈"
    created = 0

    @staticmethod
    def try_create_from_user_profile_languages():
        FakeEngine.created += 1
        return FakeEngine()

    async def recognize_async(self, bitmap):
        result = type("R", (), {})()
        result.text = FakeEngine.text
        return result


def _install_fake_winsdk(monkeypatch):
    fake_imaging = type("I", (), {"BitmapDecoder": FakeDecoder})()
    fake_ocr = type("O", (), {"OcrEngine": FakeEngine})()
    fake_streams = type("S", (), {
        "InMemoryRandomAccessStream": FakeStream,
        "DataWriter": FakeWriter,
    })()
    monkeypatch.setattr(ocr, "_wimaging", fake_imaging)
    monkeypatch.setattr(ocr, "_wocr", fake_ocr)
    monkeypatch.setattr(ocr, "_wstreams", fake_streams)
    monkeypatch.setattr(ocr, "_WINSDK_OK", True)


def test_ocr_roundtrip_text(monkeypatch):
    _install_fake_winsdk(monkeypatch)
    FakeEngine.text = "朋友圈 顶部导航"
    assert ocr.ocr_text(b"png-bytes") == "朋友圈 顶部导航"
    assert FakeEngine.created == 1


def test_ocr_unavailable_when_winsdk_missing(monkeypatch):
    monkeypatch.setattr(ocr, "_WINSDK_OK", False)
    try:
        ocr.ocr_text(b"png-bytes")
    except ocr.OcrUnavailable as exc:
        assert "winsdk" in str(exc)
    else:
        raise AssertionError("应抛 OcrUnavailable")


def test_ocr_unavailable_when_no_language_pack(monkeypatch):
    _install_fake_winsdk(monkeypatch)
    monkeypatch.setattr(FakeEngine, "try_create_from_user_profile_languages",
                        staticmethod(lambda: None))
    try:
        ocr.ocr_text(b"png-bytes")
    except ocr.OcrUnavailable as exc:
        assert "语言包" in str(exc)
    else:
        raise AssertionError("应抛 OcrUnavailable")


def test_ocr_unavailable_when_recognize_fails(monkeypatch):
    _install_fake_winsdk(monkeypatch)

    async def boom(self, bitmap):
        raise RuntimeError("引擎内部错误")

    monkeypatch.setattr(FakeEngine, "recognize_async", boom)
    try:
        ocr.ocr_text(b"png-bytes")
    except ocr.OcrUnavailable as exc:
        assert "引擎内部错误" in str(exc)
    else:
        raise AssertionError("应抛 OcrUnavailable")


# ---------- 浮球 OCR 门控 ----------

def _ball(fg=0x30, ocr_fn=None, moments_only=True, find_window=None):
    b = ball_mod.BallOverlay(
        find_window=find_window or (lambda: None),
        rect_of=lambda h: (0, 0, 400, 500),
        win_ok=lambda h: True,
        foreground_window=lambda: fg,
        ocr_fn=ocr_fn,
        grab_strip=lambda h: b"png-bytes",
        poll_ms=10 ** 6,
        moments_only=moments_only,
    )
    return b


def _join(b):
    if b._ocr_thread is not None:
        b._ocr_thread.join(timeout=5)


def test_gate_hides_while_ocr_pending():
    b = _ball(ocr_fn=lambda png: (time.sleep(0.3), "朋友圈")[1])
    b.poll()
    assert not b.isVisible(), "OCR 挂起期间隐藏，避免聊天页闪烁"
    assert b.moments_hwnd() is None
    assert b._ocr_thread is not None and b._ocr_thread.is_alive()


def test_gate_shows_when_keyword_found():
    b = _ball(ocr_fn=lambda png: "朋友圈 顶部导航")
    b.poll()
    _join(b)
    b.poll()
    assert b.isVisible(), "OCR 命中「朋友圈」应显示"
    assert b.moments_hwnd() == 0x30


def test_gate_hides_when_keyword_absent():
    b = _ball(ocr_fn=lambda png: "微信 通讯录 发现")
    b.poll()
    _join(b)
    b.poll()
    assert not b.isVisible(), "非朋友圈页应隐藏"
    assert b.moments_hwnd() is None


def test_gate_restarts_ocr_each_round():
    """结果消费后同一轮 poll 立即重启 OCR：页切换后最多两轮内跟上。"""
    calls = []

    def slow(png):
        time.sleep(0.3)
        calls.append(1)
        return "微信"

    b = _ball(ocr_fn=slow)
    b.poll()
    _join(b)
    b.poll()  # 消费第 1 次结果 → 隐藏，并立即重启
    assert calls == [1]
    assert b._ocr_thread is not None and b._ocr_thread.is_alive(), "新一轮 OCR 已启动"


def test_gate_degrades_to_foreground_show_on_error():
    def boom(png):
        raise RuntimeError("winsdk 挂了")

    b = _ball(ocr_fn=boom)
    b.poll()
    _join(b)
    b.poll()
    assert b.isVisible(), "OCR 异常应降级为前台即显"
    assert b._ocr_degraded
    b.poll()
    assert b._ocr_thread is None, "降级后不再启动 OCR 线程"


def test_gate_degrades_when_grab_strip_fails():
    def boom(hwnd):
        raise RuntimeError("窗口已最小化")

    b = ball_mod.BallOverlay(
        find_window=lambda: None,
        rect_of=lambda h: (0, 0, 400, 500),
        win_ok=lambda h: True,
        foreground_window=lambda: 0x30,
        ocr_fn=lambda png: "朋友圈",
        grab_strip=boom,
        poll_ms=10 ** 6,
    )
    b.poll()
    _join(b)
    b.poll()
    assert b.isVisible(), "截窄带失败也应降级前台即显"
    assert b._ocr_degraded


def test_moments_only_false_skips_ocr():
    calls = []

    def boom(png):
        calls.append(1)
        raise RuntimeError("不该被调")

    b = _ball(ocr_fn=boom, moments_only=False)
    b.poll()
    assert b.isVisible(), "VL_BALL_MOMENTS_ONLY=0 回到 v0.3.1 前台即显"
    assert b.moments_hwnd() == 0x30
    assert calls == [], "OCR 不应被调用"


def test_branch_a_wins_without_ocr():
    calls = []

    def boom(png):
        calls.append(1)
        raise RuntimeError("分支 A 不该走 OCR")

    b = _ball(ocr_fn=boom, find_window=lambda: 0x20)
    b.poll()
    assert b.isVisible(), "独立朋友圈窗直接显示"
    assert b.moments_hwnd() == 0x20
    assert calls == []


# ---------- 配置回显 ----------

def _win(monkeypatch, cfg):
    monkeypatch.setattr(vision, "load_config", lambda env=None, path=None: dict(cfg))
    return ConfigWindow()


def test_config_moments_only_default_on(monkeypatch):
    win = _win(monkeypatch, {})
    try:
        assert win.moments_only_check.isChecked(), "未配置时默认开启"
        assert win._fields()["VL_BALL_MOMENTS_ONLY"] == "1"
    finally:
        win.close()


def test_config_moments_only_readback_off(monkeypatch):
    win = _win(monkeypatch, {"VL_BALL_MOMENTS_ONLY": "0"})
    try:
        assert not win.moments_only_check.isChecked()
        assert win._fields()["VL_BALL_MOMENTS_ONLY"] == "0"
    finally:
        win.close()


def test_config_moments_only_readback_on(monkeypatch):
    win = _win(monkeypatch, {"VL_BALL_MOMENTS_ONLY": "1"})
    try:
        assert win.moments_only_check.isChecked()
        assert win._fields()["VL_BALL_MOMENTS_ONLY"] == "1"
    finally:
        win.close()


# ---------- UI 非阻塞 ----------

def test_ocr_worker_does_not_block_ui():
    ui_tid = threading.get_ident()
    ran_in = {}

    def slow_ocr(png):
        ran_in["tid"] = threading.get_ident()
        time.sleep(0.4)
        return "朋友圈"

    b = _ball(ocr_fn=slow_ocr)
    t0 = time.time()
    b.poll()
    poll_elapsed = time.time() - t0
    assert poll_elapsed < 0.3, "poll 不能等 OCR（%.2fs）" % poll_elapsed
    assert ran_in.get("tid") != ui_tid, "OCR 应在工作线程执行"

    t0 = time.time()
    QtWidgets.QApplication.processEvents()
    assert time.time() - t0 < 0.3, "事件循环不能被 OCR 卡住"

    _join(b)
    b.poll()
    assert b.isVisible()
