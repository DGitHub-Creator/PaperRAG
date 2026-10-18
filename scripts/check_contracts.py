"""契约目录机检（09-milestone-p0 P0-4 / X3）。

三件事：
  1. 契约内部自洽：`$ref` 全部可解析、operationId 唯一、错误码表与 JSON Schema 枚举一致、
     表写入矩阵不出现无过渡期的双写、rag_trace 投影面在 openapi/Python/Go 三处逐字段一致；
  2. 契约与前端实调集合一致：从 frontend/src 现场抽取，不维护第二份清单
     ——清单会腐烂，代码不会；
  3. 不伪装通过：任何一条不满足即 exit 1，并打印可定位的条目。

用法：uv run python scripts/check_contracts.py
依赖：PyYAML 与项目 Pydantic DTO；JSON 部分只用标准库。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import get_args, get_origin

try:
    import yaml
except ImportError:  # pragma: no cover
    print("[contracts] 需要 PyYAML：请在 uv 环境里运行（uv run python scripts/check_contracts.py）")
    raise SystemExit(2) from None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
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
    for seg_a, seg_b in zip(a, b, strict=True):
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
    # 本字段曾比实现更严格，导致照契约重写后拒绝既有客户端；从实际 DTO 提取值域。
    from backend.schemas.auth import RegisterRequest

    declared_role = ((doc.get("components") or {}).get("schemas") or {}).get("RegisterRequest", {}).get("properties", {}).get("role", {})
    model_role = RegisterRequest.model_json_schema()["properties"]["role"]
    branches = model_role.get("anyOf", [model_role])
    non_null = [branch for branch in branches if branch.get("type") != "null"]
    expected_role = dict(non_null[0]) if len(non_null) == 1 else {"anyOf": non_null}
    if len(non_null) < len(branches):
        expected_role["nullable"] = True
    if "default" in model_role:
        expected_role["default"] = model_role["default"]
    actual_role = {key: value for key, value in declared_role.items() if key not in {"title", "description"}}
    expected_role.pop("title", None)
    if actual_role != expected_role:
        errors.append("RegisterRequest.role 的类型/可空性/默认值与 Python DTO 不一致")
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
    from scripts.audit_schema import parse_ddl_columns

    built = set()
    for migration in (ROOT / "server/migrations").glob("*.up.sql"):
        built.update(parse_ddl_columns(migration.read_text(encoding="utf-8")))
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
        state = "present" if table in built else "planned"
        if len(row) < 5 or not row[4].startswith(f"[{state}]"):
            errors.append(f"{table} 存在性应标为 [{state}]，必须与迁移一致")
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


# ── rag_trace 投影面的三方一致（P1-1 会话详情接管，台账 C38 的同类问题）────────────
#
# 为什么单独一条机检：`chat_messages.rag_trace` 有 39 个声明字段，Go 原生接管后它就是
# 第二个实现方。字段名、顺序、种类只要有一处漂开，浏览器就会看到两种形状，而漂开是**静默**的
# ——读侧不报错，只是键少了或名字变了。这类"看不见的形状"靠人对账守不住，必须有机器天天核。
#
# 三方 = openapi.yaml 的 properties（权威声明）
#       + backend/schemas/schemas.py 的 pydantic 模型（当前写方与读方）
#       + server/internal/session/trace.go 的字段表（Go 读侧投影）。
# 消息信封那一层（type/content/timestamp/rag_trace 四个键）不在这里查：
# 它只有四个键且两侧都是手写结构体，漂开会直接让 tests/chain/test_go_read_session_detail.py 红。

GO_TRACE_FILE = ROOT / "server" / "internal" / "session" / "trace.go"

GO_SPEC_VAR_RE = re.compile(r"^var (\w+) = &traceSpec\{")
GO_SPEC_NAME_RE = re.compile(r'^\s*name: "([A-Za-z]+)",')
GO_FIELD_RE = re.compile(r'^\s*\{"([a-z0-9_]+)", (kind\w+), (true|false), (nil|\w+)\},')
GO_KINDS = {
    "kindString": "string",
    "kindBool": "bool",
    "kindInt": "int",
    "kindFloat": "float",
    "kindStrInt": "str|int",
    "kindObject": "object",
    "kindArray": "array",
    "kindMap": "map",
}

TRACE_ROOT_MODEL = "RagTrace"


def parse_go_trace_specs(text: str) -> tuple[dict[str, list[tuple]], list[str]]:
    """从 Go 的字段表抽 `schema 名 → [(字段, 种类, 必需, 嵌套 schema)]`。

    按行解析而不是 import：Go 侧没有可导入的元数据，而这份表就是它的声明本身。
    表写法有约定（positional 字面量、一行一个字段），改了写法这里会直接报"抽不到字段"。
    """
    problems: list[str] = []
    specs: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        var = GO_SPEC_VAR_RE.match(line)
        if var:
            current = var.group(1)
            specs[current] = {"schema": None, "fields": []}
            continue
        if current is None:
            continue
        name = GO_SPEC_NAME_RE.match(line)
        if name and specs[current]["schema"] is None:
            specs[current]["schema"] = name.group(1)
            continue
        field = GO_FIELD_RE.match(line)
        if not field:
            continue
        fname, kind, required, elem = field.groups()
        if kind not in GO_KINDS:
            problems.append(f"trace.go 里 {fname} 用了未知字段种类 {kind}，GO_KINDS 没登记它")
            continue
        specs[current]["fields"].append((fname, GO_KINDS[kind], required == "true", None if elem == "nil" else elem))
    for var, spec in specs.items():
        if spec["schema"] is None:
            problems.append(f"trace.go 的 {var} 没有 name: 行，三方核对认不出它是哪个 schema")
        if not spec["fields"]:
            problems.append(f"trace.go 的 {var} 抽不到任何字段，字段表写法变了？")
    return specs, problems


def go_specs_by_schema(specs: dict[str, dict]) -> dict[str, list[tuple]]:
    """把 `var 名 → 表` 换成 `schema 名 → 表`，并把嵌套引用从 var 名解析成 schema 名。"""
    var_to_schema = {var: spec["schema"] for var, spec in specs.items()}
    out: dict[str, list[tuple]] = {}
    for var, spec in specs.items():
        fields = []
        for fname, kind, required, elem in spec["fields"]:
            if elem is None:
                fields.append((fname, kind, required, None))
                continue
            if elem not in var_to_schema:
                fields.append((fname, kind, required, f"未定义的嵌套表 {elem}"))
                continue
            fields.append((fname, kind, required, var_to_schema[elem]))
        out[spec["schema"]] = fields
    return out


def python_trace_specs() -> dict[str, list[tuple]]:
    """从 pydantic 模型现场抽同一份表（含被嵌套引用的模型，顺着注释走）。"""
    from backend.schemas.schemas import RagTrace

    out: dict[str, list[tuple]] = {}
    queue = [RagTrace]
    while queue:
        model = queue.pop(0)
        if model.__name__ in out:
            continue
        fields = []
        for fname, info in model.model_fields.items():
            kind, nested = _annotation_kind(info.annotation)
            if nested is not None:
                if isinstance(nested, type) and hasattr(nested, "model_fields"):
                    queue.append(nested)
                else:
                    nested = None
            fields.append((fname, kind, info.is_required(), nested.__name__ if nested is not None else None))
        out[model.__name__] = fields
    return out


def _annotation_kind(ann):
    args = get_args(ann)
    if args and any(a is not type(None) for a in args):
        non_null = [a for a in args if a is not type(None)]
        if len(non_null) > 1:
            kinds = {a for a in non_null}
            if kinds == {str, int}:
                return "str|int", None
            return f"union{sorted(x.__name__ for x in kinds)}", None
        ann = non_null[0]
        args = get_args(ann)
    origin = get_origin(ann)
    if origin in (list, set, tuple):
        elem = args[0] if args else None
        return "array", elem
    if origin is dict:
        return "map", args[1] if len(args) > 1 else None
    if ann is bool:
        return "bool", None
    if ann is int:
        return "int", None
    if ann is float:
        return "float", None
    if ann is str:
        return "string", None
    if isinstance(ann, type) and hasattr(ann, "model_fields"):
        return "object", ann
    return f"未知注解 {ann}", None


def contract_trace_specs(doc: dict) -> dict[str, list[tuple]]:
    """openapi 里的声明：键序就是 properties 的书写顺序（PyYAML 保序）。

    找不到的 schema **不进结果**——少一侧就是"这一侧没声明"，比塞一张空表更容易指错方向：
    空表会让报文字说着"字段集不符"，而真相是整块 schema 被删了。
    """
    schemas = (doc.get("components") or {}).get("schemas") or {}
    out: dict[str, list[tuple]] = {}
    visited: set[str] = set()
    queue = [TRACE_ROOT_MODEL]
    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)
        node = schemas.get(name)
        if not isinstance(node, dict):
            continue
        required = set(node.get("required") or [])
        fields = []
        for key, prop in (node.get("properties") or {}).items():
            kind, ref = _openapi_kind(prop if isinstance(prop, dict) else {})
            if ref:
                queue.append(ref)
            fields.append((key, kind, key in required, ref))
        out[name] = fields
    return out


def _ref_name(node) -> str | None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            return ref.rsplit("/", 1)[-1]
    return None


def _openapi_kind(prop: dict) -> tuple[str, str | None]:
    branches = prop.get("oneOf") or prop.get("anyOf")
    if isinstance(branches, list) and branches:
        types = sorted({b.get("type") for b in branches if isinstance(b, dict)})
        if types == ["integer", "string"]:
            return "str|int", None
        return f"union{types}", None
    kind = prop.get("type")
    if kind == "boolean":
        return "bool", None
    if kind == "integer":
        return "int", None
    if kind == "number":
        return "float", None
    if kind == "string":
        return "string", None
    if kind == "array":
        return "array", _ref_name(prop.get("items"))
    if kind == "object":
        return "map", _ref_name(prop.get("additionalProperties"))
    return f"type:{kind}", None


def check_trace_projection(errors: list[str], doc: dict) -> None:
    """三方逐字段核对：名字、顺序、必需性、种类、嵌套指向。"""
    specs, problems = parse_go_trace_specs(GO_TRACE_FILE.read_text(encoding="utf-8"))
    errors.extend(problems)
    if problems:
        return
    sides = {
        "契约": contract_trace_specs(doc),
        "Python": python_trace_specs(),
        "Go": go_specs_by_schema(specs),
    }
    names = sorted(set().union(*(set(side) for side in sides.values())))
    if TRACE_ROOT_MODEL not in names:
        errors.append(f"三方核对找不到 {TRACE_ROOT_MODEL} 的声明，检查是否被改名")
        return
    for name in names:
        per_side = {label: side.get(name) for label, side in sides.items()}
        missing = [label for label, value in per_side.items() if value is None]
        if missing:
            errors.append(f"{name} 在 {'、'.join(missing)} 侧没有声明（三方必须都有，少一侧就是第二套真相）")
            continue
        fields = {label: [f[0] for f in value] for label, value in per_side.items()}
        for other in ("Python", "Go"):
            if fields["契约"] != fields[other]:
                errors.append(
                    f"{name} 的字段集/顺序与契约不符：{other} 侧缺 {sorted(set(fields['契约']) - set(fields[other]))}"
                    f"，多 {sorted(set(fields[other]) - set(fields['契约']))}（顺序不同也算不符）"
                )
        for index, (fname, kind, required, elem) in enumerate(per_side["契约"]):
            for label in ("Python", "Go"):
                other = per_side[label]
                if index >= len(other) or other[index][0] != fname:
                    continue  # 顺序已经单独报过，这里不再重复
                _, okind, orequired, oelem = other[index]
                if (okind, orequired, oelem) != (kind, required, elem):
                    errors.append(
                        f"{name}.{fname} 三方不一致：契约=({kind}, required={required}, 嵌套={elem}) "
                        f"{label}=({okind}, required={orequired}, 嵌套={oelem})"
                    )


# ── 追踪头契约的三方一致（台账 C38 的另一半：头名与接受集合）──────────────────
#
# 为什么也要机检：Go 与 Python 各有一份 `X-Trace-Id` 字面量和一份接受集合的写法，
# 三处（契约 / Go / Python）里任何一处改了边界而另两处没跟上，表现是**日志关联悄悄断掉**：
# 请求在 Go 侧被换成新 id，Python 又换成另一个，排障时两边看不出是同一个请求。

GO_OBSERVABILITY_FILE = ROOT / "server" / "internal" / "observability" / "trace.go"
PY_LOGGING_FILE = ROOT / "backend" / "core" / "logging_config.py"

GO_CONST_RE = r'const\s+{name}\s*=\s*`(?P<raw>[^`]*)`|const\s+{name}\s*=\s*"(?P<quo>[^"]*)"'
PY_CONST_RE = r'^{name}\s*=\s*r?"(?P<val>[^"]*)"'

TRACE_PARAM_NAME = "TraceId"


def _go_const(text: str, name: str, label: str, errors: list[str]) -> str | None:
    m = re.search(GO_CONST_RE.format(name=re.escape(name)), text, re.M)
    if not m:
        errors.append(f"{label} 里找不到 {name} 常量，三方核对无法判定")
        return None
    return m.group("raw") if m.group("raw") is not None else m.group("quo")


def _py_const(text: str, name: str, label: str, errors: list[str]) -> str | None:
    m = re.search(PY_CONST_RE.format(name=re.escape(name)), text, re.M)
    if not m:
        errors.append(f"{label} 里找不到 {name} 常量，三方核对无法判定")
        return None
    return m.group("val")


def check_trace_header(errors: list[str], doc: dict) -> None:
    param = ((doc.get("components") or {}).get("parameters") or {}).get(TRACE_PARAM_NAME)
    if not isinstance(param, dict):
        errors.append(f"契约的 components.parameters 缺 {TRACE_PARAM_NAME}：追踪头又变回代码里的私下约定了")
        return
    name = param.get("name")
    schema = param.get("schema") or {}
    pattern = schema.get("pattern")
    bounds = (schema.get("minLength"), schema.get("maxLength"))
    if param.get("in") != "header" or not name or not pattern:
        errors.append(f"{TRACE_PARAM_NAME} 必须是 in=header 且带 name/pattern，实得 in={param.get('in')} name={name}")
        return
    if bounds != (1, 128):
        errors.append(f"{TRACE_PARAM_NAME} 的 minLength/maxLength 应与 pattern 的 {{1,128}} 同一条口径，实得 {bounds}")

    go_header = _go_const(GO_OBSERVABILITY_FILE.read_text(encoding="utf-8"), "TraceIDHeader", "trace.go", errors)
    go_rule = _go_const(GO_OBSERVABILITY_FILE.read_text(encoding="utf-8"), "TraceIDRule", "trace.go", errors)
    py_text = PY_LOGGING_FILE.read_text(encoding="utf-8")
    py_header = _py_const(py_text, "TRACE_ID_HEADER", "logging_config.py", errors)
    py_rule = _py_const(py_text, "TRACE_ID_RULE", "logging_config.py", errors)

    for label, value in (("Go", go_header), ("Python", py_header)):
        if value is not None and value != name:
            errors.append(f"追踪头头名三方不一致：契约={name} {label}={value}")
    for label, value in (("Go", go_rule), ("Python", py_rule)):
        if value is not None and value != pattern:
            errors.append(f"追踪头接受集合三方不一致：契约 pattern={pattern} {label}={value}")
    if go_rule and py_rule and go_rule != py_rule:
        errors.append(f"Go 与 Python 的追踪头规则互不相同：{go_rule} vs {py_rule}")


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
    surface, doc = check_openapi(errors)
    schema = check_schema(errors)
    check_error_codes(errors, schema)
    check_acl(errors)
    check_trace_projection(errors, doc)
    check_trace_header(errors, doc)
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
