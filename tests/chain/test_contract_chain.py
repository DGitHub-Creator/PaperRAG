"""跨语言契约对拍骨架（`09` P0-5 的判据选择器 `-k contract`）。

与 mock 级 `check_contracts.py` 的分工要说清：那份脚本比的是"**前端实调集合 ↔ 契约文件**"，
它不看服务侧（所以 C31 那类"契约有、服务没有"的偏差它抓不到）。这里补的是另一半：
**两个真实服务对同一份契约的答复是否一致**。两者都绿才叫"契约被实现"，只绿一个都算数。

对拍一律逐字比 `detail` 文案，不比"大致意思"——P0-6 那张八行实测表就是为这个存在的，
而文案漂移在监控与前端错误提示上都是静默的。
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.chain

LOGIN_BODY = {"username": "unused", "password": "unused"}


def _login(http, url: str, seed: dict) -> dict:
    resp = http.post(url, json={"username": seed["username"], "password": seed["password"]})
    assert resp.status_code == 200, f"{url} → {resp.status_code}: {resp.text[:200]}"
    return resp.json()


def test_login_response_shape_matches(http, chain_endpoints, chain_seed):
    """同一份凭据，两侧返回的字段集合与固定值必须一致（令牌本身必然不同，不比）。"""
    go = _login(http, chain_endpoints.go("/api/v1/auth/login"), chain_seed)
    py = _login(http, chain_endpoints.py("/api/v1/auth/login"), chain_seed)

    assert set(go) == set(py), f"字段集合漂移：go={sorted(go)} py={sorted(py)}"
    assert go["token_type"] == py["token_type"] == "bearer"
    assert go["username"] == py["username"] == chain_seed["username"]
    assert go["role"] == py["role"] == "user"
    # 两边都必须是结构完整的三段式 JWT，且解得出的 claims 一致
    for field in ("access_token", "refresh_token"):
        assert go[field].count(".") == 2
        assert py[field].count(".") == 2


def test_me_returns_identical_json(http, chain_endpoints, go_token):
    """同一张 Go 令牌打到两侧：/auth/me 的 JSON 必须**逐字**相同。

    这条是"Go 接管后前端不用改一行解析"的最直接证据。
    """
    headers = {"Authorization": f"Bearer {go_token}"}
    go = http.get(chain_endpoints.go("/api/v1/auth/me"), headers=headers)
    py = http.get(chain_endpoints.py("/api/v1/auth/me"), headers=headers)
    assert go.status_code == py.status_code == 200
    assert go.json() == py.json(), f"go={go.json()} py={py.json()}"


def test_wrong_password_detail_is_identical(http, chain_endpoints, chain_seed):
    body = {"username": chain_seed["username"], "password": "Wrongpass123"}
    go = http.post(chain_endpoints.go("/api/v1/auth/login"), json=body)
    py = http.post(chain_endpoints.py("/api/v1/auth/login"), json=body)
    assert go.status_code == py.status_code == 401
    assert go.json()["detail"] == py.json()["detail"], "同为 401 但文案不一致"


def test_missing_header_detail_is_identical(http, chain_endpoints):
    """没有 Authorization 头时两侧都是 `Not authenticated`。

    这句是 `OAuth2PasswordBearer` 的现状而非 `HTTPBearer` 的
    `Invalid authentication credentials`——读源码容易记错，所以在这里现跑钉住（台账里那条
    「凡是要 Go 复刻的 detail 都从生产侧现取」的规矩在真链路上同样成立）。
    """
    go = http.get(chain_endpoints.go("/api/v1/auth/me"))
    py = http.get(chain_endpoints.py("/api/v1/auth/me"))
    assert go.status_code == py.status_code == 401
    assert go.json()["detail"] == py.json()["detail"] == "Not authenticated"


def _checks_of(resp: httpx.Response) -> dict:
    """从 200 的平铺体或 503 的 `{"detail": {...}}` 信封里取出 checks。

    两侧失败时的形状不同是**契约现状**（Python 走 HTTPException 所以整个体被包进 detail，
    Go 的 WriteError 也一样），这里把它们抹平是为了比探测语义，不是为了比信封。
    """
    body = resp.json()
    if "checks" not in body and isinstance(body.get("detail"), dict):
        body = body["detail"]
    return body.get("checks") or {}


def test_probe_endpoints_agree_on_shared_keys(http, chain_endpoints):
    """存活/就绪探针：两侧**共有的**那部分必须给同一个答案。

    两点刻意的宽松，都不是放水：
    ①只比共有的探测键——Go 的 `checks` 目前只有 `database`，Python 有 database/redis/milvus，
      把"Go 还没探 redis/milvus"判成缺陷会掩盖真正要判的那条（键名与取值语义才是事故源）。
      这条缺口已记进 `progress.json` 的 X1 红点与台账 C33 同一类问题。
    ②不要求 /ready 是 200——Python 探 milvus，而 dev 形态下 Milvus 常不起（起来也会因
      etcd 磁盘停顿半路挂，台账 C28）。**探针的状态由环境决定，判据只能断言"两侧说法一致"**。
      反过来 `/health` 不碰任何依赖，所以那条严格断言 200 与 status=="ok"。
    """
    go = http.get(chain_endpoints.go("/api/v1/health"))
    py = http.get(chain_endpoints.py("/health"))
    assert go.status_code == py.status_code == 200
    assert {"status", "version"} <= set(go.json()) and {"status", "version"} <= set(py.json())
    assert go.json()["status"] == py.json()["status"] == "ok"

    go_ready = http.get(chain_endpoints.go("/api/v1/ready"))
    py_ready = http.get(chain_endpoints.py("/ready"))
    assert go_ready.status_code in (200, 503), go_ready.text
    assert py_ready.status_code in (200, 503), py_ready.text

    go_checks, py_checks = _checks_of(go_ready), _checks_of(py_ready)
    shared = set(go_checks) & set(py_checks)
    assert shared, f"两侧没有任何共有的探测键，探针语义已经分叉：go={sorted(go_checks)} py={sorted(py_checks)}"
    for name in sorted(shared):
        assert go_checks[name]["status"] == py_checks[name]["status"], (
            f"探测键 {name} 两侧说法不一致：go={go_checks[name]} py={py_checks[name]}"
        )


def test_go_readiness_reports_database_ok_when_pg_is_up(http, chain_endpoints):
    """Go 的 /ready 必须真的探到 PG——这一条不给"永远 200"的假探针留空间。"""
    ready = http.get(chain_endpoints.go("/api/v1/ready"))
    checks = _checks_of(ready)
    assert "database" in checks, f"Go 的 /ready 没有 database 探测键：{sorted(checks)}"
    assert checks["database"]["status"] == "ok", checks["database"]
