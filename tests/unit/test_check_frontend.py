"""前端结构机检的负向用例（`docs/rules/10-frontend-structure.md` §4 FE-c）。

正向只有一条：仓库现状必须通过。更重要的是**每条规则都能被抓到**——不红的门禁只是装饰。
每条负向用例都配一条对应的正向，用来证明规则没有顺手误伤注释与合法例外。
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("check_frontend", _ROOT / "scripts" / "check_frontend.py")
assert _spec and _spec.loader
cf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cf)

_NAV_KEYS = {"newChat", "history", "settings"}
_DEPS = {"vue", "vue-i18n", "marked"}


def check(rel: str, text: str, *, dto_names=(), nav_keys=_NAV_KEYS, all_deps=_DEPS) -> list[str]:
    return cf.check_source(rel, text, dto_names=dto_names, nav_keys=nav_keys, all_deps=all_deps)


def codes(problems: list[str]) -> set[str]:
    """取违规前缀（R1 / R5 / 依赖方向 / 依赖未声明），便于断言命中了哪条规则。"""
    return {p.split(" ")[0] for p in problems}


def test_repo_current_state_passes():
    assert cf.run() == []


# R1 请求出口唯一
def test_fetch_outside_http_layer_is_caught():
    assert "R1" in codes(check("components/ChatView.vue", 'const res = await fetch("/api/v1/x")\n'))


def test_fetch_mentioned_in_comment_is_not_caught():
    assert check("components/ChatView.vue", "// 以前这里直接 fetch(...)，现在走 composable\n") == []


# R2 登录态持久化唯一所有者
def test_localstorage_outside_token_owner_is_caught():
    assert "R2" in codes(check("composables/useAuth.ts", 'localStorage.getItem("accessToken")\n'))


def test_localstorage_in_allowed_files_passes():
    assert check("api/token.ts", 'localStorage.setItem("accessToken", t)\n') == []


# R3 状态层不认识 DOM 与对话框
def test_dom_call_in_composable_is_caught():
    assert "R3" in codes(check("composables/useChat.ts", 'document.getElementById("box")\n'))


def test_alert_in_view_layer_is_allowed():
    assert check("components/ChatView.vue", 'window.scrollTo(0, 1)\n') == []


# R4 反应式状态必须声明在模块作用域
def test_state_declared_inside_use_function_is_caught():
    text = 'export function useFoo() {\n  const n = ref(0)\n  return { n }\n}\n'
    assert "R4" in codes(check("composables/useFoo.ts", text))


def test_module_scope_state_passes():
    text = 'const n = ref(0)\nexport function useFoo() {\n  return { n }\n}\n'
    assert check("composables/useFoo.ts", text) == []


# R5 JSON 解析只有一个地方
def test_response_json_parse_outside_http_layer_is_caught():
    assert "R5" in codes(check("api/client.ts", "const data = await res.json()\n"))


# R6 DTO 不得重复声明
def test_duplicate_dto_declaration_is_caught():
    text = 'export interface SessionInfo {\n  id: string\n}\n'
    assert "R6" in codes(check("composables/useSessions.ts", text, dto_names={"SessionInfo"}))


def test_same_name_in_types_file_is_the_owner():
    text = 'export interface SessionInfo {\n  id: string\n}\n'
    assert check("api/types.ts", text, dto_names={"SessionInfo"}) == []


# R7 事件只走类型化总线
def test_raw_window_event_bus_is_caught():
    assert "R7" in codes(check("App.vue", 'window.addEventListener("auth-failed", handler)\n'))


def test_typed_bus_usage_is_not_caught():
    assert check("App.vue", 'onAppEvent("auth-expired", handleLogout)\n') == []


# R8 禁止 any
def test_any_is_caught():
    assert "R8" in codes(check("composables/useChat.ts", "const payload: any = {}\n"))


def test_any_in_declared_exception_passes():
    assert check("env.d.ts", "const component: DefineComponent<{}, {}, any>\n") == []


# R9 展示文案必须走 i18n 键
def test_hardcoded_chinese_label_is_caught():
    assert "R9" in codes(check("components/SettingsView.vue", 'const text = "正在上传…"\n'))


def test_chinese_comment_is_not_caught():
    assert check("components/SettingsView.vue", "// 正在上传……这类中文注释是本仓库的书写约定\n") == []


def test_i18n_dir_may_hold_display_text():
    assert check("i18n/messages.ts", 'export const zh = { hi: "你好" }\n') == []


# R10 视图状态必须是 NavKey 成员
def test_nav_value_outside_enum_is_caught():
    assert "R10" in codes(check("App.vue", 'activeNav.value = "documents"\n'))


def test_nav_typed_as_string_is_caught():
    assert "R10" in codes(check("components/Sidebar.vue", "defineProps<{ activeNav: string }>()\n"))


def test_declared_nav_value_passes():
    assert check("App.vue", 'activeNav.value = "history"\n') == []


# 依赖方向与依赖声明
def test_view_layer_importing_request_module_is_caught():
    text = 'import { request } from "../api/http"\n'
    assert any("依赖方向" in p for p in check("components/ChatView.vue", text))


def test_composable_importing_request_module_passes():
    assert check("composables/useChat.ts", 'import * as api from "../api/client"\n') == []


def test_undeclared_package_import_is_caught():
    text = 'import axios from "axios"\n'
    assert any("依赖未声明" in p for p in check("composables/useChat.ts", text))


def test_relative_import_is_not_treated_as_dependency():
    assert cf.imported_packages('import { BASE } from "./http"\nimport { t } from "@/i18n"\n') == set()


def test_dead_runtime_dependency_is_caught():
    found = cf.check_runtime_deps_are_used(cf.SRC, {"marked", "definitely-not-imported"})
    assert [p for p in found if "definitely-not-imported" in p]
    assert not [p for p in found if "marked" in p]


# 词法切分：行号与列位保持不变，规则才谈得上可定位
def test_comment_blanking_preserves_line_numbers():
    text = 'const a = 1\n// fetch(x)\nconst b = fetch("y")\n'
    blanked = cf.code_of(text)
    assert len(blanked) == len(text)
    assert blanked.count("\n") == text.count("\n")
    assert "fetch" not in blanked.splitlines()[1]
    assert cf.FETCH_RE.search(blanked.splitlines()[2])
    assert cf.text_of(text).splitlines()[1].strip() == ""
    assert 'fetch("y")' in cf.text_of(text).splitlines()[2]
