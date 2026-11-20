"""浮窗模块：置顶无边框小窗，停在屏幕右下角。

可见性 = pinned（临时置顶）或 always_visible（常显）或 微信在前台，三者取或。
v0.1 只有「微信在前台」一条，且无托盘，启动后完全不可见 → 用户以为程序没反应。
"""
from PyQt5 import QtCore, QtWidgets

import capture

MARGIN = 16
POLL_MS = 1000


class CommentOverlay(QtWidgets.QWidget):
    generate_clicked = QtCore.pyqtSignal()
    clipboard_clicked = QtCore.pyqtSignal()
    hidden_by_user = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.pinned = False
        self.always_visible = False
        # WindowDoesNotAcceptFocus：点按钮不抢微信的前台
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        self.button = QtWidgets.QPushButton("生成评论", self)
        self.clip_button = QtWidgets.QPushButton("用剪贴板图片", self)
        self.hide_button = QtWidgets.QPushButton("隐藏", self)
        for b in (self.clip_button, self.hide_button):
            b.setFlat(True)
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
