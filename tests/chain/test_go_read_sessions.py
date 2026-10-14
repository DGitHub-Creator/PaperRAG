"""P1-1 的 chain 判据：Go 原生接管 `/sessions` 的读与删（`-k go_read`）。

这一层要证的不是"Go 能返回 200"，而是**接管之后前端不用改一行解析**：
同一份真库数据、同一个令牌，Go 与 Python 给出**逐字相同**的 JSON。
形状里最容易漂的两处都专门盯了：naive TIMESTAMP 的 `isoformat()` 渲染，
以及"没有会话时是 `[]` 还是 `null`"。

删除那条只断言 Go 与 PG 一致，不断言"Python 也立刻看不到了"——
Python 那侧还有一层 Redis 缓存，而 Go 的写不会去失效它（记在台账 C35）。
在这里断言那一半会把一个已知缺口变成偶发红。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.chain

LIST_PATH = "/api/v1/sessions"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_session(chain_pg, user_id: int, session_id: str) -> int:
    """给当前用户加一条测试专用会话，返回 chat_sessions.id。

    删除类用例**各自建自己的行**而不是动共享种子：种子是 session 级 fixture，
    谁先删了谁就把后面的用例踩红，那种红看起来像产品缺陷。
    """
    with chain_pg.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
                " VALUES (:u, :s, '{}'::json, now(), now()) RETURNING id"
            ),
            {"u": user_id, "s": session_id},
        ).scalar_one()


def _make_message(chain_pg, session_ref_id: int, content: str) -> int:
    with chain_pg.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO chat_messages (session_ref_id, message_type, content, timestamp)"
                " VALUES (:s, 'human', :c, now()) RETURNING id"
            ),
            {"s": session_ref_id, "c": content},
        ).scalar_one()


def test_go_read_session_list_matches_python_byte_for_byte(http, chain_endpoints, go_token, chain_seed):
    """接管的第一判据：列表两侧逐字相等（键、顺序、时间格式、消息计数）。"""
    go = http.get(chain_endpoints.go(LIST_PATH), headers=_bearer(go_token))
    py = http.get(chain_endpoints.py(LIST_PATH), headers=_bearer(go_token))
    assert go.status_code == py.status_code == 200, f"go={go.status_code} py={py.status_code}"
    assert go.json() == py.json(), f"\n go={go.json()}\n py={py.json()}"

    sessions = go.json()["sessions"]
    # 只对本用例种的那两条做逐字断言：删除类用例会各自建行，全量比对会把它们也算进来
    mine = [s for s in sessions if s["session_id"].startswith("chain-sess-")]
    assert [s["session_id"] for s in mine] == ["chain-sess-newer", "chain-sess-older"], "顺序必须是 updated_at 倒序"
    assert mine[0]["updated_at"] == "2026-10-14T07:08:10.123456", "带微秒的要给 6 位"
    assert mine[1]["updated_at"] == "2026-10-14T07:08:09", "微秒为 0 的要整段省略，且不带时区后缀"
    assert mine[0]["message_count"] == 2 and mine[1]["message_count"] == 1
    assert all(set(s) == {"session_id", "updated_at", "message_count"} for s in mine)


def test_go_read_session_list_is_empty_array_for_a_user_with_no_sessions(http, chain_endpoints, chain_pg):
    """没有会话的用户必须回 `[]`。Go 里 `nil` 切片会序列化成 `null`，前端 `.map()` 直接炸。"""
    from backend.core.auth import get_password_hash

    username = "no_sessions_probe"
    with chain_pg.begin() as conn:
        user_id = conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, 'user') RETURNING id"),
            {"u": username, "h": get_password_hash("Empty2026case")},
        ).scalar_one()
    try:
        token = http.post(
            chain_endpoints.go("/api/v1/auth/login"),
            json={"username": username, "password": "Empty2026case"},
        ).json()["access_token"]
        body = http.get(chain_endpoints.go(LIST_PATH), headers=_bearer(token)).json()
        assert body == {"sessions": []}, f"空结果必须恰好是 {{\"sessions\": []}}，实得 {body}"
    finally:
        with chain_pg.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})


def test_go_read_session_is_scoped_to_the_owner(http, chain_endpoints, go_token, py_token, chain_seed, chain_pg):
    """另一个用户读不到 alice 的会话——两侧都必须按 user_id 过滤，不是按 session_id 全局查。"""
    from backend.core.auth import get_password_hash

    other = "other_owner_probe"
    with chain_pg.begin() as conn:
        other_id = conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, 'user') RETURNING id"),
            {"u": other, "h": get_password_hash("Others2026case")},
        ).scalar_one()
    try:
        other_token = http.post(
            chain_endpoints.go("/api/v1/auth/login"),
            json={"username": other, "password": "Others2026case"},
        ).json()["access_token"]
        assert http.get(chain_endpoints.go(LIST_PATH), headers=_bearer(other_token)).json() == {"sessions": []}

        # 别人的会话删不掉，且与"不存在"是同一句 404——不给归属探测留缝
        mine = chain_seed["newer"]["session_id"]
        go_del = http.delete(f"{chain_endpoints.go(LIST_PATH)}/{mine}", headers=_bearer(other_token))
        assert go_del.status_code == 404, go_del.text
        assert go_del.json()["detail"] == "Session does not exist"
        with chain_pg.begin() as conn:
            still = conn.execute(
                text("SELECT COUNT(*) FROM chat_sessions WHERE user_id = :u"),
                {"u": chain_seed["user_id"]},
            ).scalar_one()
        assert still == 2, "越权删除不得真的删掉行"

        # 正向对照：同一个会话号，主人自己删得掉（放在这里是为了证明上面那个 404 不是"谁都删不掉"）
        own = _make_session(chain_pg, chain_seed["user_id"], "chain-sess-owned-by-alice")
        resp = http.delete(f"{chain_endpoints.go(LIST_PATH)}/chain-sess-owned-by-alice", headers=_bearer(py_token))
        assert resp.status_code == 200, resp.text
        with chain_pg.begin() as conn:
            left = conn.execute(
                text("SELECT COUNT(*) FROM chat_sessions WHERE id = :i"), {"i": own}
            ).scalar_one()
        assert left == 0
    finally:
        with chain_pg.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": other_id})


def test_go_read_unknown_session_delete_matches_python_text(http, chain_endpoints, go_token):
    """删一个不存在的会话：两侧都是 404，且 detail 逐字相同。"""
    go = http.delete(f"{chain_endpoints.go(LIST_PATH)}/does-not-exist", headers=_bearer(go_token))
    py = http.delete(f"{chain_endpoints.py(LIST_PATH)}/does-not-exist", headers=_bearer(go_token))
    assert go.status_code == py.status_code == 404
    assert go.json()["detail"] == py.json()["detail"] == "Session does not exist"


def test_go_read_delete_cascade_removes_messages_from_pg(http, chain_endpoints, go_token, chain_seed, chain_pg):
    """Go 发起的删除要带走消息行——靠的是基线里那条 ON DELETE CASCADE，不是 Go 多写一条 DELETE。"""
    session_id = "chain-sess-cascade"
    ref_id = _make_session(chain_pg, chain_seed["user_id"], session_id)
    _make_message(chain_pg, ref_id, "about to be cascade-removed")

    resp = http.delete(f"{chain_endpoints.go(LIST_PATH)}/{session_id}", headers=_bearer(go_token))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"session_id": session_id, "message": "Session deleted"}

    with chain_pg.begin() as conn:
        sessions_left = conn.execute(
            text("SELECT COUNT(*) FROM chat_sessions WHERE id = :i"), {"i": ref_id}
        ).scalar_one()
        # 按 id 数孤儿行：只数这一条会话的消息，别把库里其它历史孤儿行算成本用例的失败
        messages_left = conn.execute(
            text("SELECT COUNT(*) FROM chat_messages WHERE session_ref_id = :i"), {"i": ref_id}
        ).scalar_one()
    assert sessions_left == 0
    assert messages_left == 0, "消息还在说明级联没生效，Go 得自己补一条 DELETE"

    # 再删一次必须是 404，而不是把"已经没了"算成成功
    assert http.delete(f"{chain_endpoints.go(LIST_PATH)}/{session_id}", headers=_bearer(go_token)).status_code == 404
