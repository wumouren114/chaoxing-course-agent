"""
日志模块 —— 统一的运行日志（控制台 + 文件）
按天分文件，记录等级/时间/模块/消息
"""
import logging
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOGGER = None


def get_logger(name="agent", level=logging.INFO):
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 文件 handler（按天）
    log_file = LOG_DIR / f"agent_{datetime.now():%Y%m%d}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台 handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    _LOGGER = logger
    return logger


if __name__ == "__main__":
    log = get_logger("test")
    log.info("这是一条信息")
    log.warning("这是一条警告")
    log.error("这是一条错误")
    print("✅ 日志模块测试通过，日志文件:", LOG_DIR)
