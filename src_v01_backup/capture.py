"""截图模块：用 Win32 GDI 截取微信主窗口客户区，存成 PNG。"""
import time
from pathlib import Path

import win32con
import win32gui
import win32ui
from PIL import Image

WECHAT_CLASS = "WeChatMainWndForPC"
SHOT_DIR = Path(__file__).resolve().parents[1] / "screenshots"


def find_wechat_window():
    """微信 PC 主窗口句柄，找不到返回 None（最小化的窗口也算找得到）。"""
    found = []

    def _each(hwnd, _extra):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == WECHAT_CLASS:
            found.append(hwnd)
        return True

    win32gui.EnumWindows(_each, None)
    return found[0] if found else None


def client_size(hwnd):
    """客户区 (宽, 高) 与客户区左上角的屏幕坐标 (x, y)。"""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError("微信窗口客户区尺寸无效（可能已最小化）")
    return width, height, win32gui.ClientToScreen(hwnd, (0, 0))


def capture_wechat(hwnd, out_dir=SHOT_DIR):
    """截取客户区并保存，返回 PNG 路径。调用前应先把浮窗藏起来，免得拍到自己。"""
    width, height, (origin_x, origin_y) = client_size(hwnd)

    screen_dc = win32gui.GetDC(0)
    src_dc = win32ui.CreateDCFromHandle(screen_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src_dc, width, height)
    mem_dc.SelectObject(bitmap)
    mem_dc.BitBlt((0, 0), (width, height), src_dc, (origin_x, origin_y), win32con.SRCCOPY)

    # shortcut: 按桌面 32 位色深（Win10/11 默认）解 BGRX；若 GetBitmapBits 长度对不上再补 24 位分支
    pixels = bitmap.GetBitmapBits(True)
    image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)

    win32gui.DeleteObject(bitmap.GetHandle())
    mem_dc.DeleteDC()
    src_dc.DeleteDC()
    win32gui.ReleaseDC(0, screen_dc)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / time.strftime("capture_%Y%m%d_%H%M%S.png")
    image.save(str(path), "PNG")
    return str(path)
