"""VL 模块：把截图交给用户自己配置的 OpenAI 兼容 Vision 接口，取回评论草稿。"""
import base64
import json
import os
from pathlib import Path

from openai import OpenAI

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
SYSTEM_PROMPT = (
    "你是一个朋友圈评论助手。看到以下朋友圈截图，请生成一条真诚、自然、不做作的中文评论草稿。"
    "只返回评论文本，不要加前缀说明。"
)


def load_config():
    """环境变量优先，其次仓库根目录的 config.json。"""
    cfg = {k: v for k, v in os.environ.items() if k.startswith("VL_") and v}
    if not cfg and CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return cfg


def generate_comment(image_path, cfg=None):
    """返回评论文本；配置缺失或接口报错都抛异常，由调用方提示。"""
    cfg = cfg or load_config()
    missing = [k for k in ("VL_API_KEY", "VL_MODEL") if not cfg.get(k)]
    if missing:
        raise RuntimeError("缺少配置 %s（请设环境变量或写 config.json）" % "、".join(missing))

    client = OpenAI(api_key=cfg["VL_API_KEY"], base_url=cfg.get("VL_API_BASE"))
    png_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    resp = client.chat.completions.create(
        model=cfg["VL_MODEL"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "按这张朋友圈截图写一条评论。"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png_b64}},
                ],
            },
        ],
        timeout=60,
    )
    return (resp.choices[0].message.content or "").strip()
