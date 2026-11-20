"""主入口：托盘常驻 → 微信前台时显示浮窗 → 点「生成评论」→ 截图 → VL 出草稿 → 写剪贴板。

v0.2 起：单实例（二次双击唤起已有浮窗）、托盘图标、配置与日志落 %APPDATA%。
"""
import ctypes
import sys

import pyperclip
from PyQt5 import QtCore, QtGui, QtNetwork, QtWidgets

import capture
import paths
import vision
from config_window import ConfigWindow
from overlay import CommentOverlay

MUTEX_NAME = "Local\\MomentsAssistant_v2"
SERVER_NAME = "MomentsAssistant_v2"
ERROR_ALREADY_EXISTS = 183


def _set_dpi_aware():
    """PerMonitorV2 优先，失败退回 system DPI aware。必须在 QApplication 之前。"""
    try:
        # -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    ctypes.windll.user32.SetProcessDPIAware()


def _tray_icon():
    """画一个绿色圆角图标（不依赖 exe 图标资源，PyInstaller 下也稳）。"""
    pix = QtGui.QPixmap(64, 64)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setBrush(QtGui.QColor("#07c160"))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QtGui.QColor("white"))
    font = painter.font()
    font.setPixelSize(38)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect(), QtCore.Qt.AlignCenter, "评")
    painter.end()
    return QtGui.QIcon(pix)


def open_config(overlay):
    win = ConfigWindow()
    overlay.config_win = win  # 保住引用，防回收
    win.show()


def _run_generate(overlay, image_path=None):
    overlay.hide()
    QtWidgets.QApplication.processEvents()  # 先让浮窗真的消失（降级 BitBlt 时不会拍到自己）
    try:
        path = image_path or capture.capture_wechat()
        draft = vision.generate_comment(path)
        if not draft:
            raise RuntimeError("模型返回空内容")
        pyperclip.copy(draft)
        overlay.show_toast("草稿已复制到剪贴板，去微信里粘贴")
    except Exception as exc:
        paths.log().exception("generate 失败")
        overlay.show_toast("失败：%s" % exc)
    finally:
        overlay.reset_button()
        overlay.poll()


def generate(overlay):
    hwnd = capture.resolve_target()
    if not hwnd:
        overlay.show_toast("没找到微信窗口（先打开微信）")
        overlay.reset_button()
        return
    _run_generate(overlay)


def generate_from_clipboard(overlay):
    try:
        path = capture.capture_from_clipboard()
    except Exception as exc:
        overlay.show_toast("失败：%s" % exc)
        return
    _run_generate(overlay, path)


def main():
    debug = "--debug" in sys.argv
    paths.ensure_dirs()
    log = paths.setup_logging(debug)
    log.info("startup: argv=%s app_dir=%s", sys.argv[1:], paths.APP_DIR)

    _set_dpi_aware()
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关掉弹窗不要把托盘程序一起结束

    # 单实例靠 QLocalServer 判定：先在的实例占着服务名，后来者连上去让它显示浮窗
    probe = QtNetwork.QLocalSocket()
    probe.connectToServer(SERVER_NAME)
    if probe.waitForConnected(400):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(400)
        log.info("startup: 已有实例在跑，已请求唤起")
        return

    overlay = CommentOverlay()
    overlay.generate_clicked.connect(lambda: generate(overlay))
    overlay.clipboard_clicked.connect(lambda: generate_from_clipboard(overlay))

    server = QtNetwork.QLocalServer()
    QtNetwork.QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)
    server.newConnection.connect(lambda: (server.nextPendingConnection().readAll(), overlay.show_pinned()))

    tray = QtWidgets.QSystemTrayIcon(_tray_icon(), app)
    tray.setToolTip("朋友圈评论助手")
    menu = QtWidgets.QMenu()
    act_show = menu.addAction("显示浮窗")
    act_always = menu.addAction("常显浮窗")
    act_always.setCheckable(True)
    menu.addSeparator()
    act_settings = menu.addAction("设置 API…")
    act_quit = menu.addAction("退出")

    cfg = {}
    try:
        cfg = vision.load_config()
    except Exception:
        log.exception("config 读取失败")
    overlay.always_visible = bool(cfg.get("OVERLAY_ALWAYS_VISIBLE"))
    act_always.setChecked(overlay.always_visible)

    act_show.triggered.connect(overlay.show_pinned)
    act_settings.triggered.connect(lambda: open_config(overlay))
    act_quit.triggered.connect(app.quit)

    def _toggle_always(checked):
        overlay.always_visible = checked
        try:
            vision.save_field("OVERLAY_ALWAYS_VISIBLE", checked)
        except Exception:
            log.exception("保存常显设置失败")
        overlay.poll()

    act_always.toggled.connect(_toggle_always)
    overlay.hidden_by_user.connect(lambda: act_always.setChecked(False))

    # 浮窗右键也给一个设置入口
    overlay.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
    overlay.addAction(QtWidgets.QAction("设置 API…", overlay, triggered=lambda: open_config(overlay)))

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: overlay.show_pinned() if reason == QtWidgets.QSystemTrayIcon.Trigger else None
    )
    tray.show()

    overlay.poll()
    if not (cfg.get("VL_API_KEY") and cfg.get("VL_MODEL")):
        open_config(overlay)
        tray.showMessage("朋友圈评论助手", "先填 API Key 与 Model，再回微信里用。",
                         QtWidgets.QSystemTrayIcon.Information, 6000)
    elif not overlay.isVisible():
        tray.showMessage("朋友圈评论助手", "已在后台运行：微信在前台时显示浮窗，点托盘图标可随时唤出。",
                         QtWidgets.QSystemTrayIcon.Information, 6000)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
