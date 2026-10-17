"""X4 的 chain 半侧：Go ↔ Python **双向**互验令牌，跑在真 PG 上（`09` X4，real 级）。

判据选择器是 `-k go_auth`（与 `progress.json` 里 X4 那条命令逐字一致），模块名因此带 go_auth。

这一层补的是 mock 级永远补不到的那一问：golden vectors 证明的是"两侧对同一批令牌的**判定结论**
一致"，而这里证明的是"一侧**现在真的签出一张另一侧现在真的收下的令牌**"——同一个密钥、同一个库、
两个进程。缺的那一向原本是「Go 签发 → Python 校验」，因为 Python 侧此前没有对照物可打。

第三用例（伪造 secret 两侧都拒）不是顺手加的：不验它，前两条有可能因为"两侧都把 Authorization
头当成唯一凭据"而双双通过——那正是 X4 想防的那种假绿。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import jwt
from sqlalchemy import text

pytestmark = pytest.mark.chain


@pytest.mark.parametrize("side", ["go", "py"])
def test_rate_limit_login_twenty_first_request_and_spoofed_proxy(http, chain_endpoints, chain_seed, chain_rate_scope, side):
    url = getattr(chain_endpoints, side)("/api/v1/auth/login")
    payload = {"username": chain_seed["username"], "password": chain_seed["password"]}
    for number in range(20):
        response = http.post(url, json=payload, headers={"X-Forwarded-For": f"198.51.100.{number + 1}"})
        assert response.status_code == 200, response.text
        assert int(float(response.headers["X-RateLimit-Limit"])) == 20
    blocked = http.post(url, json=payload, headers={"X-Forwarded-For": "203.0.113.77"})
    assert blocked.status_code == 429, f"限流未生效: status={blocked.status_code}"
    assert set(blocked.json()) == {"detail"}
    assert int(float(blocked.headers["X-RateLimit-Limit"])) == 20


@pytest.mark.parametrize("fields,expected", [({}, 200), ({"role": None}, 200), ({"role": "root"}, 200), ({"role": ""}, 200), ({"role": "admin"}, 403)])
def test_register_parity_for_optional_and_unknown_roles(http, chain_endpoints, chain_pg, chain_rate_scope, fields, expected):
    from uuid import uuid4

    names = ["qr_" + uuid4().hex[:12] for _ in range(2)]
    responses = []
    try:
        for endpoint, username in zip((chain_endpoints.go, chain_endpoints.py), names, strict=True):
            response = http.post(endpoint("/api/v1/auth/register"), json={"username": username, "password": "Quality2026case", **fields})
            assert response.status_code == expected, f"注册行为不一致: status={response.status_code} expected={expected}"
            responses.append(response.json())
        if expected == 200:
            assert set(responses[0]) == set(responses[1])
            assert responses[0]["role"] == responses[1]["role"] == "user"
            with chain_pg.connect() as connection:
                roles = connection.execute(text("SELECT role FROM users WHERE username IN (:a, :b)"), {"a": names[0], "b": names[1]}).scalars().all()
                assert roles == ["user", "user"]
        else:
            assert responses[0] == responses[1]
    finally:
        with chain_pg.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE username IN (:a, :b)"), {"a": names[0], "b": names[1]})


def test_go_minted_token_is_accepted_by_python(http, chain_endpoints, go_token, chain_seed):
    """Go 签发的令牌打到 Python 的受保护路由：这一向在 mock 级没有判据，只有真进程能给。"""
    resp = http.get(chain_endpoints.py("/api/v1/auth/me"), headers={"Authorization": f"Bearer {go_token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == chain_seed["username"]


def test_python_minted_token_is_accepted_by_go_auth(http, chain_endpoints, py_token, chain_seed):
    resp = http.get(chain_endpoints.go("/api/v1/auth/me"), headers={"Authorization": f"Bearer {py_token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == chain_seed["username"]


def test_forged_signature_rejected_by_both(http, chain_endpoints, chain_seed):
    """同一个 claims、换成错密钥签名 → 两侧都必须 401。

    claims 里带上未来的 exp：Go 侧强制要求 exp（这是记在 `contracts/jwt_golden.json`
    `divergences` 里的**已知分歧**），不带 exp 会因为它被拒，那就测不到签名这一层了。
    """
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {
            "sub": chain_seed["username"],
            "username": chain_seed["username"],
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        "chain-layer-wrong-secret-only-for-tests",
        algorithm="HS256",
    )
    headers = {"Authorization": f"Bearer {forged}"}
    assert http.get(chain_endpoints.go("/api/v1/auth/me"), headers=headers).status_code == 401
    assert http.get(chain_endpoints.py("/api/v1/auth/me"), headers=headers).status_code == 401


def test_role_is_resolved_from_db_not_from_claims(http, chain_endpoints, go_token, chain_pg, chain_seed):
    """令牌里的 role 不可信：改库里的 role 之后，两侧读出的必须都是新值。

    这是 P0-6 那个决定（`ParseAccessToken` **连 role 都不返回**）在真链路面上的验收——
    谁哪天改成从令牌读 role，这条就会红。测完恢复原值。
    """
    headers = {"Authorization": f"Bearer {go_token}"}
    def set_role(value: str) -> None:
        with chain_pg.begin() as conn:
            conn.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": value, "i": chain_seed["user_id"]})

    set_role("admin")
    try:
        assert http.get(chain_endpoints.go("/api/v1/auth/me"), headers=headers).json()["role"] == "admin"
        assert http.get(chain_endpoints.py("/api/v1/auth/me"), headers=headers).json()["role"] == "admin"
    finally:
        set_role("user")


@pytest.mark.parametrize("fields,expected", [
    ({"password": "a１２３４５６７８"}, 200),
    ({"password": "short"}, 400),
    ({"password": "abcdefghijk"}, 400),
    ({"username": "  "}, 400),
    ({"password": None}, 400),
    ({"role": 12}, 400),
    ({"admin_code": []}, 400),
])
def test_register_validation_parity(http, chain_endpoints, chain_pg, chain_rate_scope, fields, expected):
    from uuid import uuid4

    names = ["qv_" + uuid4().hex[:12] for _ in range(2)]
    responses = []
    try:
        for endpoint, name in zip((chain_endpoints.go, chain_endpoints.py), names, strict=True):
            response = http.post(endpoint("/api/v1/auth/register"), json={"username": name, "password": "Quality2026case", **fields})
            assert response.status_code == expected, response.text
            responses.append(response.json())
        if expected != 200:
            assert responses[0] == responses[1]
    finally:
        with chain_pg.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE username IN (:a, :b)"), {"a": names[0], "b": names[1]})


@pytest.mark.parametrize("valid", [False, True])
def test_register_admin_invite_and_duplicate_parity(http, chain_endpoints, chain_pg, chain_rate_scope, valid):
    import os
    from uuid import uuid4

    invite = os.getenv("CHAIN_ADMIN_INVITE_CODE")
    if not invite:
        pytest.skip("需要隔离验证器注入本轮管理员邀请码")
    names = ["qa_" + uuid4().hex[:12] for _ in range(2)]
    try:
        responses = []
        for endpoint, name in zip((chain_endpoints.go, chain_endpoints.py), names, strict=True):
            body = {"username": name, "password": "Quality2026case", "role": "admin", "admin_code": invite if valid else "wrong-invite"}
            response = http.post(endpoint("/api/v1/auth/register"), json=body)
            assert response.status_code == (200 if valid else 403), response.text
            responses.append(response.json())
            if valid:
                assert response.json()["role"] == "admin"
                duplicate = http.post(endpoint("/api/v1/auth/register"), json={**body, "admin_code": "wrong-invite"})
                assert duplicate.status_code == 409
                assert duplicate.json() == {"detail": "Username already exists"}
        if not valid:
            assert responses[0] == responses[1]
    finally:
        with chain_pg.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE username IN (:a, :b)"), {"a": names[0], "b": names[1]})
