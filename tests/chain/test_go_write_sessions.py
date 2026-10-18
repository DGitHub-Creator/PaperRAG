"""P1-2 的 chain 判据：Go 写面在真栈上的行为（`-k go_write`）。

**为什么单独写这个文件**：P1-2 的 `verify` 写的是 `uv run pytest -m chain -k go_write`，
而在本文件出现之前那个选择器**收集 0 项**。零收集不算绿（08 §判据纪律），
所以这张卡的"已验收"从来没有承载物——和 C31（契约声明服务侧却无机检）、
C22（`rc` 恒为 1）是同一类错：命令能跑、报告好看、被测的东西没被测。

写面已有的跨语言证据在别处，这里**不重复**：注册形状/邀请码/重复用户见
`test_go_auth_cross_validation.py`，删除后消息级联消失见 `test_go_read_sessions.py`。
本文件补的是那两处覆盖不到的四件事：

  1. **成功删除的响应体逐字对拍**。既有那条只比了"未知会话"的 404 文案，
     200 那一支 `{session_id, message}` 从没比过，而前端 `deleteSession` 用的正是它。
  2. **跨边缘可见性**：Go 删掉行之后，尚未退出的 Python 读路径必须立刻读空——
     接管期间两侧不许各有各的真相（C35 移除会话缓存之后这条才成立）。
  3. **并发删除只有一个赢家**：Go 的 DELETE 靠 `WHERE user_id AND session_id` 的
     受影响行数判成败，并发请求必须恰好一次 200、其余同一份 404 信封，且不得出现 500。
     这是 P1-1 卡片里那句"并发验收仍按 P1-1 执行"的实际承载物。
  4. **并发注册撞 `users.username` 唯一约束**：写面的唯一性由数据库约束保证，
     不是靠"先查再插"的应用层检查——后者在并发下会双双成功或双双 500。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.chain

SESSIONS = "/api/v1/sessions"
REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"

# 会话行的时间列是 TIMESTAMP（无时区）：夹具一律给显式 naive 值，与 conftest 同口径。
_TS = datetime(2026, 10, 18, 3, 4, 5, 654321)

# 注册用例用的口令满足 register 的规则：≥8 个码点，小写/大写/数字至少两类。
WRITE_PASSWORD = "GoWrite2026seed"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _insert_session(chain_pg, user_id: int, session_id: str, messages: tuple[str, ...] = ()) -> int:
    """直接写 PG 铺数据：不用被测面去铺被测面的数据（第十三轮定的做法）。"""
    with chain_pg.begin() as conn:
        ref_id = conn.execute(
            text(
                "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
                " VALUES (:u, :s, '{}'::json, :ts, :ts) RETURNING id"
            ),
            {"u": user_id, "s": session_id, "ts": _TS},
        ).scalar_one()
        for content in messages:
            conn.execute(
                text(
                    "INSERT INTO chat_messages (session_ref_id, message_type, content, timestamp, rag_trace)"
                    " VALUES (:s, 'ai', :c, :ts, NULL)"
                ),
                {"s": ref_id, "c": content, "ts": _TS},
            )
    return ref_id


def _session_row_count(chain_pg, session_ref_id: int) -> int:
    with chain_pg.begin() as conn:
        return conn.execute(
            text("SELECT count(*) FROM chat_sessions WHERE id = :i"), {"i": session_ref_id}
        ).scalar_one()


def _user_row_count(chain_pg, username: str) -> int:
    with chain_pg.begin() as conn:
        return conn.execute(
            text("SELECT count(*) FROM users WHERE username = :u"), {"u": username}
        ).scalar_one()


@pytest.fixture()
def writable_session(chain_pg, chain_seed):
    """一条带两行消息的专属会话；夹具自己建、自己删。"""
    session_id = f"chain-write-{uuid4().hex[:12]}"
    ref_id = _insert_session(chain_pg, chain_seed["user_id"], session_id, ("第一问", "第一答"))
    yield {"session_id": session_id, "ref_id": ref_id}
    with chain_pg.begin() as conn:
        conn.execute(text("DELETE FROM chat_sessions WHERE id = :i"), {"i": ref_id})


@pytest.fixture()
def twin_foreign_session(chain_pg, chain_seed, writable_session):
    """另一个用户名下的两条会话：一条与请求者**同号**，一条只有他有。

    为什么要同号那条：`chat_sessions` 的唯一约束是 `(user_id, session_id)`（000001 基线），
    所以同一个 session_id 天然可以分属两个人。删除过滤器一旦漏掉 `user_id`，
    被删掉的就是别人的会话——那是数据销毁，比读泄漏更严重，必须用同号才测得出来。
    另一条只有他有的会话用来测"越权删除回 404 且行还在"。
    """
    from backend.core.auth import get_password_hash

    exclusive_id = f"chain-write-foreign-{uuid4().hex[:10]}"
    with chain_pg.begin() as conn:
        other_id = conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, 'user') RETURNING id"),
            {"u": f"chain_wtwin_{uuid4().hex[:10]}", "h": get_password_hash(WRITE_PASSWORD)},
        ).scalar_one()
        shared_ref = conn.execute(
            text(
                "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
                " VALUES (:u, :s, '{}'::json, :ts, :ts) RETURNING id"
            ),
            {"u": other_id, "s": writable_session["session_id"], "ts": _TS},
        ).scalar_one()
        exclusive_ref = conn.execute(
            text(
                "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
                " VALUES (:u, :s, '{}'::json, :ts, :ts) RETURNING id"
            ),
            {"u": other_id, "s": exclusive_id, "ts": _TS},
        ).scalar_one()
    yield {
        "user_id": other_id,
        "shared_ref": shared_ref,
        "exclusive_ref": exclusive_ref,
        "exclusive_session_id": exclusive_id,
    }
    with chain_pg.begin() as conn:
        # 只清本夹具建的那个用户；他的两条会话与消息由 ON DELETE CASCADE 带走。
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": other_id})


def test_go_write_delete_response_body_matches_python_edge_byte_for_byte(
    http, chain_endpoints, go_token, py_token, chain_seed, chain_pg
):
    """成功删除的响应体两侧同形同文案——前端只看 `res.ok` 也不代表形状可以漂。

    比的是**把会话号归一之后**的字节：两侧各删自己那条会话，`session_id` 字段按定义就不同，
    直接比整串字节是在比测试数据而不是比实现（上一轮就是这么错的，红得毫无信息量）。
    键序、键集、message 文案、状态码这四样才是这条要钉的。
    """
    got = {}
    ref_ids = []
    for edge in ("go", "py"):
        sid = f"chain-write-parity-{edge}-{uuid4().hex[:8]}"
        ref_ids.append(_insert_session(chain_pg, chain_seed["user_id"], sid))
        url = chain_endpoints.go if edge == "go" else chain_endpoints.py
        token = go_token if edge == "go" else py_token
        resp = http.delete(url(f"{SESSIONS}/{sid}"), headers=_bearer(token))
        got[edge] = (resp.status_code, resp.content.replace(sid.encode(), b"<sid>"), resp.json())
    for ref_id in ref_ids:
        with chain_pg.begin() as conn:
            conn.execute(text("DELETE FROM chat_sessions WHERE id = :i"), {"i": ref_id})

    assert got["go"][0] == got["py"][0] == 200, got
    assert got["go"][1] == got["py"][1], f"归一化后仍不同：go={got['go'][1]!r} py={got['py'][1]!r}"
    assert list(got["go"][2]) == ["session_id", "message"], f"键序即契约：实得 {list(got['go'][2])}"
    assert got["go"][2]["message"] == "Session deleted", "文案与 Python 逐字一致，不许改成中文或 204"


def test_go_write_delete_is_immediately_visible_on_the_python_read_path(
    http, chain_endpoints, go_token, py_token, writable_session, chain_pg
):
    """Go 删掉行之后，仍在服务的 Python 读路径必须立刻读到空。

    接管期间最怕的就是"Go 以为删了、Python 还从缓存里给出来"。C35 已移除会话缓存，
    这条用例就是那个决定的**持续**证据，不是历史证据。
    """
    sid = writable_session["session_id"]
    resp = http.delete(chain_endpoints.go(f"{SESSIONS}/{sid}"), headers=_bearer(go_token))
    assert resp.status_code == 200, resp.text[:200]
    assert _session_row_count(chain_pg, writable_session["ref_id"]) == 0, "行必须真的没了"

    for name, url in (("go", chain_endpoints.go), ("py", chain_endpoints.py)):
        detail = http.get(url(f"{SESSIONS}/{sid}"), headers=_bearer(go_token))
        assert detail.status_code == 200 and detail.content == b'{"messages":[]}', (
            f"{name} 侧仍看得见已删会话：{detail.text[:200]}"
        )
    listing = http.get(chain_endpoints.go(SESSIONS), headers=_bearer(go_token))
    assert sid not in [item["session_id"] for item in listing.json()["sessions"]], "列表里还有已删会话"


def test_go_write_delete_of_other_users_session_is_404_and_their_row_survives(
    http, chain_endpoints, go_token, py_token, twin_foreign_session
):
    """删一条只有别人拥有的会话：两侧同一份 404 信封，而那行必须还在。

    404 而不是 403 是 As-Is 口径（设计审查 §8：接管不换语义）——这条接口不做归属与
    不存在的区分，因此也不给归属探测留信号。
    """
    sid = twin_foreign_session["exclusive_session_id"]
    responses = [http.delete(url(f"{SESSIONS}/{sid}"), headers=_bearer(token))
                 for url, token in ((chain_endpoints.go, go_token), (chain_endpoints.py, py_token))]

    go_resp, py_resp = responses
    assert go_resp.status_code == py_resp.status_code == 404, (go_resp.status_code, py_resp.status_code)
    assert go_resp.content == py_resp.content, f"404 信封也要逐字一致：{go_resp.content!r} vs {py_resp.content!r}"


def test_go_write_delete_with_shared_session_id_only_removes_the_requesters_row(
    http, chain_endpoints, go_token, writable_session, twin_foreign_session, chain_pg
):
    """同一个 session_id 分属两人时，删除只准拿掉请求者自己那一行。

    这是 `WHERE user_id = $1 AND session_id = $2` 那半个条件的直接证据：
    少了 `user_id`，这里会是 200 且**别人的**行消失。
    """
    sid = writable_session["session_id"]
    resp = http.delete(chain_endpoints.go(f"{SESSIONS}/{sid}"), headers=_bearer(go_token))
    assert resp.status_code == 200, resp.text[:200]

    assert _session_row_count(chain_pg, writable_session["ref_id"]) == 0, "请求者自己的行要删掉"
    assert _session_row_count(chain_pg, twin_foreign_session["shared_ref"]) == 1, "同号但属于别人的行被牵连了"


def test_go_write_concurrent_delete_has_exactly_one_winner(http, chain_endpoints, go_token, writable_session, chain_pg):
    """并发删除同一会话：恰好一次 200，其余全是同一份 404，且不许出现 500。

    这条钉的是"删成功"的判定方式——Go 用受影响行数，而不是"先 SELECT 再 DELETE"。
    后者在并发下会让两个请求都以为自己删成功（或者双双 500）。
    """
    sid = writable_session["session_id"]
    url = chain_endpoints.go(f"{SESSIONS}/{sid}")

    def call(_):
        return http.delete(url, headers=_bearer(go_token)).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(call, range(8)))

    assert codes.count(200) == 1, f"恰好一个赢家，实得 {codes}"
    assert set(codes) == {200, 404}, f"其余必须是 404，实得 {sorted(set(codes))}"
    assert _session_row_count(chain_pg, writable_session["ref_id"]) == 0


def test_go_write_concurrent_register_keeps_exactly_one_account(
    http, chain_endpoints, chain_pg, chain_rate_scope
):
    """并发注册同一用户名：只有一个成功落库，其余给契约内的错误，库里恒为一行。

    选这条而不是"注册 + 重复注册"的顺序用例：唯一性由 `users.username` 约束保证，
    应用层的"先查再插"在并发下会双双成功（两行同名）或双双撞约束后裸 500——
    这条就是那两种走偏的探测器。
    """
    username = f"gorace{uuid4().hex[:10]}"
    url = chain_endpoints.go(REGISTER)

    def call(_):
        return http.post(url, json={"username": username, "password": WRITE_PASSWORD})

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(call, range(8)))

    codes = sorted(r.status_code for r in responses)
    assert codes.count(200) == 1, f"恰好一个注册成功，实得 {codes}"
    assert set(codes) <= {200, 400, 409}, f"失败支必须落在契约内，实得 {sorted(set(codes))}"
    assert 500 not in codes, "撞唯一约束不能裸 500"
    assert _user_row_count(chain_pg, username) == 1, "同名账号必须恒为一行"

    with chain_pg.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})

    # 失败支的响应体也得是 detail 信封——前端按 detail 分支，不能收到 HTML 或空体。
    for resp in responses:
        if resp.status_code != 200:
            assert "detail" in resp.json(), f"错误响应缺 detail 信封：{resp.text[:200]}"


def test_go_write_register_and_login_return_the_same_shape_across_edges(
    http, chain_endpoints, chain_pg, chain_rate_scope
):
    """Go 写进去的账号，两侧登录返回**同一组键**，且 Go 自己的注册/登录同形。

    为什么不是"比 body"：token 每次不同（iat/签名都比不出相等），能比的是**形状**——
    前端 store 直接消费这组键，多一个少一个都让"注册成功却进不去"。
    Python 侧 `AuthResponse` 同时挂在 register 与 login 上（backend/api/auth.py:36,95），
    Go 也必须保持这一个形状，不能注册多返回一个 `user` 而登录没有。
    """
    username = f"gowrite{uuid4().hex[:10]}"
    body = {"username": username, "password": WRITE_PASSWORD}

    registered = http.post(chain_endpoints.go(REGISTER), json=body)
    assert registered.status_code == 200, registered.text[:200]
    try:
        login_go = http.post(chain_endpoints.go(LOGIN), json=body)
        login_py = http.post(chain_endpoints.py(LOGIN), json=body)

        assert login_go.status_code == login_py.status_code == 200, (login_go.text[:200], login_py.text[:200])
        assert set(login_go.json()) == set(login_py.json()), (
            f"登录键集两侧不同：go={sorted(login_go.json())} py={sorted(login_py.json())}"
        )
        assert set(registered.json()) == set(login_go.json()), (
            f"Go 的注册与登录不同形：register={sorted(registered.json())} login={sorted(login_go.json())}"
        )
        for payload in (registered.json(), login_go.json(), login_py.json()):
            assert "detail" not in payload, payload
            assert payload.get("token_type") == "bearer", payload
    finally:
        with chain_pg.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
