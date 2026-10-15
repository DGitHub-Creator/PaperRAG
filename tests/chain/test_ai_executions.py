"""P0-7 的 chain 判据：`/internal/v1/ai/*` 在**真服务**上的生命周期（`-k ai_executions`）。

与 `tests/integration/test_ai_executions_internal_surface.py` 的分工要说清：
集成层用 `TestClient` + 桩 loader，判的是**语义**（幂等键、终态不可逆、错误码信封）；
本层打的是 `dev.py serve` 起的那个真进程，用的是**真 `document_loader`**，判的是
"这条面在真栈上到底通不通"。两层的断言会重叠，但只有这层能证明没有导入路径、
依赖注入或配置读取上的空转。

三个刻意的设计：
  - **成功路径不靠竞态**：取消语义用「已过 deadline 的行不起跑」和「终态不可逆」两条
    确定性路径验，不去抢"提交后立刻 cancel"的时间窗——那种用例会随机器负载偶发红，
    而偶发红的门禁最后都会被人加 `|| true`（`08 §6`）。
  - **令牌只从环境变量读**：它没有默认值，缺了就红并给出可执行的下一步；
    把 dev 令牌写进仓库等于给内部面一个公开口令。
  - **文件名走 `payload.filename` 引用**：`inputs` 不传字节，所以本用例先把一份
    真 PDF 落进 `UPLOAD_DIR`，再让服务自己去解析。
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.chain

EXECUTE = "/internal/v1/ai/execute"
SUBMIT = "/internal/v1/ai/executions"
HEALTHZ = "/internal/v1/ai/healthz"

FIXTURE_PDF = "chain-fixture.pdf"


def _token() -> str:
    tok = os.environ.get("AICORE_INTERNAL_TOKEN", "")
    if not tok:
        pytest.fail(
            "内部执行面需要 AICORE_INTERNAL_TOKEN。dev 形态下起服务与跑用例要用同一个值：\n"
            "  $env:AICORE_INTERNAL_TOKEN='<本机随机值>'   # 先设进会话\n"
            "  uv run python scripts/dev.py serve         # 用它起 ai-core\n"
            "  uv run python -m pytest -m chain -k ai_executions\n"
            "留空时这一面按设计拒绝一切请求（internal_api/auth.py），所以缺令牌不是环境问题，"
            "但**也不该让用例静默通过**。"
        )
    return tok


@pytest.fixture(scope="session")
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}"}


@pytest.fixture(scope="session")
def fixture_pdf() -> str:
    """把一份**真能解析**的 PDF 放进服务的上传目录。

    集成层用的是 `b"%PDF-1.4 fake"`——桩 loader 不读字节所以够用，但真解析器会 PARSE_FAILED，
    于是"成功路径"就只能在桩上验，永远落不到 real 档。
    """
    import fitz

    from backend.core.config import UPLOAD_DIR

    target = Path(UPLOAD_DIR) / FIXTURE_PDF
    if not target.exists():
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "ResearchPilot chain fixture.")
        page.insert_text((72, 130), "Section one: chunking under structural splitting.")
        page.insert_text((72, 160), "Section two: citations, formulas, retrieval trace.")
        doc.save(target)
        doc.close()
    return FIXTURE_PDF


def body(task_id: str, task_type: str = "PARSE_PAPER", filename: str = FIXTURE_PDF,
         minutes: int = 10, **extra) -> dict:
    """`idempotency_key` 与 `deadline` 都是必填，且 deadline 必须带时区。"""
    payload = extra.pop("payload", {"filename": filename})
    return {
        "task_id": task_id,
        "task_type": task_type,
        "idempotency_key": f"chain-run:{task_type}:{task_id}",
        "deadline": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "payload": payload,
        **extra,
    }


def _new_task_id() -> str:
    return f"chain-{uuid.uuid4().hex[:10]}"


def test_ai_executions_healthz_is_401_without_token_and_200_with(http, chain_endpoints, auth):
    """P0-7 验收点名的那条：无 token 401。顺带确证"有 token 时这面确实是活的"——
    只测拒绝会漏掉"整面永远 401"这种假绿。"""
    anonymous = http.get(chain_endpoints.py(HEALTHZ))
    assert anonymous.status_code == 401, anonymous.text
    assert "detail" in anonymous.json(), "错误信封只有一种形状（contracts/error-codes.md §2）"

    ok = http.get(chain_endpoints.py(HEALTHZ), headers=auth)
    assert ok.status_code == 200, ok.text


def test_ai_executions_wrong_token_is_401(http, chain_endpoints):
    resp = http.get(chain_endpoints.py(HEALTHZ),
                    headers={"Authorization": "Bearer definitely-not-the-token"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "内部令牌无效"


def test_ai_executions_execute_parses_a_real_pdf(http, chain_endpoints, auth, fixture_pdf):
    """成功路径：真解析器读真 PDF，返回 succeeded 且 chunk_count 是真实分块数。"""
    task_id = _new_task_id()
    resp = http.post(chain_endpoints.py(EXECUTE), json=body(task_id), headers=auth)
    assert resp.status_code == 200, resp.text
    row = resp.json()
    assert row["status"] == "succeeded", row
    assert row["result"]["filename"] == fixture_pdf
    assert row["result"]["parsed"] is True
    assert row["result"]["chunk_count"] >= 1, f"解析出了 0 块说明解析器根本没读到这页：{row}"
    assert uuid.UUID(row["execution_id"]), "execution_id 必须是 UUID"


def test_ai_executions_submit_then_poll_then_result(http, chain_endpoints, auth, fixture_pdf):
    """异步提交 → 轮询状态 → 领取结果（卡片验收点名的三段）。"""
    task_id = _new_task_id()
    submitted = http.post(chain_endpoints.py(SUBMIT), json=body(task_id), headers=auth)
    # 200 不是 202：`POST /executions` 走的是同步返回行的形态（router.py:134），
    # 而 K4 之后校验失败也降级成 400——判据要照实现与契约，不能照 REST 直觉。
    assert submitted.status_code == 200, submitted.text
    execution_id = submitted.json()["execution_id"]
    assert submitted.json()["status"] in ("queued", "running", "succeeded")

    result = _await_result(http, chain_endpoints, auth, execution_id)
    assert result["status"] == "succeeded", result
    assert result["result"]["parsed"] is True


def test_ai_executions_repeat_task_id_never_reruns(http, chain_endpoints, auth, fixture_pdf):
    """幂等：同一 `task_id` 第二次直接返回既有行，`replayed=True`，不重跑解析。"""
    task_id = _new_task_id()
    first = http.post(chain_endpoints.py(EXECUTE), json=body(task_id), headers=auth)
    second = http.post(chain_endpoints.py(EXECUTE), json=body(task_id), headers=auth)
    assert first.json()["execution_id"] == second.json()["execution_id"], "命中幂等键必须复用同一行"
    assert second.json()["result"] == first.json()["result"]

    replay = http.post(chain_endpoints.py(SUBMIT), json=body(task_id), headers=auth)
    assert replay.json().get("replayed") is True, replay.text


def test_ai_executions_cancel_on_a_finished_row_is_not_replayed(http, chain_endpoints, auth, fixture_pdf):
    """终态不可逆：跑完之后再 cancel，状态必须还是 succeeded，结果照样领得到。

    这条钉的是 §3.4 的另一半——"过期结果被丢弃"只适用于**还没结束**的行，
    把已经写好的结果抹掉会让 Go 领到一个不存在的执行。
    """
    task_id = _new_task_id()
    executed = http.post(chain_endpoints.py(EXECUTE), json=body(task_id), headers=auth)
    execution_id = executed.json()["execution_id"]

    cancelled = http.post(chain_endpoints.py(f"{SUBMIT}/{execution_id}/cancel"), headers=auth)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "succeeded", "终态不可逆"

    after = http.get(chain_endpoints.py(f"{SUBMIT}/{execution_id}/result"), headers=auth)
    assert after.status_code == 200, after.text
    assert after.json()["result"]["parsed"] is True


def test_ai_executions_expired_deadline_never_starts(http, chain_endpoints, auth, fixture_pdf):
    """已过 deadline 的行不起跑：`start()` 直接判 MODEL_TIMEOUT，所以"过期结果被丢弃"
    有一条**不靠竞态**的可验路径（提交后必然还是这个终态）。"""
    task_id = _new_task_id()
    submitted = http.post(chain_endpoints.py(SUBMIT), json=body(task_id, minutes=-1), headers=auth)
    assert submitted.status_code == 200, submitted.text
    execution_id = submitted.json()["execution_id"]

    final = _await_terminal(http, chain_endpoints, auth, execution_id)
    assert final["status"] == "failed", final
    errors = http.get(chain_endpoints.py(f"{SUBMIT}/{execution_id}/result"), headers=auth)
    assert errors.status_code == 504, errors.text
    assert errors.json()["errors"][0]["code"] == "MODEL_TIMEOUT", "Go 靠 code 区分，不靠文本"
    assert errors.json()["errors"][0]["retryable"] is True, "超时是可重试的，与 PARSE_FAILED 相反"


def test_ai_executions_unregistered_task_type_is_400(http, chain_endpoints, auth):
    """没注册的类型必须显式失败，不能走到某个看起来能跑的默认分支（registry.py 的立身理由）。"""
    resp = http.post(chain_endpoints.py(EXECUTE), json=body(_new_task_id(), task_type="READ_PAPER"),
                     headers=auth)
    assert resp.status_code == 400, resp.text
    assert resp.json()["errors"][0]["code"] == "UNSUPPORTED_TASK_TYPE"
    assert resp.json()["errors"][0]["retryable"] is False


def test_ai_executions_invalid_payload_codes_are_distinguishable(http, chain_endpoints, auth, fixture_pdf):
    """三种"失败"的码必须能分开：请求体缺字段（400）、payload 引用的文件不存在（422）、
    字段齐但类型没注册（400）。混成一个码，Go 就无法判断该重试、该报错，还是该提示用户重传。"""
    missing_file = http.post(
        chain_endpoints.py(EXECUTE),
        json=body(_new_task_id(), payload={}),
        headers=auth,
    )
    assert missing_file.status_code == 400, missing_file.text
    assert missing_file.json()["errors"][0]["code"] == "INVALID_PAYLOAD"

    no_required_fields = http.post(
        chain_endpoints.py(EXECUTE),
        json={"task_id": _new_task_id(), "task_type": "PARSE_PAPER"},
        headers=auth,
    )
    assert no_required_fields.status_code == 400, no_required_fields.text
    assert set(no_required_fields.json()) == {"detail"}, "K4 之后校验失败降级成 400 + 一句话"

    not_on_disk = http.post(
        chain_endpoints.py(EXECUTE),
        json=body(_new_task_id(), filename="definitely-not-uploaded.pdf"),
        headers=auth,
    )
    assert not_on_disk.status_code == 422, not_on_disk.text
    assert not_on_disk.json()["errors"][0]["code"] == "PARSE_FAILED"


def test_ai_executions_naive_deadline_is_rejected(http, chain_endpoints, auth):
    """不带时区的 deadline 会被两侧各自按本地时间解释，幂等与超时判定都会漂移。

    实现里它由 `model_validator` 挡下，再经 K4 降级为 **400**（不是 FastAPI 默认的 422）。
    """
    payload = body(_new_task_id())
    payload["deadline"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    resp = http.post(chain_endpoints.py(EXECUTE), json=payload, headers=auth)
    assert resp.status_code == 400, resp.text
    assert "deadline" in resp.json()["detail"], resp.text


def test_ai_executions_unknown_id_is_404_on_all_read_paths(http, chain_endpoints, auth):
    for method, path in (
        ("GET", f"{SUBMIT}/does-not-exist"),
        ("GET", f"{SUBMIT}/does-not-exist/result"),
        ("POST", f"{SUBMIT}/does-not-exist/cancel"),
    ):
        resp = getattr(http, method.lower())(chain_endpoints.py(path), headers=auth)
        assert resp.status_code == 404, f"{method} {path} → {resp.status_code} {resp.text[:120]}"


def test_ai_executions_surface_is_invisible_to_the_go_entry(http, chain_endpoints):
    """内部面只能由带令牌的进程内调用打到，**不能**经 Go 的公开入口访问。

    Go 的反代确实覆盖 `/internal/*`（dev 形态需要它），所以这里判的是：浏览器不带内部令牌时
    经 Go 打过去仍然 401——R3 管住 nginx，这条管住 Go 门面本身。
    """
    resp = http.get(chain_endpoints.go(HEALTHZ))
    assert resp.status_code == 401, f"经公开入口打内部面必须拒绝，实得 {resp.status_code} {resp.text[:120]}"


# ── 轮询helper：等待上限 20 s，够真解析跑完一轮 ──

def _await_result(http, chain_endpoints, auth, execution_id: str, *, tries: int = 40) -> dict:
    import time

    for _ in range(tries):
        resp = http.get(chain_endpoints.py(f"{SUBMIT}/{execution_id}/result"), headers=auth)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 409:
            # 409 才是"还没结束"；其余是终态失败（504/422/409-CANCELLED 各自映射），
            # 直接把响应体摊开——等一条永远不会成功的路径是这类用例最难查的形态。
            pytest.fail(f"{execution_id} 以非成功终态结束：{resp.status_code} {resp.text[:300]}")
        time.sleep(0.5)
    pytest.fail(f"{execution_id} 在 {tries * 0.5:.0f} s 内没出结果")


def _await_terminal(http, chain_endpoints, auth, execution_id: str, *, tries: int = 40) -> dict:
    import time

    for _ in range(tries):
        resp = http.get(chain_endpoints.py(f"{SUBMIT}/{execution_id}"), headers=auth)
        assert resp.status_code == 200, resp.text
        status = resp.json()["status"]
        if status in ("succeeded", "failed", "cancelled"):
            return resp.json()
        time.sleep(0.5)
    pytest.fail(f"{execution_id} 一直没进终态")
