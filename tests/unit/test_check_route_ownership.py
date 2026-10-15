"""归属门禁自己的用例：每条规则一正一篡改。

`08 §6` 的规矩是**判据要能证明自己会红**。这里尤其要紧的是那两类"看着绿其实没判"的形态：
表格解析不出行（门禁静默空过）、例外登记写了却没用例（假证据占住一条永久遗留）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_route_ownership as ro  # noqa: E402


def row(method: str, path: str, owner: str, still: str = "—") -> str:
    return f"| {method} | `{path}` | {owner} | {still} | 说明 |"


class TestTableParsing:
    def test_real_table_has_every_expected_owner(self):
        rows = ro.table_rows()
        assert len(rows) >= 30, "真表读不出足够行，多半是列格式改了而解析器没跟着改"
        assert {r[2] for r in rows} == {"go", "shared", "proxy", "internal"}

    def test_non_table_lines_are_ignored(self):
        # 归属取值那一节里有 `| go | ... |` 这样的说明行，方法列不是动词 → 不该被当数据吃进来
        assert ro.ROW_RE.match("| 归属 | 含义 | 机检要求 |") is None

    def test_empty_table_fails_closed(self, tmp_path, monkeypatch):
        f = tmp_path / "route-ownership.md"
        f.write_text("# 空表\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        assert ro.check() == [f"{f.name} 没解析出任何行，归属门禁等于没有（宁可报错也不要空过）"]


class TestOwnershipRules:
    def make(self, monkeypatch, go, py):
        monkeypatch.setattr(ro, "go_routes", lambda: set(go))
        monkeypatch.setattr(ro, "python_routes", lambda: set(py))

    def test_go_owner_requires_registration(self, monkeypatch, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# h\n\n| 方法 | 路径 | 归属 | Python 仍在 | 说明 |\n| --- | --- | --- | --- | --- |\n"
                     + row("POST", "/api/v1/x", "go") + "\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        self.make(monkeypatch, go=[], py=[])
        assert any("接管是纸面的" in e for e in ro.check())

    def test_proxy_must_not_be_registered_in_go(self, monkeypatch, tmp_path):
        """Go 已经显式注册却还标 proxy，与没搬却标 go 是同一类漂移。"""
        f = tmp_path / "t.md"
        f.write_text("# h\n\n| 方法 | 路径 | 归属 | Python 仍在 | 说明 |\n| --- | --- | --- | --- | --- |\n"
                     + row("GET", "/api/v1/y", "proxy") + "\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        self.make(monkeypatch, go=[("GET", "/api/v1/y")], py=[("GET", "/api/v1/y")])
        assert any("搬完要改归属" in e for e in ro.check())

    def test_internal_owner_rejects_a_public_path(self, monkeypatch, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# h\n\n| 方法 | 路径 | 归属 | Python 仍在 | 说明 |\n| --- | --- | --- | --- | --- |\n"
                     + row("GET", "/api/v1/ai/execute", "internal") + "\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        self.make(monkeypatch, go=[], py=[("GET", "/api/v1/ai/execute")])
        assert any("R3 管不到它" in e for e in ro.check())

    def test_unregistered_go_route_is_reported(self, monkeypatch, tmp_path):
        """接线不登记=无人负责。反向覆盖这一向必须有，否则表会退化成"想写才写"。"""
        f = tmp_path / "t.md"
        f.write_text("# h\n\n| 方法 | 路径 | 归属 | Python 仍在 | 说明 |\n| --- | --- | --- | --- | --- |\n"
                     + row("GET", "/api/v1/registered", "go") + "\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        self.make(monkeypatch, go=[("GET", "/api/v1/registered"), ("GET", "/api/v1/orphan")], py=[])
        assert any("Go 注册了 GET /api/v1/orphan" in e for e in ro.check())

    def test_new_python_surface_must_be_claimed(self, monkeypatch, tmp_path):
        f = tmp_path / "t.md"
        f.write_text("# h\n\n| 方法 | 路径 | 归属 | Python 仍在 | 说明 |\n| --- | --- | --- | --- | --- |\n"
                     + row("GET", "/api/v1/claimed", "proxy") + "\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        self.make(monkeypatch, go=[], py=[("GET", "/api/v1/claimed"), ("POST", "/api/v1/sneaky")])
        assert any("新增面要先认领归属" in e for e in ro.check())

    def test_static_and_docs_mounts_are_not_business_surface(self, monkeypatch, tmp_path):
        """/docs 与静态挂载不进"必须登记"的分母——它们不是业务面，要求登记只会让人开始乱填表。"""
        f = tmp_path / "t.md"
        f.write_text("# h\n\n| 方法 | 路径 | 归属 | Python 仍在 | 说明 |\n| --- | --- | --- | --- | --- |\n"
                     + row("GET", "/api/v1/claimed", "proxy") + "\n", encoding="utf-8")
        monkeypatch.setattr(ro, "TABLE_FILE", f)
        self.make(monkeypatch, go=[], py=[("GET", "/api/v1/claimed"), ("GET", "/docs"),
                                          ("GET", "/assets/app.js")])
        assert ro.check() == []


class TestExceptionLedger:
    """`go` 归属 + Python 仍在服务 = 例外登记，两种写法各有各的硬要求。"""

    def test_claimed_parity_without_a_selector_is_red(self):
        e = ro.check_exception("POST", "/api/v1/auth/register", "对拍保留（P1-2 删）")
        assert e and "没指到用例" in e[0]

    def test_selector_pointing_at_a_missing_case_is_red(self, tmp_path, monkeypatch):
        chain = tmp_path / "tests" / "chain"
        chain.mkdir(parents=True)
        (chain / "test_x.py").write_text("def test_real():\n    pass\n", encoding="utf-8")
        monkeypatch.setattr(ro, "ROOT", tmp_path)
        e = ro.check_exception("GET", "/api/v1/sessions", "对拍保留（P1-1 删，tests/chain/test_x.py::test_ghost）")
        assert any("指不到" in x and "def test_ghost" in x for x in e)

    def test_good_selector_passes(self, tmp_path, monkeypatch):
        chain = tmp_path / "tests" / "chain"
        chain.mkdir(parents=True)
        (chain / "test_x.py").write_text("def test_real():\n    pass\n", encoding="utf-8")
        monkeypatch.setattr(ro, "ROOT", tmp_path)
        assert ro.check_exception(
            "GET", "/api/v1/sessions", "对拍保留（P1-1 删，tests/chain/test_x.py::test_real）") == []

    def test_unpaired_retention_needs_a_ledger_id(self):
        assert ro.check_exception("POST", "/api/v1/x", "**未对拍保留**（P1-2 删，台账 C36）") == []
        e = ro.check_exception("POST", "/api/v1/x", "**未对拍保留**（P1-2 删）")
        assert e and "没台账号" in e[0]

    def test_dash_means_no_exception_needed(self):
        assert ro.check_exception("POST", "/api/v1/x", "—") == []

    def test_vague_text_without_anywhere_to_go_is_red(self):
        e = ro.check_exception("POST", "/api/v1/x", "以后再说")
        assert e and "没写去向" in e[0]


def test_go_wildcard_is_not_counted_as_a_registration():
    """`/api/*` 那类通配是**转发**，不是归属。把它当注册会让每条 proxy 面都"已被 Go 注册"。"""
    src = (
        'router.Get("/api/v1/sessions", session.ListHandler(svc))\n'
        'for _, prefix := range []string{"/api/*", "/internal/*"} {\n'
        '    r.Handle(prefix, upstream)\n'
        '}\n'
    )
    found = {(ro.METHOD_BY_GO[m.group(1)], m.group("path")) for m in ro.GO_ROUTE_RE.finditer(src)}
    assert found == {("GET", "/api/v1/sessions")}
