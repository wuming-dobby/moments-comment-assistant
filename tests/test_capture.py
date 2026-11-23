"""A7 选窗 / A9 裁切 / A10 无效图判据 —— 全部用注入桩，不碰真实 Win32。"""
import pytest
from PIL import Image

import capture


def _finder(windows, foreground=0):
    """windows: {hwnd: (进程名, 面积)}"""
    return capture.find_wechat_window(
        enum_windows=lambda: list(windows),
        proc_name_of=lambda h: windows.get(h, ("", 0))[0],
        foreground=lambda: foreground,
        class_of=lambda h: "",  # 类名置空：证明不再靠类名判据
        area_of=lambda h: windows.get(h, ("", 0))[1],
    )


def test_a7_picks_largest_by_proc_name_not_class():
    wins = {0x10: ("WeChat.exe", 100), 0x20: ("WeChat.exe", 900), 0x30: ("chrome.exe", 5000)}
    assert _finder(wins) == 0x20


def test_a7_foreground_wechat_wins():
    wins = {0x10: ("weixin.exe", 2000), 0x20: ("weixin.exe", 300)}
    assert _finder(wins, foreground=0x20) == 0x20


def test_a7_no_wechat_returns_none():
    assert _finder({0x30: ("chrome.exe", 5000)}) is None


def test_a9_crop_client_maps_offset():
    img = Image.new("RGB", (400, 300), "white")
    img.putpixel((8, 31), (255, 0, 0))
    out = capture.crop_client(img, (100, 100, 500, 400), (360, 240), (108, 131))
    assert out.size == (360, 240)
    assert out.getpixel((0, 0))[:3] == (255, 0, 0)


def test_a9_crop_out_of_range_raises():
    img = Image.new("RGB", (100, 100))
    with pytest.raises(ValueError):
        capture.crop_client(img, (0, 0, 100, 100), (200, 200), (0, 0))


def test_a10_black_is_invalid():
    bad, info = capture.is_invalid(Image.new("RGB", (300, 200), "black"))
    assert bad and info["reason"] == "全黑"


def test_a10_white_is_invalid():
    bad, info = capture.is_invalid(Image.new("RGB", (300, 200), "white"))
    assert bad and info["reason"] == "全白"


def test_a10_single_color_is_invalid():
    bad, info = capture.is_invalid(Image.new("RGB", (300, 200), (200, 210, 220)))
    assert bad and info["reason"] == "无内容"


def test_a10_rich_image_is_valid():
    img = Image.new("RGB", (300, 200), "white")
    for x in range(0, 300, 10):
        for y in range(0, 200, 10):
            img.putpixel((x, y), (x % 255, y % 255, (x * y) % 255))
    bad, info = capture.is_invalid(img)
    assert not bad, info


def _moments_finder(windows):
    """windows: {hwnd: (进程名, 标题)}"""
    return capture.find_moments_window(
        enum_windows=lambda: list(windows),
        proc_name_of=lambda h: windows.get(h, ("", ""))[0],
        title_of=lambda h: windows.get(h, ("", ""))[1],
    )


def test_a11_moments_hit_by_cn_title():
    wins = {0x10: ("WeChat.exe", "微信"), 0x20: ("WeChat.exe", "朋友圈")}
    assert _moments_finder(wins) == 0x20


def test_a11_moments_hit_by_en_title():
    wins = {0x10: ("WeChat.exe", "微信"), 0x20: ("WeChat.exe", "Moments")}
    assert _moments_finder(wins) == 0x20


def test_a11_main_window_title_not_moments():
    assert _moments_finder({0x10: ("WeChat.exe", "微信")}) is None


def test_a11_no_wechat_process_returns_none():
    assert _moments_finder({0x30: ("chrome.exe", "朋友圈")}) is None
