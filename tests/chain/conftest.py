"""chain 层 fixtures：三个被测面的地址、真库种子、两侧令牌（`09` P0-5）。

种子数据**直接写 PG**，不走任何一条 HTTP 接口——这是刻意的：用被测面去铺被测面的数据，
一旦那条接口本身有问题，测试会以"铺数据失败"的形态报错，看不出真实缺陷。写库用的表与列
都取自 `server/migrations/000001_baseline.up.sql`，所以种子失败也能当场暴露"表还没建"。

时间列一律给**显式的 naive 值**，其中一个带微秒、一个不带：`updated_at`/`timestamp` 在库里
是 `TIMESTAMP`（无时区），两侧都要把它们渲染成 Python `datetime.isoformat()` 那个形状
（微秒为 0 时整段省略），不给固定值就没法验这条格式化。
"""

from __future__ import annotations

import os
import warnings
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

from tests.chain._runtime import (
    probe_infra,
    preflight_action,
    resolve_endpoints,
    startup_hint,
)

# 满足 register 的口令规则：≥8 个码点，且小写/大写/数字至少两类
CHAIN_PASSWORD = "Chain2026seed"

_TS_WITH_MICRO = datetime(2026, 10, 14, 7, 8, 10, 123456)
_TS_NO_MICRO = datetime(2026, 10, 14, 7, 8, 9)
_TS_OLDER = datetime(2026, 10, 13, 9, 0, 0)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def chain_endpoints():
    return resolve_endpoints(os.environ, dotenv_values(REPO_ROOT / ".env"))


@pytest.fixture(scope="session", autouse=True)
def chain_infra(chain_endpoints, request):
    """preflight：不可达时按"是不是显式选了 chain"决定红还是跳过。

    策略本身在 `_runtime.preflight_action`，由单测钉住；这里只负责执行。
    """
    problems = probe_infra(chain_endpoints)
    if not problems:
        return
    message = "chain 层起不来：\n  - " + "\n  - ".join(problems) + "\n" + startup_hint()
    if preflight_action(request.config.option.markexpr) == "fail":
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def chain_pg(chain_endpoints):
    engine = create_engine(chain_endpoints.database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def http():
    # 超时给到 10 s：真栈首请求可能要连池，2 s 会误报成"服务不可达"
    with httpx.Client(timeout=10.0) as client:
        yield client


def _insert_session(conn, user_id: int, session_id: str, updated_at: datetime) -> int:
    return conn.execute(
        text(
            "INSERT INTO chat_sessions (user_id, session_id, metadata_json, updated_at, created_at)"
            " VALUES (:user_id, :session_id, '{}'::json, :updated_at, :created_at)"
            " RETURNING id"
        ),
        {
            "user_id": user_id,
            "session_id": session_id,
            "updated_at": updated_at,
            "created_at": updated_at,
        },
    ).scalar_one()


def _insert_message(
    conn,
    session_ref_id: int,
    message_type: str,
    content: str,
    timestamp: datetime,
    rag_trace: str | None,
) -> int:
    return conn.execute(
        text(
            "INSERT INTO chat_messages (session_ref_id, message_type, content, timestamp, rag_trace)"
            " VALUES (:sid, :type, :content, :timestamp, CAST(:rag_trace AS json))"
            " RETURNING id"
        ),
        {
            "sid": session_ref_id,
            "type": message_type,
            "content": content,
            "timestamp": timestamp,
            "rag_trace": rag_trace,
        },
    ).scalar_one()


@pytest.fixture(scope="session")
def chain_seed(chain_pg):
    """一个用户 + 两个会话（一个带 rag_trace、一个只有 system 消息）。

    会话列表按 `updated_at DESC`，所以 newer 在前——两侧都必须还原出这个顺序。
    """
    from backend.core.auth import get_password_hash

    username = f"chain_{uuid4().hex[:12]}"
    password = CHAIN_PASSWORD

    with chain_pg.begin() as conn:
        user_id = conn.execute(
            text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, 'user') RETURNING id"),
            {"u": username, "h": get_password_hash(password)},
        ).scalar_one()
        newer = _insert_session(conn, user_id, "chain-sess-newer", _TS_WITH_MICRO)
        older = _insert_session(conn, user_id, "chain-sess-older", _TS_NO_MICRO)
        _insert_message(conn, newer, "human", "What is secure multiparty computation?", _TS_NO_MICRO, None)
        _insert_message(
            conn,
            newer,
            "ai",
            "MPC lets parties jointly compute a function without revealing inputs.",
            _TS_WITH_MICRO,
            '{"query": "mpc", "sources": [{"filename": "mpc.pdf", "page": 3}]}',
        )
        _insert_message(conn, older, "system", "session seeded for chain tests", _TS_OLDER, None)

    yield {
        "username": username,
        "password": password,
        "user_id": user_id,
        "newer": {"id": newer, "session_id": "chain-sess-newer", "updated_at": _TS_WITH_MICRO},
        "older": {"id": older, "session_id": "chain-sess-older", "updated_at": _TS_NO_MICRO},
    }

    with chain_pg.begin() as conn:
        # 级联会带走 chat_sessions 与 chat_messages，但带不走 Redis 里可能留下的缓存
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    _flush_chat_cache(username)


def _flush_chat_cache(username: str) -> None:
    """清掉该用户的会话缓存键。

    失败只可能让下一轮读到陈旧缓存，不会让本轮断言变绿，所以这里不抛——
    但也不静默：真栈上 Redis 是 preflight 之后必然在的，正常路径永远走不到 except。
    """
    try:
        from backend.services.cache import cache

        cache.delete_pattern(f"chat_*:{username}*")
    except Exception:  # noqa: BLE001
        warnings.warn("会话缓存清理失败，链路验证可能读到旧数据", RuntimeWarning, stacklevel=2)


def _login(client: httpx.Client, url: str, seed: dict) -> str:
    resp = client.post(url, json={"username": seed["username"], "password": seed["password"]})
    assert resp.status_code == 200, f"登录失败 {resp.status_code}: {resp.text[:200]}"
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def go_token(http, chain_endpoints, chain_seed) -> str:
    """go-api 签发的访问令牌。"""
    return _login(http, chain_endpoints.go("/api/v1/auth/login"), chain_seed)


@pytest.fixture(scope="session")
def py_token(http, chain_endpoints, chain_seed) -> str:
    """ai-core 签发的访问令牌（与 Go 用同一个 JWT_SECRET_KEY）。"""
    return _login(http, chain_endpoints.py("/api/v1/auth/login"), chain_seed)


@pytest.fixture()
def bearer(go_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {go_token}"}
