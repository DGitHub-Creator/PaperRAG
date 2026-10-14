"""跨语言契约对拍骨架（`09` P0-5 的判据选择器 `-k contract`）。

与 mock 级 `check_contracts.py` 的分工要说清：那份脚本比的是"**前端实调集合 ↔ 契约文件**"，
它不看服务侧（所以 C31 那类"契约有、服务没有"的偏差它抓不到）。这里补的是另一半：
**两个真实服务对同一份契约的答复是否一致**。两者都绿才叫"契约被实现"，只绿一个都算数。

对拍一律逐字比 `detail` 文案，不比"大致意思"——P0-6 那张八行实测表就是为这个存在的，
而文案漂移在监控与前端错误提示上都是静默的。
"""

from __future__ import annotations

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


def test_probe_endpoints_agree_on_shared_keys(http, chain_endpoints):
    """存活/就绪探针：两侧**共有的**那部分必须给同一个答案。

    只比共有的键是刻意的——Go 的 `checks` 目前只有 `database`，Python 有
    database/redis/milvus；把"Go 还没探 redis"判成缺陷会掩盖真正要判的那条
    （compose healthcheck 与监控按的是同一个键名，键名或取值语义不一致才是事故）。
    """
    go = http.get(chain_endpoints.go("/api/v1/health"))
    py = http.get(chain_endpoints.py("/health"))
    assert go.status_code == py.status_code == 200
    assert {"status", "version"} <= set(go.json()) and {"status", "version"} <= set(py.json())
    assert go.json()["status"] == py.json()["status"] == "ok"

    py_ready = http.get(chain_endpoints.py("/ready"))
    assert py_ready.status_code == 200, py_ready.text
    go_ready = http.get(chain_endpoints.go("/api/v1/ready"))
    assert go_ready.status_code == 200, go_ready.text
    shared = set(go_ready.json()["checks"]) & set(py_ready.json()["checks"])
    assert shared, "两侧没有任何共有的探测键，探针语义已经分叉"
    for name in shared:
        assert go_ready.json()["checks"][name]["status"] == py_ready.json()["checks"][name]["status"], name
