"""截图模块：按进程名找微信窗口（兼容微信 3.x / 4.x），PrintWindow 截图后裁客户区。

v0.1 只认类名 WeChatMainWndForPC（微信 3.x），在微信 4.x 上一个窗口都找不到。
现在改成按进程名枚举，类名只用于日志提示。
"""
import ctypes
import statistics
import time
from pathlib import Path

import win32con
import win32gui
import win32process
import win32ui
from PIL import Image

import paths

WECHAT_PROCS = {"weixin.exe", "wechat.exe"}
WECHAT_CLASSES = {"WeChatMainWndForPC", "Qt51514QWindowIcon"}
PW_RENDERFULLCONTENT = 2
CACHE_SECONDS = 2.0
_CACHE = {"at": 0.0, "hwnd": None}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


# ---------- 可注入的 Win32 依赖 ----------

def enum_visible_windows():
    """所有可见顶层窗口句柄列表。"""
    out = []

    def _each(hwnd, _extra):
        if win32gui.IsWindowVisible(hwnd):
            out.append(hwnd)
        return True

    win32gui.EnumWindows(_each, None)
    return out


def proc_name_of(hwnd):
    """窗口所属进程的可执行文件名（小写），取不到返回空串。"""
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = ctypes.c_ulong(512)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.rsplit("\\", 1)[-1].lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def class_of(hwnd):
    try:
        return win32gui.GetClassName(hwnd)
    except Exception:
        return ""


def area_of(hwnd):
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return 0
    return max(0, right - left) * max(0, bottom - top)


def foreground_hwnd():
    return win32gui.GetForegroundWindow()


# ---------- 选窗 ----------

def find_wechat_window(*, enum_windows=None, proc_name_of=None, foreground=None,
                       class_of=None, area_of=None):
    """微信窗口句柄：前台窗属于微信就优先用它（朋友圈是独立窗），否则取面积最大的可见窗。"""
    enum_windows = enum_windows or globals()["enum_visible_windows"]
    proc_name_of = proc_name_of or globals()["proc_name_of"]
    foreground = foreground or globals()["foreground_hwnd"]
    class_of = class_of or globals()["class_of"]
    area_of = area_of or globals()["area_of"]

    cands = [h for h in enum_windows() if proc_name_of(h).lower() in WECHAT_PROCS]
    if not cands:
        return None

    fg = foreground()
    if fg and (fg in cands or proc_name_of(fg).lower() in WECHAT_PROCS):
        return fg

    best = max(cands, key=area_of)
    cls = class_of(best)
    paths.log().debug("find_wechat: cands=%d pick=%s class=%s known=%s",
                      len(cands), hex(best), cls, cls in WECHAT_CLASSES)
    return best


def resolve_target(use_cache=True):
    """带 2 秒缓存的选窗；缓存的是「目标窗」，每轮用 IsWindow 校验。"""
    now = time.time()
    if use_cache and _CACHE["hwnd"] and now - _CACHE["at"] < CACHE_SECONDS:
        if win32gui.IsWindow(_CACHE["hwnd"]):
            return _CACHE["hwnd"]
    hwnd = find_wechat_window()
    _CACHE.update(at=now, hwnd=hwnd)
    return hwnd


def wechat_in_foreground(*, foreground=None, proc_name_of=None):
    """前台窗口属于微信进程且没最小化。"""
    foreground = foreground or globals()["foreground_hwnd"]
    proc_name_of = proc_name_of or globals()["proc_name_of"]
    fg = foreground()
    if not fg or proc_name_of(fg) not in WECHAT_PROCS:
        return False
    return not win32gui.IsIconic(fg)


# ---------- 纯函数（可单测） ----------

def crop_client(img, wr, cr, c0):
    """从整窗图里裁出客户区。

    wr=(left, top, right, bottom) 窗口矩形；cr=(宽, 高) 客户区；c0=(x, y) 客户区左上角的屏幕坐标。
    位图局部偏移 = 客户区屏幕坐标 - 窗口矩形左上角。
    """
    dx, dy = c0[0] - wr[0], c0[1] - wr[1]
    box = (dx, dy, dx + cr[0], dy + cr[1])
    w, h = img.size
    if dx < 0 or dy < 0 or box[2] > w or box[3] > h or cr[0] <= 0 or cr[1] <= 0:
        raise ValueError("客户区超出窗口位图：box=%s size=%s" % (box, img.size))
    return img.crop(box)


def is_invalid(img):
    """无效画面判据（任一命中即降级）：全黑 / 全白 / 无内容。返回 (invalid, info)。"""
    thumb = img.convert("L").resize((128, 128))
    px = list(thumb.getdata())
    mean = statistics.fmean(px)
    stdev = statistics.pstdev(px)
    rgb = img.convert("RGB").resize((128, 128))
    uniq = {(r >> 3, g >> 3, b >> 3) for r, g, b in rgb.getdata()}
    reason = ""
    if mean < 8 and stdev < 2:
        reason = "全黑"
    elif mean > 250 and stdev < 2:
        reason = "全白"
    elif len(uniq) < 4:
        reason = "无内容"
    info = {"mean": round(mean, 1), "stdev": round(stdev, 1), "uniq": len(uniq), "reason": reason}
    return bool(reason), info


# ---------- 取图 ----------

def _window_bitmap(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise RuntimeError("微信窗口尺寸无效（可能已最小化）")
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    src_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src_dc, width, height)
    mem_dc.SelectObject(bitmap)
    try:
        ok = user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)
        if not ok:
            raise RuntimeError("PrintWindow 返回 0")
        pixels = bitmap.GetBitmapBits(True)
        image = Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)
        return image, (left, top, right, bottom)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        mem_dc.DeleteDC()
        src_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)


def _screen_bitmap(hwnd):
    """降级路径：直接 BitBlt 屏幕上的客户区（v0.1 的老办法）。"""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width, height = right - left, bottom - top
    ox, oy = win32gui.ClientToScreen(hwnd, (0, 0))
    screen_dc = win32gui.GetDC(0)
    src_dc = win32ui.CreateDCFromHandle(screen_dc)
    mem_dc = src_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(src_dc, width, height)
    mem_dc.SelectObject(bitmap)
    try:
        mem_dc.BitBlt((0, 0), (width, height), src_dc, (ox, oy), win32con.SRCCOPY)
        pixels = bitmap.GetBitmapBits(True)
        return Image.frombuffer("RGB", (width, height), pixels, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        mem_dc.DeleteDC()
        src_dc.DeleteDC()
        win32gui.ReleaseDC(0, screen_dc)


def _client_box(hwnd):
    cl, ct, cr_, cb = win32gui.GetClientRect(hwnd)
    return (cr_ - cl, cb - ct), win32gui.ClientToScreen(hwnd, (0, 0))


def capture_wechat(hwnd=None, out_dir=None):
    """截微信窗口客户区并保存 PNG，返回路径。"""
    hwnd = hwnd or resolve_target()
    if not hwnd:
        raise RuntimeError("没找到微信窗口（微信要先打开）")
    if win32gui.IsIconic(hwnd):
        raise RuntimeError("微信窗口已最小化，先还原再截")

    cr, c0 = _client_box(hwnd)
    image = None
    bad, info = True, {"reason": "未执行"}
    try:
        full, wr = _window_bitmap(hwnd)
        image = crop_client(full, wr, cr, c0)
        bad, info = is_invalid(image)
        paths.log().info("capture: PrintWindow ok %s", info)
    except Exception as exc:
        paths.log().warning("capture: PrintWindow 失败 %s", exc)
        bad, info = True, {"reason": str(exc)[:60]}

    if bad:
        image = _screen_bitmap(hwnd)
        bad, info = is_invalid(image)
        paths.log().info("capture: BitBlt fallback %s", info)

    if bad:
        raise RuntimeError("截图失败（%s），请改用「用剪贴板图片」" % info.get("reason"))
    if image is None:
        raise RuntimeError("截图失败：没有取到画面")

    out_dir = Path(out_dir or paths.shot_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / time.strftime("capture_%Y%m%d_%H%M%S.png")
    image.save(str(path), "PNG")
    paths.prune_shots()
    return str(path)


def capture_from_clipboard(out_dir=None):
    """F5b 兜底：直接从剪贴板位图取图（用户用 Win+Shift+S 或微信自带截图）。"""
    from PIL import ImageGrab

    image = ImageGrab.grabclipboard()
    if not isinstance(image, Image.Image):
        raise RuntimeError("剪贴板里没有图片，先截图再点这里")
    if image.mode != "RGB":
        image = image.convert("RGB")
    out_dir = Path(out_dir or paths.shot_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / time.strftime("clip_%Y%m%d_%H%M%S.png")
    image.save(str(path), "PNG")
    paths.prune_shots()
    return str(path)
