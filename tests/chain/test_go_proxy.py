"""P1-0 的 chain 判据：Go 反向代理门面在真栈上的行为（`-k proxy`）。

**为什么单独写这个文件**：P1-0 的 `verify` 写的是 `pytest -m chain -k proxy`，
但在本文件出现之前，那个选择器只命中两条**限流**用例（它们名字里带 proxy 是因为
"伪造 X-Forwarded-For"）——命令能跑、用例能绿，而**代理转发本身一条都没测**。
这正是本仓库反复登记的那类错：判据指向了不是它要管的东西（同 C22 的 `rc 恒为 1`、
C31 的"契约声明服务侧却无机检"）。补上这些条，P1-0 的 real 档才有承载物。

各条钉的是：
  1. 鉴权头透传：带令牌的请求经 Go 与直连 Python 拿到同一份结果（403 而非 401 才证明头到了上游）
  2. 未鉴权时错误信封逐字一致（Go 不能把 Python 的 `Not authenticated` 换成自己的文案）
  3. 已提权用户的响应体原样透传（403 那条证明不了 body 没被改写）
  4. 未接管面不在 Go 侧提前 404
  5. 追踪号在边缘只有一个值，入站合法值被沿用（台账 C38）
  6. 通配转发不遮蔽 Go 原生探针面

⚠️ **探针路径必须跟着接管进度走**：本文件最初用 `/api/v1/sessions*` 做转发探针，
而 P1-1 把这两条面搬成 Go 原生之后，它们测的就不再是"经过上游"而是"Go 自己"——
判据静默失效但照样绿。所以这里的探针一律取归属表里仍是 `proxy` 的面（`/api/v1/stats/usage`、
`/metrics`），每接管一条就换掉对应探针。
路径/查询串的原样转发不在本文件证明：全仓 Python 路由不读 query
（`grep -rn 'Query(' backend/api/` 零命中），真栈上观测不到；那半边由
`server/internal/httpapi/upstream_test.go` 的桩上游直接断言 `URL.Path` 与 `URL.RawQuery`。
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from backend.core.logging_config import TRACE_ID_RULE

pytestmark = pytest.mark.chain

TRACE_HEADER = "X-Trace-Id"


def test_proxy_forwards_path_and_query_to_python(http, chain_endpoints, go_token):
    """查询串与路径必须原样到达上游。

    Go 原生列表接口会忽略未知 query，所以这里拿**仍在 Python 的会话详情路径**做探针：
    若反代把前缀裁掉或把 query 丢了，两侧就会一个 200 一个 404/形状不同。
    """
    headers = {"Authorization": f"Bearer {go_token}"}
    path = "/api/v1/sessions"
    go = http.get(chain_endpoints.go(path), params={"page": 1, "size": 50}, headers=headers)
    py = http.get(chain_endpoints.py(path), params={"page": 1, "size": 50}, headers=headers)

    assert go.status_code == py.status_code == 200, (go.status_code, py.status_code)
    assert go.json() == py.json()


def test_proxy_passes_bearer_token_and_returns_identical_body(http, chain_endpoints, go_token):
    """带令牌的请求经 Go 门面与直连 Python 必须拿到逐字相同的响应。

    **为什么不用 `/api/v1/sessions*`**：那两条现在归 Go 原生，拿它们当"代理透传"的探针
    等于测了个没经过上游的用例——正是本文件开头登记的那类错（判据指向不是它要管的东西）。
    改取 `/api/v1/stats/usage`：归属表里它是 `proxy`，且 `backend/api/stats.py:16` 要 admin。
    chain 的种子用户是 `user`，所以两侧都应回 **403 而不是 401**：
    401 意味着 Bearer 根本没送到上游，403 才证明 Python 认出了这个用户并拒绝了他的角色。
    """
    headers = {"Authorization": f"Bearer {go_token}"}
    path = "/api/v1/stats/usage"
    go = http.get(chain_endpoints.go(path), headers=headers)
    py = http.get(chain_endpoints.py(path), headers=headers)

    assert go.status_code == py.status_code == 403, (go.status_code, go.text[:200], py.status_code)
    assert go.json() == py.json(), "透传后的权限判定必须与直连同一份结果"


def test_proxy_keeps_python_error_envelope_for_unauthenticated(http, chain_endpoints):
    """没有凭据时，Go 不许把上游的 401 文案换成自己的一句——前端按 detail 分支。

    同样选仍在 Python 的面：`/api/v1/sessions` 已搬走，拿它比 401 只会比出两份 Go 的实现。
    """
    path = "/api/v1/stats/usage"
    go = http.get(chain_endpoints.go(path))
    py = http.get(chain_endpoints.py(path))

    assert go.status_code == py.status_code == 401, (go.status_code, go.text[:200], py.status_code)
    assert go.json() == py.json(), "未鉴权信封必须逐字一致"


def test_proxy_emits_exactly_one_trace_header_and_reuses_inbound(http, chain_endpoints):
    """追踪号在边缘只出现一次，且入站值被沿用（台账 C38 的修复在这里落到真栈）。

    曾经实测 `curl -D - :8080/metrics` 给出**两行相同的 X-Trace-Id**：
    Trace 中间件先 Set，ReverseProxy 再逐值 Add 上游同名头。修法是丢弃上游回写。
    """
    inbound = "chain-proxy-trace-0001"
    through = http.get(chain_endpoints.go("/metrics"), headers={TRACE_HEADER: inbound})
    assert through.status_code == 200, through.status_code
    values = through.headers.get_list(TRACE_HEADER)
    assert values == [inbound], f"入站追踪号应被沿用且只有一个值，实得 {values}"

    generated = http.get(chain_endpoints.go("/metrics"))
    generated_values = generated.headers.get_list(TRACE_HEADER)
    assert len(generated_values) == 1, f"缺入站值时应由 Go 生成一个，实得 {generated_values}"
    assert generated_values[0], "生成的追踪号不能是空串"


def test_proxy_rejects_illegal_trace_inbound_on_both_edges(http, chain_endpoints):
    """非法追踪号必须被换掉且**不回显**（契约 `components.parameters.TraceId`，设计审查 §8）。

    两侧都要测：Go 是浏览器侧的唯一边缘，而 Python 仍可被内部调用方直连——
    只在 Go 侧清洗的话，直连那半边还是"什么值都收"。
    生成形态两侧不同（Go 16 hex、Python 32 hex）是 §6 批准的口径，所以断言的是
    "符合契约接受集合且不等于入站值"，不是"两侧值相同"。

    ⚠️ 这里**不测非 ASCII 值**：HTTP 头值只能按 latin-1 编码，中文入站会让 httpx 客户端
    在发出前就抛错，测到的是客户端而不是服务端。那条形状由
    `tests/unit/test_trace_header.py` 与 `server/internal/observability/trace_test.go` 覆盖。
    """
    edges = (("go", chain_endpoints.go), ("py", chain_endpoints.py))
    for label, inbound in (("含空格", "bad trace id"), ("超长", "a" * 129), ("复合值", "a,b"), ("含冒号", "a:b"), ("含引号", "'q'")):
        for name, url in edges:
            resp = http.get(url("/metrics"), headers={TRACE_HEADER: inbound})
            assert resp.status_code == 200, (label, name, resp.status_code)
            values = resp.headers.get_list(TRACE_HEADER)
            assert len(values) == 1, f"{label}/{name}：响应头必须单值，实得 {values}"
            assert values[0] != inbound, f"{label}/{name}：非法值被回显了"
            assert re.fullmatch(TRACE_ID_RULE, values[0]), f"{label}/{name}：{values[0]!r} 不符合契约形状"

    # 128 是边界内，必须原样沿用——只测"超长被拒"不测"边界值被收"，规则写错一位也发现不了。
    boundary = "a" * 128
    for name, url in edges:
        resp = http.get(url("/metrics"), headers={TRACE_HEADER: boundary})
        assert resp.headers.get_list(TRACE_HEADER) == [boundary], f"{name}：128 个字符的合法值应被沿用"


def test_proxy_does_not_shadow_native_probe_routes(http, chain_endpoints):
    """已搬到 Go 的面不能被通配转发盖住：Go 的 `/api/v1/health` 有 PG+Redis 两个探测键，
    而 Python 那侧连 `/api/v1` 前缀都没有（契约的 healthRootAlias 才是它的根路径）。
    """
    go = http.get(chain_endpoints.go("/api/v1/health"))
    assert go.status_code == 200, go.text[:200]
    assert go.json().get("status") == "ok", go.json()

    py = http.get(chain_endpoints.py("/api/v1/health"))
    assert py.status_code == 404, f"这条前缀只有 Go 满足，Python 应 404（台账 C31），实得 {py.status_code}"


def test_proxy_returns_python_response_body_verbatim_for_admin_surface(
    http, chain_endpoints, go_token, py_token, chain_pg, chain_seed
):
    """未接管面的响应体必须原样透传：Go 不许改写、重排或重新序列化上游的 JSON。

    为什么这条不能拿 `/api/v1/stats/usage` 比字节：**它自己就是请求计数面**——
    这一次探测本身会把 `count` 加一、把 `last_accessed` 推后，两侧必然不同。
    上一轮我就是这么写的，红出来的差异全是测试自己造成的，一点信息量都没有。
    所以这里分两步：usage 面比**结构**（键集与条目集合），字节级对拍交给
    `/api/v1/documents/upload/jobs`（两侧打到同一个 Python 进程，任务表不因读而变）。

    提权用 `UPDATE users SET role`（同 test_go_auth_cross_validation 的做法），
    `finally` 恢复原值；会话面按 `user_id` 过滤，角色变了不影响其它用例。
    """
    headers = {"go": {"Authorization": f"Bearer {go_token}"}, "py": {"Authorization": f"Bearer {py_token}"}}

    def set_role(value: str) -> None:
        with chain_pg.begin() as conn:
            conn.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": value, "i": chain_seed["user_id"]})

    set_role("admin")
    try:
        jobs_go = http.get(chain_endpoints.go("/api/v1/documents/upload/jobs"), headers=headers["go"])
        jobs_py = http.get(chain_endpoints.py("/api/v1/documents/upload/jobs"), headers=headers["py"])
        assert jobs_go.status_code == jobs_py.status_code == 200, (jobs_go.text[:200], jobs_py.text[:200])
        assert jobs_go.content == jobs_py.content, (
            f"透传响应体被改写了：\n go ={jobs_go.content[:400]!r}\n py ={jobs_py.content[:400]!r}"
        )

        usage_go = http.get(chain_endpoints.go("/api/v1/stats/usage"), headers=headers["go"])
        usage_py = http.get(chain_endpoints.py("/api/v1/stats/usage"), headers=headers["py"])
        assert usage_go.status_code == usage_py.status_code == 200, usage_go.text[:200]
        # get_stats() 返回的是**按路径的记录数组**（`[{path, count, last_accessed}, ...]`），不是对象，
        # 所以这里比"条目集合 + 每条的键集"，不比 count/last_accessed——那两个字段正是这次探测自己改的。
        records_go, records_py = usage_go.json(), usage_py.json()
        assert isinstance(records_go, list) and isinstance(records_py, list), (type(records_go), type(records_py))
        assert {item["path"] for item in records_go} == {item["path"] for item in records_py}, (
            "转发面报出的路径条目集合与直连不同"
        )
        assert {tuple(sorted(item)) for item in records_go} == {tuple(sorted(item)) for item in records_py}, (
            "每条记录的键集两侧不同"
        )
    finally:
        set_role("user")


def test_proxy_forwards_unhandled_business_surface_that_python_still_serves(http, chain_endpoints):
    """反代前缀覆盖但未接管的业务面必须真的落到 Python，而不是在 Go 侧 404。

    取 `/api/v1/stats/usage`：归属表里它是 `proxy`、前端不调但仍可达。
    Go 若把它当成"没人认领"而 404，12 条待迁移面就会在 P1 期间静默失联。
    """
    resp = http.get(chain_endpoints.go("/api/v1/stats/usage"))
    py = http.get(chain_endpoints.py("/api/v1/stats/usage"))
    assert resp.status_code == py.status_code, (resp.status_code, py.status_code)
    assert resp.status_code != 404 or py.status_code == 404, "Go 不该比 Python 更早给出 404"
    assert resp.headers.get_list(TRACE_HEADER), "转发路径也要带追踪号"
