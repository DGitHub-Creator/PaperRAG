"""P1 设计审查门禁自己的用例（`08 §6`：判据必须能证明自己会红）。

四类失败是任务里点名的：**缺失章节 / 缺失引用 / 非法状态 / 未批准提前开工**。
再加两类真风险：引用了一个**不存在的契约条目**（比引用不存在的文件更隐蔽也更贵——
它会让人以为依据已经对上），以及 `approved` 但人工确认没签完。

用例全部打 `check_review()` 这个纯函数，文件系统访问以参数注入，所以负向用例不需要
往仓库里写临时夹具（那会让门禁自己成为副作用源）；唯一读真文件的是正向用例，
它验的就是"仓库里那份文档现在确实合规"。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_design_review as dr  # noqa: E402

NL = chr(10)
UNCHECKED = chr(0x2610)   # 未勾选的方框
CHECKED = chr(0x2611)     # 已勾选的方框

STATUS_OK = (
    "| 字段 | 值 |" + NL
    + "| --- | --- |" + NL
    + "| status | proposed |" + NL
    + "| 适用卡 | P1-1, P1-2 |" + NL
    + "| 依据契约 | `contracts/error-codes.md` |" + NL
    + "| 关联决策 | D4 |" + NL
)


def _dim(index: int, name: str) -> str:
    return (
        f"## {index}. {name}" + NL + NL
        + "- **结论**：" + NL + "  1. 业务键对外，代理主键不出进程。" + NL
        + "- **依据**：`contracts/error-codes.md`" + NL
        + "- **未决**：文档实体没有稳定 id。" + NL
        + "- **判据**：`uv run python scripts/check_contracts.py`" + NL + NL
    )


# 夹具按维度清单生成，保证"缺哪个维度"这类负向用例删的是真东西，
# 而不是碰巧命中夹具本身的不全。
DIM = "".join(_dim(i, name) for i, name in enumerate(dr.DIMENSIONS, start=1))


def doc(dimensions: str = DIM) -> str:
    return "# 审查" + NL + NL + STATUS_OK + NL + dimensions


def exists_everywhere(*_args, **_kwargs) -> bool:
    """文件系统替身：一切引用都算存在，好让单条负向用例只对它改的那件事敏感。"""
    return True


PROGRESS = json.loads((ROOT / "docs" / "progress.json").read_text(encoding="utf-8"))


def progress_with(card: str, status: str) -> dict:
    data = json.loads(json.dumps(PROGRESS))
    for phase in data["phases"]:
        if phase["id"] == "P1":
            for task in phase["tasks"]:
                if task["id"] == card:
                    task["status"] = status
    return data


def read_file(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8", errors="replace")


class TestHappyPath:
    def test_shipped_review_passes(self):
        """仓库里那份文档现在必须过——这是门禁的第一条正向证据。"""
        errors = dr.check_review(
            dr.REVIEW.read_text(encoding="utf-8"), PROGRESS, Path.is_file, read_file)
        assert errors == [], errors

    def test_status_table_stops_at_first_heading(self):
        """只读文档开头那张字段表；§6 的人工确认表也是同样的行形状，不能被当成状态字段。"""
        text = (
            "# t" + NL + NL
            + "| 字段 | 值 |" + NL + "| --- | --- |" + NL + "| status | proposed |" + NL + NL
            + "## 6. 人工确认" + NL + NL + "| # | 维度 |" + NL + "| --- | --- |" + NL + "| 1 | 数据标识 |" + NL
        )
        assert dr.read_status_table(text) == {"status": "proposed"}

    def test_list_style_conclusion_is_not_treated_as_empty(self):
        """结论写成换行的 1./2. 是本仓库的常见形态；用行尾 lookahead 会把这种写法判成空。"""
        body = _dim(1, dr.DIMENSIONS[0])
        assert dr.subsection_state(body, "结论") == (False, False)
        assert dr.subsection_state(body, "不存在的小节") == (False, True)


class TestMissingSections:
    def test_missing_dimension_is_red(self):
        errors = dr.check_review(doc(DIM.split("## 2. ")[0]), PROGRESS, Path.is_file, exists_everywhere)
        assert any("缺维度章节" in e and "服务职责" in e for e in errors)

    def test_missing_subsection_is_red(self):
        body = DIM.replace("- **未决**：文档实体没有稳定 id。" + NL, "")
        errors = dr.check_review(doc(body), PROGRESS, Path.is_file, exists_everywhere)
        assert any("数据标识：缺 未决 小节" in e for e in errors)

    def test_empty_subsection_is_red_and_says_why(self):
        """空着分不清"没想到"与"没填"，所以要求写「无」。"""
        body = DIM.replace("- **未决**：文档实体没有稳定 id。", "- **未决**：")
        errors = dr.check_review(doc(body), PROGRESS, Path.is_file, exists_everywhere)
        assert any("未决 小节是空的" in e for e in errors)


class TestReferences:
    def test_missing_reference_file_is_red(self):
        body = DIM.replace("`contracts/error-codes.md`", "`contracts/no-such-contract.md`")
        errors = dr.check_review(doc(body), PROGRESS, lambda p: False, exists_everywhere)
        assert any("依据指向不存在的文件" in e for e in errors)

    def test_missing_anchor_inside_existing_file_is_red(self):
        """文件在、条目不在——这种错最贵：读的人会以为依据已经对上。"""
        body = DIM.replace("- **依据**：`contracts/error-codes.md`",
                           "- **依据**：`contracts/error-codes.md::NOT_A_REAL_KEY`")
        errors = dr.check_review(doc(body), PROGRESS, Path.is_file, read_file)
        assert any("该文件里没有 NOT_A_REAL_KEY" in e for e in errors)

    def test_real_anchor_passes(self):
        body = DIM.replace("- **依据**：`contracts/error-codes.md`",
                           "- **依据**：`contracts/ai-execution.schema.json::ExecuteRequest`")
        errors = dr.check_review(doc(body), PROGRESS, Path.is_file, read_file)
        assert not any("依据指向" in e or "没有 ExecuteRequest" in e for e in errors)

    def test_card_number_must_exist(self):
        text = doc().replace("| 适用卡 | P1-1, P1-2 |", "| 适用卡 | P1-99 |")
        errors = dr.check_review(text, PROGRESS, Path.is_file, exists_everywhere)
        assert any("P1-99 不在 progress.json 的 P1 任务里" in e for e in errors)

    def test_dangling_decision_reference_is_red(self):
        """决策被合并或改名后，引用它的文档必须跟着修——否则记录之间互相矛盾。"""
        text = doc().replace("| 关联决策 | D4 |", "| 关联决策 | D42 |")
        errors = dr.check_review(text, PROGRESS, Path.is_file, exists_everywhere)
        assert any("D42" in e for e in errors)


class TestStatusMachine:
    def test_illegal_status_is_red(self):
        text = doc().replace("| status | proposed |", "| status | 差不多了 |")
        errors = dr.check_review(text, PROGRESS, Path.is_file, exists_everywhere)
        assert any("状态字段非法" in e for e in errors)

    def test_rejected_fails_loudly(self):
        text = doc().replace("| status | proposed |", "| status | rejected |")
        errors = dr.check_review(text, PROGRESS, Path.is_file, exists_everywhere)
        assert any("rejected" in e for e in errors)

    def test_proposed_is_not_blessed_as_approved(self):
        """proposed 不因为"章节都齐"就被当成批过了。"""
        errors = dr.check_review(doc(), progress_with("P1-1", "in_progress"), Path.is_file, exists_everywhere)
        assert any("准入门禁未过不得开工" in e for e in errors)

    def test_approved_but_unsigned_is_red(self):
        text = doc().replace("| status | proposed |", "| status | approved |")
        text += "| 1 | 数据标识 | " + UNCHECKED + " |" + NL
        errors = dr.check_review(text, PROGRESS, Path.is_file, exists_everywhere)
        assert any("未勾选项" in e for e in errors)


class TestTakeoverCoupling:
    """G5 是这道门禁的全部意义：没批就不能开工；但草稿期绝不拦人。"""

    def test_draft_phase_is_not_blocked(self):
        """卡还在 pending、审查还是 proposed → 必须绿。否则门禁会变成人人加 `|| true` 的常态红。"""
        errors = dr.check_review(doc(), progress_with("P1-1", "pending"), Path.is_file, exists_everywhere)
        assert errors == [], errors

    @pytest.mark.parametrize("status", ["in_progress", "done"])
    def test_takeover_started_without_approval_is_red(self, status):
        errors = dr.check_review(doc(), progress_with("P1-1", status), Path.is_file, exists_everywhere)
        assert any("准入门禁未过不得开工" in e for e in errors), errors

    def test_takeover_started_with_approved_and_signed_review_is_green(self):
        text = doc().replace("| status | proposed |", "| status | approved |")
        text += "| 1 | 数据标识 | " + CHECKED + " |" + NL
        errors = dr.check_review(text, progress_with("P1-1", "in_progress"), Path.is_file, exists_everywhere)
        assert errors == [], errors

    def test_missing_review_file_is_reported_by_main(self, monkeypatch, capsys):
        monkeypatch.setattr(dr, "REVIEW", ROOT / "contracts" / "does-not-exist.md")
        assert dr.main() == 1
        assert "缺文件" in capsys.readouterr().out
