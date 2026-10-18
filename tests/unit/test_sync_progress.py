"""进度真相源的机检规则（08 §3/§4/§8）：不允许用 mock 冒充完成，产物不许漂移。"""

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync_progress.py"
_spec = importlib.util.spec_from_file_location("sync_progress", _SCRIPT)
assert _spec and _spec.loader
sync_progress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_progress)


def make_data(exit_level="real", status="pending", evidence="none", requires="real"):
    """最小合法数据集，按需篡改单项规则。"""
    return {
        "project": "T",
        "as_of": "2026-10-09",
        "baseline_commit": "abc",
        "capacity_hours_per_week": "15-20",
        "current": "x",
        "principles": ["p"],
        "phases": [
            {
                "id": "P0",
                "title": "骨架",
                "goal": "跑通一条链路",
                "status": "in_progress",
                "weeks": "W1",
                "demo": "curl health 200",
                "exits": [
                    {"id": "X1", "desc": "起来", "command": "make x", "level": exit_level, "result": "not_run"}
                ],
                "tasks": [
                    {"id": "P0-0", "title": "t", "status": status, "evidence": evidence,
                     "requires": requires, "hours": 4, "deps": [], "verify": "make x", "note": ""}
                ],
            }
        ],
        "schedule": [{"id": "W1", "dates": "10/12", "goal": "g", "phase": "P0", "status": "planned"}],
    }


class TestFakeCompletionIsRejected:
    def test_done_below_required_evidence(self):
        errors = sync_progress.validate(make_data(status="done", evidence="mock", requires="real"))
        assert any("不允许用 mock 冒充完成" in e for e in errors), errors

    def test_done_with_matching_evidence(self):
        assert sync_progress.validate(make_data(status="done", evidence="e2e", requires="e2e")) == []

    def test_done_without_verify_command(self):
        data = make_data(status="done", evidence="real", requires="real")
        data["phases"][0]["tasks"][0]["verify"] = ""
        assert any("没有可复现的验收命令" in e for e in sync_progress.validate(data))

    def test_e2e_exit_is_mandatory_per_phase(self):
        # 原则①：阶段退出标准不能全是 mock 级
        assert any("端到端优先" in e for e in sync_progress.validate(make_data(exit_level="mock")))


class TestStructuralRules:
    def test_exit_without_command(self):
        data = make_data()
        data["phases"][0]["exits"][0]["command"] = ""
        assert any("缺判定命令" in e for e in sync_progress.validate(data))

    def test_current_phase_exit_may_not_reference_a_missing_script(self):
        """判定命令里写的 scripts/*.py 不存在 → 违规。

        这条规则防的是"退出标准看起来有办法、实际上跑不动"：X2/X5 曾经就是这样，
        progress.json 里有命令，仓库里没有那个脚本。
        """
        data = make_data()
        data["phases"][0]["exits"][0]["command"] = "uv run python scripts/no_such_gate.py"
        errors = sync_progress.validate(data)
        assert any("scripts/no_such_gate.py" in e for e in errors), errors

    def test_future_phase_may_reserve_a_script_it_has_not_written_yet(self):
        """P2/P3 的命令引用的是那一阶段要新建的脚本。

        要求它现在就存在会把"未来的活"变成"今天的违规"，门禁天天红，人人绕过——
        那是把检查废掉的另一种方式，所以规则只管 in_progress/done 的阶段。
        """
        data = make_data()
        data["phases"][0]["status"] = "pending"
        data["phases"][0]["exits"][0]["command"] = "uv run python scripts/rebuild_chunks.py"
        assert sync_progress.validate(data) == []

    def test_exit_command_with_an_existing_script_passes(self):
        data = make_data()
        data["phases"][0]["exits"][0]["command"] = "uv run python scripts/check_nginx_routes.py && echo ok"
        assert sync_progress.validate(data) == []

    def test_only_script_paths_are_checked(self):
        """命令里提到 openapi.yaml / 别的 .py 不该被当成脚本引用。"""
        data = make_data()
        data["phases"][0]["exits"][0]["command"] = "uv run python scripts/check_contracts.py"
        assert sync_progress.validate(data) == []

    def test_unknown_dependency(self):
        data = make_data()
        data["phases"][0]["tasks"][0]["deps"] = ["P9-9"]
        assert any("依赖不存在" in e for e in sync_progress.validate(data))

    def _with_dep(self, data, dep_status):
        data["phases"][0]["tasks"].append(
            {"id": "P0-1", "title": "t2", "status": dep_status, "evidence": "none",
             "requires": "mock", "hours": 2, "deps": [], "verify": "x", "note": ""}
        )
        data["phases"][0]["tasks"][0]["deps"] = ["P0-1"]
        return data

    def test_in_progress_may_overlap_with_in_progress_dep(self):
        # 前置的 real 部分常常阻塞本卡的 mock 部分，允许并行，但见下一条
        data = self._with_dep(make_data(status="in_progress", requires="mock"), "in_progress")
        assert sync_progress.validate(data) == []

    def test_in_progress_blocks_untouched_dep(self):
        data = self._with_dep(make_data(status="in_progress", requires="mock"), "pending")
        errors = sync_progress.validate(data)
        assert any("尚未开始" in e for e in errors), errors

    def test_done_requires_deps_done(self):
        # done 是硬门：不能继承别人没验完的前置
        data = self._with_dep(make_data(status="done", evidence="real", requires="real"), "in_progress")
        errors = sync_progress.validate(data)
        assert any("依赖尚未完成" in e for e in errors), errors

    def test_bad_enums(self):
        data = make_data(status="almost")
        data["phases"][0]["exits"][0]["result"] = "maybe"
        errors = sync_progress.validate(data)
        assert any("status 非法" in e for e in errors)
        assert any("result 非法" in e for e in errors)

    def test_hours_are_positive_ints(self):
        data = make_data()
        data["phases"][0]["tasks"][0]["hours"] = 0
        assert any("hours" in e for e in sync_progress.validate(data))


class TestDecisionLedgerCoherence:
    """同一个决策号不能既待拍又已拍——D3 双挂过几天，此前没有任何检查会发现它。"""

    def test_same_id_in_pending_and_resolved_is_red(self):
        data = make_data()
        data["decisions_pending"] = [{"id": "D3", "question": "q", "recommendation": "r"}]
        data["decisions_resolved"] = [{"id": "D3", "question": "q", "decision": "d", "decided_at": "2026-10-15"}]
        errors = sync_progress.validate(data)
        assert any("同时挂在 pending 与 resolved" in e and "D3" in e for e in errors), errors

    def test_disjoint_ledgers_pass(self):
        data = make_data()
        data["decisions_pending"] = [{"id": "D7", "question": "q", "recommendation": "r"}]
        data["decisions_resolved"] = [{"id": "D3", "question": "q", "decision": "d", "decided_at": "2026-10-15"}]
        assert sync_progress.validate(data) == []

    def test_the_real_progress_file_has_no_double_ledgered_decision(self):
        """真实文件必须自洽：夹具能造出违规，但收口判据是仓库里那份。"""
        real = json.loads((Path(__file__).resolve().parents[2] / "docs" / "progress.json").read_text(encoding="utf-8"))
        pending = {d.get("id") for d in real.get("decisions_pending", [])}
        resolved = {d.get("id") for d in real.get("decisions_resolved", [])}
        assert pending & resolved == set(), f"这些决策被同时登记在两边：{sorted(pending & resolved)}"


class TestCompute:
    def test_deferred_and_cancelled_excluded_from_denominator(self):
        data = make_data(status="done", evidence="real", requires="real")
        data["phases"][0]["tasks"] += [
            {"id": "P0-1", "title": "推后", "status": "deferred", "evidence": "none",
             "requires": "real", "hours": 100, "deps": [], "verify": "", "note": ""},
            {"id": "P0-2", "title": "待办", "status": "pending", "evidence": "none",
             "requires": "real", "hours": 6, "deps": [], "verify": "", "note": ""},
        ]
        stats = sync_progress.compute(data)
        assert stats["hours_total"] == 10
        assert stats["percent"] == 40
        assert stats["hours_todo"] == 6

    def test_frontier_lists_only_ready_tasks(self):
        data = make_data(status="done", evidence="mock", requires="mock")
        data["phases"][0]["tasks"] += [
            {"id": "P0-1", "title": "等依赖", "status": "pending", "evidence": "none",
             "requires": "real", "hours": 2, "deps": ["P0-2"], "verify": "", "note": ""},
            {"id": "P0-2", "title": "可开工", "status": "pending", "evidence": "none",
             "requires": "real", "hours": 2, "deps": [], "verify": "", "note": ""},
        ]
        assert sync_progress.compute(data)["frontier"] == ["P0-2"]

    def test_weeks_are_ascending(self):
        stats = sync_progress.compute(make_data())
        low, high = stats["weeks_remaining"].split("-")
        assert float(low) <= float(high)


class TestOutputs:
    def test_render_is_deterministic(self):
        data = sync_progress.load()
        stats = sync_progress.compute(data)
        assert sync_progress.render_md(data, stats) == sync_progress.render_md(data, stats)
        assert sync_progress.render_html(data, stats) == sync_progress.render_html(data, stats)

    def test_html_embeds_parsable_json(self):
        data = sync_progress.load()
        html = sync_progress.render_html(data, sync_progress.compute(data))
        start = html.index('<script type="application/json" id="data">') + len('<script type="application/json" id="data">')
        payload = html[start : html.index("</script>", start)].replace("<\\/", "</")
        assert json.loads(payload)["project"] == data["project"]

    def test_shipped_artifacts_match_source(self):
        # 产物漂移就是 --check 要拦的事，这里等价复现一次
        data = sync_progress.load()
        stats = sync_progress.compute(data)
        assert sync_progress.OUT_MD.read_text(encoding="utf-8") == sync_progress.render_md(data, stats)
        assert sync_progress.OUT_HTML.read_text(encoding="utf-8") == sync_progress.render_html(data, stats)

    def test_check_mode_does_not_write(self, tmp_path, monkeypatch):
        target = tmp_path / "out.md"
        assert sync_progress.write_if_changed(target, "abc", check=True) is False
        assert not target.exists()
        assert sync_progress.write_if_changed(target, "abc", check=False) is True
        assert sync_progress.write_if_changed(target, "abc", check=True) is True

    def test_shipped_source_has_no_violation(self):
        assert sync_progress.validate(sync_progress.load()) == []
