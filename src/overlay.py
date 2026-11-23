"""浮窗模块：置顶无边框小窗，停在屏幕右下角。

可见性 = pinned（临时置顶）或 always_visible（常显）或 微信在前台，三者取或。
朋友圈窗口开着时（moments_finder 命中）一律让位给浮球（v0.3）。
v0.1 只有「微信在前台」一条，且无托盘，启动后完全不可见 → 用户以为程序没反应。
"""
from PyQt5 import QtCore, QtGui, QtWidgets

import capture
import vision

MARGIN = 16
POLL_MS = 1000


def animations_enabled():
    """VL_ANIMATIONS=0 时全关动画（直接设终态）；配置读不到默认开。"""
    try:
        return str(vision.load_config().get("VL_ANIMATIONS") or "") != "0"
    except Exception:
        return True


class AnimatedButton(QtWidgets.QPushButton):
    """hover/按下背景色渐变；动画关闭时一步到位。"""

    def __init__(self, text, base="#f2f2f2", hover="#e0f5e9", press="#c8eccf",
                 text_color="#333333", parent=None):
        super().__init__(text, parent)
        self._base, self._hover, self._press = base, hover, press
        self._text_color = text_color
        self._current = base
        self._anim = None
        self._set_color(base)

    def _set_color(self, color):
        self.setStyleSheet(
            "QPushButton { background-color: %s; color: %s; }"
            "QPushButton:disabled { color: #999999; }" % (color, self._text_color)
        )

    def _animate_to(self, color):
        if not animations_enabled():
            self._current = color
            self._set_color(color)
            return
        start = QtGui.QColor(self._current)
        self._current = color
        end = QtGui.QColor(color)
        anim = QtCore.QVariantAnimation(self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.valueChanged.connect(
            lambda t, s=start, e=end: self._set_color(QtGui.QColor(
                round(s.red() + (e.red() - s.red()) * t),
                round(s.green() + (e.green() - s.green()) * t),
                round(s.blue() + (e.blue() - s.blue()) * t)).name()
            )
        )
        anim.start()
        self._anim = anim

    def enterEvent(self, e):
        if self.isEnabled():
            self._animate_to(self._hover)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_to(self._base)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self.isEnabled():
            self._animate_to(self._press)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton and self.isEnabled():
            self._animate_to(self._hover if self.underMouse() else self._base)
        super().mouseReleaseEvent(e)


class CommentOverlay(QtWidgets.QWidget):
    generate_clicked = QtCore.pyqtSignal()
    clipboard_clicked = QtCore.pyqtSignal()
    hidden_by_user = QtCore.pyqtSignal()

    def __init__(self, moments_finder=None):
        super().__init__()
        self.pinned = False
        self.always_visible = False
        self._moments_finder = moments_finder
        # WindowDoesNotAcceptFocus：点按钮不抢微信的前台
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        self.button = AnimatedButton("生成评论", base="#07c160", hover="#05a954",
                                     press="#048f47", text_color="white", parent=self)
        self.clip_button = AnimatedButton("用剪贴板图片", parent=self)
        self.hide_button = AnimatedButton("隐藏", base="#f2f2f2", hover="#fdecea",
                                          press="#f8cfc8", parent=self)
        self.toast = QtWidgets.QLabel(self)
        self.toast.setWordWrap(True)
        self.toast.setMaximumWidth(180)
        self.toast.hide()

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.clip_button)
        row.addStretch(1)
        row.addWidget(self.hide_button)

        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        box.addWidget(self.button)
        box.addLayout(row)
        box.addWidget(self.toast)

        self.button.clicked.connect(self._on_generate)
        self.clip_button.clicked.connect(self.clipboard_clicked.emit)
        self.hide_button.clicked.connect(self.hide_now)

        self.setVisible(False)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(POLL_MS)

    # ---------- 可见性 ----------

    def place_bottom_right(self):
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(area.right() - self.width() - MARGIN, area.bottom() - self.height() - MARGIN)

    def want_visible(self):
        if self._moments_finder and self._moments_finder():
            return False  # 朋友圈窗在：浮球接管，浮窗让位
        return bool(self.pinned or self.always_visible or capture.wechat_in_foreground())

    def poll(self):
        want = self.want_visible()
        if want:
            if not self.isVisible():
                self.place_bottom_right()
            self.show()
        elif self.isVisible():
            self.hide()

    def show_pinned(self):
        """托盘单击 / 单实例唤起：临时置顶，直到用户点「隐藏」。"""
        self.pinned = True
        self.poll()

    def hide_now(self):
        """「隐藏」按钮：两个开关都清掉，并且真的消失。"""
        self.pinned = False
        self.always_visible = False
        self.hide()
        self.hidden_by_user.emit()

    # ---------- 按钮态 ----------

    def _on_generate(self):
        self.button.setEnabled(False)
        self.button.setText("生成中…")
        self.generate_clicked.emit()

    def reset_button(self):
        self.button.setEnabled(True)
        self.button.setText("生成评论")

    def show_toast(self, text):
        self.toast.setText(text)
        self.toast.setVisible(True)
        self.adjustSize()
        QtCore.QTimer.singleShot(4000, self.toast.hide)
