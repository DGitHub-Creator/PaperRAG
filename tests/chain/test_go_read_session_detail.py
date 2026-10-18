"""G02 第一切片：`GET /api/v1/sessions/{session_id}` 的 Go 原生接管逐字对拍（`-k go_read_detail`）。

判据是**响应字节相同**，不是"两边都 200"：这一条接口返回的是历史消息，
前端直接渲染 `content` 与 `rag_trace` 的键集，任何一侧多一个键、少一个键、
把一个 `<` 转成 `\u003c`、把 3.0 写成 3，用户都会看见，而对拍只看状态码就全绿。

三种历史行分别对应三种风险，缺一不可：
  1. 新写入的规范行（保存前已过 `RagTrace.model_validate`）；
  2. 未知键与缺失可选键（投影面：丢弃 / 补 null）；
  3. 坏历史行（缺必需键、嵌套缺必需键、标量、越界布尔）——**整条追踪变 null，正文保留**。
第 3 类是台账 C34 的口径，也是接管最容易悄悄改掉语义的地方。

至于"这条真的是 Go 在服务而不是反代"：`server/cmd/api/main_test.go` 用"上游桩被碰到就记一笔"
钉住了路由归属——反代给出同样 JSON 不能算接管证据（设计审查 §0），所以那半边放在不需要真栈的 Go 单测里。
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.chain.conftest import CHAIN_PASSWORD

pytestmark = pytest.mark.chain

DETAIL_BASE = "/api/v1/sessions"

_TS = datetime(2026, 10, 14, 7, 8, 10, 123456)

# 越权用例里"别人的正文"必须是一句能在响应里被搜出来的话；用它做探针，
# 而不是只断言状态码——泄漏的响应照样是 200。
FOREIGN_MARK = "别人的会话内容-DO-NOT-LEAK"

# 新写入的形状：`conversation_storage.py:23` 用 model_dump(exclude_none=True)，
# 所以库里只有被赋过值的键，响应里才补齐成全集——这一对不对称必须一起测。
CANONICAL_TRACE = {
    "tool_used": True,
    "tool_name": "knowledge_search",
    "query": "共识安全证明 <UC> & 部分同步",
    "candidate_k": 20,
    "rerank_enabled": True,
    "retrieved_chunks": [
        {
            "filename": "mpc.pdf",
            "page_number": 3,
            "text": "协议在 f<n/3 故障下成立",
            "score": 0.82,
            "rrf_rank": 1,
            "has_theorem_in_parent": True,
            "chapter_path": "4 安全证明",
        },
        {"filename": "sync.pdf", "page_number": "7", "score": 1, "rrf_rank": 2.0},
    ],
    "source_map": {
        # 键序是文档顺序：Python 侧 dict 保持插入序，Go 用 map 就会漂（已在投影里按顺序解码）
        "[Source 2]": {"filename": "sync.pdf", "page": "7", "source_label": "[Source 2]"},
        "[Source 1]": {"filename": "mpc.pdf", "page": 3, "chunk_id": "mpc.pdf#p3#c1"},
    },
    "citations": [
        {"claim": "协议成立", "source_label": "[Source 1]", "supported": True, "filename": "mpc.pdf", "page": 3},
    ],
    "unsupported_claims": [{"claim": "这是首个该类结果", "reason": "未检索到支撑证据"}],
    "expanded_chunk_count": 2,
}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def detail_session(chain_pg, chain_seed):
    """给对拍建一条专属会话，用完删掉——共享种子会被并发用例互相踩。"""
    session_id = "chain-sess-detail-parity"
    with chain_pg.begin() as conn:
        ref_id = conn.execute(
            text(
                "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
                " VALUES (:u, :s, '{}'::json, :ts, :ts) RETURNING id"
            ),
            {"u": chain_seed["user_id"], "s": session_id, "ts": _TS},
        ).scalar_one()
    yield {"session_id": session_id, "ref_id": ref_id}
    with chain_pg.begin() as conn:
        conn.execute(text("DELETE FROM chat_sessions WHERE id = :i"), {"i": ref_id})


def _seed_messages(chain_pg, ref_id: int, rows: list[tuple[str, object]]) -> None:
    with chain_pg.begin() as conn:
        for index, (content, trace) in enumerate(rows):
            raw = None if trace is None else (trace if isinstance(trace, str) else json.dumps(trace, ensure_ascii=False))
            conn.execute(
                text(
                    "INSERT INTO chat_messages (session_ref_id, message_type, content, timestamp, rag_trace)"
                    " VALUES (:s, 'ai', :c, :ts, CAST(:t AS json))"
                ),
                {"s": ref_id, "c": content, "ts": _TS, "t": raw},
            )


@pytest.fixture()
def twin_foreign_session(chain_pg, chain_seed, detail_session):
    """另一个用户名下建一条**同 session_id** 的会话，并塞进一句可辨认的正文。

    为什么用同号而不是随便一个号：`chat_sessions` 的唯一约束是 `(user_id, session_id)`
    （000001 基线），所以同一个 id 天然可以属于两个人。此时读过滤器只要漏掉 `user_id`，
    返回的就是别人的消息内容——这条用例因此同时是**越权**用例，不只是"空数组"用例。
    """
    from backend.core.auth import get_password_hash

    with chain_pg.begin() as conn:
        other_id = conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, 'user') RETURNING id"),
            {"u": f"chain_twin_{uuid4().hex[:10]}", "h": get_password_hash(CHAIN_PASSWORD)},
        ).scalar_one()
        foreign_ref = conn.execute(
            text(
                "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
                " VALUES (:u, :s, '{}'::json, :ts, :ts) RETURNING id"
            ),
            {"u": other_id, "s": detail_session["session_id"], "ts": _TS},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO chat_messages (session_ref_id, message_type, content, timestamp, rag_trace)"
                " VALUES (:s, 'ai', :c, :ts, NULL)"
            ),
            {"s": foreign_ref, "c": FOREIGN_MARK, "ts": _TS},
        )
    yield {"user_id": other_id}
    with chain_pg.begin() as conn:
        # 只清理本夹具建的那个用户；会话与消息由 ON DELETE CASCADE 带走。
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": other_id})


def _parity(http, chain_endpoints, token: str, session_id: str) -> tuple[bytes, bytes, list[dict]]:
    """两侧各取一次，先要求**字节相同**，再把解析后的消息交给调用方继续断言。"""
    path = f"{DETAIL_BASE}/{session_id}"
    go = http.get(chain_endpoints.go(path), headers=_bearer(token))
    py = http.get(chain_endpoints.py(path), headers=_bearer(token))
    assert go.status_code == py.status_code == 200, f"go={go.status_code} py={py.status_code}: {go.text[:200]}"
    assert go.content == py.content, (
        "逐字对拍失败：\n"
        f"  go={go.content.decode('utf-8', 'replace')[:600]}\n"
        f"  py={py.content.decode('utf-8', 'replace')[:600]}"
    )
    return go.content, py.content, go.json()["messages"]


def test_go_read_detail_canonical_trace_matches_byte_for_byte(http, chain_endpoints, go_token, detail_session, chain_pg):
    _seed_messages(chain_pg, detail_session["ref_id"], [("规范追踪", CANONICAL_TRACE)])
    _, _, messages = _parity(http, chain_endpoints, go_token, detail_session["session_id"])
    assert len(messages) == 1
    trace = messages[0]["rag_trace"]
    # 响应侧补齐成全集：39 个声明键一个都不能少（写侧稀疏、读侧全量是既有口径）
    assert len(trace) == 39, f"投影后的键数不是 39：{len(trace)}"
    assert trace["query"] == "共识安全证明 <UC> & 部分同步", "正文里的 < > & 不该被转义成 \\u00xx"
    assert trace["retrieved_chunks"][0]["has_proof_in_parent"] is None, "未提供的声明键要给 null 而不是消失"
    assert trace["retrieved_chunks"][1]["score"] == 1.0, "int 落进 float 声明要渲染成 1.0"
    assert trace["retrieved_chunks"][1]["page_number"] == "7", "str|int 两种形态都要原样保留"
    assert list(trace["source_map"]) == ["[Source 2]", "[Source 1]"], "source_map 的键序要跟库里的文档顺序"
    assert trace["citations"][0]["supported"] is True, "supported 只表示标签校验，不表示语义接地（D3）"


def test_go_read_detail_projection_drops_unknown_and_keeps_answer(http, chain_endpoints, go_token, detail_session, chain_pg):
    _seed_messages(chain_pg, detail_session["ref_id"], [
        ("未知键要丢弃", {"tool_used": True, "tool_name": "rag", "query": "q", "who_knows_me": 42,
                          "retrieved_chunks": [{"filename": "a.pdf", "side_notes": []}]}),
        ("没有追踪", None),
    ])
    _, _, messages = _parity(http, chain_endpoints, go_token, detail_session["session_id"])
    assert messages[0]["rag_trace"].get("who_knows_me") is None, "未声明的键不能透传——那是第二套真相"
    assert "who_knows_me" not in json.dumps(messages[0]["rag_trace"])
    assert "side_notes" not in json.dumps(messages[0]["rag_trace"]["retrieved_chunks"][0])
    assert messages[1]["rag_trace"] is None and messages[1]["content"] == "没有追踪"


@pytest.mark.parametrize(
    ("label", "trace"),
    [
        ("缺必需键", {"query": "mpc", "sources": [{"filename": "mpc.pdf", "page": 3}]}),
        ("必需键类型不对", {"tool_used": "maybe", "tool_name": "rag"}),
        ("越界布尔", {"tool_used": 2, "tool_name": "rag"}),
        ("整条不是对象", ["tool_used"]),
        # 库里要存"JSON 字符串标量"必须传带引号的 JSON 文档；直接传 Python str 会被
        # _seed_messages 当成已编码原文，PG 一律拒 `invalid input syntax for type json`——
        # 上一轮这条就是这样根本没铺进去，测了个空。
        ("整条是标量", '"不是对象"'),
        ("嵌套元素缺必需键", {"tool_used": True, "tool_name": "rag", "retrieved_chunks": [{"page_number": 3}]}),
        ("嵌套元素越界类型", {"tool_used": True, "tool_name": "rag", "retrieved_chunks": [{"filename": "a", "page_number": 3.5}]}),
        ("引用元素缺 claim", {"tool_used": True, "tool_name": "rag", "unsupported_claims": [{"reason": "x"}]}),
        ("int 字段是指数串", {"tool_used": True, "tool_name": "rag", "candidate_k": "1e2"}),
        ("int 字段是有损小数", {"tool_used": True, "tool_name": "rag", "candidate_k": 10.5}),
    ],
)
def test_go_read_detail_unusable_trace_becomes_null_but_answer_stays(
    http, chain_endpoints, go_token, detail_session, chain_pg, label, trace
):
    """坏历史行只让 rag_trace 变 null，正文必须留着——两侧同判（台账 C34）。"""
    _seed_messages(chain_pg, detail_session["ref_id"], [(f"正文：{label}", trace)])
    _, _, messages = _parity(http, chain_endpoints, go_token, detail_session["session_id"])
    assert messages[0]["rag_trace"] is None, f"{label}：期望整条 null"
    assert messages[0]["content"] == f"正文：{label}"


def test_go_read_detail_lax_coercion_agrees_across_languages(http, chain_endpoints, go_token, detail_session, chain_pg):
    """历史行没有写前校验，字符串数字、"yes"、0/1 都真实存在过；两侧必须给同一个渲染结果。

    取值集合是**本机实测 pydantic 钉出来的**，不是照抄直觉：int 字段收 `"10.0"` 与 `true` 而拒 `"1e2"`，
    float 字段收 `true` 而给 `1.0`，`str | int` 的 union 把 `"10.0"` 留在字符串分支。
    Go 多接受或少接受一种，浏览器就会在同一列上看见两种形状。
    """
    _seed_messages(chain_pg, detail_session["ref_id"], [
        ("宽松转换", {"tool_used": "yes", "tool_name": "rag", "candidate_k": "10", "rerank_applied": 1,
                      "retrieved_chunks": [{"filename": "a.pdf", "score": 1, "rrf_rank": 2.0, "has_proof_in_parent": 0}]}),
        ("边界取值", {"tool_used": True, "tool_name": "rag", "candidate_k": "10.0", "auto_merge_threshold": True,
                      "retrieved_chunks": [{"filename": "b.pdf", "score": True, "page_number": 3.0},
                                           {"filename": "c.pdf", "page_number": "10.0"}]}),
    ])
    body, _, messages = _parity(http, chain_endpoints, go_token, detail_session["session_id"])
    trace = messages[0]["rag_trace"]
    assert trace["tool_used"] is True and trace["rerank_applied"] is True
    assert trace["candidate_k"] == 10
    chunk = trace["retrieved_chunks"][0]
    assert chunk["score"] == 1.0 and chunk["rrf_rank"] == 2 and chunk["has_proof_in_parent"] is False
    # 字节里必须真出现 `1.0`：Python 的 json 渲染对整数值 float 也带小数点，Go 默认会写成 1
    assert b'"score":1.0' in body, body[:400]

    edges = messages[1]["rag_trace"]
    assert edges["candidate_k"] == 10, '"10.0" 落进 int 字段要成 10'
    assert edges["auto_merge_threshold"] == 1, "布尔落进 int 字段要给 1，两侧一样"
    assert edges["retrieved_chunks"][0]["score"] == 1.0, "布尔落进 float 字段要给 1.0"
    assert b'"page_number":3,' in body, "3.0 无损落进 str|int 要给整数 3"
    assert edges["retrieved_chunks"][1]["page_number"] == "10.0", "str|int 要把字符串留在字符串分支"


def test_go_read_detail_orders_by_message_id_not_timestamp(http, chain_endpoints, go_token, detail_session, chain_pg):
    """同一轮问答的 timestamp 可以完全相同，排序只能靠写入顺序（chat_messages.id）。"""
    _seed_messages(chain_pg, detail_session["ref_id"], [("第一问", None), ("第二答", None)])
    _, _, messages = _parity(http, chain_endpoints, go_token, detail_session["session_id"])
    assert [m["content"] for m in messages] == ["第一问", "第二答"]
    assert all(m["timestamp"] == "2026-10-14T07:08:10.123456" for m in messages)
    assert all(list(m) == ["type", "content", "timestamp", "rag_trace"] for m in messages), "消息键序即契约"


def test_go_read_detail_unknown_and_foreign_session_are_200_empty(http, chain_endpoints, go_token, py_token, detail_session):
    """不存在与别人的会话都是 200 + `{"messages": []}`：这条接口不做存在性判断（As-Is）。"""
    for token, sid, label in (
        (go_token, "chain-sess-never-inserted", "不存在"),
        (py_token, detail_session["session_id"], "空会话"),
    ):
        resp = http.get(chain_endpoints.go(f"{DETAIL_BASE}/{sid}"), headers=_bearer(token))
        assert resp.status_code == 200, f"{label}：{resp.status_code} {resp.text[:200]}"
        assert resp.content == b'{"messages":[]}', f"{label}：实得 {resp.text[:200]}"


def test_go_read_detail_same_session_id_under_another_user_does_not_leak(
    http, chain_endpoints, go_token, detail_session, chain_pg, twin_foreign_session
):
    """同一个 session_id 挂在两个用户名下时，读接口只准返回自己那一条会话。

    两侧都得为空之外还得不含别人的正文：泄漏的响应照样是 200，所以断言的是**内容**。
    Python 侧按 `username` join（conversation_storage.py:63），Go 侧按 `cs.user_id` 过滤
    （sql/queries/chat_sessions.sql）——两条路径等价这件事正是这条用例要证的。
    """
    _seed_messages(chain_pg, detail_session["ref_id"], [("只属于我的正文", None)])
    body, _, messages = _parity(http, chain_endpoints, go_token, detail_session["session_id"])
    assert [m["content"] for m in messages] == ["只属于我的正文"], messages
    assert FOREIGN_MARK.encode() not in body, "响应里出现了另一个用户的正文"


def test_go_read_detail_requires_authentication_on_both_sides(http, chain_endpoints, detail_session):
    path = f"{DETAIL_BASE}/{detail_session['session_id']}"
    go = http.get(chain_endpoints.go(path))
    py = http.get(chain_endpoints.py(path))
    assert go.status_code == py.status_code == 401
    assert go.content == py.content, f"401 信封也要逐字一致：{go.text!r} vs {py.text!r}"
