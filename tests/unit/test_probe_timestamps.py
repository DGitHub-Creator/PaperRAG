"""`scripts/probe_timestamps.py` 的判定单测（P0-2 / X6 第三问的 mock 级证据）。

这个脚本的价值全在**它不假装判过**：分布法与交叉法在没有存量数据时必须报 `no_data`，
而不是给一个看起来合理的判定。所以这里的用例分两类：

  1. 结论生成点：`classify_offset` 是全脚本唯一把"秒差"翻译成"UTC/本地/不可判"的地方，
     而它的输出是 `05 §4.2` 转换迁移的输入——判错就等于按错误的偏移重写全库时间。
  2. 不许假判：没有 DATABASE_URL 时 exit 2；没有数据时报 no_data；
     列本身是 timestamptz 时不再套用"naive 语义不确定"那套结论。

这些用例**都不连库**，所以任何机器上都能跑。真库上的三法实跑结果记在
`docs/reference/timestamp-audit.md`（生成时间、PG 版本、9 组探针数据都在里面）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.probe_timestamps import (  # noqa: E402
    AWARE_TYPE,
    DEFAULT_SESSION_TZS,
    NAIVE_TYPE,
    PROBE_UTC,
    VERDICTS,
    WRITE_PATHS,
    build_report,
    classify_offset,
    main,
    per_column_verdicts,
    render_markdown,
)

EIGHT_HOURS = 8 * 3600


class TestOffsetClassification:
    """`classify_offset` 是结论生成点：它的输出决定"这张表按什么偏移重写"。"""

    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "utc"),
        (4.9, "utc"),                 # 容差内的抖动仍算 UTC，别让毫秒级噪声变成"混杂"
        (-4.9, "utc"),
        (float(EIGHT_HOURS), "local"),    # Asia/Shanghai 实测到的那一条
        (-float(EIGHT_HOURS), "local"),
        (float(3600), "local"),
        (float(3601), "local"),      # 整小时 + 1 秒：**仍是 local**。容差存在的理由就在这里——
                                     # 探针要跨宿主与容器两边取时，把 1 秒抖动翻成"不可判"
                                     # 就会让真实的 +08:00 结论消失，那比误判更糟。
        (float(90 * 60), "unknown"),      # 半小时偏移不是本项目任何时区的语义，落到不可判
        (float(3600 + 120), "unknown"),   # 超出 5 秒容差 → 说明真值取法有问题，不硬归类
    ])
    def test_classify_offset(self, seconds, expected):
        verdict, whole = classify_offset(seconds)
        assert verdict == expected, f"{seconds}s 应判 {expected}，实得 {verdict}"
        if expected == "unknown":
            assert whole is False

    def test_zero_and_local_are_distinguishable_at_half_hour(self):
        """+08:30（印度之类不适用在这里，但半小时时区真实存在）不能与 0 混同。"""
        assert classify_offset(0.0)[0] == "utc"
        assert classify_offset(30 * 60)[0] == "unknown"


class TestNoFabricatedVerdicts:
    def test_refuses_without_database_url(self, monkeypatch):
        """没有库就 exit 2。这条是"不把跑不了说成跑过了"的机检形式。"""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert main(["--database-url", ""]) == 2

    def test_refusal_does_not_write_the_report(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        out = tmp_path / "timestamp-audit.md"
        assert main(["--database-url", "", "--out", str(out)]) == 2
        assert not out.exists(), "拒跑时不该产出一个空/假的审计报告"

    def test_no_data_column_is_reported_as_no_data(self):
        """分布法拿不到行时必须给 no_data，而不是默认 utc。"""
        columns = [{"table_name": "users", "column_name": "created_at", "data_type": NAIVE_TYPE}]
        distribution = [{"table": "users", "column": "created_at", "verdict": "no_data", "rows": 0}]
        rows = per_column_verdicts(columns, distribution, probes=[])
        assert rows[0]["verdict"] == "no_data"

    def test_missing_distribution_entry_is_unknown_not_utc(self):
        """没统计到 ≠ 判过。缺条目必须落到 unknown，否则"漏统计"会伪装成"结论是 UTC"。"""
        columns = [{"table_name": "chat_sessions", "column_name": "created_at", "data_type": NAIVE_TYPE}]
        rows = per_column_verdicts(columns, distribution=[], probes=[])
        assert rows[0]["verdict"] == "unknown"

    def test_aware_column_does_not_get_the_naiveTreatment(self):
        """timestamptz 本身语义无歧义，不该被卷进"naive 列的时区不确定性"。"""
        columns = [{"table_name": "ai_executions", "column_name": "created_at", "data_type": AWARE_TYPE}]
        rows = per_column_verdicts(columns, distribution=[], probes=[])
        assert rows[0]["verdict"] == "aware"

    def test_all_emitted_verdicts_come_from_the_declared_domain(self):
        columns = [
            {"table_name": "users", "column_name": "created_at", "data_type": NAIVE_TYPE},
            {"table_name": "ai_executions", "column_name": "created_at", "data_type": AWARE_TYPE},
        ]
        distribution = [
            {"table": "users", "column": "created_at", "verdict": "has_data",
             "rows": 100, "peak_hour": 15, "peak_share": 0.6},
        ]
        for row in per_column_verdicts(columns, distribution, probes=[]):
            assert row["verdict"] in VERDICTS, row


class TestPerColumnPriority:
    def test_has_data_with_a_sharp_peak_is_called_mixed(self):
        """峰值过于集中（≥50% 挤在同一小时）说明这批值的来源高度一致，
        而"一致"本身在没有时间基准参照时不能当成 UTC —— 保守地报 mixed。"""
        columns = [{"table_name": "chat_messages", "column_name": "timestamp", "data_type": NAIVE_TYPE}]
        distribution = [{"table": "chat_messages", "column": "timestamp", "verdict": "has_data",
                         "rows": 500, "peak_hour": 3, "peak_share": 0.72}]
        assert per_column_verdicts(columns, distribution, probes=[])[0]["verdict"] == "mixed"

    def test_has_data_with_a_flat_peak_is_unknown(self):
        columns = [{"table_name": "chat_messages", "column_name": "timestamp", "data_type": NAIVE_TYPE}]
        distribution = [{"table": "chat_messages", "column": "timestamp", "verdict": "has_data",
                         "rows": 500, "peak_hour": 3, "peak_share": 0.11}]
        assert per_column_verdicts(columns, distribution, probes=[])[0]["verdict"] == "unknown"


class TestReportShape:
    def _report(self):
        probes = [
            {
                "session_tz": "Asia/Shanghai", "write_path": "python_aware_datetime_utc",
                "reference": "fixed_instant", "stored_text": "2026-01-01 15:08:09",
                "stored_wallclock": "2026-01-01 15:08:09", "offset_seconds": float(EIGHT_HOURS),
                "offset_hours": 8.0, "is_whole_hour_offset": True, "verdict": "local",
                "expected_utc_wallclock": "2026-01-01 07:08:09", "matches_utc_wallclock": False,
            },
            {
                "session_tz": "UTC", "write_path": "python_aware_datetime_utc",
                "reference": "fixed_instant", "stored_text": "2026-01-01 07:08:09",
                "stored_wallclock": "2026-01-01 07:08:09", "offset_seconds": 0.0,
                "offset_hours": 0.0, "is_whole_hour_offset": True, "verdict": "utc",
                "expected_utc_wallclock": "2026-01-01 07:08:09", "matches_utc_wallclock": True,
            },
        ]
        columns = [{"table_name": "users", "column_name": "created_at", "data_type": NAIVE_TYPE}]
        distribution = [{"table": "users", "column": "created_at", "verdict": "no_data", "rows": 0}]
        cross = {"method": "chat_messages id vs timestamp", "verdict": "no_data",
                 "sessions_checked": 0, "violations": 0}
        facts = {"timezone": "Etc/UTC", "log_timezone": "Etc/UTC", "server_version": "15.19"}
        return build_report(facts, columns, probes, distribution, cross,
                            per_column_verdicts(columns, distribution, probes)), probes

    def test_naive_and_aware_are_counted_separately(self):
        report, _ = self._report()
        assert report["naive_timestamp_columns"] == 1
        assert report["aware_timestamp_columns"] == 0

    def test_markdown_shows_the_local_finding_not_only_the_clean_one(self):
        """只展示"偏移为 0"的探针行会让报告看起来一切正常。
        Asia/Shanghai 那 +8h 的一行必须出现在表里，它才是本节要交付的结论。"""
        report, _ = self._report()
        md = render_markdown(report)
        assert "2026-01-01 15:08:09" in md
        assert "| 8.0 | local |" in md
        assert "不能假定为 UTC" in md

    def test_markdown_keeps_the_boundaries_section(self):
        """边界段消失 = 读者会以为三法都判过了。这里钉住它不被"顺手清理"掉。"""
        report, _ = self._report()
        md = render_markdown(report)
        assert "## 5. 本报告的边界" in md
        assert "C20" in md, "必须点名原真库不可复原这件事，否则 no_data 看着像暂时缺数据"

    def test_markdown_reports_no_data_as_no_data(self):
        report, _ = self._report()
        md = render_markdown(report)
        assert "**no_data**" in md
        assert "utc" not in md.split("## 2.")[1].split("## 3.")[0].lower(), \
            "分布法没有数据时不该出现任何 utc 字样"


class TestProbeInputsArePinned:
    def test_probe_instant_is_fixed(self):
        """探针时刻必须是常量，否则两次跑出的偏移不可比，报告也就无法复核。"""
        assert PROBE_UTC.tzinfo is not None, "探针时刻必须是 aware，否则它自己就带着歧义"
        assert PROBE_UTC.second == 9 and PROBE_UTC.hour == 7

    def test_three_write_paths_match_doc_05_section_4_1(self):
        """`05 §4.1` 点名了两条路径（SQL 的 now() AT TIME ZONE 'UTC' 与 datetime.now(UTC)），
        本脚本额外加一条"字面量 UTC 挂钟"作参照。三条都要在，少一条就没有参照系了。"""
        assert "sql_now_at_tz_utc" in WRITE_PATHS
        assert "python_aware_datetime_utc" in WRITE_PATHS
        assert "sql_literal_utc_wallclock" in WRITE_PATHS

    def test_session_timezone_set_covers_the_two_ends(self):
        """UTC 与 Asia/Shanghai 是本项目会遇到的两端，缺一端就看不出偏移。"""
        assert "UTC" in DEFAULT_SESSION_TZS
        assert "Asia/Shanghai" in DEFAULT_SESSION_TZS
