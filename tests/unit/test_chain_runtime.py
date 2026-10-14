"""chain 层 preflight 策略的单测（`tests/chain/_runtime.py`）。

为什么这条要单独有负向用例：chain 层的价值全押在"起不来就红"上，而它同时又要让
全量 `pytest -q` 在没起栈的机器上保持绿——这两个要求靠一个分档函数调和，
那个函数写反了（比如恒返回 skip）就会让 X4 的判据**永远不可能变绿**，
而这正是台账 C22 记过的那类判据缺陷。所以这里正反各钉一遍。
"""

from __future__ import annotations

import pytest

from tests.chain._runtime import ChainEndpoints, preflight_action, resolve_endpoints

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("markexpr", "expected"),
    [
        ("chain", "fail"),
        ("chain and not slow", "fail"),
        ("(unit or chain)", "fail"),
        ("", "skip"),
        ("unit", "skip"),
        ("integration and not slow", "skip"),
    ],
)
def test_preflight_action_follows_selection(markexpr, expected):
    assert preflight_action(markexpr) == expected


def test_explicit_chain_selection_never_skips():
    """选了 chain 就不许 skip——否则"`-m chain` 全绿"可以是"一个都没跑"。"""
    assert preflight_action("chain") == "fail"


def test_plain_full_run_does_not_fail():
    """没选 chain 的全量跑必须只跳过，否则 CI 在没有真栈时长期红。"""
    assert preflight_action("") == "skip"


def test_resolve_endpoints_prefers_environment_over_dotenv():
    ep = resolve_endpoints(
        {"CHAIN_GO_API_URL": "http://127.0.0.1:19999", "DATABASE_URL": "postgresql+psycopg2://h/db"},
        {"CHAIN_GO_API_URL": "http://from-dotenv:8080", "DATABASE_URL": "postgresql+psycopg2://dotenv/db"},
    )
    assert ep.go_api == "http://127.0.0.1:19999"
    assert ep.database_url == "postgresql+psycopg2://h/db"


def test_resolve_endpoints_keeps_database_url_empty_when_absent():
    """凭据没有默认值：`.env` 与环境变量都没有就是没有，不能拿一个假 URL 去连。"""
    ep = resolve_endpoints({}, {})
    assert ep.database_url == ""
    assert ep.ai_core == "http://127.0.0.1:8000"


def test_endpoints_join_paths_without_double_slash():
    ep = ChainEndpoints(go_api="http://127.0.0.1:8080/", ai_core="http://127.0.0.1:8000/", database_url="x")
    assert ep.go("/api/v1/health") == "http://127.0.0.1:8080/api/v1/health"
    assert ep.py("/health") == "http://127.0.0.1:8000/health"
