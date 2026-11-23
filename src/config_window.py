"""BYOK 配置页：主通道三项 + 人设问卷 + 备用通道 → 存 %APPDATA%\\MomentsAssistant\\config.json。"""
import base64
import html
import io
import json

from openai import OpenAI
from PIL import Image
from PyQt5 import QtCore, QtWidgets

import paths
import vision
from overlay import AnimatedButton, animations_enabled

_buf = io.BytesIO()
Image.new("RGB", (1, 1), "white").save(_buf, "PNG")
PNG_1X1_B64 = base64.b64encode(_buf.getvalue()).decode("ascii")

GENDER_OPTIONS = (("不填", ""), ("男", "男"), ("女", "女"))
STYLE_OPTIONS = ("温和真诚", "幽默调侃", "简洁干脆")
CLOSENESS_OPTIONS = ("一般", "很熟", "偏同事客户")
DEFAULT_STYLE = "温和真诚"
DEFAULT_CLOSENESS = "一般"


class ConfigWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 配置（BYOK）")
        self.setMinimumWidth(460)
        self._faded_in = False
        self._anim = None

        form = QtWidgets.QFormLayout()
        self.base_edit = QtWidgets.QLineEdit()
        self.base_edit.setPlaceholderText("如 https://open.bigmodel.cn/api/paas/v4；留空走 OpenAI 官方")
        self.key_edit = QtWidgets.QLineEdit()
        self.model_edit = QtWidgets.QLineEdit()
        self.model_edit.setPlaceholderText("如 GLM-4.6V-Flash")
        form.addRow("API Base URL", self.base_edit)
        form.addRow("API Key", self.key_edit)
        form.addRow("Model", self.model_edit)

        persona_group = QtWidgets.QGroupBox("人设（写评论时扮演你，让评论更像本人）")
        persona_form = QtWidgets.QFormLayout()
        self.gender_combo = QtWidgets.QComboBox()
        for label, data in GENDER_OPTIONS:
            self.gender_combo.addItem(label, data)
        self.style_combo = QtWidgets.QComboBox()
        for style in STYLE_OPTIONS:
            self.style_combo.addItem(style, style)
        self.catchphrase_edit = QtWidgets.QLineEdit()
        self.catchphrase_edit.setPlaceholderText("如「哈哈哈」「好家伙」，可不填")
        self.closeness_combo = QtWidgets.QComboBox()
        for closeness in CLOSENESS_OPTIONS:
            self.closeness_combo.addItem(closeness, closeness)
        persona_form.addRow("性别", self.gender_combo)
        persona_form.addRow("说话风格", self.style_combo)
        persona_form.addRow("口头禅", self.catchphrase_edit)
        persona_form.addRow("与好友熟络度", self.closeness_combo)
        persona_hint = QtWidgets.QLabel("这些信息与截图一样，只随请求发给上面配置的 API，本项目不经手。")
        persona_hint.setWordWrap(True)
        persona_form.addRow(persona_hint)
        persona_group.setLayout(persona_form)

        self.fallback_group = QtWidgets.QGroupBox("备用通道（主通道限流时自动切换，可选）")
        self.fallback_group.setCheckable(True)
        self.fallback_group.setChecked(False)
        fb_form = QtWidgets.QFormLayout()
        self.fb_base_edit = QtWidgets.QLineEdit()
        self.fb_base_edit.setPlaceholderText("如 https://api-inference.modelscope.cn/v1/")
        self.fb_key_edit = QtWidgets.QLineEdit()
        self.fb_model_edit = QtWidgets.QLineEdit()
        self.fb_model_edit.setPlaceholderText("如 Qwen/Qwen2.5-VL-7B-Instruct")
        fb_form.addRow("备用 Base URL", self.fb_base_edit)
        fb_form.addRow("备用 API Key", self.fb_key_edit)
        fb_form.addRow("备用 Model", self.fb_model_edit)
        self.fallback_group.setLayout(fb_form)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.hide()

        self.test_btn = AnimatedButton("检测 Key", parent=self)
        save_btn = AnimatedButton("保存", parent=self)
        close_btn = AnimatedButton("关闭", hover="#e0e0e0", press="#c9c9c9", parent=self)
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
        box.addWidget(persona_group)
        box.addWidget(self.fallback_group)
        box.addWidget(self.status)
        box.addLayout(buttons)

        self._load()

    def showEvent(self, e):
        super().showEvent(e)
        if self._faded_in:
            return
        self._faded_in = True
        self.setWindowOpacity(0.0)
        if not animations_enabled():
            self.setWindowOpacity(1.0)
            return
        anim = QtCore.QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim

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

        self._select_data(self.gender_combo, str(cfg.get("VL_PERSONA_GENDER") or ""))
        self._select_data(self.style_combo, str(cfg.get("VL_PERSONA_STYLE") or ""), DEFAULT_STYLE)
        self.catchphrase_edit.setText(str(cfg.get("VL_PERSONA_CATCHPHRASE") or ""))
        self._select_data(self.closeness_combo, str(cfg.get("VL_PERSONA_CLOSENESS") or ""),
                          DEFAULT_CLOSENESS)

        fb_vals = [str(cfg.get(k) or "") for k in vision.FALLBACK_KEYS]
        if any(fb_vals):
            self.fallback_group.setChecked(True)
            self.fb_base_edit.setText(fb_vals[0])
            self.fb_key_edit.setText(fb_vals[1])
            self.fb_model_edit.setText(fb_vals[2])

    @staticmethod
    def _select_data(combo, value, default=""):
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findData(default)
        combo.setCurrentIndex(max(idx, 0))

    def _fields(self):
        fields = {
            "VL_API_BASE": self.base_edit.text().strip(),
            "VL_API_KEY": self.key_edit.text().strip(),
            "VL_MODEL": self.model_edit.text().strip(),
            "VL_PERSONA_GENDER": self.gender_combo.currentData() or "",
            "VL_PERSONA_STYLE": self.style_combo.currentData() or "",
            "VL_PERSONA_CATCHPHRASE": self.catchphrase_edit.text().strip(),
            "VL_PERSONA_CLOSENESS": self.closeness_combo.currentData() or "",
        }
        if self.fallback_group.isChecked():
            fields.update({
                "VL_FALLBACK_API_BASE": self.fb_base_edit.text().strip(),
                "VL_FALLBACK_KEY": self.fb_key_edit.text().strip(),
                "VL_FALLBACK_MODEL": self.fb_model_edit.text().strip(),
            })
        else:
            fields.update({k: "" for k in vision.FALLBACK_KEYS})
        return fields

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
