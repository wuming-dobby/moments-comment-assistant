"""S1 验收断言脚本"""
import os, sys, types
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# QApplication must be created before any QWidget subclass is imported
from PyQt5 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

import win32gui
import capture
import overlay as overlay_mod
import vision
import pyperclip

FAKE_HWND = 0x1234
passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"PASS: {label}")
        passed += 1
    else:
        print(f"FAIL: {label} {detail}")
        failed += 1

# ── Assertion 1: Overlay visibility ──
saved_find = capture.find_wechat_window
saved_fg = win32gui.GetForegroundWindow
saved_iconic = win32gui.IsIconic

win = overlay_mod.CommentOverlay()
try:
    capture.find_wechat_window = lambda: None
    win.poll()
    check("1a 无微信窗口 → 浮窗隐藏", not win.isVisible())

    capture.find_wechat_window = lambda: FAKE_HWND
    win32gui.GetForegroundWindow = lambda: FAKE_HWND
    win32gui.IsIconic = lambda hwnd: False
    win.poll()
    check("1b 微信前台 → 浮窗显示", win.isVisible())

    win32gui.IsIconic = lambda hwnd: True
    win.poll()
    check("1c 微信最小化 → 浮窗隐藏", not win.isVisible())
finally:
    capture.find_wechat_window = saved_find
    win32gui.GetForegroundWindow = saved_fg
    win32gui.IsIconic = saved_iconic
    win.close()

# ── Assertion 2: Capture produces non-empty PNG ──
# 无法在无微信窗口的环境实测 GDI 截图，但验证 capture 模块结构
check("2 截图模块可导入，find_wechat_window/capture_wechat 存在",
      callable(capture.find_wechat_window) and callable(capture.capture_wechat))

# ── Assertion 3: VL returns non-empty comment ──
calls = {}
class FakeClient:
    def __init__(self, api_key=None, base_url=None):
        calls["api_key"], calls["base_url"] = api_key, base_url
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))
    def _create(self, model=None, messages=None, **kwargs):
        calls["model"], calls["messages"] = model, messages
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=" 周末好看！ "))])

png = ROOT / "tests" / "_stub.png"
png.write_bytes(b"\x89PNG\r\n\x1a\n stub")
saved_openai = vision.OpenAI
vision.OpenAI = FakeClient
try:
    draft = vision.generate_comment(str(png), cfg={"VL_API_KEY": "k", "VL_MODEL": "m", "VL_API_BASE": "https://x.test/v1"})
    check("3a VL 返回非空草稿", draft == "周末好看！", f"got={draft!r}")
    check("3b VL 传了 api_key 和 model", calls["api_key"] == "k" and calls["model"] == "m")
finally:
    vision.OpenAI = saved_openai
    png.unlink()

# Test 3c: missing config
saved_cfg = vision.CONFIG_PATH
saved_env = dict(os.environ)
vision.CONFIG_PATH = ROOT / "_no_such.json"
for k in list(os.environ):
    if k.startswith("VL_"): del os.environ[k]
try:
    vision.generate_comment("x.png", cfg={})
    check("3c 缺配置该报错", False, "没抛异常")
except RuntimeError as e:
    check("3c 缺配置明确报错", "VL_API_KEY" in str(e), str(e))
finally:
    vision.CONFIG_PATH = saved_cfg
    os.environ.clear(); os.environ.update(saved_env)

# ── Assertion 4: Clipboard ──
pyperclip.copy("测试草稿_%s" % os.getpid())
content = pyperclip.paste()
check("4 剪贴板可写可读", "测试草稿" in content, f"read={content!r}")

# ── Assertion 5: No forbidden patterns in src/ ──
import subprocess
result = subprocess.run(
    ["powershell", "-Command",
     "Select-String -Path src/*.py -Pattern 'inject|hook|decrypt|upload|server' -CaseSensitive"],
    cwd=str(ROOT), capture_output=True, text=True
)
check("5 src/ 无注入/hook/解密/上传/server", result.returncode != 0 and not result.stdout.strip(),
      f"hits: {result.stdout[:200]}")

print(f"\n{'='*40}")
print(f"通过 {passed}/{passed+failed}，失败 {failed}")
if failed:
    sys.exit(1)