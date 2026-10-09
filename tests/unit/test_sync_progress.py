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
