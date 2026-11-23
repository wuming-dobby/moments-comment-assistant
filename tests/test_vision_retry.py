"""A7 瞬态错误重试 + 备用通道：429/1305/1302 主通道重试 2 次（2s/4s），仍失败切 VL_FALLBACK_*。"""
import types

import pytest
from PIL import Image

import vision


def _make_png(path):
    Image.new("RGB", (320, 200), "white").save(path, "PNG")
    return str(path)


class ScriptedClient:
    """按脚本顺序抛异常或返回评论；每次调用记下 kwargs 供断言。"""

    def __init__(self, script, calls, api_key=None, base_url=None):
        # 共享同一 list：重试每次新建 client，脚本进度必须跨 client 延续
        self.script = script
        self.calls = calls
        self.constructed = {"api_key": api_key, "base_url": base_url}
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=" " + step + " "))]
        )


def _install(monkeypatch, script):
    calls = []
    constructed = []

    def factory(api_key=None, base_url=None):
        client = ScriptedClient(script, calls, api_key=api_key, base_url=base_url)
        constructed.append(client.constructed)
        return client

    monkeypatch.setattr(vision, "OpenAI", factory)
    sleeps = []
    monkeypatch.setattr(vision, "_sleep", sleeps.append)
    return calls, constructed, sleeps


MAIN = {"VL_API_KEY": "main-key", "VL_MODEL": "main-vl", "VL_API_BASE": "https://main.test/v1"}
LIMIT_429 = Exception("Error code: 429 - 请求过于频繁")
LIMIT_1305 = Exception("Error code: 1305")


def test_retry_twice_then_success(tmp_path, monkeypatch):
    calls, constructed, sleeps = _install(monkeypatch, [LIMIT_429, LIMIT_429, "这次成功了"])

    draft = vision.generate_comment(_make_png(tmp_path / "shot.png"), cfg=dict(MAIN))

    assert draft == "这次成功了"
    assert sleeps == [2, 4], "两次重试应各睡 2s、4s，实际：%r" % sleeps
    assert len(calls) == 3
    assert all(c["model"] == "main-vl" for c in calls)
    assert len(constructed) == 3, "重试期间不得新建备用客户端"


def test_fallback_used_after_retries(tmp_path, monkeypatch):
    cfg = dict(MAIN, VL_FALLBACK_API_BASE="https://fb.test/v1",
               VL_FALLBACK_KEY="fb-key", VL_FALLBACK_MODEL="fb-vl")
    calls, constructed, sleeps = _install(
        monkeypatch, [LIMIT_429, LIMIT_429, LIMIT_429, "备用通道回复"]
    )

    draft = vision.generate_comment(_make_png(tmp_path / "shot.png"), cfg=cfg)

    assert draft == "备用通道回复"
    assert sleeps == [2, 4]
    assert len(calls) == 4
    assert calls[3]["model"] == "fb-vl", "第四次调用必须用备用 model"
    assert constructed[3] == {"api_key": "fb-key", "base_url": "https://fb.test/v1"}, \
        "备用客户端必须用 VL_FALLBACK_* 三项"


def test_fallback_also_fails_raises_limit_hint(tmp_path, monkeypatch):
    cfg = dict(MAIN, VL_FALLBACK_API_BASE="https://fb.test/v1",
               VL_FALLBACK_KEY="fb-key", VL_FALLBACK_MODEL="fb-vl")
    calls, constructed, sleeps = _install(monkeypatch, [LIMIT_429] * 3 + [LIMIT_429])

    with pytest.raises(RuntimeError) as exc:
        vision.generate_comment(_make_png(tmp_path / "shot.png"), cfg=cfg)

    assert vision.LIMIT_HINT in str(exc.value), "错误必须带限流提示文案"
    assert sleeps == [2, 4]
    assert len(calls) == 4


def test_code_1305_and_hint_are_transient(tmp_path, monkeypatch):
    cfg = dict(MAIN, VL_FALLBACK_API_BASE="https://fb.test/v1",
               VL_FALLBACK_KEY="fb-key", VL_FALLBACK_MODEL="fb-vl")
    calls, constructed, sleeps = _install(
        monkeypatch, [LIMIT_1305, Exception("API 访问量过大"), LIMIT_429, "好了"]
    )

    draft = vision.generate_comment(_make_png(tmp_path / "shot.png"), cfg=cfg)
    assert draft == "好了"
    assert len(calls) == 4, "1305 与「访问量过大」都应走重试+切备用"


def test_non_transient_raises_immediately(tmp_path, monkeypatch):
    calls, constructed, sleeps = _install(monkeypatch, [Exception("Error code: 401")])

    with pytest.raises(Exception, match="401"):
        vision.generate_comment(_make_png(tmp_path / "shot.png"), cfg=dict(MAIN))

    assert sleeps == [], "401 不是瞬态错误，不许重试"
    assert len(calls) == 1


def test_incomplete_fallback_skipped(tmp_path, monkeypatch):
    cfg = dict(MAIN, VL_FALLBACK_API_BASE="https://fb.test/v1",
               VL_FALLBACK_KEY="fb-key")  # 缺 VL_FALLBACK_MODEL
    calls, constructed, sleeps = _install(monkeypatch, [LIMIT_429] * 3)

    with pytest.raises(RuntimeError) as exc:
        vision.generate_comment(_make_png(tmp_path / "shot.png"), cfg=cfg)

    assert vision.LIMIT_HINT in str(exc.value)
    assert len(calls) == 3, "备用三项不齐时不得发起第四次调用"
