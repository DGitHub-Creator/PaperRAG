"""统一日志配置 —— 为所有模块提供标准化日志输出。

日志格式统一化：
    [2026-05-20 15:05:10] [INFO   ] module_name [filename:lineno] - message

特性:
- 控制台输出: INFO 级别，简洁格式
- 文件输出: DEBUG 级别，含文件名/行号
- JSON 模式（可选）: 通过 JSON_LOG=true 环境变量开启，输出结构化 JSON 日志
  包含 timestamp、level、module、message、trace_id 字段，便于接入 APM
- 模块级 logger 获取函数，无需各模块重复配置 handler
"""

import json
import logging
import os
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

# ── JSON 模式 ────────────────────────────────────────────────────
JSON_LOG_ENABLED = os.getenv("JSON_LOG", "false").lower() == "true"

# ── 全局初始化标记 ────────────────────────────────────────────────
_initialized = False


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志格式化器。

    输出格式:
        {"timestamp": "...", "level": "INFO", "module": "...",
         "filename": "...", "lineno": 123, "message": "..."}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, DATE_FORMAT),
            "level": record.levelname,
            "module": record.name,
            "filename": record.filename,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_root_logger() -> None:
    """初始化根 logger：控制台 + 文件双输出。

    仅需在 app.py 入口调用一次，后续各模块通过 get_logger() 获取
    子 logger 即可自动继承 handler。

    当 JSON_LOG=true 时，控制台输出 JSON 格式日志。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    if JSON_LOG_ENABLED:
        json_fmt = JsonFormatter()
        # 控制台 handler（INFO 级别，JSON 格式）
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(json_fmt)
        root.addHandler(console)

        # 文件 handler（DEBUG 级别，JSON 格式）
        fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(json_fmt)
        root.addHandler(fh)
    else:
        text_fmt = logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT)
        # 控制台 handler（INFO 级别）
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(text_fmt)
        root.addHandler(console)

        # 文件 handler（DEBUG 级别）
        fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(text_fmt)
        root.addHandler(fh)


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
