"""浮窗模块：置顶无边框小窗，只在微信处于前台时出现，停在屏幕右下角。"""
import win32gui
from PyQt5 import QtCore, QtWidgets

import capture

MARGIN = 16
POLL_MS = 1000


def wechat_is_foreground():
    """微信主窗口存在、没最小化、且是当前前台窗口。"""
    hwnd = capture.find_wechat_window()
    if not hwnd or win32gui.IsIconic(hwnd):
        return False
    return win32gui.GetForegroundWindow() == hwnd


class CommentOverlay(QtWidgets.QWidget):
    generate_clicked = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        # WindowDoesNotAcceptFocus：点按钮不会把前台从微信抢走，否则轮询会立刻把浮窗藏掉
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        self.button = QtWidgets.QPushButton("生成评论", self)
        self.toast = QtWidgets.QLabel(self)
        self.toast.setWordWrap(True)
        self.toast.setMaximumWidth(180)
        self.toast.hide()
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 8)
        box.addWidget(self.button)
        box.addWidget(self.toast)
        self.button.clicked.connect(self._on_click)

        self.setVisible(False)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(POLL_MS)

    def place_bottom_right(self):
        area = QtWidgets.QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(area.right() - self.width() - MARGIN, area.bottom() - self.height() - MARGIN)

    def poll(self):
        want = wechat_is_foreground()
        if want == self.isVisible():
            return
        if want:
            self.place_bottom_right()
            self.show()
        else:
            self.hide()

    def _on_click(self):
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
