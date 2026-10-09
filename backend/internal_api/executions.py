"""`ai_executions` 行的状态机与存储（Python 独占写，02 §3.4）。

这里的进程内实现是 **mock 级验证用的那一份**：字段与将来的 `ai_executions` 表一一对应，
幂等键、租约比对、"取消后丢弃过期结果"三条语义都在这一层实现并可被单测覆盖。
换成 PG 后端时要改的是这个类的持久化，不是 router 的语义。
"""

import copy
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from backend.internal_api.codes import spec_for
from backend.internal_api.schemas import ErrorDetail, ExecuteRequest, Status, Usage

TERMINAL: frozenset[Status] = frozenset({"succeeded", "failed", "cancelled"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Execution:
    execution_id: str
    task_id: str
    task_type: str
    idempotency_key: str
    status: Status
    deadline: datetime
    created_at: datetime
    updated_at: datetime
    run_id: str | None = None
    trace_id: str | None = None
    lease_token: str | None = None
    result: dict | None = None
    result_ref: str | None = None
    proposed_tasks: list[dict] = field(default_factory=list)
    evidence_candidates: list[dict] = field(default_factory=list)
    usage: Usage | None = None
    errors: list[ErrorDetail] = field(default_factory=list)

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"


class ExecutionStore:
    """幂等提交 + 状态推进。所有变更都在锁内完成，对外一律返回快照副本。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, Execution] = {}
        self._by_idempotency: dict[tuple[str | None, str], str] = {}
        self._by_task_id: dict[str, str] = {}

    def reset(self) -> None:
        with self._lock:
            self._rows.clear()
            self._by_idempotency.clear()
            self._by_task_id.clear()

    def submit(self, req: ExecuteRequest) -> tuple[Execution, bool]:
        """重复提交返回既有 execution_id（`replayed=True`），**不重跑模型**。

        两个键都要查：契约的 UNIQUE 是 `(run_id, idempotency_key)`，而 §3.4 又要求
        "以 task_id 建行"，Go 重试时可能只保住其中一个。
        """
        key = (req.run_id, req.idempotency_key)
        with self._lock:
            existing_id = self._by_idempotency.get(key) or self._by_task_id.get(req.task_id)
            if existing_id is not None:
                return _view(self._rows[existing_id]), True

            now = _now()
            row = Execution(
                execution_id=str(uuid.uuid4()),
                task_id=req.task_id,
                task_type=req.task_type,
                idempotency_key=req.idempotency_key,
                run_id=req.run_id,
                trace_id=req.trace_id,
                status="queued",
                deadline=req.deadline,
                created_at=now,
                updated_at=now,
            )
            self._rows[row.execution_id] = row
            self._by_idempotency[key] = row.execution_id
            self._by_task_id[row.task_id] = row.execution_id
            return _view(row), False

    def get(self, execution_id: str) -> Execution | None:
        with self._lock:
            row = self._rows.get(execution_id)
            return None if row is None else _view(row)

    def start(self, execution_id: str, lease_token: str | None = None) -> Execution | None:
        """queued → running。已经取消/过期/终态的执行返回 None，调用方据此不起跑。"""
        with self._lock:
            row = self._rows.get(execution_id)
            if row is None or row.status != "queued":
                return None
            if row.deadline <= _now():
                self._fail_locked(row, "MODEL_TIMEOUT", "deadline 已到，任务未起跑", Usage(calls=0, tokens=0, cost=0))
                return None
            row.status = "running"
            row.lease_token = lease_token
            row.updated_at = _now()
            return _view(row)

    def succeed(
        self,
        execution_id: str,
        *,
        result: dict | None = None,
        result_ref: str | None = None,
        proposed_tasks: list[dict] | None = None,
        evidence_candidates: list[dict] | None = None,
        usage: Usage | None = None,
    ) -> Execution | None:
        """写结果前比对是否已被取消：取消后的过期结果直接丢弃（§3.4）。"""
        with self._lock:
            row = self._rows.get(execution_id)
            if row is None:
                return None
            if row.status == "cancelled":
                return None
            if row.status in TERMINAL:
                return _view(row)
            row.result = result
            row.result_ref = result_ref
            row.proposed_tasks = proposed_tasks or []
            row.evidence_candidates = evidence_candidates or []
            row.usage = usage
            row.status = "succeeded"
            row.updated_at = _now()
            return _view(row)

    def fail(
        self,
        execution_id: str,
        code: str,
        detail: str,
        *,
        usage: Usage | None = None,
        trace_id: str | None = None,
    ) -> Execution | None:
        with self._lock:
            row = self._rows.get(execution_id)
            if row is None:
                return None
            return _view(self._fail_locked(row, code, detail, usage, trace_id))

    def cancel(self, execution_id: str) -> Execution | None:
        """协作取消。终态不可逆：已经跑完的不把结果抹掉，Go 按 /result 领取即可。"""
        with self._lock:
            row = self._rows.get(execution_id)
            if row is None:
                return None
            if row.status in TERMINAL:
                return _view(row)
            row.status = "cancelled"
            row.errors = [_error("CANCELLED", "任务被取消；运行中产生的过期结果会被丢弃", row.trace_id)]
            row.updated_at = _now()
            return _view(row)

    def _fail_locked(
        self,
        row: Execution,
        code: str,
        detail: str,
        usage: Usage | None = None,
        trace_id: str | None = None,
    ) -> Execution:
        row.status = "failed"
        row.usage = usage
        row.errors = [_error(code, detail, trace_id or row.trace_id)]
        row.updated_at = _now()
        return row


def _error(code: str, detail: str, trace_id: str | None) -> ErrorDetail:
    spec = spec_for(code)  # type: ignore[arg-type]
    return ErrorDetail(code=spec.code, retryable=spec.retryable, detail=detail, trace_id=trace_id)


def _view(row: Execution) -> Execution:
    """锁内做的快照：响应序列化发生在锁外，不能让并发写入改到调用方手上的行。"""
    return replace(
        row,
        result=copy.deepcopy(row.result),
        proposed_tasks=list(row.proposed_tasks),
        evidence_candidates=list(row.evidence_candidates),
        errors=list(row.errors),
    )


# 进程内单例。Go 侧对接时换成 PG 后端；换的是持久化，不是状态机语义。
store = ExecutionStore()
