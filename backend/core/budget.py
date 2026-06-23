"""LLM 调用预算追踪 —— 按查询隔离的调用计数与成本控制。

使用 contextvars 确保每个请求有独立的预算计数器。
当调用次数或估算成本超过阈值时，budget_ok() 返回 False，
调用方应跳过昂贵操作（如 HyDE/Step-back 重写）。
"""

import contextvars

from backend.core.config import (
    LLM_COST_PER_1K_TOKENS,
    MAX_COST_PER_QUERY,
    MAX_LLM_CALLS_PER_QUERY,
)
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

_call_count_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_llm_call_count", default=0
)
_estimated_tokens_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_llm_estimated_tokens", default=0
)


def reset_budget() -> None:
    """每轮对话开始时重置预算计数器。"""
    _call_count_var.set(0)
    _estimated_tokens_var.set(0)


def record_llm_call(estimated_tokens: int = 0) -> None:
    """记录一次 LLM 调用。

    Args:
        estimated_tokens: 估算的 token 消耗量（输入+输出），用于成本估算。
    """
    count = _call_count_var.get() + 1
    _call_count_var.set(count)
    tokens = _estimated_tokens_var.get() + estimated_tokens
    _estimated_tokens_var.set(tokens)


def budget_ok() -> bool:
    """检查当前查询是否仍在预算内。

    Returns:
        True 表示还有预算，可以继续调用 LLM。
        False 表示已超限，应跳过昂贵操作。
    """
    count = _call_count_var.get()
    tokens = _estimated_tokens_var.get()
    estimated_cost = (tokens / 1000) * LLM_COST_PER_1K_TOKENS

    if count >= MAX_LLM_CALLS_PER_QUERY:
        logger.warning(
            "LLM 调用预算耗尽: %d/%d 次, 估算成本 $%.4f",
            count, MAX_LLM_CALLS_PER_QUERY, estimated_cost,
        )
        return False

    if estimated_cost >= MAX_COST_PER_QUERY:
        logger.warning(
            "LLM 成本预算耗尽: $%.4f/$%.4f, 已调用 %d 次",
            estimated_cost, MAX_COST_PER_QUERY, count,
        )
        return False

    return True


def get_budget_status() -> dict:
    """返回当前预算状态信息（用于日志和调试）。"""
    return {
        "call_count": _call_count_var.get(),
        "max_calls": MAX_LLM_CALLS_PER_QUERY,
        "estimated_tokens": _estimated_tokens_var.get(),
        "estimated_cost": (_estimated_tokens_var.get() / 1000) * LLM_COST_PER_1K_TOKENS,
        "max_cost": MAX_COST_PER_QUERY,
    }
