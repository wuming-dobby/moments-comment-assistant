import os, sys, json, types, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PyQt5 import QtWidgets
app = QtWidgets.QApplication.instance()
if app is None:
    app = QtWidgets.QApplication([])
print(f"QApplication created: {app}")

import config_window
import vision

vision.CONFIG_PATH = Path(tempfile.mkdtemp()) / "s2_test_config.json"

# Test 1: save and read back
win = config_window.ConfigWindow()
win.base_edit.setText("https://x.test/v1")
win.key_edit.setText("k-123")
win.model_edit.setText("m-vl")
win.save()
saved = json.loads(vision.CONFIG_PATH.read_text())
assert saved == {"VL_API_BASE": "https://x.test/v1", "VL_API_KEY": "k-123", "VL_MODEL": "m-vl"}, saved
print("PASS 1 配置页可填可存")

# Test 2: reload from config
win2 = config_window.ConfigWindow()
assert win2.base_edit.text() == "https://x.test/v1"
assert win2.key_edit.text() == "k-123"
print("PASS 2 可回读 config.json")

# Test 3: bad key
real_openai = config_window.OpenAI
config_window.OpenAI = lambda **kw: (_ for _ in ()).throw(RuntimeError("401 Unauthorized"))
win2.test_key()
assert "检测失败" in win2.status.text(), win2.status.text()
print("PASS 3 bad key -> red/fail")

# Test 4: good key
class FakeClient:
    def __init__(self, **kw):
        def _create(**kw2):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))]
            )
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))

config_window.OpenAI = FakeClient
win2.test_key()
assert "检测通过" in win2.status.text(), win2.status.text()
print("PASS 4 good key -> green/pass")
config_window.OpenAI = real_openai

print("\nS2 配置页四项自检全部通过")