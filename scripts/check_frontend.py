"""前端结构机检（`docs/refactor/10` §3 的 R1–R11）。

为什么要有这个脚本：结构约定光写在文档里会腐烂，`npm run typecheck` 只保证类型不保证分层。
这里检查的是**形状**而不是类型：谁是唯一的请求出口、谁碰得到 localStorage、状态层里有没有
DOM 与对话框、DTO 是否在别处被重复声明。

实现取舍：用一个极简词法切分把源码分成 code / 注释 / 字符串 三类片段，规则只在对应类别上匹配。
理由有两条——注释一律中文（`08` §6），不该被"禁止硬编码文案"误伤；注释里会提到 `fetch`，
也不该被"唯一请求出口"误伤。正则字面量里的 `//` 这类极端情况不处理，代价是漏报而不是误报。

用法：
    uv run python scripts/check_frontend.py            # 检查 frontend/src
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"
PKG = FRONTEND / "package.json"

CODE = "code"
COMMENT = "comment"
STRING = "string"

# 各规则的例外文件（相对 frontend/src），必须是有意为之的例外并写清原因
LOCALSTORAGE_OK = {"api/token.ts", "i18n/index.ts"}
ANY_OK = {"env.d.ts", "i18n/index.ts"}
REQUEST_OK = {"api/http.ts"}
CJK_OK_PREFIX = "i18n/"

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
ANY_RE = re.compile(r"\bany\b")
FETCH_RE = re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b")
JSON_CALL_RE = re.compile(r"\.json\s*\(\s*\)")
LOCAL_STORAGE_RE = re.compile(r"\blocalStorage\b")
SIDEffects_RE = re.compile(r"\balert\s*\(|\bconfirm\s*\(|\bdocument\.|\bwindow\.")
RAW_EVENT_BUS_RE = re.compile(r"\bwindow\.addEventListener\b|\bdispatchEvent\s*\(|\bnew CustomEvent\b")
STATE_CREATOR_RE = re.compile(r"\b(?:ref|reactive)\s*[(<]")
EXPORT_USE_RE = re.compile(r"^export (?:function|const) use\w+", re.M)
DTO_DECL_RE = re.compile(r"^export (?:interface|type)\s+(\w+)", re.M)
IMPORT_FROM_RE = re.compile(r"""(?:from\s+|import\s+)["']([^"']+)["']""")
NAV_LITERAL_ASSIGN_RE = re.compile(r"""activeNav\.value\s*=\s*["'](\w+)["']""")
NAV_STRING_PROP_RE = re.compile(r"activeNav\s*:\s*string")
REQUEST_MODULE_IMPORT_RE = re.compile(r'''["']\.{1,2}/(?:[\w./-]*/)?api/(?:http|client)["']''')


def scan_segments(text: str) -> list[tuple[str, str]]:
    """把源码切成 (类别, 原文) 片段序列，顺序覆盖全文。"""
    segments: list[tuple[str, str]] = []
    buf: list[str] = []
    i = 0
    n = len(text)

    def flush(kind: str) -> None:
        nonlocal buf
        if buf:
            segments.append((kind, "".join(buf)))
            buf = []

    while i < n:
        ch = text[i]
        if text.startswith("//", i) or text.startswith("<!--", i):
            end = text.find("\n", i) if text.startswith("//", i) else text.find("-->", i)
            end = n if end == -1 else (end if text.startswith("//", i) else end + 3)
            flush(CODE)
            segments.append((COMMENT, text[i:end]))
            i = end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i)
            end = n if end == -1 else end + 2
            flush(CODE)
            segments.append((COMMENT, text[i:end]))
            i = end
            continue
        if ch in "\"'`":
            end = _string_end(text, i)
            flush(CODE)
            segments.append((STRING, text[i:end]))
            i = end
            continue
        buf.append(ch)
        i += 1
    flush(CODE)
    return segments


def _string_end(text: str, start: int) -> int:
    """返回字符串字面量结束位置（含结束引号）。"""
    quote = text[start]
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return len(text)


def code_of(text: str) -> str:
    """只保留代码片段（注释与字符串替换为等长空白，行号与列位置不变）。"""
    out: list[str] = []
    for kind, chunk in scan_segments(text):
        out.append(chunk if kind == CODE else re.sub(r"[^\n]", " ", chunk))
    return "".join(out)


def text_of(text: str) -> str:
    """只把注释换成等长空白，代码与字符串字面量原样保留；需要匹配字面量内容的规则用它。"""
    out: list[str] = []
    for kind, chunk in scan_segments(text):
        out.append(chunk if kind != COMMENT else re.sub(r"[^\n]", " ", chunk))
    return "".join(out)


def strings_of(text: str) -> list[str]:
    return [chunk for kind, chunk in scan_segments(text) if kind == STRING]


def iter_sources(src: Path) -> Iterable[tuple[str, Path]]:
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".vue"}:
            continue
        yield path.relative_to(src).as_posix(), path


def collect_dto_names(src: Path) -> set[str]:
    types_file = src / "api" / "types.ts"
    if not types_file.exists():
        return set()
    return set(DTO_DECL_RE.findall(code_of(types_file.read_text(encoding="utf-8"))))


def collect_nav_keys(src: Path) -> set[str]:
    nav_file = src / "composables" / "useNav.ts"
    if not nav_file.exists():
        return set()
    text = nav_file.read_text(encoding="utf-8")
    match = re.search(r"export type NavKey\s*=\s*([^;]+?)\n", text_of(text), re.S)
    if not match:
        return set()
    return set(re.findall(r'["\'](\w+)["\']', match.group(1)))


def collect_declared_deps(pkg_file: Path) -> tuple[set[str], set[str]]:
    """返回 (运行时依赖, 全部依赖)。运行时依赖必须被 import，未被 import 的就是死依赖。"""
    if not pkg_file.exists():
        return set(), set()
    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    deps = set(pkg.get("dependencies", {}))
    all_deps = deps | set(pkg.get("devDependencies", {}))
    return deps, all_deps


def package_of(specifier: str) -> str:
    """`highlight.js/lib/core` → `highlight.js`，`@vue/runtime` → `@vue/runtime`。"""
    if specifier.startswith("@"):
        parts = specifier.split("/")
        return "/".join(parts[:2])
    return specifier.split("/")[0]


def imported_packages(text: str) -> set[str]:
    specs = {m for m in IMPORT_FROM_RE.findall(text_of(text)) if not m.startswith((".", "@/"))}
    return {package_of(m) for m in specs}


def check_source(
    rel: str,
    text: str,
    *,
    dto_names: Iterable[str],
    nav_keys: Iterable[str],
    all_deps: Iterable[str],
) -> list[str]:
    """返回违规描述列表；rel 是相对 frontend/src 的路径。"""
    problems: list[str] = []
    code = code_of(text)
    dto_names = set(dto_names)
    nav_keys = set(nav_keys)
    all_deps = set(all_deps)
    is_composable = rel.startswith("composables/")
    is_api = rel.startswith("api/")
    is_view = not is_api and not is_composable and not rel.startswith("utils/")

    # R1：请求出口唯一
    if rel not in REQUEST_OK and FETCH_RE.search(code):
        problems.append("R1 请求出口唯一：只有 api/http.ts 能出现 fetch/XMLHttpRequest")

    # R2：登录态持久化唯一所有者
    if LOCAL_STORAGE_RE.search(code) and rel not in LOCALSTORAGE_OK:
        problems.append("R2 localStorage 只允许 api/token.ts 与 i18n 的 locale 读写")

    # R3：状态层不认识 DOM 与对话框
    if is_composable:
        hit = SIDEffects_RE.search(code)
        if hit:
            problems.append(f"R3 状态层不得有 UI 副作用：命中 {hit.group(0).strip()}")

    # R4：状态层只允许一种模式——模块级单例
    if is_composable:
        use_at = EXPORT_USE_RE.search(code)
        if use_at:
            for m in STATE_CREATOR_RE.finditer(code):
                if m.start() > use_at.start():
                    line = code.count("\n", 0, m.start()) + 1
                    problems.append(f"R4 反应式状态必须声明在模块作用域（第 {line} 行的 {m.group(0).strip()} 在 use* 之后）")
                    break

    # R5：JSON 解析只有一个地方
    if rel not in REQUEST_OK and JSON_CALL_RE.search(code):
        problems.append("R5 只有 api/http.ts 能调 res.json()，其余层拿到的应是 DTO")

    # R6：DTO 只在 api/types.ts 声明，别处不得重复
    for name in DTO_DECL_RE.findall(code):
        if rel != "api/types.ts" and name in dto_names:
            problems.append(f"R6 DTO `{name}` 已在 api/types.ts 声明，此处重复定义会漂移")

    # R7：事件只走 api/events.ts 的类型化总线
    hit = RAW_EVENT_BUS_RE.search(code)
    if hit:
        problems.append(f"R7 不得裸用 window 事件总线：命中 {hit.group(0)}")

    # R8：不允许 any
    if rel not in ANY_OK and ANY_RE.search(code):
        problems.append("R8 禁止 any：类型边界一旦漏洞，契约对齐就无从验证")

    # R9：展示文案必须是 i18n 键（注释里的中文不受本规则约束）
    if not rel.startswith(CJK_OK_PREFIX):
        for chunk in strings_of(text):
            if CJK_RE.search(chunk):
                problems.append(f"R9 字符串字面量里不得有中文文案（应走 i18n 键）：{chunk[:24]}")
                break

    # R10：视图状态必须是 NavKey 成员，props 不得退回 string
    if NAV_STRING_PROP_RE.search(code):
        problems.append("R10 activeNav 必须是 NavKey，不是裸 string")
    for value in NAV_LITERAL_ASSIGN_RE.findall(text_of(text)):
        if nav_keys and value not in nav_keys:
            problems.append(f"R10 activeNav 赋值 `{value}` 不在 NavKey 枚举里")

    # 依赖方向：视图层（components 与入口）只能通过 composables 使用请求层
    if is_view and REQUEST_MODULE_IMPORT_RE.search(text_of(text)):
        problems.append("依赖方向：视图层不得直接 import api/http 或 api/client，请经 composables")

    # R11：import 的包必须在 package.json 里声明
    if all_deps:
        for pkg in imported_packages(text):
            if pkg not in all_deps:
                problems.append(f"依赖未声明：import 了 `{pkg}`，但 frontend/package.json 里没有它")

    return problems


def check_runtime_deps_are_used(src: Path, runtime_deps: set[str]) -> list[str]:
    used: set[str] = set()
    for _, path in iter_sources(src):
        used |= imported_packages(path.read_text(encoding="utf-8"))
    dead = sorted(runtime_deps - used)
    return [f"死依赖：`{name}` 在 dependencies 里声明，但 frontend/src 无任何 import" for name in dead]


def run(src: Path = SRC, pkg_file: Path = PKG) -> list[str]:
    if not src.exists():
        return [f"缺少前端源码目录：{src}"]
    dto_names = collect_dto_names(src)
    nav_keys = collect_nav_keys(src)
    runtime_deps, all_deps = collect_declared_deps(pkg_file)
    problems: list[str] = []
    for rel, path in iter_sources(src):
        found = check_source(
            rel,
            path.read_text(encoding="utf-8"),
            dto_names=dto_names,
            nav_keys=nav_keys,
            all_deps=all_deps,
        )
        problems.extend(f"{rel}: {p}" for p in found)
    # R11 的另一半：声明了却没被 import 的就是死依赖（删掉 axios 却留着条目会误导下一个人）
    problems.extend(check_runtime_deps_are_used(src, runtime_deps))
    return problems


def main(argv: list[str] | None = None) -> int:
    problems = run()
    if problems:
        print(f"frontend 结构检查未通过，共 {len(problems)} 项：")
        for line in problems:
            print(f"  x {line}")
        print("\n规则出处：docs/refactor/10-frontend-structure.md §3")
        return 1
    files = sum(1 for _ in iter_sources(SRC))
    print(f"frontend 结构检查通过：{files} 个源文件，R1–R11 全部满足。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
