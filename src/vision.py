"""VL 模块：把截图交给用户自己配置的 OpenAI 兼容 Vision 接口，取回评论草稿。"""
import base64
import io
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from PIL import Image

import paths

MAX_EDGE = 800
JPEG_QUALITY = 75

RETRY_DELAYS = (2, 4)
FALLBACK_KEYS = ("VL_FALLBACK_API_BASE", "VL_FALLBACK_KEY", "VL_FALLBACK_MODEL")
TRANSIENT_CODES = ("429", "1305", "1302")
TRANSIENT_HINTS = ("访问量过大",)
LIMIT_HINT = "免费池高峰会限流，属正常，稍后再试或配置备用通道"

_sleep = time.sleep

SYSTEM_PROMPT_TEMPLATE = (
    "你就是用户本人，正在给微信好友的朋友圈写评论。按下面的人设和规矩写。\n"
    "\n"
    "【人设】{persona_block}\n"
    "\n"
    "【规矩】\n"
    "1. 5~25个字，像真人随手打的字，口语。最多1个emoji，也可以不用。\n"
    "2. 必须抓帖子里一个具体细节（那盘菜、那个地方、那只猫、那件事）来说。空泛夸奖一律不行。\n"
    "3. 禁用：太棒了、为你点赞、精彩分享、必须支持、羡慕了家人们、绝绝子、yyds。不许连续感叹号，不许排比，不许上价值升华，不许广告腔。\n"
    "4. 看帖子氛围定语气：\n"
    "   喜事好消息→真诚祝贺，很熟的朋友可以轻微调侃；\n"
    "   生病难过坏消息→简短关心，绝不幽默；\n"
    "   日常风景美食→轻松，可以幽默；\n"
    "   晒娃晒宠物→夸具体细节；\n"
    "   工作加班→共情，不打鸡血。\n"
    "5. 幽默只在帖子本身轻松时用，不强行抖机灵；拿不准就朴实真诚。\n"
    "6. 玩笑尺度按人设里的熟络程度把握：「很熟」才调侃；「偏同事客户」客气克制，不拆台。\n"
    "\n"
    "【范例】\n"
    "晒红烧肉→\"这色泽，米饭杀手啊\"（好）／\"太棒了！厨艺精湛，为你点赞！\"（坏：广告腔）\n"
    "晒娃\"终于会走路了\"→\"恭喜，离离家出走又近一步\"（好：熟人调侃，抓细节）／\"宝宝好可爱，天天开心！\"（坏：空泛）\n"
    "加班深夜→\"辛苦了，早点歇\"（好）／\"加油！奋斗的人最美丽！\"（坏：打鸡血）\n"
    "\n"
    "只输出评论正文，不要引号、解释或候选。"
)

PERSONA_FALLBACK = "未填写，按普通朋友的分寸写，朴实真诚。"

_PERSONA_LABELS = (
    ("VL_PERSONA_GENDER", "性别"),
    ("VL_PERSONA_STYLE", "说话风格"),
    ("VL_PERSONA_CATCHPHRASE", "口头禅"),
    ("VL_PERSONA_CLOSENESS", "与好友熟络度"),
)

_QUOTE_PAIRS = {"「": "」", "“": "”", '"': '"', "'": "'"}


def build_persona_block(cfg):
    """人设四字段拼接成「性别：X；说话风格：X；…」，空项跳过；全空用兜底文案。"""
    parts = []
    for key, label in _PERSONA_LABELS:
        value = str(cfg.get(key) or "").strip()
        if value:
            parts.append("%s：%s" % (label, value))
    if not parts:
        return PERSONA_FALLBACK
    return "；".join(parts)


def _strip_quotes(text):
    """strip 后去掉首尾成对引号（「」“” \" '），循环剥净。"""
    text = (text or "").strip()
    while len(text) >= 2 and text[-1] == _QUOTE_PAIRS.get(text[0]):
        text = text[1:-1].strip()
    return text


def image_to_data_url(image_path):
    """长边压到 800px、JPEG q75 后转 data URL；本地保存的截图文件不动。"""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > MAX_EDGE:
            scale = MAX_EDGE / max(w, h)
            img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=JPEG_QUALITY)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


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


def _is_transient(exc):
    text = str(exc)
    return any(code in text for code in TRANSIENT_CODES) or any(
        hint in text for hint in TRANSIENT_HINTS
    )


def _call_vl(cfg, data_url):
    base = (cfg.get("VL_API_BASE") or "").strip() or None
    client = OpenAI(api_key=cfg["VL_API_KEY"], base_url=base)
    paths.log().info("api: model=%s base=%s key=%s", cfg.get("VL_MODEL"), base or "(默认)",
                     paths.mask_key(cfg["VL_API_KEY"]))
    resp = client.chat.completions.create(
        model=cfg["VL_MODEL"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(persona_block=build_persona_block(cfg))},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "按这张朋友圈截图写一条评论。"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        max_tokens=512,  # v0.3.1: 混合推理模型（deepseek/GLM/qwen3-vl）思考要占 token，40 会被烧光致 content 空
        temperature=0.8,
        timeout=60,
    )
    return _strip_quotes(resp.choices[0].message.content)


def _fallback_cfg(cfg):
    """三项 VL_FALLBACK_* 齐全才返回备用配置，否则 None。"""
    if not all((cfg.get(k) or "").strip() for k in FALLBACK_KEYS):
        return None
    merged = dict(cfg)
    merged.update({
        "VL_API_BASE": cfg["VL_FALLBACK_API_BASE"],
        "VL_API_KEY": cfg["VL_FALLBACK_KEY"],
        "VL_MODEL": cfg["VL_FALLBACK_MODEL"],
    })
    return merged


def generate_comment(image_path, cfg=None):
    """返回评论文本；配置缺失或接口报错都抛异常，由调用方提示。

    瞬态错误（429/1305/1302/访问量过大）：主通道重试 2 次（2s/4s 退避），仍失败且
    配了备用通道（VL_FALLBACK_* 三项齐全）再切备用试 1 次。红线：不做多账号轮询/代理池。
    """
    cfg = cfg or load_config()
    missing = [k for k in ("VL_API_KEY", "VL_MODEL") if not cfg.get(k)]
    if missing:
        raise RuntimeError("缺少配置 %s（点浮窗右键「设置 API…」）" % "、".join(missing))

    data_url = image_to_data_url(image_path)
    last_exc = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return _call_vl(cfg, data_url)
        except Exception as exc:
            if not _is_transient(exc):
                raise
            last_exc = exc
            if attempt < len(RETRY_DELAYS):
                paths.log().warning("api: 瞬态错误（%s），%ds 后重试 %d/%d",
                                    exc, RETRY_DELAYS[attempt], attempt + 1, len(RETRY_DELAYS))
                _sleep(RETRY_DELAYS[attempt])

    fb = _fallback_cfg(cfg)
    if fb is not None:
        paths.log().warning("api: 主通道重试后仍失败，切换备用通道 %s", fb["VL_MODEL"])
        try:
            return _call_vl(fb, data_url)
        except Exception as exc:
            last_exc = exc
            paths.log().error("api: 备用通道也失败：%s", exc)
    raise RuntimeError("VL 调用失败：%s。%s" % (last_exc, LIMIT_HINT))
