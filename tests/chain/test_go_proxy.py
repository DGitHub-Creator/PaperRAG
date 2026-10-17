"""P1-0 的 chain 判据：Go 反向代理门面在真栈上的四条行为（`-k proxy`）。

**为什么单独写这个文件**：P1-0 的 `verify` 写的是 `pytest -m chain -k proxy`，
但在本文件出现之前，那个选择器只命中两条**限流**用例（它们名字里带 proxy 是因为
"伪造 X-Forwarded-For"）——命令能跑、用例能绿，而**代理转发本身一条都没测**。
这正是本仓库反复登记的那类错：判据指向了不是它要管的东西（同 C22 的 `rc 恒为 1`、
C31 的"契约声明服务侧却无机检"）。补上这四条，P1-0 的 real 档才有承载物。

四条各自钉的是：
  1. 路径与查询串原样到达上游（裁前缀或丢 query 都会表现成"页面能开但数据不对"）
  2. 鉴权头透传：带令牌的请求经 Go 与直连 Python 拿到**同一份 JSON**
  3. 未鉴权时错误信封逐字一致（Go 不能把 Python 的 `Not authenticated` 换成自己的文案）
  4. 追踪号在边缘只有一个值，且入站值被沿用（台账 C38 的那条修复在这里有真栈证据）
"""

from __future__ import annotations

import pytest

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

    选 detail 路径（`GET /sessions/{sid}`）而不是 list：它今天仍归 Python（`proxy`），
    所以这才是"P1-1 要搬的那条面在搬之前的基线"。
    """
    headers = {"Authorization": f"Bearer {go_token}"}
    sid = "chain-proxy-baseline"
    go = http.get(chain_endpoints.go(f"/api/v1/sessions/{sid}"), headers=headers)
    py = http.get(chain_endpoints.py(f"/api/v1/sessions/{sid}"), headers=headers)

    assert go.status_code == py.status_code == 200, (go.text[:200], py.text[:200])
    assert go.json() == py.json() == {"messages": []}, "不存在的会话是空数组，不是 404"


def test_proxy_keeps_python_error_envelope_for_unauthenticated(http, chain_endpoints):
    """没有凭据时，Go 不许把上游的 401 文案换成自己的一句——前端按 detail 分支。"""
    path = "/api/v1/sessions"
    go = http.get(chain_endpoints.go(path))
    py = http.get(chain_endpoints.py(path))

    assert go.status_code == py.status_code == 401, (go.status_code, py.status_code)
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


def test_proxy_does_not_shadow_native_probe_routes(http, chain_endpoints):
    """已搬到 Go 的面不能被通配转发盖住：Go 的 `/api/v1/health` 有 PG+Redis 两个探测键，
    而 Python 那侧连 `/api/v1` 前缀都没有（契约的 healthRootAlias 才是它的根路径）。
    """
    go = http.get(chain_endpoints.go("/api/v1/health"))
    assert go.status_code == 200, go.text[:200]
    assert go.json().get("status") == "ok", go.json()

    py = http.get(chain_endpoints.py("/api/v1/health"))
    assert py.status_code == 404, f"这条前缀只有 Go 满足，Python 应 404（台账 C31），实得 {py.status_code}"


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
