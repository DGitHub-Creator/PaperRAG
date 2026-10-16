import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from backend.internal_api.postgres_executions import PostgresExecutionStore
from backend.internal_api.schemas import ExecuteRequest


def request():
    identifier = uuid4().hex
    return ExecuteRequest(
        task_id=identifier, task_type="PARSE_PAPER", run_id="quality",
        idempotency_key=f"quality:PARSE_PAPER:{identifier}",
        deadline=datetime.now(UTC) + timedelta(minutes=2), payload={"filename": "paper.pdf"},
    )


def test_concurrent_submit_is_unique_and_new_instance_sees_committed_state(isolated_pg_factory):
    store = PostgresExecutionStore(isolated_pg_factory)
    req = request()
    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(lambda _: store.submit(req), range(12)))
    assert len({row.execution_id for row, _ in results}) == 1
    assert sum(not replayed for _, replayed in results) == 1
    row = results[0][0]
    assert PostgresExecutionStore(isolated_pg_factory).get(row.execution_id).status == "queued"


def test_cancel_and_fencing_reject_late_result_and_failure(isolated_pg_factory):
    store = PostgresExecutionStore(isolated_pg_factory)
    row, _ = store.submit(request())
    store.start(row.execution_id, lease_token="current")
    assert store.succeed(row.execution_id, result={"wrong": True}, lease_token="stale") is None
    assert store.get(row.execution_id).status == "running"
    store.cancel(row.execution_id)
    assert store.succeed(row.execution_id, result={"late": True}, lease_token="current") is None
    assert store.fail(row.execution_id, "INTERNAL", "late", lease_token="current").status == "cancelled"
    assert PostgresExecutionStore(isolated_pg_factory).get(row.execution_id).status == "cancelled"


def test_result_pointer_and_terminal_state_survive_a_new_process(isolated_pg_factory):
    store = PostgresExecutionStore(isolated_pg_factory)
    row, _ = store.submit(request())
    store.start(row.execution_id)
    store.succeed(row.execution_id, result_ref="pg://result/one")
    assert store.fail(row.execution_id, "INTERNAL", "late error").status == "succeeded"
    env = os.environ.copy()
    env["DATABASE_URL"] = env["REFACTOR_TEST_DATABASE_URL"]
    code = "from backend.internal_api.router import store; r=store.get('" + row.execution_id + "'); print(r.status, r.result_ref)"
    process = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert process.returncode == 0, "新进程读取执行记录失败"
    assert process.stdout.strip().endswith("succeeded pg://result/one")


def test_abandoned_running_execution_expires_persistently(isolated_pg_factory):
    store = PostgresExecutionStore(isolated_pg_factory)
    row, _ = store.submit(request())
    store.start(row.execution_id)
    with isolated_pg_factory.begin() as db:
        db.execute(text("UPDATE ai_executions SET deadline = :deadline WHERE execution_id = :id"), {
            "deadline": datetime.now(UTC) - timedelta(seconds=1), "id": row.execution_id,
        })
    status = PostgresExecutionStore(isolated_pg_factory).get(row.execution_id)
    assert status.status == "failed"
    assert status.errors[0].code == "MODEL_TIMEOUT"
    assert store.get(row.execution_id).status == "failed"
