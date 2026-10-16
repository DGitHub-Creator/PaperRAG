"""LLM 调用预算追踪 —— 按查询隔离的调用计数与成本控制。

使用 contextvars 确保每个请求有独立的预算计数器。
当调用次数或估算成本超过阈值时，budget_ok() 返回 False，
调用方应跳过昂贵操作（如 HyDE/Step-back 重写）。
"""

import contextvars
from dataclasses import dataclass, field
from threading import Lock

from backend.core.config import (
    LLM_COST_PER_1K_TOKENS,
    MAX_COST_PER_QUERY,
    MAX_LLM_CALLS_PER_QUERY,
)
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class _Budget:
    calls: int = 0
    tokens: int = 0
    lock: Lock = field(default_factory=Lock)


_budget_var: contextvars.ContextVar[_Budget | None] = contextvars.ContextVar("llm_budget", default=None)


def _current_budget() -> _Budget:
    budget = _budget_var.get()
    if budget is None:
        budget = _Budget()
        _budget_var.set(budget)
    return budget


def reset_budget() -> None:
    # 一轮请求一个可共享对象；LangGraph 子任务/线程复制上下文时仍共享本轮计数。
    _budget_var.set(_Budget())


def record_llm_call(estimated_tokens: int = 0) -> None:
    if estimated_tokens < 0:
        raise ValueError("token 估算值不得为负数")
    budget = _current_budget()
    with budget.lock:
        budget.calls += 1
        budget.tokens += estimated_tokens


def budget_ok() -> bool:
    """检查当前查询是否仍在预算内。

    Returns:
        True 表示还有预算，可以继续调用 LLM。
        False 表示已超限，应跳过昂贵操作。
    """
    status = get_budget_status()
    count = status["call_count"]
    tokens = status["estimated_tokens"]
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
    budget = _current_budget()
    with budget.lock:
        calls, tokens = budget.calls, budget.tokens
    return {
        "call_count": calls,
        "max_calls": MAX_LLM_CALLS_PER_QUERY,
        "estimated_tokens": tokens,
        "estimated_cost": (tokens / 1000) * LLM_COST_PER_1K_TOKENS,
        "max_cost": MAX_COST_PER_QUERY,
    }
