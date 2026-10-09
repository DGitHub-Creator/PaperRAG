"""`/internal/v1/ai` 的 HTTP 级用例（09 P0-7 验收）。

这里是 **mock 级**证据：进程内 store、假 loader、假 writer，不碰 PG/Milvus/LLM。
链级用例（`pytest -m chain -k ai_executions`）要真容器，本机没有 Docker，记为 not_run。

断言的重点不是"能跑通"，而是三条契约语义真的落地：幂等不重跑、取消后结果被丢弃、
两侧都写 usage；以及 Go 只读 `errors[].code` 就能区分同为 400/409 的不同原因。
"""

import re
from datetime import datetime, timedelta, timezone
from json import loads
from pathlib import Path

import pytest

from backend.internal_api.executions import store
from backend.internal_api.registry import REGISTRY
from backend.internal_api.schemas import ExecuteRequest

pytestmark = pytest.mark.integration

TOKEN = "internal-test-token"
EXECUTE = "/internal/v1/ai/execute"
SUBMIT = "/internal/v1/ai/executions"
SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "ai-execution.schema.json"
OPENAPI = SCHEMA.parent / "openapi.yaml"


def _normalize(path: str) -> str:
    """`{id}` 与 `{execution_id}` 是同一位形状，比对时都要归一。"""
    return re.sub(r"\{[^}]+\}", "{}", path)


def _deadline(seconds: int = 60) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def base(task_id: str = "t-1", task_type: str = "PARSE_PAPER", filename: str = "a.pdf", key: str | None = None, **extra) -> dict:
    body = {
        "task_id": task_id,
        "task_type": task_type,
        "idempotency_key": key or f"r-1:{task_type}:{task_id}",
        "run_id": "r-1",
        "payload": {"filename": filename},
        "deadline": _deadline(),
        "trace_id": "trace-abc",
    }
    body.update(extra)
    return body


@pytest.fixture(autouse=True)
def _configured_token(monkeypatch):
    """每个用例独立的令牌与独立的 store：store 是模块单例，不重置会串味。"""
    monkeypatch.setattr("backend.core.config.AICORE_INTERNAL_TOKEN", TOKEN, raising=False)
    store.reset()
    yield
    store.reset()


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def uploads(monkeypatch, tmp_path):
    d = tmp_path / "uploads"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr("backend.internal_api.registry.UPLOAD_DIR", d)
    return d


@pytest.fixture
def loader_calls(monkeypatch, uploads):
    """假 loader：记录被调用了几次，这就是"幂等没有重跑模型"的直接证据。"""
    calls: list[str] = []

    class _Loader:
        def load_document(self, path: str, filename: str) -> list[dict]:
            calls.append(filename)
            return [{"page_content": "text", "metadata": {"page": 1, "source": path}}]

    monkeypatch.setattr("backend.internal_api.registry.get_document_loader", lambda: _Loader())
    return calls


# ── §3.5 鉴权：内部面对浏览器不可见，未配置即拒绝 ──


@pytest.mark.parametrize(
    ("method", "path", "needs_body"),
    [
        ("get", "/internal/v1/ai/healthz", False),
        ("get", "/internal/v1/ai/readyz", False),
        ("get", "/internal/v1/ai/executions/any-id", False),
        ("get", "/internal/v1/ai/executions/any-id/result", False),
        ("post", "/internal/v1/ai/executions/any-id/cancel", False),
        ("post", EXECUTE, True),
        ("post", SUBMIT, True),
    ],
)
def test_every_internal_route_needs_a_token(client, method, path, needs_body):
    """P0-7 明写 healthz 无 token 也要 401：探活同样只对内网开放。

    POST 带合法 body 是为了证明这个 401 来自鉴权而不是请求体校验。
    """
    resp = getattr(client, method)(path, **({"json": base()} if needs_body else {}))
    assert resp.status_code == 401
    assert set(resp.json().keys()) == {"detail"}


def test_wrong_token_is_401(client):
    resp = client.get("/internal/v1/ai/healthz", headers={"Authorization": "Bearer not-the-token"})
    assert resp.status_code == 401
    assert "无效" in resp.json()["detail"]


def test_unconfigured_token_refuses_service(client, monkeypatch, auth):
    monkeypatch.setattr("backend.core.config.AICORE_INTERNAL_TOKEN", "", raising=False)
    resp = client.get("/internal/v1/ai/healthz", headers=auth)
    assert resp.status_code == 401
    assert "未配置" in resp.json()["detail"], "没配令牌必须是拒绝，不能默认开放"


# ── §3.1 同步执行 ──


def test_execute_returns_result(client, auth, loader_calls):
    resp = client.post(EXECUTE, json=base(), headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["result"] == {"filename": "a.pdf", "chunk_count": 1, "parsed": True}
    assert body["usage"] == {"calls": 0, "tokens": 0, "cost": 0}
    assert loader_calls == ["a.pdf"]


def test_healthz_with_token(client, auth):
    resp = client.get("/internal/v1/ai/healthz", headers=auth)
    assert resp.status_code == 200


# ── §3.1 异步提交 + 轮询 + 领取结果 ──


def test_submit_then_poll_then_result(client, auth, loader_calls):
    submitted = client.post(SUBMIT, json=base(), headers=auth).json()
    assert set(submitted) == {"execution_id", "status", "replayed"}
    assert submitted["replayed"] is False
    eid = submitted["execution_id"]

    status = client.get(f"{SUBMIT}/{eid}", headers=auth)
    assert status.status_code == 200
    assert status.json()["status"] == "succeeded", "TestClient 会在响应返回后跑完后台任务"

    result = client.get(f"{SUBMIT}/{eid}/result", headers=auth)
    assert result.json()["result"]["parsed"] is True
    assert loader_calls == ["a.pdf"]


# ── §3.4 幂等：重复提交不重跑模型 ──


def test_repeat_task_id_never_reruns_the_handler(client, auth, loader_calls):
    first = client.post(EXECUTE, json=base(task_id="same"), headers=auth)
    again = client.post(EXECUTE, json=base(task_id="same"), headers=auth)
    posted = client.post(SUBMIT, json=base(task_id="same"), headers=auth)

    assert first.json()["execution_id"] == again.json()["execution_id"] == posted.json()["execution_id"]
    assert posted.json()["replayed"] is True
    assert loader_calls == ["a.pdf"], "命中幂等键必须直接返回既有结果"


def test_replay_matches_on_idempotency_key(client, auth, loader_calls):
    """契约的 UNIQUE 是 `(run_id, idempotency_key)`：task_id 不同但键相同，仍是一次执行。"""
    a = client.post(EXECUTE, json=base(task_id="t-a"), headers=auth)
    b = client.post(EXECUTE, json=base(task_id="t-b", key="r-1:PARSE_PAPER:t-a"), headers=auth)
    assert a.json()["execution_id"] == b.json()["execution_id"]
    assert loader_calls == ["a.pdf"]


def test_cancelled_row_discards_late_result_at_http_level(client, auth):
    """直接在 store 里造一行 queued（模拟 Go 已提交但本轮还没起跑），再用 HTTP 面观察语义。"""
    row, _ = store.submit(ExecuteRequest(**base(task_id="t-q")))

    pending = client.get(f"{SUBMIT}/{row.execution_id}/result", headers=auth)
    assert pending.status_code == 409
    assert set(pending.json()) == {"detail"}, "还没结束不是错误码，只有 detail"

    cancelled = client.post(f"{SUBMIT}/{row.execution_id}/cancel", headers=auth)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    after = client.get(f"{SUBMIT}/{row.execution_id}/result", headers=auth)
    assert after.status_code == 409
    assert after.json()["errors"][0]["code"] == "CANCELLED", "同为 409，Go 靠 code 而不是文本区分"


# ── 错误码与信封（error-codes.md §1） ──


def test_unregistered_task_type_is_unsupported(client, auth, loader_calls):
    resp = client.post(EXECUTE, json=base(task_type="READ_PAPER"), headers=auth)
    assert resp.status_code == 400
    body = resp.json()
    assert set(body) == {"detail", "errors"}
    assert body["errors"][0] == {"code": "UNSUPPORTED_TASK_TYPE", "retryable": False, "detail": body["detail"], "trace_id": "trace-abc"}
    assert loader_calls == []


def test_extra_request_field_is_rejected(client, auth):
    resp = client.post(EXECUTE, json=base(scheduler="go"), headers=auth)
    assert resp.status_code == 400
    assert set(resp.json()) == {"detail"}, "K4：校验失败只有字符串 detail"


@pytest.mark.parametrize("bad", [
    {"deadline": "2026-10-09T12:00:00"},
    {"idempotency_key": "only:two"},
    {"task_id": None},
])
def test_contract_shape_is_enforced(client, auth, bad):
    resp = client.post(EXECUTE, json={**base(), **bad}, headers=auth)
    assert resp.status_code == 400


def test_expired_deadline_fails_before_running(client, auth, loader_calls):
    """deadline 已过：不起跑、直接 failed，并且仍写 usage 供 Go 记账。"""
    sync = client.post(EXECUTE, json=base(task_id="t-s", deadline=_deadline(-1)), headers=auth)
    assert sync.status_code == 504
    assert sync.json()["errors"][0]["code"] == "MODEL_TIMEOUT"
    assert sync.json()["errors"][0]["retryable"] is True

    submitted = client.post(SUBMIT, json=base(task_id="t-a", deadline=_deadline(-1)), headers=auth)
    status = client.get(f"{SUBMIT}/{submitted.json()['execution_id']}", headers=auth)
    assert status.json()["status"] == "failed"
    assert status.json()["usage"] == {"calls": 0, "tokens": 0, "cost": 0}
    assert loader_calls == []


def test_missing_file_is_parse_failed(client, auth, loader_calls):
    resp = client.post(EXECUTE, json=base(filename="ghost.pdf"), headers=auth)
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "PARSE_FAILED"
    assert loader_calls == []


def test_filename_cannot_escape_upload_dir(client, auth, loader_calls, uploads, tmp_path):
    """inputs 只传引用，所以文件名必须被夹在 UPLOAD_DIR 内。"""
    outside = tmp_path / "other.pdf"
    outside.write_bytes(b"%PDF-1.4 outside")
    resp = client.post(EXECUTE, json=base(filename="../other.pdf"), headers=auth)
    assert resp.status_code == 422
    assert "other.pdf" in resp.json()["detail"]
    assert loader_calls == [], "目录外的文件一次都不该被打开"


def test_loader_exception_maps_to_parse_failed(client, auth, uploads, monkeypatch):
    class _Boom:
        def load_document(self, path: str, filename: str) -> list[dict]:
            raise RuntimeError("no text layer")

    monkeypatch.setattr("backend.internal_api.registry.get_document_loader", lambda: _Boom())
    resp = client.post(EXECUTE, json=base(), headers=auth)
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["code"] == "PARSE_FAILED"


def test_index_paper_reports_index_unavailable(client, auth, uploads, monkeypatch):
    """INDEX_PAPER 的失败是依赖故障，必须映射成可重试的 503 而不是 500。"""

    class _Loader:
        def load_document(self, path: str, filename: str) -> list[dict]:
            return [{"page_content": "text", "metadata": {}}]

    class _BoomWriter:
        def write_documents(self, documents: list[dict]) -> int:
            raise RuntimeError("milvus down")

    monkeypatch.setattr("backend.internal_api.registry.get_document_loader", lambda: _Loader())
    monkeypatch.setattr("backend.internal_api.registry.get_milvus_writer", lambda: _BoomWriter())
    resp = client.post(EXECUTE, json=base(task_type="INDEX_PAPER"), headers=auth)
    assert resp.status_code == 503
    assert resp.json()["errors"][0]["code"] == "INDEX_UNAVAILABLE"
    assert resp.json()["errors"][0]["retryable"] is True


def test_unknown_execution_id_is_404(client, auth):
    for method, path in [
        ("get", f"{SUBMIT}/nope"),
        ("get", f"{SUBMIT}/nope/result"),
        ("post", f"{SUBMIT}/nope/cancel"),
    ]:
        resp = getattr(client, method)(path, headers=auth) if method == "get" else client.post(path, headers=auth)
        assert resp.status_code == 404, path
        assert set(resp.json()) == {"detail"}


# ── 实现与契约不许各说各话 ──


def _contract() -> dict:
    return loads(SCHEMA.read_text(encoding="utf-8"))


def test_registered_paths_are_exactly_the_contract_surface(app):
    """`x-endpoints` 声明的 7 条必须与真实注册的路径一一对应，多一条少一条都红。

    内部面不在 `contracts/openapi.yaml` 里，`check_contracts.py` 看不见它；这一条是它唯一的机检。
    """
    declared = set()
    for entry in _contract()["x-endpoints"]:
        method, path = entry.split(" ", 1)
        declared.add(f"{method} {_normalize(path)}")

    actual = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/internal/v1/ai"):
            continue
        for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}):
            actual.add(f"{method} {_normalize(path)}")
    assert actual == declared, f"契约与实现漂移：只在此={actual - declared} 只在那={declared - actual}"


def test_registered_task_types_are_the_p0_two():
    assert sorted(REGISTRY) == sorted(_contract()["x-p0-registered-task-types"])


def test_internal_surface_stays_out_of_the_public_contract():
    assert "/internal/" not in OPENAPI.read_text(encoding="utf-8")
