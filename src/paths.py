"""统一路径：配置、日志、截图都放 %APPDATA%\\MomentsAssistant。

onefile 打包后 __file__ 落在 _MEIPASS 临时目录，退出即删，不能用来存配置
（v0.1 的配置就是这样每次启动都丢的）。
"""
import logging
import logging.handlers
import os
from pathlib import Path

APP_NAME = "MomentsAssistant"
APP_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
LEGACY_CONFIG = Path(__file__).resolve().parents[1] / "config.json"
KEEP_SHOTS = 20

_log_ready = False


def config_path() -> Path:
    return APP_DIR / "config.json"


def shot_dir() -> Path:
    return APP_DIR / "screenshots"


def log_path() -> Path:
    return APP_DIR / "app.log"


def ensure_dirs() -> None:
    for p in (APP_DIR, shot_dir()):
        p.mkdir(parents=True, exist_ok=True)


def setup_logging(debug: bool = False) -> logging.Logger:
    global _log_ready
    logger = logging.getLogger(APP_NAME)
    if _log_ready:
        return logger
    ensure_dirs()
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    try:
        fh = logging.handlers.RotatingFileHandler(
            str(log_path()), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # 另一个实例占着日志文件时不影响启动
    if debug:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    _log_ready = True
    return logger


def log() -> logging.Logger:
    return logging.getLogger(APP_NAME)


def mask_key(key: str) -> str:
    """日志里只留 Key 后 4 位。"""
    if not key:
        return "(空)"
    return "***" + key[-4:] if len(key) > 4 else "***"


def prune_shots(keep: int = KEEP_SHOTS) -> None:
    files = sorted(shot_dir().glob("capture_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
