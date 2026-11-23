"""v0.3 模块②：persona 四字段拼接与 system message 注入（离线打桩）。"""
import tempfile
import types
from pathlib import Path

from PIL import Image

import vision


def test_persona_all_four_fields():
    cfg = {
        "VL_PERSONA_GENDER": "男",
        "VL_PERSONA_STYLE": "幽默调侃",
        "VL_PERSONA_CATCHPHRASE": "哈哈哈",
        "VL_PERSONA_CLOSENESS": "很熟",
    }
    block = vision.build_persona_block(cfg)
    assert block == "性别：男；说话风格：幽默调侃；口头禅：哈哈哈；与好友熟络度：很熟"


def test_persona_skips_empty():
    cfg = {"VL_PERSONA_GENDER": "女", "VL_PERSONA_CATCHPHRASE": "好家伙"}
    block = vision.build_persona_block(cfg)
    assert block == "性别：女；口头禅：好家伙"


def test_persona_all_empty_fallback():
    assert vision.build_persona_block({}) == vision.PERSONA_FALLBACK
    assert vision.build_persona_block({"VL_PERSONA_GENDER": ""}) == vision.PERSONA_FALLBACK
    assert "未填写" in vision.PERSONA_FALLBACK


def test_persona_injected_into_system_message():
    client_holder = {}

    class FakeClient:
        def __init__(self, api_key=None, base_url=None):
            client_holder["self"] = self
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=self._create)
            )

        def _create(self, model=None, messages=None, **kwargs):
            self.messages = messages
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="好"))]
            )

    with tempfile.TemporaryDirectory() as tmp:
        img = Path(tmp) / "s.png"
        Image.new("RGB", (32, 32), "white").save(img, "PNG")
        saved = vision.OpenAI
        vision.OpenAI = FakeClient
        try:
            vision.generate_comment(
                str(img),
                cfg={
                    "VL_API_KEY": "k",
                    "VL_MODEL": "m",
                    "VL_PERSONA_STYLE": "简洁干脆",
                    "VL_PERSONA_CLOSENESS": "偏同事客户",
                },
            )
        finally:
            vision.OpenAI = saved

    system = client_holder["self"].messages[0]
    assert system["role"] == "system"
    assert "说话风格：简洁干脆；与好友熟络度：偏同事客户" in system["content"]
    assert "【人设】" in system["content"]
