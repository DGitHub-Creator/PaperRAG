"""AI 执行状态机：内存单测与 PostgreSQL 生产存储共用转换语义。"""

import copy
from contextlib import contextmanager
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.internal_api.codes import spec_for
from backend.internal_api.schemas import ErrorDetail, ExecuteRequest, Status, Usage

TERMINAL: frozenset[Status] = frozenset({"succeeded", "failed", "cancelled"})


def _now() -> datetime:
    return datetime.now(UTC)


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
    request_payload: dict | None = None
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


def new_execution(req: ExecuteRequest) -> Execution:
    now = _now()
    return Execution(
        execution_id=str(uuid.uuid4()), task_id=req.task_id, task_type=req.task_type,
        idempotency_key=req.idempotency_key, status="queued", deadline=req.deadline,
        created_at=now, updated_at=now, run_id=req.run_id, trace_id=req.trace_id, request_payload=req.model_dump(mode="json"),
    )


class ExecutionStore:
    """单测用内存存储；生产 PostgreSQL 实现复用下面的状态转换。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._rows: dict[str, Execution] = {}
        self._by_idempotency: dict[tuple[str | None, str], str] = {}
        self._by_task_id: dict[str, str] = {}
        self._active: set[str] = set()

    @contextmanager
    def run_lock(self, execution_id: str):
        with self._lock:
            acquired = execution_id not in self._active
            if acquired:
                self._active.add(execution_id)
        try:
            yield acquired
        finally:
            if acquired:
                with self._lock:
                    self._active.discard(execution_id)

    def pending_ids(self):
        with self._lock:
            identifiers = [row.execution_id for row in self._rows.values() if row.status not in TERMINAL]
        yield from identifiers

    def reset(self) -> None:
        with self._lock:
            self._rows.clear()
            self._by_idempotency.clear()
            self._by_task_id.clear()

    def submit(self, req: ExecuteRequest) -> tuple[Execution, bool]:
        key = (req.run_id, req.idempotency_key)
        with self._lock:
            existing = self._by_idempotency.get(key) or self._by_task_id.get(req.task_id)
            if existing is not None:
                return copy.deepcopy(self._rows[existing]), True
            row = new_execution(req)
            self._rows[row.execution_id] = row
            self._by_idempotency[key] = row.execution_id
            self._by_task_id[row.task_id] = row.execution_id
            return copy.deepcopy(row), False

    def _mutate(self, execution_id, change):
        with self._lock:
            row = self._rows.get(execution_id)
            if row is None:
                return None
            result = change(row)
            return copy.deepcopy(result)

    def get(self, execution_id: str) -> Execution | None:
        def read(row):
            if row.status not in TERMINAL and row.deadline <= _now():
                self._fail_locked(row, "MODEL_TIMEOUT", "执行已超过 deadline", Usage(calls=0, tokens=0, cost=0))
            return row
        return self._mutate(execution_id, read)

    def start(self, execution_id: str, lease_token: str | None = None, *, recover: bool = False) -> Execution | None:
        def change(row):
            if row.status != "queued" and not (recover and row.status == "running"):
                return None
            if row.deadline <= _now():
                self._fail_locked(row, "MODEL_TIMEOUT", "deadline 已到，任务未起跑", Usage(calls=0, tokens=0, cost=0))
                return None
            row.status, row.lease_token, row.updated_at = "running", lease_token, _now()
            return row
        return self._mutate(execution_id, change)

    def succeed(self, execution_id: str, *, result=None, result_ref=None, proposed_tasks=None, evidence_candidates=None, usage=None, lease_token=None):
        if (result is None) == (result_ref is None):
            raise ValueError("result 与 result_ref 必须且只能提供一项")

        def change(row):
            if row.status == "cancelled":
                return None
            if row.status in TERMINAL:
                return row
            if row.status != "running" or row.lease_token != lease_token:
                return None
            if row.deadline <= _now():
                return self._fail_locked(row, "MODEL_TIMEOUT", "结果超过 deadline，已丢弃", usage)
            row.result, row.result_ref = copy.deepcopy(result), result_ref
            row.proposed_tasks = copy.deepcopy(proposed_tasks or [])
            row.evidence_candidates = copy.deepcopy(evidence_candidates or [])
            row.usage, row.status, row.updated_at = copy.deepcopy(usage), "succeeded", _now()
            return row
        return self._mutate(execution_id, change)

    def fail(self, execution_id: str, code: str, detail: str, *, usage=None, trace_id=None, lease_token=None):
        def change(row):
            if row.status in TERMINAL:
                return row
            if row.lease_token is not None and row.lease_token != lease_token:
                return None
            return self._fail_locked(row, code, detail, usage, trace_id)
        return self._mutate(execution_id, change)

    def cancel(self, execution_id: str) -> Execution | None:
        def change(row):
            if row.status not in TERMINAL:
                row.status, row.updated_at = "cancelled", _now()
                row.errors = [_error("CANCELLED", "任务被取消；过期结果将被丢弃", row.trace_id)]
            return row
        return self._mutate(execution_id, change)

    @staticmethod
    def _fail_locked(row, code, detail, usage=None, trace_id=None):
        row.status, row.updated_at, row.usage = "failed", _now(), copy.deepcopy(usage)
        row.errors = [_error(code, detail, trace_id or row.trace_id)]
        return row


def _error(code: str, detail: str, trace_id: str | None) -> ErrorDetail:
    spec = spec_for(code)
    return ErrorDetail(code=spec.code, retryable=spec.retryable, detail=detail, trace_id=trace_id)
