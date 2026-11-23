"""浮球模块：48px 半透明圆球，点它生成评论草稿。

显隐双分支（v0.3 规格改判 33ef761）：
- 分支 A：有独立朋友圈窗口（旧版微信）→ 锚定该窗右上角内侧；
- 分支 B：微信 4.x 无独立朋友圈窗（常态）→ 微信主窗在前台时锚定主窗右上角内侧。
  v0.3.2（§八 方案A）：分支 B 再经 OCR 门控——后台线程截主窗顶部窄带，
  系统 OCR 命中「朋友圈」才显示；OCR 不可用则降级为「前台即显」。
微信最小化/关闭 → 淡出隐藏。1s 轮询，可拖拽；拖过后按锚点偏移跟随窗口移动。
置顶但不抢焦点（WindowDoesNotAcceptFocus + WA_ShowWithoutActivating）。
"""
import threading

import win32gui
from PyQt5 import QtCore, QtGui, QtWidgets

import capture
import ocr
import paths
from overlay import animations_enabled

SIZE = 36          # v0.3.1: 48→36，用户嫌大
RIGHT_MARGIN = 48  # v0.3.1: 锚点离窗口右上角一段距离（窗内右边距）
TOP_MARGIN = 64    # v0.3.1: 窗内上边距（避开标题栏）
OPACITY = 0.85
FADE_MS = 150


def _default_rect_of(hwnd):
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def _default_foreground_wechat():
    """分支 B：微信主窗在前台且未最小化时返回其 hwnd，否则 None。只读枚举。"""
    try:
        if capture.wechat_in_foreground():
            return capture.foreground_hwnd() or None
    except Exception:
        pass
    return None


class BallOverlay(QtWidgets.QWidget):
    clicked = QtCore.pyqtSignal()
    shown = QtCore.pyqtSignal()

    def __init__(self, *, find_window=None, rect_of=None, win_ok=None,
                 foreground_window=None, poll_ms=1000,
                 ocr_fn=None, grab_strip=None, moments_only=True):
        super().__init__()
        self._find_window = find_window or capture.find_moments_window
        self._rect_of = rect_of or _default_rect_of
        self._win_ok = win_ok or win32gui.IsWindow
        self._foreground_window = foreground_window or _default_foreground_wechat
        self._ocr_fn = ocr_fn or ocr.ocr_text
        self._grab_strip = grab_strip or capture.grab_top_strip
        self.moments_only = moments_only
        self._hwnd = None
        self._busy = False
        self._dragged = False
        self._drag_offset = None
        self._press_global = None
        self._press_pos = None
        self._moved = False
        self._anim = None
        self._ocr_thread = None
        self._ocr_result = None
        self._last_hit = False
        self._ocr_degraded = False
        self._ocr_warned = False

        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        # 不用 setFixedSize：hover 缩放靠 geometry 动画，固定尺寸会把它钳回去
        self.setGeometry(0, 0, SIZE, SIZE)
        self.setWindowOpacity(0.0)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(poll_ms)

    # ---------- 状态 ----------

    def set_busy(self, busy):
        self._busy = busy
        self.update()

    def moments_hwnd(self):
        return self._hwnd

    # ---------- 轮询与锚定 ----------

    def poll(self):
        # 分支 A：独立朋友圈窗（旧版微信）
        hwnd = self._find_window()
        if not (hwnd and self._win_ok(hwnd)):
            # 分支 B：微信 4.x 常态——主窗在前台即锚定主窗
            hwnd = self._foreground_window()
            if hwnd and not self._win_ok(hwnd):
                hwnd = None
            if hwnd and self.moments_only:
                hwnd = self._ocr_gate(hwnd)
        if hwnd:
            self._hwnd = hwnd
            self._anchor()
            if not self.isVisible():
                self._fade_in()
                self.shown.emit()
        else:
            self._hwnd = None
            if self.isVisible():
                self._fade_out()

    # ---------- 分支 B OCR 门控（v0.3.2 §八 方案A） ----------

    def _ocr_gate(self, hwnd):
        """OCR 判朋友圈页：挂起中维持上一轮判定（防闪烁）；消费结果后立即重启下一轮。"""
        if self._ocr_degraded:
            self._ocr_thread = None
            if not self._ocr_warned:
                paths.log().warning("朋友圈页面识别降级：微信前台即显浮球")
                self._ocr_warned = True
            return hwnd
        thread = self._ocr_thread
        if thread is not None and thread.is_alive():
            return hwnd if self._last_hit else None
        if thread is not None:
            self._ocr_thread = None
            result, self._ocr_result = self._ocr_result, None
            self._last_hit = bool(result)
            self._start_ocr(hwnd)
            return hwnd if result else None
        self._start_ocr(hwnd)
        return None

    def _start_ocr(self, hwnd):
        self._ocr_thread = threading.Thread(
            target=self._ocr_run, args=(hwnd,), daemon=True)
        self._ocr_thread.start()

    def _ocr_run(self, hwnd):
        """OCR 工作线程：截窄带→识别→写结果。任何异常→会话内降级「前台即显」。"""
        try:
            png = self._grab_strip(hwnd)
            text = self._ocr_fn(png) or ""
            self._ocr_result = ocr.MOMENTS_KEYWORD in text
        except Exception as exc:
            paths.log().warning("ball OCR 失败，降级前台即显：%s", exc)
            self._ocr_result = None
            self._ocr_degraded = True

    def _anchor_pos(self):
        wr = self._rect_of(self._hwnd) if self._hwnd else None
        if not wr:
            return None
        pos = QtCore.QPoint(wr[2] - SIZE - RIGHT_MARGIN, wr[1] + TOP_MARGIN)
        if self._dragged and self._drag_offset is not None:
            pos += self._drag_offset
        return pos

    def _anchor(self):
        pos = self._anchor_pos()
        if pos is not None:
            self.move(pos)

    # ---------- 淡入淡出 ----------

    def _fade_in(self):
        self.setWindowOpacity(0.0)
        self.show()
        if not animations_enabled():
            self.setWindowOpacity(OPACITY)
            return
        anim = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(FADE_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(OPACITY)
        anim.start()
        self._anim = anim

    def _fade_out(self):
        if not animations_enabled():
            self.hide()
            return
        anim = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(FADE_MS)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        anim.start()
        self._anim = anim

    # ---------- hover 缩放 ----------

    def _scaled_geometry(self, scale):
        size = round(SIZE * scale)
        cur = self.geometry()
        return QtCore.QRect(cur.x() - (size - cur.width()) // 2,
                            cur.y() - (size - cur.height()) // 2, size, size)

    def _animate_scale(self, scale):
        if not animations_enabled():
            self.setGeometry(self._scaled_geometry(scale))
            return
        anim = QtCore.QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(FADE_MS)
        anim.setStartValue(self.geometry())
        anim.setEndValue(self._scaled_geometry(scale))
        anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim

    def enterEvent(self, e):
        if not self._busy:
            self._animate_scale(1.08)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_scale(1.0)
        super().leaveEvent(e)

    # ---------- 拖拽 / 点击 ----------

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._press_global = e.globalPos()
            self._press_pos = self.pos()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._press_global is not None and (e.globalPos() - self._press_global).manhattanLength() > 3:
            self._moved = True
            self.move(self._press_pos + e.globalPos() - self._press_global)

    def mouseReleaseEvent(self, e):
        if e.button() != QtCore.Qt.LeftButton or self._press_global is None:
            return
        if self._moved:
            anchor = self._anchor_pos()
            if anchor is not None:
                self._dragged = True
                self._drag_offset = self.pos() - anchor
            else:
                self._dragged = False
                self._drag_offset = None
        elif not self._busy:
            self.clicked.emit()
        self._press_global = None

    # ---------- 绘制 ----------

    def paintEvent(self, _e):
        w, h = self.width(), self.height()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QColor("#9e9e9e" if self._busy else "#07c160"))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(0, 0, w, h)
        p.setPen(QtGui.QColor("white"))
        font = p.font()
        font.setPixelSize(round(20 * w / SIZE))
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), QtCore.Qt.AlignCenter, "…" if self._busy else "评")
        p.end()
