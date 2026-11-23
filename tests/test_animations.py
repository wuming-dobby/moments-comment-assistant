"""模块⑤动画单测：VL_ANIMATIONS=0 全关（直接终态、无 anim 对象），开时动画能跑到终值。"""
from PyQt5 import QtCore, QtGui, QtWidgets

import vision
from ball import OPACITY, SIZE, BallOverlay
from config_window import ConfigWindow
from overlay import AnimatedButton


def _spin(ms):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def _cfg_off(monkeypatch):
    monkeypatch.setattr(vision, "load_config", lambda *a, **k: {"VL_ANIMATIONS": "0"})


def _cfg_on(monkeypatch):
    monkeypatch.setattr(vision, "load_config", lambda *a, **k: {"VL_ANIMATIONS": "1"})


def _ball(hwnd=0x20, rect=(100, 100, 400, 500)):
    return BallOverlay(find_window=lambda: hwnd, rect_of=lambda h: rect,
                       win_ok=lambda h: True, foreground_window=lambda: None,
                       poll_ms=10 ** 6)


def _event(t):
    return QtCore.QEvent(t)


def _mouse(t, buttons):
    return QtGui.QMouseEvent(t, QtCore.QPointF(1, 1), QtCore.Qt.LeftButton,
                             buttons, QtCore.Qt.NoModifier)


def test_anim_off_button_direct_colors(monkeypatch):
    _cfg_off(monkeypatch)
    btn = AnimatedButton("测")
    assert "background-color: #f2f2f2" in btn.styleSheet()
    btn.enterEvent(_event(QtCore.QEvent.Enter))
    assert "background-color: #e0f5e9" in btn.styleSheet()
    btn.mousePressEvent(_mouse(QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton))
    assert "background-color: #c8eccf" in btn.styleSheet()
    btn.mouseReleaseEvent(_mouse(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton))
    assert "background-color: #f2f2f2" in btn.styleSheet()
    btn.leaveEvent(_event(QtCore.QEvent.Leave))
    assert "background-color: #f2f2f2" in btn.styleSheet()
    assert btn._anim is None


def test_anim_off_ball_fade_direct(monkeypatch):
    _cfg_off(monkeypatch)
    ball = _ball()
    ball.poll()
    assert ball.isVisible()
    # offscreen 平台 windowOpacity 按 8 位 alpha 存储（0.85→216/255），容差给 0.01
    assert abs(ball.windowOpacity() - OPACITY) < 0.01
    assert ball._anim is None
    ball._find_window = lambda: None
    ball.poll()
    assert not ball.isVisible()
    assert ball._anim is None


def test_anim_off_ball_hover_direct(monkeypatch):
    _cfg_off(monkeypatch)
    ball = _ball()
    ball.poll()
    ball.enterEvent(_event(QtCore.QEvent.Enter))
    assert ball.width() == round(SIZE * 1.08)
    assert ball._anim is None
    ball.leaveEvent(_event(QtCore.QEvent.Leave))
    assert ball.width() == SIZE
    assert ball._anim is None


def test_anim_busy_ball_skips_hover(monkeypatch):
    _cfg_off(monkeypatch)
    ball = _ball()
    ball.poll()
    ball.set_busy(True)
    ball.enterEvent(_event(QtCore.QEvent.Enter))
    assert ball.width() == SIZE
    assert ball._anim is None


def test_anim_off_config_fade_direct(monkeypatch):
    _cfg_off(monkeypatch)
    win = ConfigWindow()
    try:
        win.show()
        assert win._faded_in
        assert abs(win.windowOpacity() - 1.0) < 1e-9
        assert win._anim is None
    finally:
        win.close()


def test_anim_on_button_hover_interpolates(monkeypatch):
    _cfg_on(monkeypatch)
    btn = AnimatedButton("测")
    btn.enterEvent(_event(QtCore.QEvent.Enter))
    assert btn._anim is not None
    _spin(250)
    assert "background-color: #e0f5e9" in btn.styleSheet()


def test_anim_on_config_fade(monkeypatch):
    _cfg_on(monkeypatch)
    win = ConfigWindow()
    try:
        win.show()
        assert win._faded_in
        assert win._anim is not None
        _spin(300)
        assert abs(win.windowOpacity() - 1.0) < 0.01
    finally:
        win.close()


def test_anim_on_ball_fade_and_hover_scale(monkeypatch):
    _cfg_on(monkeypatch)
    ball = _ball()
    ball.poll()
    assert ball.isVisible()
    assert ball._anim is not None
    _spin(250)
    assert abs(ball.windowOpacity() - OPACITY) < 0.01
    ball.enterEvent(_event(QtCore.QEvent.Enter))
    assert ball._anim is not None
    _spin(250)
    assert ball.width() == round(SIZE * 1.08)
    ball.leaveEvent(_event(QtCore.QEvent.Leave))
    _spin(250)
    assert ball.width() == SIZE
