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
    surface, _ = cc.check_openapi(errors)
    schema = cc.check_schema(errors)
    cc.check_error_codes(errors, schema)
    cc.check_acl(errors)
    cc.check_surface(errors, surface)
    assert errors == []
    # 13 条前端在用 + 5 条探针（01 §3 与 X3 的口径）
    assert len(surface) == 18


def test_dangling_ref_is_caught(contracts):
    errors = run_openapi(contracts, ('- $ref: "#/components/schemas/StreamDoneEvent"', '- $ref: "#/components/schemas/StreamGhostEvent"'))
    assert any("StreamGhostEvent" in e for e in errors)


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
    monkeypatch.setattr(cc, "FRONTEND_SRC", make_frontend(tmp_path, 'authFetch(`/sessions/${sid}`, { method: "DELETE" })\n'))
    calls = cc.extract_frontend_calls(cc.FRONTEND_SRC)
    assert calls == {("delete", "/api/v1/sessions/{}")}


def test_frontend_call_missing_from_contract(contracts, tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "FRONTEND_SRC", make_frontend(tmp_path, 'authFetch("/ghost/endpoint")\n'))
    errors: list[str] = []
    surface, _ = cc.check_openapi(errors)
    cc.check_surface(errors, surface)
    assert any("前端在调但契约没有：GET /api/v1/ghost/endpoint" in e for e in errors)


def test_contract_declares_uncalled_operation(contracts, tmp_path, monkeypatch):
    """契约只能覆盖前端真在用的：多进一条没人调的接口，就是 01 §3 那 12 条僵尸契约的复发。"""
    monkeypatch.setattr(cc, "FRONTEND_SRC", make_frontend(tmp_path, 'authFetch("/auth/me")\napiFetch("/auth/login", { method: "POST" })\n'))
    errors: list[str] = []
    surface, _ = cc.check_openapi(errors)
    cc.check_surface(errors, surface)
    assert any("契约声明了前端没在调的操作" in e for e in errors)
