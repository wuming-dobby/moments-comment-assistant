"""v0.3 模块①：SYSTEM_PROMPT 规格 §2.1、调用参数、输出去引号（离线打桩）。"""
import types
from pathlib import Path

import pytest
from PIL import Image

import vision


def _make_png(path):
    Image.new("RGB", (64, 64), "white").save(path, "PNG")


class _FakeClient:
    def __init__(self, api_key=None, base_url=None):
        self.api_key, self.base_url = api_key, base_url
        self.calls = {}
        self.content = " 周末的日落真好看  "
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, model=None, messages=None, **kwargs):
        self.calls.update(kwargs)
        self.calls["model"], self.calls["messages"] = model, messages
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=self.content))]
        )


def test_system_prompt_contains_rules_and_banned_words():
    banned = ["太棒了", "为你点赞", "绝绝子", "yyds"]
    assert "{persona_block}" in vision.SYSTEM_PROMPT_TEMPLATE
    assert "【规矩】" in vision.SYSTEM_PROMPT_TEMPLATE
    assert "【范例】" in vision.SYSTEM_PROMPT_TEMPLATE
    assert "5~25个字" in vision.SYSTEM_PROMPT_TEMPLATE
    assert vision.SYSTEM_PROMPT_TEMPLATE.strip().endswith("只输出评论正文，不要引号、解释或候选。")
    for word in banned:
        assert word in vision.SYSTEM_PROMPT_TEMPLATE, "提示词须含禁用词表 %r" % word


@pytest.mark.parametrize("raw,expect", [
    ('"周末愉快"', "周末愉快"),
    ("「周末愉快」", "周末愉快"),
    ("“周末愉快”", "周末愉快"),
    ("'周末愉快'", "周末愉快"),
    ("「\"周末愉快\"」", "周末愉快"),
    ("  周末愉快  ", "周末愉快"),
    ("周末愉快", "周末愉快"),
    ("", ""),
])
def test_strip_quotes(raw, expect):
    assert vision._strip_quotes(raw) == expect


def test_generate_comment_params_and_quote_strip(tmp_path, monkeypatch):
    img = tmp_path / "shot.png"
    _make_png(img)
    fake = _FakeClient()
    fake.content = '"这色泽，米饭杀手啊"'
    monkeypatch.setattr(vision, "OpenAI", lambda **kw: fake)

    draft = vision.generate_comment(
        str(img),
        cfg={"VL_API_KEY": "k", "VL_MODEL": "m", "VL_API_BASE": "https://x.test/v1"},
    )
    assert draft == "这色泽，米饭杀手啊"
    assert fake.calls["max_tokens"] == 512  # v0.3.1: 推理模型思考占 token，40 会致 content 空
    assert fake.calls["temperature"] == 0.8
    assert fake.calls["timeout"] == 60
    system = fake.calls["messages"][0]
    assert system["role"] == "system"
    assert vision.PERSONA_FALLBACK in system["content"]
    assert "【规矩】" in system["content"]
