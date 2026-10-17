"""`ai_executions` 状态机的单元级验证（02 §3.4 的幂等/取消/超时三条）。

这些语义在 HTTP 层不好复现（TestClient 的 BackgroundTasks 在响应内就跑完了），
所以在存储层直接断言。HTTP 层的等价用例见 `tests/integration/test_ai_executions_internal_surface.py`。
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.internal_api.executions import ExecutionStore
from backend.internal_api.schemas import ExecuteRequest

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_req(task_id: str = "t-1", run_id: str = "r-1", key: str | None = None, seconds: int = 60) -> ExecuteRequest:
    return ExecuteRequest(
        task_id=task_id,
        run_id=run_id,
        task_type="PARSE_PAPER",
        idempotency_key=key or f"{run_id}:PARSE_PAPER:{task_id}",
        deadline=_now() + timedelta(seconds=seconds),
        payload={"filename": "a.pdf"},
    )


def test_repeat_submit_returns_same_execution():
    store = ExecutionStore()
    first, replayed_a = store.submit(make_req())
    second, replayed_b = store.submit(make_req())
    assert replayed_a is False and replayed_b is True
    assert first.execution_id == second.execution_id


def test_task_id_is_also_an_idempotency_key():
    """§3.4 要求"以 task_id 建行"：Go 重试时 run_id 未必每次都带得一样。"""
    store = ExecutionStore()
    first, _ = store.submit(make_req(task_id="same", run_id="r-1"))
    second, replayed = store.submit(make_req(task_id="same", run_id="r-2"))
    assert replayed is True
    assert second.execution_id == first.execution_id


def test_expired_deadline_never_starts_and_writes_usage():
    store = ExecutionStore()
    row, _ = store.submit(make_req(seconds=-1))
    assert store.start(row.execution_id) is None
    after = store.get(row.execution_id)
    assert after.status == "failed"
    assert after.errors[0].code == "MODEL_TIMEOUT"
    assert after.usage is not None, "超时也要写 usage，Go 据此记账"


def test_cancelled_execution_discards_late_result():
    store = ExecutionStore()
    row, _ = store.submit(make_req())
    store.start(row.execution_id)
    store.cancel(row.execution_id)
    assert store.succeed(row.execution_id, result={"chunk_count": 1}) is None
    assert store.get(row.execution_id).status == "cancelled", "取消后的过期结果必须被丢弃，不能反写回 succeeded"


def test_cancel_is_terminal_and_no_op_after_success():
    store = ExecutionStore()
    row, _ = store.submit(make_req())
    store.start(row.execution_id)
    store.succeed(row.execution_id, result={"ok": True})
    after = store.cancel(row.execution_id)
    assert after.status == "succeeded"


def test_read_returns_snapshot_not_the_live_row():
    """响应序列化在锁外进行，所以拿到的必须是快照，否则并发的状态推进会改掉正在发送的响应。"""
    store = ExecutionStore()
    row, _ = store.submit(make_req())
    store.start(row.execution_id, lease_token="L1")
    snapshot = store.succeed(row.execution_id, result={"chunks": [{"page": 1}]}, lease_token="L1")
    snapshot.status = "queued"
    snapshot.result["chunks"].append({"page": 2})
    again = store.get(row.execution_id)
    assert again.status == "succeeded"
    assert again.result == {"chunks": [{"page": 1}]}


def test_execution_retains_first_request_when_retried_with_other_payload():
    store = ExecutionStore()
    first = make_req()
    first.payload = {"filename": "first.pdf"}
    row, replayed = store.submit(first)
    assert replayed is False
    changed = first.model_copy(update={"payload": {"filename": "replacement.pdf"}})
    retried, replayed = store.submit(changed)
    assert replayed is True and retried.execution_id == row.execution_id
    assert retried.request_payload["payload"]["filename"] == "first.pdf"


def test_recovered_lease_fences_result_from_interrupted_attempt():
    store = ExecutionStore()
    row, _ = store.submit(make_req())
    store.start(row.execution_id, lease_token="old")
    with store.run_lock(row.execution_id) as acquired:
        assert acquired
        with store.run_lock(row.execution_id) as duplicate:
            assert duplicate is False
        assert store.start(row.execution_id, lease_token="new", recover=True) is not None
        assert store.succeed(row.execution_id, result={"stale": True}, lease_token="old") is None
        assert store.succeed(row.execution_id, result={"fresh": True}, lease_token="new").status == "succeeded"
