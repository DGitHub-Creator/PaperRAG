"""契约目录机检（09-milestone-p0 P0-4 / X3）。

三件事：
  1. 契约内部自洽：`$ref` 全部可解析、operationId 唯一、错误码表与 JSON Schema 枚举一致、
     表写入矩阵不出现无过渡期的双写；
  2. 契约与前端实调集合一致：从 frontend/src 现场抽取，不维护第二份清单
     ——清单会腐烂，代码不会；
  3. 不伪装通过：任何一条不满足即 exit 1，并打印可定位的条目。

用法：uv run python scripts/check_contracts.py
依赖：PyYAML（openapi.yaml 是手写的 YAML；JSON 部分只用标准库）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("[contracts] 需要 PyYAML：请在 uv 环境里运行（uv run python scripts/check_contracts.py）")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
FRONTEND_SRC = ROOT / "frontend" / "src"

# 探针类接口允许出现在契约里而前端不调：它们由 compose healthcheck 与监控使用。
PROBE_PATHS = {
    ("get", "/health"),
    ("get", "/ready"),
    ("get", "/api/v1/health"),
    ("get", "/api/v1/ready"),
    ("get", "/metrics"),
}

METHOD_RE = re.compile(r"""method\s*:\s*["'](GET|POST|PUT|PATCH|DELETE)["']""", re.I)
# 请求层的三个出口就是前端实调集合的唯一来源（api/client.ts 集中路径字面量）：
# request/openStream/uploadFile 都吃 (path, { method, ... })，动词在同一对括号里找。
CALL_RE = re.compile(
    r"""(?:request|openStream|uploadFile|fetch)\s*(?:<[^<>()]*>)?\s*\(\s*"""
    r"""(?P<q>["`])(?P<path>(?:\\.|[^\\])*?)(?P=q)"""
)
XHR_RE = re.compile(r"""\.open\s*\(\s*["'](?P<method>GET|POST|PUT|PATCH|DELETE)["']\s*,\s*(?P<q>["`])(?P<path>(?:\\.|[^\\])*?)(?P=q)""")
WS_RE = re.compile(r"(?P<path>/api/v1/ws/[A-Za-z0-9_/-]+|/ws/[A-Za-z0-9_/-]+)")
TEMPLATE_RE = re.compile(r"""\$\{[^}]*\}""")
TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*$")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

WRITE_TOKENS = {"W", "R", "X"}


def normalize_path(raw: str) -> str:
    """把前端字面量转成与 openapi 路径可比的形状。

    `${BASE}` 丢掉并补回 `/api/v1` 前缀（BASE 常量就是它，见 api/http.ts）；
    `${encodeURIComponent(jobId)}` → `{}`（一个路径段占位）；查询串剥掉
    （WS 的 `?token=` 不是路径的一部分）。
    """
    p = raw.replace("${BASE}", "").replace("{BASE}", "")
    p = TEMPLATE_RE.sub("{}", p)
    p = p.split("?")[0]
    if not p.startswith("/"):
        p = "/" + p
    return p if p.startswith("/api/v1") else "/api/v1" + p


def match_statement(text: str, open_paren_at: int) -> str:
    """从调用的左括号起取到配平的右括号，用于在同一条语句里找 method:。"""
    depth = 0
    for i in range(open_paren_at, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_at : i + 1]
    return text[open_paren_at:]


def extract_frontend_calls(src_dir: Path) -> set[tuple[str, str]]:
    calls: set[tuple[str, str]] = set()
    for file in sorted(src_dir.rglob("*")):
        if file.suffix not in {".ts", ".js", ".vue"} or not file.is_file():
            continue
        text = file.read_text(encoding="utf-8")
        for m in CALL_RE.finditer(text):
            stmt = match_statement(text, text.index("(", m.start()))
            mm = METHOD_RE.search(stmt)
            method = (mm.group(1) if mm else "GET").lower()
            calls.add((method, normalize_path(m.group("path"))))
        for m in XHR_RE.finditer(text):
            calls.add((m.group("method").lower(), normalize_path(m.group("path"))))
        for m in WS_RE.finditer(text):
            # WebSocket 在 OpenAPI 里没有正式表达，契约以「GET + 101」占位（见 openapi.yaml）。
            calls.add(("get", normalize_path(m.group("path"))))
    return calls


def path_matches(contract_path: str, called_path: str) -> bool:
    """契约里的 {param} 段匹配被调路径的任意单段（前端用 encodeURIComponent 填）。"""
    a = contract_path.strip("/").split("/")
    b = called_path.strip("/").split("/")
    if len(a) != len(b):
        return False
    for seg_a, seg_b in zip(a, b):
        if seg_a.startswith("{") and seg_a.endswith("}"):
            continue
        if seg_a != seg_b:
            return False
    return True


def iter_refs(node, prefix="#/"):
    """深度遍历，产出所有 $ref 字符串。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from iter_refs(value, prefix)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item, prefix)


def resolve_pointer(doc, ref: str):
    """解析 #/a/b/c 形式的 JSON Pointer。"""
    if not ref.startswith("#/"):
        return None
    cur = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def parse_md_tables(text: str) -> dict[str, list[list[str]]]:
    """按「表头上一个非空行」当锚点收集 markdown 表格；键是表头首格内容。"""
    tables: dict[str, list[list[str]]] = {}
    rows: list[list[str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue  # 分隔行
            if header is None:
                header = cells
                rows = []
                continue
            rows.append(cells)
        else:
            if header and rows:
                tables[header[0]] = rows
            header, rows = None, []
    if header and rows:
        tables[header[0]] = rows
    return tables


def check_openapi(errors: list[str]) -> tuple[set[tuple[str, str]], dict]:
    path = CONTRACTS / "openapi.yaml"
    if not path.is_file():
        errors.append(f"缺文件：{path.relative_to(ROOT)}")
        return set(), {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        errors.append("openapi.yaml 不是映射")
        return set(), {}

    surface: set[tuple[str, str]] = set()
    ops: list[str] = []
    for p, item in (doc.get("paths") or {}).items():
        if not p.startswith("/"):
            errors.append(f"openapi 路径必须以 / 开头：{p}")
            continue
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                continue
            if not isinstance(op, dict):
                errors.append(f"openapi {method.upper()} {p} 的 operation 不是映射")
                continue
            surface.add((method, p))
            op_id = op.get("operationId")
            if not op_id:
                errors.append(f"openapi {method.upper()} {p} 缺 operationId")
            else:
                ops.append(op_id)
            codes = set((op.get("responses") or {}).keys())
            if not any(c.startswith("2") or c == "101" for c in codes):
                errors.append(f"openapi {method.upper()} {p} 没有成功响应")
            public = op.get("security") == []
            if not public and "401" not in codes:
                errors.append(f"openapi {method.upper()} {p} 需鉴权却没声明 401")

    dupes = {o for o in ops if ops.count(o) > 1}
    if dupes:
        errors.append(f"operationId 重复：{'、'.join(sorted(dupes))}")

    for ref in iter_refs(doc):
        if resolve_pointer(doc, ref) is None:
            errors.append(f"openapi $ref 无法解析：{ref}")

    schemes = set((doc.get("components") or {}).get("securitySchemes") or {})
    declared = [doc.get("security")] + [op.get("security") for _, op in _iter_ops(doc)]
    scopes = {name for entry in declared if entry for req in entry for name in req}
    unknown = scopes - schemes
    if unknown:
        errors.append(f"security 引用了未定义的安全方案：{'、'.join(sorted(unknown))}")
    return surface, doc


def _iter_ops(doc: dict):
    for p, item in (doc.get("paths") or {}).items():
        for method, op in (item or {}).items():
            if isinstance(op, dict) and method in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                yield f"{method.upper()} {p}", op


def check_error_codes(errors: list[str], schema: dict) -> None:
    path = CONTRACTS / "error-codes.md"
    if not path.is_file():
        errors.append(f"缺文件：{path.relative_to(ROOT)}")
        return
    tables = parse_md_tables(path.read_text(encoding="utf-8"))
    rows = tables.get("code")
    if not rows:
        errors.append("error-codes.md 没找到以 `code` 为表首的内部错误码表")
        return
    codes: set[str] = set()
    for row in rows:
        if len(row) < 3:
            errors.append(f"error-codes.md 行缺列：{row}")
            continue
        code, retryable, http = row[0], row[1], row[2]
        code = code.strip("`")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", code):
            errors.append(f"错误码必须是大写下划线形式：{code}")
        if retryable not in {"true", "false"}:
            errors.append(f"{code} 的 retryable 必须是 true/false，实为 {retryable!r}")
        if not (http.isdigit() and 100 <= int(http) <= 599):
            errors.append(f"{code} 的 http 映射必须是状态码，实为 {http!r}")
        if code in codes:
            errors.append(f"错误码重复：{code}")
        codes.add(code)

    enum = ((schema.get("$defs") or {}).get("ErrorCode") or {}).get("enum") or []
    if set(enum) != codes:
        missing = codes - set(enum)
        extra = set(enum) - codes
        parts = []
        if missing:
            parts.append(f"schema 缺 {'、'.join(sorted(missing))}")
        if extra:
            parts.append(f"schema 多出 {'、'.join(sorted(extra))}")
        errors.append(f"错误码枚举与 error-codes.md 不一致：{'；'.join(parts)}")


def check_schema(errors: list[str]) -> dict:
    path = CONTRACTS / "ai-execution.schema.json"
    if not path.is_file():
        errors.append(f"缺文件：{path.relative_to(ROOT)}")
        return {}
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"ai-execution.schema.json 不是合法 JSON：{exc}")
        return {}
    for ref in iter_refs(schema):
        if resolve_pointer(schema, ref) is None:
            errors.append(f"schema $ref 无法解析：{ref}")
    task_types = ((schema.get("$defs") or {}).get("TaskType") or {}).get("enum") or []
    registered = schema.get("x-p0-registered-task-types") or []
    unknown = [t for t in registered if t not in task_types]
    if unknown:
        errors.append(f"P0 注册的 task_type 不在枚举内：{'、'.join(unknown)}")
    for ep in schema.get("x-endpoints") or []:
        if "/internal/v1/ai/" not in ep:
            errors.append(f"内部端点必须挂 /internal/v1/ai/：{ep}")
    return schema


def check_acl(errors: list[str]) -> None:
    path = CONTRACTS / "table-acl.md"
    if not path.is_file():
        errors.append(f"缺文件：{path.relative_to(ROOT)}")
        return
    rows = parse_md_tables(path.read_text(encoding="utf-8")).get("table")
    if not rows:
        errors.append("table-acl.md 没找到以 `table` 为表首的矩阵")
        return
    python_writes: list[str] = []
    for row in rows:
        if len(row) < 4:
            errors.append(f"table-acl.md 行缺列：{row}")
            continue
        table, go, py, transition = row[0], row[1], row[2], row[3]
        table = table.strip("`")
        if not SNAKE_RE.match(table):
            errors.append(f"表名必须是 snake_case：{table}")
        if go not in WRITE_TOKENS or py not in WRITE_TOKENS:
            errors.append(f"{table} 的写权限标记必须是 W/R/X，实为 go={go!r} python={py!r}")
        writes = [side for side, tok in (("go", go), ("python", py)) if tok == "W"]
        if len(writes) == 2 and transition.strip() in {"", "-"}:
            errors.append(f"{table} 双写但没有标过渡期：{writes}")
        if py == "W":
            python_writes.append(table)
        if table == "ai_executions" and (go, py) != ("R", "W"):
            errors.append("ai_executions 必须是 go=R python=W（Python 独占写，02 §6.2）")
        if (table.startswith("research_") or table.endswith("_events")) and py != "X":
            errors.append(f"{table} 属 L1 调度域，Python 侧必须是 X（Go 是唯一调度中心）")
    if len(python_writes) > 2:
        errors.append(f"Python 可写表超过 2 张：{'、'.join(python_writes)}")


def check_surface(errors: list[str], surface: set[tuple[str, str]]) -> None:
    if not surface:
        return
    if not FRONTEND_SRC.is_dir():
        errors.append(f"找不到前端源码目录，无法核对实调集合：{FRONTEND_SRC}")
        return
    called = extract_frontend_calls(FRONTEND_SRC)
    if not called:
        errors.append("前端实调集合抽取为空，检查抽取规则是否还适配 frontend/src 的写法")
        return

    for method, path in sorted(called):
        if not any(p == path for _, p in surface):
            if not any(path_matches(cp, path) for _, cp in surface):
                errors.append(f"前端在调但契约没有：{method.upper()} {path}")

    for method, path in sorted(surface):
        if (method, path) in PROBE_PATHS:
            continue
        if not any(m == method and path_matches(p, path) for m, p in called):
            errors.append(f"契约声明了前端没在调的操作：{method.upper()} {path}（要么删除，要么进 PROBE_PATHS）")


def main() -> int:
    errors: list[str] = []
    surface, _ = check_openapi(errors)
    schema = check_schema(errors)
    check_error_codes(errors, schema)
    check_acl(errors)
    check_surface(errors, surface)

    if errors:
        print(f"[contracts] FAIL：{len(errors)} 项")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"[contracts] OK：{len(surface)} 个对浏览器操作 + 内部执行面 + 错误码表 + 写入矩阵自洽")
    return 0


if __name__ == "__main__":
    sys.exit(main())
