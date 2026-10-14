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
from jose import jwt
from sqlalchemy import text

pytestmark = pytest.mark.chain


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
        "chain-layer-wrong-secret",
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
