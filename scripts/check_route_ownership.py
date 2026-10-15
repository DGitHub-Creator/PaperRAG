"""路由归属机检（分工的可执行版本，对照表在 `contracts/route-ownership.md`）。

为什么光有文档不够：`rules/frontend-backend-division-of-labor.md` 写着「Go 负责入口与编排、
Python 负责核心业务端」，但一句话的描述保不住三件事——
①接管了一条路径而 Python 那条**没删**（今天就有五条，因为 chain 对拍需要两侧在场）；
②Go 里挂了一条**没登记**的路由；
③Python 新加了一条**没人认领**的面。
这三件事没有任何现有门禁会红：`check_contracts.py` 只比前端↔契约，压根不看服务侧（台账 C31）。
所以本脚本把表回查到三个真相源：**Go 源码的路由注册、Python 的实际路由表、chain 用例的覆盖**。

设计上有两处刻意从严：
  - 归属为 `go` 而 Python 仍在服务的，必须在「Python 仍在」列写明去向（卡片号/台账号/「对拍」），
    且该路径字面量必须真的出现在 `tests/chain/` 里。没有对拍用例的"暂时保留"就是没人会再去删的遗留。
  - `proxy` 不得同时被 Go 显式注册。搬完了却还标 proxy，与没搬却标 go，是同一类漂移。

用法：
    uv run python scripts/check_route_ownership.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE_FILE = ROOT / "contracts" / "route-ownership.md"
CHAIN_DIR = ROOT / "tests" / "chain"
GO_ROUTE_FILES = (
    ROOT / "server" / "cmd" / "api" / "main.go",
    ROOT / "server" / "internal" / "httpapi" / "router.go",
)

GO_METHODS = ("Get", "Post", "Put", "Delete", "Patch")
#: `router.Get("/api/v1/health", ...)` 这一形态。通配（`/api/*`）不算注册——它是转发，不是归属。
GO_ROUTE_RE = re.compile(
    r"\.(" + "|".join(GO_METHODS) + r")\(\s*\"(?P<path>[^\"]+)\"" , re.M)
METHOD_BY_GO = {"Get": "GET", "Post": "POST", "Put": "PUT", "Delete": "DELETE", "Patch": "PATCH"}

ROW_RE = re.compile(r"^\|\s*(GET|POST|PUT|DELETE|PATCH|WS)\s*\|\s*`([^`]+)`\s*\|\s*(\w+)\s*\|\s*([^|]*?)\s*\|")
#: 例外必须有去向：卡片号（P1-2）或台账号（C35）。
JUSTIFICATION_RE = re.compile(r"(P\d+-\d+|C\d+)")
#: 「对拍保留」必须指到**用例名**，不是路径字面量：`test_go_read_sessions.py` 里删除面写的是
#: `LIST_PATH + 具体 id`，按字面量 grep 会把已经测过的判成没测过。
CHAIN_SELECTOR_RE = re.compile(r"(tests/chain/\w+\.py)::(\w+)")

#: Python 侧这些根路径不进表就无人认领（探针与指标都在 `/api` 之外）。
ROOT_API_PATHS = {"/health", "/ready", "/metrics"}


def go_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for f in GO_ROUTE_FILES:
        text = f.read_text(encoding="utf-8")
        for m in GO_ROUTE_RE.finditer(text):
            path = m.group("path")
            if "*" in path:
                continue
            out.add((METHOD_BY_GO[m.group(1)], path))
    return out


def python_routes() -> set[tuple[str, str]]:
    """从 FastAPI 的路由表取，而不是从文档抄。静态挂载（`StaticFiles`）与 docs 端点不算业务面。"""
    from fastapi.routing import APIRoute

    # scripts/ 不是包，直接跑时仓库根不在 sys.path 上（pytest 会注入，命令行不会），
    # 于是 `import backend` 以 ModuleNotFound 失败——那会被下面的 except 误报成"服务侧判不了"。
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from backend.app import app
    except Exception as exc:  # 导不动就等于没法判，宁可红也不要默默通过
        raise SystemExit(f"[ownership] 导入 backend.app 失败，无法判定服务侧: {exc}")

    out: set[tuple[str, str]] = set()
    for route in app.routes:
        cls = type(route).__name__
        if isinstance(route, APIRoute):
            for method in route.methods:
                if method in ("HEAD", "OPTIONS"):
                    continue
                out.add((method, route.path))
        elif cls == "APIWebSocketRoute":
            out.add(("WS", route.path))
    return out


def table_rows() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for line in TABLE_FILE.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return rows


def chain_selector_declared(still: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in CHAIN_SELECTOR_RE.finditer(still)]


def selector_covered(rel_path: str, test_name: str) -> str | None:
    """返回 None 表示这个选择器确实在指一条用例，否则返回失败原因。"""
    f = ROOT / rel_path
    if not f.is_file():
        return f"用例文件不存在: {rel_path}"
    text = f.read_text(encoding="utf-8")
    if f"def {test_name}" not in text:
        return f"{rel_path} 里没有 def {test_name}"
    return None


def check() -> list[str]:
    errors: list[str] = []
    go = go_routes()
    py = python_routes()

    rows = table_rows()
    if not rows:
        return [f"{TABLE_FILE.name} 没解析出任何行，归属门禁等于没有（宁可报错也不要空过）"]

    table_keys: set[tuple[str, str]] = set()
    for method, path, owner, still in rows:
        key = (method, path)
        if key in table_keys:
            errors.append(f"{method} {path}：表里重复登记")
        table_keys.add(key)

        if owner == "go":
            if key not in go:
                errors.append(f"{method} {path}：标 `go` 但 Go 源码里没有这条注册——接管是纸面的")
            errors += check_exception(method, path, still)
        elif owner == "shared":
            if key not in go or key not in py:
                errors.append(f"{method} {path}：标 `shared` 就要两侧都在（Go {key in go} / Python {key in py}）")
        elif owner == "proxy":
            if key not in py:
                errors.append(f"{method} {path}：标 `proxy` 但 Python 没有这条面——反代指向死路")
            if key in go:
                errors.append(f"{method} {path}：Go 已显式注册，表里却还标 `proxy`——搬完要改归属")
        elif owner == "internal":
            if not path.startswith("/internal/"):
                errors.append(f"{method} {path}：`internal` 的路径必须以 `/internal/` 开头，否则 R3 管不到它")
            if key not in py:
                errors.append(f"{method} {path}：标 `internal` 但 Python 没有这条面")
        else:
            errors.append(f"{method} {path}：归属取值不认识: {owner}")

    # 反向覆盖：接线了却没登记、新加了没人认领，都算漂移。
    for method, path in sorted(go - table_keys):
        errors.append(f"Go 注册了 {method} {path}，但归属表里没有这一行")
    for method, path in sorted(py - table_keys):
        if path.startswith(("/api", "/internal")) or path in ROOT_API_PATHS:
            errors.append(f"Python 暴露 {method} {path}，但归属表里没有这一行（新增面要先认领归属）")
    return errors


def check_exception(method: str, path: str, still: str) -> list[str]:
    """`go` 归属下 Python 仍在服务时的两种写法（对拍保留 / 未对拍保留），各有一条硬要求。

    这一格写 `—` 表示 Python 那条已经不在了，不需要例外登记。
    """
    if still in ("—", "-", ""):
        return []
    prefix = f"{method} {path}：例外登记"

    if "未对拍" in still:
        # 没对拍就得是**已登记的欠账**，否则这条遗留没有去处。
        if not re.search(r"C\d+", still):
            return [f"{prefix}写了「未对拍」却没台账号——欠账要登记进 rules/12 才会被处置"]
        return []

    if "对拍保留" in still:
        declared = chain_selector_declared(still)
        if not declared:
            return [f"{prefix}声称对拍保留，但没指到用例（写法：tests/chain/<文件>.py::<用例名>）"]
        out: list[str] = []
        for rel_path, test_name in declared:
            reason = selector_covered(rel_path, test_name)
            if reason:
                out.append(f"{prefix}的用例指不到：{reason}")
        if not JUSTIFICATION_RE.search(still):
            out.append(f"{prefix}没写删除去向（卡片号 P\\d+-\\d+ 或台账号 C\\d+）")
        return out

    if not JUSTIFICATION_RE.search(still):
        return [f"{prefix}既不是「对拍保留」也不是「未对拍保留」，也没写去向: {still}"]
    return []


def main() -> int:
    errors = check()
    for e in errors:
        print(f"[ownership] 违反：{e}")
    if errors:
        print(f"[ownership] 未通过（{len(errors)} 条）。真相源：Go 路由注册、backend.app 路由表、tests/chain 用例。")
        return 1
    print(f"[ownership] 通过：{len(table_rows())} 行归属与三个真相源一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
