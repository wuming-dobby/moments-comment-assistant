"""VL 模块：把截图交给用户自己配置的 OpenAI 兼容 Vision 接口，取回评论草稿。"""
import base64
import json
import os
from pathlib import Path

from openai import OpenAI

import paths

SYSTEM_PROMPT = (
    "你是一个朋友圈评论助手。看到以下朋友圈截图，请生成一条真诚、自然、不做作的中文评论草稿。"
    "只返回评论文本，不要加前缀说明。"
)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_config(env=None, path=None):
    """字段级合并：VL_* 环境变量 > %APPDATA%\\MomentsAssistant\\config.json > 旧 config.json。

    只设一个环境变量时，其余字段仍从文件取（v0.1 是整体覆盖，会缺 Model 报错）。
    """
    env = dict(os.environ if env is None else env)
    env_cfg = {k: v for k, v in env.items() if k.startswith("VL_") and v}

    target = Path(path or paths.config_path())
    cfg = {}

    legacy = paths.LEGACY_CONFIG
    if legacy.exists() and legacy.resolve() != target.resolve():
        old = _read_json(legacy)
        if old:
            cfg.update(old)
            try:  # 一次性迁移，成功后把旧文件改名，避免反复迁
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
                legacy.rename(legacy.with_name(legacy.name + ".migrated"))
                paths.log().info("config: 已从旧 config.json 迁移到 %s", target)
            except OSError as exc:
                paths.log().warning("config: 迁移失败 %s", exc)

    cfg.update(_read_json(target))
    cfg.update(env_cfg)
    return cfg


def save_field(key, value):
    """往 config.json 里写一个键（常显开关等界面状态），其余字段保留。"""
    target = Path(paths.config_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    cfg = _read_json(target)
    cfg[key] = value
    target.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_comment(image_path, cfg=None):
    """返回评论文本；配置缺失或接口报错都抛异常，由调用方提示。"""
    cfg = cfg or load_config()
    missing = [k for k in ("VL_API_KEY", "VL_MODEL") if not cfg.get(k)]
    if missing:
        raise RuntimeError("缺少配置 %s（点浮窗右键「设置 API…」）" % "、".join(missing))

    base = (cfg.get("VL_API_BASE") or "").strip() or None
    client = OpenAI(api_key=cfg["VL_API_KEY"], base_url=base)
    png_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    paths.log().info("api: model=%s base=%s key=%s", cfg.get("VL_MODEL"), base or "(默认)",
                     paths.mask_key(cfg["VL_API_KEY"]))
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
