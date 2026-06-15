"""统一日志配置 —— 为所有模块提供标准化日志输出。

日志格式统一化：
    [2026-05-20 15:05:10] [INFO   ] module_name [filename:lineno] - message

特性:
- 控制台输出: INFO 级别，简洁格式
- 文件输出: DEBUG 级别，含文件名/行号
- 模块级 logger 获取函数，无需各模块重复配置 handler
"""

import logging
import sys
from pathlib import Path

# ── 日志格式 ──────────────────────────────────────────────────────
CONSOLE_FORMAT = (
    "[%(asctime)s] [%(levelname)-7s] %(name)s [%(filename)s:%(lineno)d] - %(message)s"
)
FILE_FORMAT = CONSOLE_FORMAT  # 文件与控制台使用相同格式
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── 日志目录 ──────────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# ── 全局初始化标记 ────────────────────────────────────────────────
_initialized = False


def setup_root_logger() -> None:
    """初始化根 logger：控制台 + 文件双输出。

    仅需在 app.py 入口调用一次，后续各模块通过 get_logger() 获取
    子 logger 即可自动继承 handler。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 控制台 handler（INFO 级别）
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # 文件 handler（DEBUG 级别）
    file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger。

    各模块调用 get_logger(__name__) 即可获得已配置的 logger，
    无需自行添加 handler。

    Args:
        name: 通常传入 __name__，自动映射为短模块名（如 'rag_utils'）。

    Returns:
        已配置的 logging.Logger 实例。
    """
    # 将 __name__ 映射为短名称（去掉 'backend.' 等前缀）
    short_name = name.rsplit(".", 1)[-1] if "." in name else name
    logger = logging.getLogger(short_name)
    return logger
