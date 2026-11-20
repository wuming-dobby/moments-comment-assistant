"""BYOK 配置页：三项输入 → 存 %APPDATA%\\MomentsAssistant\\config.json；「检测 Key」发一条最小 VL 请求验证。"""
import base64
import html
import io
import json

from openai import OpenAI
from PIL import Image
from PyQt5 import QtWidgets

import paths
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
        self.base_edit.setPlaceholderText("如 https://open.bigmodel.cn/api/paas/v4；留空走 OpenAI 官方")
        self.key_edit = QtWidgets.QLineEdit()
        self.model_edit = QtWidgets.QLineEdit()
        self.model_edit.setPlaceholderText("如 GLM-4.6V-Flash")
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
        """回显用合并后的配置（env 优先），用户看到的就是实际会用的值。"""
        try:
            cfg = vision.load_config()
        except Exception as exc:
            self._set_status(False, "✗ 配置读取失败：%s" % exc)
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
        paths.ensure_dirs()
        target = paths.config_path()
        try:
            existing = {}
            if target.exists():
                existing = json.loads(target.read_text(encoding="utf-8"))
            existing.update(self._fields())
            target.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self._set_status(False, "✗ 保存失败：%s" % exc)
            paths.log().exception("保存配置失败")
            return
        self._set_status(True, "✓ 已保存到 %s" % target)
        paths.log().info("config: 已保存（key=%s）", paths.mask_key(self.key_edit.text().strip()))

    def test_key(self):
        cfg = self._fields()
        if not (cfg["VL_API_KEY"] and cfg["VL_MODEL"]):
            self._set_status(False, "✗ 先填 API Key 和 Model 再检测")
            return
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
