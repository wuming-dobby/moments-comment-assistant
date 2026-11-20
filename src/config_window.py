"""BYOK 配置页：三项输入 → 存 config.json；「检测 Key」发一条最小 VL 请求验证。"""
import base64
import html
import io
import json

from openai import OpenAI
from PIL import Image
from PyQt5 import QtWidgets

import vision

_buf = io.BytesIO()
Image.new("RGB", (1, 1), "white").save(_buf, "PNG")
PNG_1X1_B64 = base64.b64encode(_buf.getvalue()).decode("ascii")


class ConfigWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 配置（BYOK）")
        self.setMinimumWidth(460)

        form = QtWidgets.QFormLayout()
        self.base_edit = QtWidgets.QLineEdit()
        self.base_edit.setPlaceholderText("如 https://api.siliconflow.cn/v1；留空走 OpenAI 官方")
        self.key_edit = QtWidgets.QLineEdit()
        self.model_edit = QtWidgets.QLineEdit()
        self.model_edit.setPlaceholderText("如 Qwen/Qwen2.5-VL-7B-Instruct")
        form.addRow("API Base URL", self.base_edit)
        form.addRow("API Key", self.key_edit)
        form.addRow("Model", self.model_edit)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.hide()

        self.test_btn = QtWidgets.QPushButton("检测 Key")
        save_btn = QtWidgets.QPushButton("保存")
        close_btn = QtWidgets.QPushButton("关闭")
        self.test_btn.clicked.connect(self.test_key)
        save_btn.clicked.connect(self.save)
        close_btn.clicked.connect(self.close)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.test_btn)
        buttons.addStretch(1)
        buttons.addWidget(save_btn)
        buttons.addWidget(close_btn)

        box = QtWidgets.QVBoxLayout(self)
        box.addLayout(form)
        box.addWidget(self.status)
        box.addLayout(buttons)

        self._load()

    def _load(self):
        if not vision.CONFIG_PATH.exists():
            return
        try:
            cfg = json.loads(vision.CONFIG_PATH.read_text(encoding="utf-8"))
        except ValueError as exc:
            self._set_status(False, "✗ config.json 损坏：%s" % exc)
            return
        self.base_edit.setText(str(cfg.get("VL_API_BASE") or ""))
        self.key_edit.setText(str(cfg.get("VL_API_KEY") or ""))
        self.model_edit.setText(str(cfg.get("VL_MODEL") or ""))

    def _fields(self):
        return {
            "VL_API_BASE": self.base_edit.text().strip(),
            "VL_API_KEY": self.key_edit.text().strip(),
            "VL_MODEL": self.model_edit.text().strip(),
        }

    def save(self):
        vision.CONFIG_PATH.write_text(
            json.dumps(self._fields(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._set_status(True, "✓ 已保存 config.json")

    def test_key(self):
        cfg = self._fields()
        if not (cfg["VL_API_KEY"] and cfg["VL_MODEL"]):
            self._set_status(False, "✗ 先填 API Key 和 Model 再检测")
            return
        # shortcut: 请求在 UI 线程同步跑（最久卡 timeout 秒），要顺滑再挪 QThread
        self.test_btn.setEnabled(False)
        self._set_status(None, "检测中…")
        try:
            client = OpenAI(api_key=cfg["VL_API_KEY"], base_url=cfg["VL_API_BASE"] or None)
            resp = client.chat.completions.create(
                model=cfg["VL_MODEL"],
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "请只回复 ok"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + PNG_1X1_B64}},
                ]}],
                timeout=15,
            )
            content = (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            self._set_status(False, "✗ 检测失败：%s" % exc)
        else:
            if content:
                self._set_status(True, "✓ 检测通过：%s" % content[:40])
            else:
                self._set_status(False, "✗ 接口无报错但返回为空")
        finally:
            self.test_btn.setEnabled(True)

    def _set_status(self, ok, text):
        color = "#2e7d32" if ok is True else "#c62828" if ok is False else "#616161"
        self.status.setText('<span style="color:%s">%s</span>' % (color, html.escape(text)))
        self.status.show()
