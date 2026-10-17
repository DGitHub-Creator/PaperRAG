"""`/internal/v1/ai` 路由（02 §3.1 的六个端点 + 探活）。

三条语义在这个文件里落地，都是 §3.4 的硬要求：

- 幂等：重复 `task_id` / `(run_id, idempotency_key)` 返回既有 `execution_id`，
  且 `replayed=true`，**不重跑**（省钱的关键，也是 Go 重试的前提）。
- 取消：`/cancel` 之后，运行中的结果在落库前被丢弃（`ExecutionStore.succeed` 返回 None）。
- 超时：deadline 已过而不起跑也算失败并写 `usage`，Go 是唯一记账方。

错误体是 `{"detail": "<给人看>", "errors": [{"code","retryable",...}]}`：`detail` 让全仓
只有信封这一条约定继续成立，`errors[].code` 让 Go 不解析文本就能区分同为 400 的
`INVALID_PAYLOAD` 与 `UNSUPPORTED_TASK_TYPE`（`contracts/error-codes.md` §1）。
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from uuid import uuid4

from backend.api.health import health as _liveness
from backend.api.health import readiness as _readiness
from backend.internal_api.auth import require_internal_token
from backend.internal_api.codes import spec_for
from backend.internal_api.executions import Execution
from backend.internal_api.postgres_executions import PostgresExecutionStore
from backend.core.logging_config import get_logger
from backend.internal_api.registry import REGISTRY, TaskError
from backend.internal_api.schemas import (
    ErrorDetail,
    ExecuteRequest,
    ResultResponse,
    StatusResponse,
    SubmitResponse,
)

router = APIRouter(prefix="/internal/v1/ai", tags=["内部执行面"], dependencies=[Depends(require_internal_token)])
store = PostgresExecutionStore()
logger = get_logger(__name__)

_NOT_FOUND = JSONResponse(status_code=404, content={"detail": "Execution not found"})


def _error(code: str, detail: str, trace_id: str | None = None) -> ErrorDetail:
    spec = spec_for(code)  # type: ignore[arg-type]
    return ErrorDetail(code=spec.code, retryable=spec.retryable, detail=detail, trace_id=trace_id)


def _error_response(code: str, detail: str, trace_id: str | None = None) -> JSONResponse:
    spec = spec_for(code)  # type: ignore[arg-type]
    return JSONResponse(
        status_code=spec.http,
        content={"detail": detail, "errors": [_error(code, detail, trace_id).model_dump(mode="json")]},
    )


def _status_response(row: Execution) -> StatusResponse:
    return StatusResponse(
        execution_id=row.execution_id,
        status=row.status,
        usage=row.usage,
        errors=row.errors or None,
        updated_at=row.updated_at,
    )


def _result_response(row: Execution) -> ResultResponse:
    return ResultResponse(
        execution_id=row.execution_id,
        status=row.status,
        result=row.result,
        result_ref=row.result_ref,
        proposed_tasks=row.proposed_tasks or None,
        evidence_candidates=row.evidence_candidates or None,
        usage=row.usage,
        errors=row.errors or None,
    )


def _terminal_failure_response(row: Execution) -> JSONResponse:
    """失败/取消的执行没有合法 ResultResponse（契约要求 result 与 result_ref 二选一），
    所以按错误码自己的 HTTP 映射返回，而不是把 200 用在"完成但没结果"上。"""
    first = row.errors[0] if row.errors else _error("INTERNAL", "执行失败且未记录错误码", row.trace_id)
    return _error_response(first.code, first.detail, first.trace_id)


def _run(execution_id: str, req: ExecuteRequest | None = None, *, recover: bool = False) -> Execution | None:
    with store.run_lock(execution_id) as acquired:
        if not acquired:
            return store.get(execution_id)
        current = store.get(execution_id)
        if current is None or current.status in {"succeeded", "failed", "cancelled"}:
            return current
        try:
            # 幂等重试必须执行首次已接受的输入，不能偷偷换成本次请求的 payload。
            req = ExecuteRequest.model_validate(current.request_payload)
        except ValueError:
            return store.fail(execution_id, "INVALID_PAYLOAD", "执行缺少有效的恢复输入，请重新提交新任务", lease_token=current.lease_token)
        lease_token = uuid4().hex
        if store.start(execution_id, lease_token=lease_token, recover=recover) is None:
            return store.get(execution_id)
        spec = REGISTRY.get(req.task_type)
        if spec is None:
            return store.fail(execution_id, "UNSUPPORTED_TASK_TYPE", "任务类型未注册", trace_id=req.trace_id, lease_token=lease_token)
        try:
            outcome = spec.handler(req)
        except TaskError as exc:
            return store.fail(execution_id, exc.code, exc.detail, trace_id=req.trace_id, lease_token=lease_token)
        except Exception:
            logger.exception("内部执行失败: execution_id=%s, trace_id=%s", execution_id, req.trace_id)
            return store.fail(execution_id, "INTERNAL", "内部执行失败，请按 trace_id 查询日志", trace_id=req.trace_id, lease_token=lease_token)
        finished = store.succeed(
            execution_id, result=outcome.result, proposed_tasks=outcome.proposed_tasks,
            evidence_candidates=outcome.evidence_candidates, usage=outcome.usage, lease_token=lease_token,
        )
        return finished if finished is not None else store.get(execution_id)


def recover_executions() -> int:
    """启动时恢复本地已接受请求；PG 锁排除其他进程仍在执行的记录。"""
    recovered = 0
    for execution_id in store.pending_ids():
        result = _run(execution_id, recover=True)
        if result is not None and result.status in {"succeeded", "failed", "cancelled"}:
            recovered += 1
    return recovered


def _pending_response(row: Execution) -> JSONResponse:
    """结果还没产生。等待由 Go 轮询状态表达，不占错误码（九码里没有"尚未结束"这一码）。"""
    return JSONResponse(status_code=409, content={"detail": f"执行尚未结束（status={row.status}）"})


def _response_for(row: Execution) -> ResultResponse | JSONResponse:
    if row.status == "succeeded":
        return _result_response(row)
    if row.status in {"queued", "running"}:
        return _pending_response(row)
    return _terminal_failure_response(row)


@router.post("/execute", response_model=None)
def execute(req: ExecuteRequest) -> ResultResponse | JSONResponse:
    """同步执行单个有界任务（§3.1：只用于确定短时的任务，必须带 deadline）。"""
    if req.task_type not in REGISTRY:
        return _error_response("UNSUPPORTED_TASK_TYPE", f"未注册的任务类型：{req.task_type}", req.trace_id)

    try:
        row, replayed = store.submit(req)
    except ValueError as exc:
        return _error_response("INVALID_PAYLOAD", str(exc), req.trace_id)
    # 幂等命中一个还没起跑的行也由本次调用跑完；命中已结束的则直接返回既有结果，不重跑模型
    if row.status == "queued":
        row = _run(row.execution_id, req) or row
    return _response_for(row)


@router.post("/executions", response_model=None)
def submit(req: ExecuteRequest, background_tasks: BackgroundTasks) -> SubmitResponse | JSONResponse:
    """提交即返回 `execution_id`，执行放到响应之后的后台任务里（异步前置，§3.1）。"""
    if req.task_type not in REGISTRY:
        return _error_response("UNSUPPORTED_TASK_TYPE", f"未注册的任务类型：{req.task_type}", req.trace_id)

    try:
        row, replayed = store.submit(req)
    except ValueError as exc:
        return _error_response("INVALID_PAYLOAD", str(exc), req.trace_id)
    if row.status == "queued":
        background_tasks.add_task(_run, row.execution_id, req)
    return SubmitResponse(execution_id=row.execution_id, status=row.status, replayed=replayed)


@router.get("/executions/{execution_id}", response_model=None)
def get_status(execution_id: str) -> StatusResponse | JSONResponse:
    row = store.get(execution_id)
    if row is None:
        return _NOT_FOUND
    return _status_response(row)


@router.get("/executions/{execution_id}/result", response_model=None)
def get_result(execution_id: str) -> ResultResponse | JSONResponse:
    row = store.get(execution_id)
    if row is None:
        return _NOT_FOUND
    return _response_for(row)


@router.post("/executions/{execution_id}/cancel", response_model=None)
def cancel(execution_id: str) -> StatusResponse | JSONResponse:
    row = store.cancel(execution_id)
    if row is None:
        return _NOT_FOUND
    return _status_response(row)


@router.get("/healthz")
async def healthz():
    """沿用 `backend/api/health.py` 的存活语义，不另造一套探活。"""
    return await _liveness()


@router.get("/readyz")
async def readyz():
    """沿用就绪探针的三项依赖检查（PG/Redis/Milvus），失败仍是 503。"""
    return await _readiness()
