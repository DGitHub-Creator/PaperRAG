"""P0-4 契约机检的负向用例（09 §0 X3）。

正向只有一条：仓库里的 contracts/ 必须自洽。更重要的是**每条规则都能被抓到**——
门禁如果不红，就只是装饰。契约一律从仓库复制进 tmp 后局部篡改，绝不改动真相源。
"""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_contracts", _ROOT / "scripts" / "check_contracts.py")
assert _spec and _spec.loader
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


@pytest.fixture()
def contracts(tmp_path, monkeypatch):
    """把仓库契约复制进 tmp 并让脚本指向它；用例结束后自动还原。"""
    dst = tmp_path / "contracts"
    shutil.copytree(_ROOT / "contracts", dst)
    monkeypatch.setattr(cc, "CONTRACTS", dst)
    return dst


def run_openapi(contracts_dir: Path, mutate) -> list[str]:
    rewrite(contracts_dir / "openapi.yaml", *mutate)
    errors: list[str] = []
    cc.check_openapi(errors)
    return errors


def rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"锚点不存在，篡改无效：{old}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def make_frontend(base: Path, body: str) -> Path:
    src = base / "fe" / "composables"
    src.mkdir(parents=True, exist_ok=True)
    (src / "useDemo.ts").write_text(body, encoding="utf-8")
    return base / "fe"


def test_repo_contracts_are_self_consistent(monkeypatch):
    """真相源必须绿；这条就是 X3 的 mock 级证据。"""
    monkeypatch.setattr(cc, "CONTRACTS", _ROOT / "contracts")
    monkeypatch.setattr(cc, "FRONTEND_SRC", _ROOT / "frontend" / "src")
    errors: list[str] = []
    surface, doc = cc.check_openapi(errors)
    schema = cc.check_schema(errors)
    cc.check_error_codes(errors, schema)
    cc.check_acl(errors)
    cc.check_trace_projection(errors, doc)
    cc.check_trace_header(errors, doc)
    cc.check_surface(errors, surface)
    assert errors == []
    # 16 条前端在用 + 5 条探针（01 §3 与 X3 的口径；2026-10-14 新增改密码与偏好两条前端在用的面，13→16）
    assert len(surface) == 21


def test_dangling_ref_is_caught(contracts):
    errors = run_openapi(contracts, ('- $ref: "#/components/schemas/StreamDoneEvent"', '- $ref: "#/components/schemas/StreamGhostEvent"'))
    assert any("StreamGhostEvent" in e for e in errors)


@pytest.mark.parametrize("role", [
    {"type": "string", "enum": ["user", "admin"], "nullable": True, "default": "user"},
    {"type": "string", "nullable": False, "default": "user"},
    {"type": "string", "nullable": True, "default": "admin"},
])
def test_register_role_cannot_drift_from_actual_request_model(contracts, role):
    path = contracts / "openapi.yaml"
    doc = cc.yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["components"]["schemas"]["RegisterRequest"]["properties"]["role"] = role
    path.write_text(cc.yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    errors = []
    cc.check_openapi(errors)
    assert any("RegisterRequest.role" in error for error in errors)


def test_operation_needs_success_response(contracts):
    me = (
        "      responses:\n"
        '        "200":\n'
        "          description: 成功\n"
        "          content:\n"
        "            application/json:\n"
        "              schema:\n"
        '                $ref: "#/components/schemas/CurrentUserResponse"'
    )
    errors = run_openapi(contracts, (me, '      responses:\n        "401":\n          $ref: "#/components/responses/Unauthorized"'))
    assert any("没有成功响应" in e for e in errors)


def test_unknown_security_scheme_is_caught(contracts):
    errors = run_openapi(contracts, ("  - bearerAuth: []", "  - cookieAuth: []"))
    assert any("未定义的安全方案" in e for e in errors)


def test_duplicate_operation_id_is_caught(contracts):
    errors = run_openapi(contracts, ("      operationId: me", "      operationId: login"))
    assert any("operationId 重复" in e for e in errors)


def test_error_code_enum_must_match_markdown(contracts):
    path = contracts / "ai-execution.schema.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["$defs"]["ErrorCode"]["enum"].remove("CANCELLED")
    doc["$defs"]["ErrorCode"]["enum"].append("MADE_UP_CODE")
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    errors: list[str] = []
    schema = cc.check_schema(errors)
    cc.check_error_codes(errors, schema)
    assert any("schema 缺 CANCELLED" in e for e in errors)
    assert any("schema 多出 MADE_UP_CODE" in e for e in errors)


def test_registered_task_type_must_be_in_enum(contracts):
    rewrite(contracts / "ai-execution.schema.json", '["PARSE_PAPER", "INDEX_PAPER"]', '["WRITE_DIRECTLY"]')
    errors: list[str] = []
    cc.check_schema(errors)
    assert any("不在枚举内：WRITE_DIRECTLY" in e for e in errors)


def test_retryable_must_be_boolean_literal(contracts):
    rewrite(contracts / "error-codes.md", "| `MODEL_TIMEOUT` | true | 504 |", "| `MODEL_TIMEOUT` | 是 | 504 |")
    errors: list[str] = []
    cc.check_error_codes(errors, cc.check_schema(errors))
    assert any("MODEL_TIMEOUT 的 retryable" in e for e in errors)


def test_acl_double_write_needs_transition(contracts):
    rewrite(contracts / "table-acl.md", "| `chat_messages` | W | X | - |", "| `chat_messages` | W | W | - |")
    errors: list[str] = []
    cc.check_acl(errors)
    assert any("chat_messages 双写但没有标过渡期" in e for e in errors)


@pytest.mark.parametrize("old,new", [
    ("[planned] Go 是文献实体权威", "[present] Go 是文献实体权威"),
    ("[present] Python 独占", "[planned] Python 独占"),
])
def test_acl_presence_must_match_migrations(contracts, old, new):
    rewrite(contracts / "table-acl.md", old, new)
    errors = []
    cc.check_acl(errors)
    assert any("存在性应标为" in error for error in errors)


def test_scheduler_tables_must_be_python_denied(contracts):
    rewrite(contracts / "table-acl.md", "| `research_tasks` | W | X | - |", "| `research_tasks` | W | R | - |")
    errors: list[str] = []
    cc.check_acl(errors)
    assert any("research_tasks 属 L1 调度域" in e for e in errors)


def test_ai_executions_must_be_python_owned(contracts):
    rewrite(contracts / "table-acl.md", "| `ai_executions` | R | W | - |", "| `ai_executions` | W | W | - |")
    errors: list[str] = []
    cc.check_acl(errors)
    assert any("ai_executions 必须是 go=R python=W" in e for e in errors)


def test_python_writable_table_cap(contracts):
    rewrite(contracts / "table-acl.md", "| `users` | W | R | - |", "| `users` | W | W | until-A0 |")
    errors: list[str] = []
    cc.check_acl(errors)
    assert any("Python 可写表超过 2 张" in e for e in errors)


def test_normalization_of_templated_paths():
    assert cc.normalize_path("${BASE}/documents/upload/async") == "/api/v1/documents/upload/async"
    assert cc.normalize_path("/sessions/${encodeURIComponent(sessionId)}") == "/api/v1/sessions/{}"
    assert cc.normalize_path("/api/v1/ws/chat?token=${t}") == "/api/v1/ws/chat"
    assert cc.normalize_path("/auth/me") == "/api/v1/auth/me"


def test_method_comes_from_the_call_statement(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cc,
        "FRONTEND_SRC",
        make_frontend(tmp_path, 'request<SessionDeleteResponse>(`/sessions/${sid}`, { method: "DELETE" })\n'),
    )
    calls = cc.extract_frontend_calls(cc.FRONTEND_SRC)
    assert calls == {("delete", "/api/v1/sessions/{}")}


def test_generic_free_call_defaults_to_get(tmp_path, monkeypatch):
    """`request<T>(...)` 的泛型参数不能被当成路径的一部分——真实 client.ts 全是这个形状。"""
    monkeypatch.setattr(
        cc,
        "FRONTEND_SRC",
        make_frontend(tmp_path, 'return request<CurrentUserResponse>("/auth/me")\n'),
    )
    assert cc.extract_frontend_calls(cc.FRONTEND_SRC) == {("get", "/api/v1/auth/me")}


def test_stream_and_upload_helpers_are_recognised(tmp_path, monkeypatch):
    body = (
        'const r = await openStream("/chat/stream", { method: "POST", body: input, signal })\n'
        'return uploadFile<JobStartResponse>("/documents/upload/async", file, { method: "POST" })\n'
    )
    monkeypatch.setattr(cc, "FRONTEND_SRC", make_frontend(tmp_path, body))
    assert cc.extract_frontend_calls(cc.FRONTEND_SRC) == {
        ("post", "/api/v1/chat/stream"),
        ("post", "/api/v1/documents/upload/async"),
    }


def test_frontend_call_missing_from_contract(contracts, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "FRONTEND_SRC", make_frontend(tmp_path, 'request("/ghost/endpoint")\n'))
    errors: list[str] = []
    surface, _ = cc.check_openapi(errors)
    cc.check_surface(errors, surface)
    assert any("前端在调但契约没有：GET /api/v1/ghost/endpoint" in e for e in errors)


def test_contract_declares_uncalled_operation(contracts, tmp_path, monkeypatch):
    """契约只能覆盖前端真在用的：多进一条没人调的接口，就是 01 §3 那 12 条僵尸契约的复发。"""
    body = 'return request<AuthResponse>("/auth/login", { method: "POST" })\n'
    monkeypatch.setattr(cc, "FRONTEND_SRC", make_frontend(tmp_path, body))
    errors: list[str] = []
    surface, _ = cc.check_openapi(errors)
    cc.check_surface(errors, surface)
    assert any("契约声明了前端没在调的操作" in e for e in errors)


# ── rag_trace 投影面的三方核对（P1-1 会话详情接管）──────────────────────────
#
# 这一组的价值全在"每条都能红"：字段名、顺序、种类、必需性、嵌套指向、以及
# 表写法本身被改坏。任何一条抓不到，Go 与 Python 就会静默漂成两种形状（台账 C38 的同类）。

GO_TRACE = _ROOT / "server" / "internal" / "session" / "trace.go"


@pytest.fixture()
def projection(contracts, monkeypatch, tmp_path):
    """给核对函数一套可篡改的副本：契约来自 tmp，Go 字段表也复制到 tmp。"""
    go = tmp_path / "trace.go"
    shutil.copy(GO_TRACE, go)
    monkeypatch.setattr(cc, "GO_TRACE_FILE", go)

    def run(mutate_yaml=None, mutate_go=None):
        path = contracts / "openapi.yaml"
        if mutate_yaml:
            rewrite(path, *mutate_yaml)
        if mutate_go:
            text = go.read_text(encoding="utf-8")
            mutated = mutate_go(text)
            assert mutated != text, "Go 侧篡改没命中锚点，这条负向用例是假的"
            go.write_text(mutated, encoding="utf-8")
        doc = cc.yaml.safe_load(path.read_text(encoding="utf-8"))
        errors: list[str] = []
        cc.check_trace_projection(errors, doc)
        return errors

    return run


def test_trace_projection_three_sides_agree(projection):
    assert projection() == []


def test_contract_field_rename_is_caught(projection):
    errors = projection(('        tool_name:\n          type: string\n', '        tool_named:\n          type: string\n'))
    assert any("tool_name" in e and "RagTrace" in e for e in errors)


def test_contract_dropping_a_field_is_caught(projection):
    errors = projection(('        hypothetical_doc:\n          type: string\n          nullable: true\n', ''))
    assert any("hypothetical_doc" in e for e in errors)


def test_contract_required_set_drift_is_caught(projection):
    errors = projection(("      required: [tool_used, tool_name]", "      required: [tool_used]"))
    assert any("RagTrace.tool_name 三方不一致" in e for e in errors)


def test_missing_nested_schema_is_caught(projection):
    errors = projection(('    RetrievedChunk:\n', '    RetrievedGhost:\n'))
    assert any("RetrievedChunk" in e and "没有声明" in e for e in errors)


def test_go_dropping_a_field_is_caught(projection):
    errors = projection(mutate_go=lambda t: t.replace('\t\t{"grade_route", kindString, false, nil},\n', '', 1))
    assert any("grade_route" in e for e in errors)


def test_go_wrong_kind_is_caught(projection):
    errors = projection(mutate_go=lambda t: t.replace('{"candidate_k", kindInt, false, nil}', '{"candidate_k", kindString, false, nil}', 1))
    assert any("candidate_k 三方不一致" in e for e in errors)


def test_go_wrong_nested_target_is_caught(projection):
    errors = projection(mutate_go=lambda t: t.replace('{"citations", kindArray, false, citationSpec}', '{"citations", kindArray, false, chunkSpec}', 1))
    assert any("citations 三方不一致" in e for e in errors)


def test_unknown_kind_token_is_reported_not_silently_skipped(projection):
    errors = projection(mutate_go=lambda t: t.replace('{"query", kindString, false, nil}', '{"query", kindGhost, false, nil}', 1))
    assert any("kindGhost" in e for e in errors)


def test_field_table_style_change_fails_loudly(projection):
    """字段表改成别的写法时不能"抽到 0 个字段然后说一致"。"""
    import re

    strip = re.sub(r'^\s*\{"\w+", kind\w+, \w+, \w+\},\n', '', GO_TRACE.read_text(encoding="utf-8"), flags=re.M)
    errors = projection(mutate_go=lambda _t: strip)
    assert any("抽不到任何字段" in e for e in errors)


def test_projection_helpers_parse_the_real_tables():
    """自校验：Go 表确实被解析出来了，否则上面那些"红"可能只是因为解析器返回空。"""
    specs, problems = cc.parse_go_trace_specs(GO_TRACE.read_text(encoding="utf-8"))
    assert problems == []
    by_schema = cc.go_specs_by_schema(specs)
    assert set(by_schema) == {"RagTrace", "RetrievedChunk", "SourceReference", "CitationInfo", "UnsupportedClaim"}
    assert len(by_schema["RagTrace"]) == 39
    assert by_schema["RagTrace"][0] == ("tool_used", "bool", True, None)
    assert by_schema["RagTrace"][-3] == ("source_map", "map", False, "SourceReference")
    assert cc.python_trace_specs()["RagTrace"] == by_schema["RagTrace"]


# ── 追踪头 X-Trace-Id 的三方核对（台账 C38）─────────────────────────────────

GO_OBS = _ROOT / "server" / "internal" / "observability" / "trace.go"
PY_LOGGING = _ROOT / "backend" / "core" / "logging_config.py"


@pytest.fixture()
def trace_header(contracts, monkeypatch, tmp_path):
    """契约 + Go 常量 + Python 常量三份可篡改副本。"""
    go = tmp_path / "trace.go"
    shutil.copy(GO_OBS, go)
    py = tmp_path / "logging_config.py"
    shutil.copy(PY_LOGGING, py)
    monkeypatch.setattr(cc, "GO_OBSERVABILITY_FILE", go)
    monkeypatch.setattr(cc, "PY_LOGGING_FILE", py)

    def run(mutate_yaml=None, mutate_go=None, mutate_py=None):
        # 三个篡改器同形：都接收文件全文、返回改后的全文。接口不一致会让负向用例
        # 静默变成 TypeError——那种"红"根本不指向任何被检规则。
        path = contracts / "openapi.yaml"
        for file_, mutator in ((path, mutate_yaml), (go, mutate_go), (py, mutate_py)):
            if mutator:
                text = file_.read_text(encoding="utf-8")
                mutated = mutator(text)
                assert mutated != text, f"{file_.name} 的篡改没命中锚点，这条负向用例是假的"
                file_.write_text(mutated, encoding="utf-8")
        errors: list[str] = []
        cc.check_trace_header(errors, cc.yaml.safe_load(path.read_text(encoding="utf-8")))
        return errors

    return run


def test_trace_header_three_sides_agree(trace_header):
    assert trace_header() == []


def test_trace_header_rule_drift_is_caught(trace_header):
    errors = trace_header(mutate_go=lambda t: t.replace("{1,128}", "{1,64}", 1))
    assert any("接受集合三方不一致" in e and "Go" in e for e in errors)


def test_trace_header_name_drift_is_caught(trace_header):
    errors = trace_header(mutate_py=lambda t: t.replace('TRACE_ID_HEADER = "X-Trace-Id"', 'TRACE_ID_HEADER = "X-Request-Id"', 1))
    assert any("头名三方不一致" in e for e in errors)


def test_missing_trace_param_declaration_is_caught(trace_header):
    """契约里删掉声明就等于回到"两端代码私下约定"——正是 C38 登记的原始缺陷。"""
    errors = trace_header(
        mutate_yaml=lambda t: t.replace("    TraceId:\n", "    TraceGhost:\n", 1)
    )
    assert any("缺 TraceId" in e for e in errors)


def test_contract_bounds_disagreeing_with_pattern_are_caught(trace_header):
    errors = trace_header(
        mutate_yaml=lambda t: t.replace("        maxLength: 128\n", "        maxLength: 256\n", 1)
    )
    assert any("minLength/maxLength" in e for e in errors)


def test_constant_removal_fails_loudly_not_silently(trace_header):
    """实现侧常量被改名/删除时，核对必须报"找不到"，不能当成一致通过。"""
    errors = trace_header(mutate_go=lambda t: t.replace("const TraceIDRule", "const TraceIDX", 1))
    assert any("找不到 TraceIDRule" in e for e in errors)


def test_trace_header_helpers_parse_the_real_sources():
    """自校验：两边确实都能从真实源码抽到常量，否则上面的红可能是解析器返回空。"""
    errors: list[str] = []
    go = GO_OBS.read_text(encoding="utf-8")
    assert cc._go_const(go, "TraceIDHeader", "trace.go", errors) == "X-Trace-Id"
    assert cc._go_const(go, "TraceIDRule", "trace.go", errors) == r"^[A-Za-z0-9._-]{1,128}$"
    py = PY_LOGGING.read_text(encoding="utf-8")
    assert cc._py_const(py, "TRACE_ID_HEADER", "logging_config.py", errors) == "X-Trace-Id"
    assert cc._py_const(py, "TRACE_ID_RULE", "logging_config.py", errors) == r"^[A-Za-z0-9._-]{1,128}$"
    assert errors == []
