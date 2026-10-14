"""chain 层的地址解析与 preflight 策略（纯函数，可单测）。

为什么把"不可达时到底 fail 还是 skip"单独抽出来：这是这条门禁**唯一的假绿风险点**。
全量 `pytest -q` 会连 tests/chain/ 一起收集，而 CI 与没有真栈的机器上都跑不了它——
一律 skip 会让"`-m chain -k go_auth` 全绿"变成一句空话（X4 正是这么红的：收 0 项），
一律 fail 又会让日常全量测试在任何没起栈的机器上长红。

所以按**选择意图**分档：命令行显式选了 chain（`-m` 表达式里有 chain）就是"我要跑它"，
起不来必须**红**；没选它只是被全量顺带收到，那就 skip 并写明原因。
这条分档由 `tests/unit/test_chain_runtime.py` 的负向用例钉住。
"""

from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Mapping

DEFAULT_GO_API = "http://127.0.0.1:8080"
DEFAULT_AI_CORE = "http://127.0.0.1:8000"

PROBE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ChainEndpoints:
    """三个被测面的地址。DATABASE_URL 没有默认值——它是凭据，不该写进仓库。"""

    go_api: str
    ai_core: str
    database_url: str

    def go(self, path: str) -> str:
        return f"{self.go_api.rstrip('/')}{path}"

    def py(self, path: str) -> str:
        return f"{self.ai_core.rstrip('/')}{path}"


def preflight_action(markexpr: str) -> str:
    """`"fail"`＝显式选了 chain；`"skip"`＝被全量收集顺带路过。

    按子串判，所以 `-m "not chain"` 也会返回 fail——但那种表达式下 chain 用例根本不会被收集，
    preflight 走不到，所以不存在"排除却报错"的路径。反过来 `-m "(unit or chain)"` 判 fail 是对的。
    """
    return "fail" if "chain" in (markexpr or "") else "skip"


def resolve_endpoints(environ: Mapping[str, str], dotenv: Mapping[str, str]) -> ChainEndpoints:
    """环境变量优先，其次 `.env`。chain 专用变量只在本层生效，不污染应用配置。"""
    return ChainEndpoints(
        go_api=environ.get("CHAIN_GO_API_URL") or DEFAULT_GO_API,
        ai_core=environ.get("CHAIN_AI_CORE_URL") or DEFAULT_AI_CORE,
        database_url=environ.get("DATABASE_URL") or dotenv.get("DATABASE_URL") or "",
    )


def probe_infra(ep: ChainEndpoints) -> list[str]:
    """返回"哪儿没起来"的清单；空列表＝三个被测面都在。

    这里刻意宽 catch：探针的职责就是如实回答"通不通"，把 OSError/HTTPStatusError
    分类讨论只会让 preflight 自己变成需要维护的代码。
    """
    problems: list[str] = []

    for label, url in (
        ("go-api", ep.go("/api/v1/health")),
        ("ai-core", ep.py("/health")),
    ):
        if not url.startswith("http"):
            problems.append(f"{label} 地址不成样子：{url!r}")
            continue
        try:
            resp = httpx.get(url, timeout=PROBE_TIMEOUT_SECONDS)
            if resp.status_code != 200:
                problems.append(f"{label} {url} 返回 {resp.status_code}，期望 200")
        except Exception as err:  # noqa: BLE001 - 探针要吞掉一切连接错误并如实上报
            problems.append(f"{label} {url} 不可达：{err.__class__.__name__}")

    if not ep.database_url:
        problems.append("没有 DATABASE_URL：既不在环境变量里，也不在 .env 里")
    else:
        problems.extend(_probe_pg(ep.database_url))
    return problems


def _probe_pg(database_url: str) -> list[str]:
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as err:  # noqa: BLE001
        return [f"PostgreSQL 不可达：{err.__class__.__name__}: {str(err)[:160]}"]
    return []


def startup_hint() -> str:
    """起不来时给读者的那三行命令（与 X1 判据同一套形态：中间件容器 + 源码起进程）。"""
    return (
        "chain 层需要：\n"
        "  1) uv run python scripts/dev.py infra        # 或 up postgres redis\n"
        "  2) uv run python scripts/dev.py serve        # ai-core，:8000\n"
        "  3) uv run python scripts/dev.py go-serve     # go-api，:8080\n"
    )
