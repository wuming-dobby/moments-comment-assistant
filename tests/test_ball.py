"""浮球单测：只读打桩，不碰真微信。"""
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QEvent, QPoint, Qt

import ball


def _spin(ms):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def _ball(hwnd=0x20, rect=(100, 100, 400, 500)):
    state = {"hwnd": hwnd, "rect": rect, "fg": None}
    clicks = []
    b = ball.BallOverlay(
        find_window=lambda: state["hwnd"],
        rect_of=lambda h: state["rect"],
        win_ok=lambda h: state["hwnd"] is not None or h == state.get("fg"),
        foreground_window=lambda: state["fg"],
        poll_ms=10 ** 6,
    )
    b.clicked.connect(lambda: clicks.append(1))
    return b, state, clicks


def _event(kind, x, y, button=Qt.NoButton):
    # 6 参构造：localPos 与 globalPos 同值——拖拽判定用的是 globalPos
    return QtGui.QMouseEvent(kind, QtCore.QPointF(x, y), QtCore.QPointF(x, y),
                             button, button, Qt.NoModifier)


def test_b2_shows_when_moments_window():
    b, _, _ = _ball()
    b.poll()
    assert b.isVisible()
    assert b.moments_hwnd() == 0x20
    assert b.pos() == QPoint(344, 108)  # (400-48-8, 100+8)


def test_b2_hides_when_window_gone():
    b, state, _ = _ball()
    b.poll()
    state["hwnd"] = None
    b.poll()
    _spin(250)  # 等淡出动画走完
    assert not b.isVisible()
    assert b.moments_hwnd() is None


def test_b2_click_emits_signal():
    b, _, clicks = _ball()
    b.poll()
    b.mousePressEvent(_event(QEvent.MouseButtonPress, 5, 5, Qt.LeftButton))
    b.mouseReleaseEvent(_event(QEvent.MouseButtonRelease, 5, 5, Qt.LeftButton))
    assert clicks == [1]


def test_b2_busy_suppresses_click():
    b, _, clicks = _ball()
    b.set_busy(True)
    b.mousePressEvent(_event(QEvent.MouseButtonPress, 5, 5, Qt.LeftButton))
    b.mouseReleaseEvent(_event(QEvent.MouseButtonRelease, 5, 5, Qt.LeftButton))
    assert clicks == []


def test_b2_drag_moves_and_keeps_offset():
    b, state, clicks = _ball()
    b.poll()
    b.mousePressEvent(_event(QEvent.MouseButtonPress, 5, 5, Qt.LeftButton))
    b.mouseMoveEvent(_event(QEvent.MouseMove, 20, 5))
    b.mouseReleaseEvent(_event(QEvent.MouseButtonRelease, 20, 5, Qt.LeftButton))
    assert clicks == []
    assert b.pos() == QPoint(359, 108)  # 344+15
    state["rect"] = (200, 100, 500, 500)
    b.poll()
    assert b.pos() == QPoint(459, 108)  # (500-56,108)+用户拖出的偏移(15,0)


# ---------- v0.3 规格改判（33ef761）：双分支显隐 ----------

def test_b3_fallback_shows_on_main_window_when_no_moments_window():
    """微信 4.x 常态：无独立朋友圈窗，主窗在前台→球锚定主窗右上角。"""
    b, state, _ = _ball(hwnd=None)
    state["fg"] = 0x30
    state["rect"] = (200, 150, 600, 700)
    b.poll()
    assert b.isVisible(), "微信前台时浮球该显示"
    assert b.moments_hwnd() == 0x30
    assert b.pos() == QPoint(600 - 48 - 8, 150 + 8)  # 主窗右上角内侧


def test_b3_fallback_hides_when_wechat_not_foreground():
    b, state, _ = _ball(hwnd=None)
    state["fg"] = 0x30
    b.poll()
    assert b.isVisible()
    state["fg"] = None  # 微信最小化/失焦
    b.poll()
    _spin(250)
    assert not b.isVisible(), "微信不在前台且无独立朋友圈窗时浮球该藏"
    assert b.moments_hwnd() is None


def test_b3_moments_window_wins_over_fallback():
    """分支 A 优先：独立朋友圈窗存在时锚定它，不用主窗。"""
    b, state, _ = _ball(hwnd=0x20, rect=(100, 100, 400, 500))
    state["fg"] = 0x30
    b.poll()
    assert b.moments_hwnd() == 0x20
    assert b.pos() == QPoint(344, 108)
