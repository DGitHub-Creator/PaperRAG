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
import re
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

# ── 日志格式 ──────────────────────────────────────────────────────
CONSOLE_FORMAT = (
    "[%(asctime)s] [%(levelname)-7s] %(name)s [%(filename)s:%(lineno)d] [trace_id=%(trace_id)s] - %(message)s"
)
FILE_FORMAT = CONSOLE_FORMAT  # 文件与控制台使用相同格式
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── 日志目录 ──────────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

# ── JSON 模式 ────────────────────────────────────────────────────
JSON_LOG_ENABLED = os.getenv("JSON_LOG", "false").lower() == "true"

# ── 全局初始化标记 ────────────────────────────────────────────────
_initialized = False
request_trace_id: ContextVar[str] = ContextVar("request_trace_id", default="-")

# ── 请求追踪号的接受集合（契约 components.parameters.TraceId，台账 C38）──────
# 头名与这串字面量同 Go 的 server/internal/observability/trace.go:TraceIDHeader/TraceIDRule、
# 契约 openapi.yaml 的 name/pattern 必须逐字节相同，由 scripts/check_contracts.py 三方核对。
# 追踪号只用于关联日志：不参与认证/授权判定，也不能当幂等键或防重放凭据。
TRACE_ID_HEADER = "X-Trace-Id"
TRACE_ID_RULE = r"^[A-Za-z0-9._-]{1,128}$"
_TRACE_ID_RE = re.compile(TRACE_ID_RULE)


def sanitize_trace_id(inbound: str | None) -> str:
    """入站追踪号合法就沿用，非法或缺失就新生成一个 32 位十六进制值。

    用 fullmatch 而不是 match：Python 的 `$` 也允许匹配结尾换行之前的位置，
    `match` 会把 "abc\\n" 判成合法值，而 Go 的 RE2 不会 —— 两侧接受集合一漂，
    同一个请求在两端日志里就再也关联不起来。非法入站值不回显。
    """
    if inbound is not None and _TRACE_ID_RE.fullmatch(inbound):
        return inbound
    return uuid4().hex


class _TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = request_trace_id.get()
        return True


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
        log_entry["trace_id"] = getattr(record, "trace_id", request_trace_id.get())
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
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = JsonFormatter() if JSON_LOG_ENABLED else logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    for handler in (console, file_handler):
        handler.setFormatter(formatter)
        handler.addFilter(_TraceFilter())
        root.addHandler(handler)
    _initialized = True


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
