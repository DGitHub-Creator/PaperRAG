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


def test_execution_owner_cannot_be_stolen_by_another_store(isolated_pg_factory):
    first = PostgresExecutionStore(isolated_pg_factory)
    second = PostgresExecutionStore(isolated_pg_factory)
    row, _ = first.submit(request())
    with first.run_lock(row.execution_id) as owned:
        assert owned
        with second.run_lock(row.execution_id) as stolen:
            assert stolen is False
    with second.run_lock(row.execution_id) as recovered:
        assert recovered is True
    first.cancel(row.execution_id)


def test_process_crash_replays_accepted_request_from_postgresql(isolated_pg_factory, tmp_path, monkeypatch):
    import fitz
    from backend.internal_api import registry, router

    path = tmp_path / "paper.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 550, 780), "Actual parsing recovery regression with substantive research methodology and verified results. " * 25, fontsize=10)
        document.save(path)
    store = PostgresExecutionStore(isolated_pg_factory)
    req = request()
    row, _ = store.submit(req)
    environment = {**os.environ, "DATABASE_URL": os.environ["REFACTOR_TEST_DATABASE_URL"]}
    script = """
import os, sys
from pathlib import Path
from backend.internal_api import registry, router
from backend.rag.document_loader import DocumentLoader
registry.UPLOAD_DIR = Path(sys.argv[2])
load = DocumentLoader.load_document
def crash_after_real_parse(self, *arguments):
    load(self, *arguments)
    os._exit(17)
DocumentLoader.load_document = crash_after_real_parse
router._run(sys.argv[1])
raise RuntimeError('fault point not reached')
"""
    child = subprocess.run([sys.executable, "-c", script, row.execution_id, str(tmp_path)], env=environment, capture_output=True, timeout=120)
    assert child.returncode == 17, child.stderr.decode("utf-8", errors="replace")[-2000:]
    assert store.get(row.execution_id).status == "running"
    assert store.get(row.execution_id).request_payload["payload"] == req.payload
    monkeypatch.setattr(registry, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(router, "store", PostgresExecutionStore(isolated_pg_factory))
    assert router.recover_executions() >= 1
    recovered = router.store.get(row.execution_id)
    assert recovered.status == "succeeded"
    assert recovered.result["parsed"] is True and recovered.result["chunk_count"] > 0
    # A changed retry cannot replace the original request or rerun a terminal execution.
    changed = req.model_copy(update={"payload": {"filename": "different.pdf"}})
    assert router._run(row.execution_id, changed).result == recovered.result
