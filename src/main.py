"""主入口：浮窗常驻右下角 → 点「生成评论」→ 截图 → VL 出草稿 → 写进剪贴板。"""
import ctypes
import sys

import pyperclip
from PyQt5 import QtWidgets

import capture
import vision
from overlay import CommentOverlay


def generate(overlay):
    # shortcut: 接口调用在 UI 线程里同步跑（几秒卡顿），要顺滑响应时再挪进 QThread
    hwnd = capture.find_wechat_window()
    if not hwnd:
        overlay.show_toast("没找到微信窗口")
        overlay.reset_button()
        return
    overlay.hide()
    QtWidgets.QApplication.processEvents()  # 先让浮窗真的消失，截图里不会拍到自己
    try:
        draft = vision.generate_comment(capture.capture_wechat(hwnd))
        pyperclip.copy(draft)
        overlay.show_toast("草稿已复制到剪贴板，去微信里粘贴")
    except Exception as exc:
        overlay.show_toast("失败：%s" % exc)
    finally:
        overlay.reset_button()
        overlay.poll()


def main():
    ctypes.windll.user32.SetProcessDPIAware()  # 坐标按物理像素，截图尺寸才等于真实客户区
    app = QtWidgets.QApplication(sys.argv)
    overlay = CommentOverlay()
    overlay.generate_clicked.connect(lambda: generate(overlay))
    overlay.poll()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
