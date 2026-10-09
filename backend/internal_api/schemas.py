"""内部执行面的请求/响应模型，逐字段照 `contracts/ai-execution.schema.json` 的 `$defs`。

`extra="forbid"` 不是 stylistic：契约里所有 `$defs` 对象都写了 `additionalProperties: false`，
Go 多发一个字段就必须是 400 而不是被静默吃掉——静默吃掉会让两边对"这个字段有没有生效"产生分歧。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TaskType = Literal[
    "PLAN_RESEARCH",
    "SEARCH_PAPERS",
    "SCREEN_PAPERS",
    "PARSE_PAPER",
    "INDEX_PAPER",
    "READ_PAPER",
    "EXTRACT_KNOWLEDGE",
    "COMPARE_PAPERS",
    "EXPLORE_GAPS",
    "VERIFY_EVIDENCE",
    "GENERATE_REPORT",
]

Status = Literal["queued", "running", "succeeded", "failed", "cancelled"]

ErrorCode = Literal[
    "INVALID_PAYLOAD",
    "UNSUPPORTED_TASK_TYPE",
    "BUDGET_EXCEEDED",
    "MODEL_TIMEOUT",
    "MODEL_RATE_LIMIT",
    "PARSE_FAILED",
    "INDEX_UNAVAILABLE",
    "CANCELLED",
    "INTERNAL",
]

# 02 §3.4 的 canonical 形式：run_id:task_type:canonical_target，三段都不许为空
_IDEMPOTENCY_PATTERN = r"^[^:]+:[^:]+:.+$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Budget(Strict):
    max_llm_calls: int | None = Field(default=None, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)


class TaskConfig(Strict):
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)


class TaskInputs(Strict):
    object_ids: list[str] | None = None


class Usage(Strict):
    calls: int = Field(ge=0)
    tokens: int = Field(ge=0)
    cost: float = Field(ge=0)


class ErrorDetail(Strict):
    code: ErrorCode
    retryable: bool
    detail: str
    trace_id: str | None = None


class ExecuteRequest(Strict):
    task_id: str
    task_type: TaskType
    idempotency_key: str = Field(pattern=_IDEMPOTENCY_PATTERN)
    deadline: datetime
    run_id: str | None = None
    payload: dict | None = None
    inputs: TaskInputs | None = None
    config: TaskConfig | None = None
    budget: Budget | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _deadline_must_be_tz_aware(self) -> "ExecuteRequest":
        # 不带时区的 deadline 会被两边各自按本地时间解释，幂等判定与超时判定都会漂移
        if self.deadline.tzinfo is None:
            raise ValueError("deadline 必须带时区（ISO 8601，如 2026-10-09T12:00:00Z）")
        return self


class SubmitResponse(Strict):
    execution_id: str
    status: Status
    replayed: bool | None = None


class StatusResponse(Strict):
    execution_id: str
    status: Status
    usage: Usage | None = None
    errors: list[ErrorDetail] | None = None
    updated_at: datetime | None = None


class ResultResponse(Strict):
    execution_id: str
    status: Status
    result: dict | None = None
    result_ref: str | None = None
    proposed_tasks: list[dict] | None = None
    evidence_candidates: list[dict] | None = None
    usage: Usage | None = None
    errors: list[ErrorDetail] | None = None

    @model_validator(mode="after")
    def _result_xor_result_ref(self) -> "ResultResponse":
        # 契约用 oneOf 表达"大输出走引用、不内联"，两个都给或都不给都不合法
        if (self.result is None) == (self.result_ref is None):
            raise ValueError("result 与 result_ref 必须恰好提供一个")
        return self
