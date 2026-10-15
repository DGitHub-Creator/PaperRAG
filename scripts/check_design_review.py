"""P1 设计审查的准入门禁（`contracts/p1-design-review.md` 的执行者）。

**为什么要有它**：`plans/04 §4.4` 说"P1 接管卡开工前必须过设计审查"。一句要求没有判据，
就会变成"大家都以为自己过了"。本脚本把能被机械判定的那部分钉住——**它只判结构与一致性**：

  G1 审查文件存在，状态字段合法（`proposed` / `approved` / `rejected`）
  G2 五个维度齐全，每个都有 结论 / 依据 / 未决 / 判据 四小节且非空
  G3 每条"依据"引用的文件**真实存在**；写成 `文件::锚点` 的，锚点必须真在该文件里
     （这一条防的是最贵的那种错：文档引用了一个不存在的契约条目）
  G4 适用卡号必须真在 `progress.json` 的 P1 任务里；引用的 D 系列决策必须还在决策记录里
  G5 **状态联动**：任一适用卡进入 `in_progress` / `done`，而审查仍不是 `approved` → 失败
  G6 `approved` 时人工确认表里不许留未勾选项（`☐`）；`rejected` 一律失败

G1–G4/G6 是结构，G5 是准入。**结构齐了不等于架构正确**——正确性由文档 §6 的人工确认负责，
本脚本的作用恰恰是：没签完就不能开工，从而让"人工确认"这件事不可能被悄悄跳过。

草稿阶段（没有任何适用卡开工）时，即使审查还是 `proposed`，本脚本也**必须绿**——
把一个尚未到时的门禁挂成常态红，最后只会得到人人加 `|| true`（`AGENTS.md §8` 对
`check_nginx_routes.py` 的同一条判断）。

用法：
    uv run python scripts/check_design_review.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "contracts" / "p1-design-review.md"
PROGRESS = ROOT / "docs" / "progress.json"

DIMENSIONS = ("数据标识", "服务职责", "错误语义", "流式事件契约", "数据所有权")
SUBSECTIONS = ("结论", "依据", "未决", "判据")
VALID_STATUS = ("proposed", "approved", "rejected")
TAKEOVER_ACTIVE = ("in_progress", "done")

FIELD_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|\s*$")
CARD_RE = re.compile(r"P1-\d+")
DECISION_RE = re.compile(r"\bD(\d+)\b")
# 依据行里的引用：`路径[/路径…].扩展名[::锚点]`
REF_RE = re.compile(r"`(?P<path>[\w./-]+\.(?:md|py|go|sql|json|ya?ml|ts|vue))(?:::(?P<anchor>[\w.-]+))?`")


def read_status_table(text: str) -> dict[str, str]:
    """读文档开头那张 `| 字段 | 值 |` 表。只认第一张，避免把 §6 的确认表也吃进来。"""
    fields: dict[str, str] = {}
    seen_header = False
    for line in text.splitlines():
        if line.startswith("## "):
            break
        m = FIELD_ROW_RE.match(line)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        if key in {"字段", "---"} or set(key) <= {"-", " "}:
            seen_header = True
            continue
        if seen_header:
            fields[key] = value
    return fields


def dimension_sections(text: str) -> dict[str, str]:
    """按 `## N. 维度名` 切出五个维度的正文（到下一个 `## ` 为止）。"""
    out: dict[str, str] = {}
    parts = re.split(r"^## ", text, flags=re.M)
    for part in parts[1:]:
        title = part.splitlines()[0]
        for dim in DIMENSIONS:
            if dim in title:
                body = part[len(title):]
                # 尾部的人工确认章节（§6）与附录不属于维度正文
                body = re.split(r"^---\s*$", body, flags=re.M)[0]
                out[dim] = body
    return out



def subsection_state(body: str, sub: str) -> tuple[bool, bool]:
    r"""返回 (是否为空, 是否缺失)。

    写成两个布尔而不是三态字符串，是因为调用方只有"缺失"与"空"两种报法。
    注意**不能**用 `\*\*结论\*\*：(?!\s*$)` 这种 lookahead：本仓库的结论是列表式
    （`**结论**：` 换行再写 1./2.），行尾恰好就是 `$`，那条 lookahead 会把所有列表都判成空。
    """
    m = re.search(rf"\*\*{sub}\*\*：", body)
    if not m:
        return False, True
    rest = body[m.end():]
    nxt = re.search(r"^- \*\*(?:%s)\*\*：" % "|".join(SUBSECTIONS), rest, re.M)
    chunk = (rest[:nxt.start()] if nxt else rest).strip()
    return (len(chunk) == 0), False


def parse_references(body: str) -> list[tuple[str, str | None]]:
    """只取「依据」小节里的引用。结论/未决里出现的文件名多为叙述，判红会误伤。"""
    m = re.search(r"\*\*依据\*\*：(?P<refs>.*?)(?=^- \*\*|\n- \*\*|\Z)", body, re.M | re.S)
    if not m:
        return []
    return [(r.group("path"), r.group("anchor")) for r in REF_RE.finditer(m.group("refs"))]


def p1_task_ids(progress: dict) -> list[str]:
    for phase in progress.get("phases", []):
        if phase.get("id") == "P1":
            return [t.get("id", "") for t in phase.get("tasks", [])]
    return []


def task_status(progress: dict, task_id: str) -> str | None:
    for phase in progress.get("phases", []):
        for t in phase.get("tasks", []):
            if t.get("id") == task_id:
                return t.get("status")
    return None


def known_decisions(progress: dict) -> set[str]:
    ids: set[str] = set()
    for key in ("decisions_pending", "decisions_resolved"):
        for item in progress.get(key, []) or []:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    return ids


def check_review(review_text: str, progress: dict, file_exists, file_contains) -> list[str]:
    """纯函数版校验：把文件系统访问注入进来，好让负向用例不必去改仓库。"""
    errors: list[str] = []
    fields = read_status_table(review_text)

    status = fields.get("status", "").replace("**", "").strip().lower()
    if status not in VALID_STATUS:
        errors.append(f"状态字段非法或缺失：{status or '(空)'}（要 {VALID_STATUS} 之一）")
    if status == "rejected":
        errors.append("审查结论是 rejected——被否决的设计上不得开工任何适用卡")

    for required in ("适用卡", "依据契约"):
        if not fields.get(required, "").strip("—- "):
            errors.append(f"状态块缺必填字段：{required}")

    cards = CARD_RE.findall(fields.get("适用卡", ""))
    if not cards:
        errors.append("适用卡为空：门禁不知道该拦谁，等于没有门禁")
    known = p1_task_ids(progress)
    for card in cards:
        if card not in known:
            errors.append(f"适用卡 {card} 不在 progress.json 的 P1 任务里（不许引用不存在的卡号）")

    sections = dimension_sections(review_text)
    for dim in DIMENSIONS:
        body = sections.get(dim)
        if body is None:
            errors.append(f"缺维度章节：{dim}")
            continue
        for sub in SUBSECTIONS:
            empty, missing = subsection_state(body, sub)
            if missing:
                errors.append(f"{dim}：缺 {sub} 小节")
            elif empty:
                errors.append(f"{dim}：{sub} 小节是空的（写「无」也要写出来，空着分不清是没想还是没填）")
        for path, anchor in parse_references(body):
            f = ROOT / path
            if not file_exists(f):
                errors.append(f"{dim}：依据指向不存在的文件 {path}")
                continue
            if anchor and not file_contains(f, anchor):
                errors.append(f"{dim}：依据写 {path}::{anchor}，但该文件里没有 {anchor}（引用不存在的契约条目）")

    for decision in sorted(set(DECISION_RE.findall(fields.get("关联决策", "")))):
        did = f"D{decision}"
        if known_decisions(progress) and did not in known_decisions(progress):
            errors.append(f"关联决策 {did} 已不在决策记录里（要么它从未存在，要么已改名——引用要跟着修）")

    # G5：状态联动。草稿期（没有适用卡开工）到此为止，不拦任何人。
    active = [c for c in cards if task_status(progress, c) in TAKEOVER_ACTIVE]
    if active and status != "approved":
        errors.append(
            f"接管卡 {', '.join(active)} 已进入 in_progress/done，而设计审查仍是 {status or '(无状态)'}"
            "——准入门禁未过不得开工（approved 的条件见 §6）")

    if status == "approved" and "☐" in review_text:
        errors.append("状态是 approved，但 §6 的人工确认表仍有未勾选项（☐）——机器能查一致性，查不出正确")

    return errors


def main() -> int:
    if not REVIEW.is_file():
        print(f"[design-review] 违反：缺文件 {REVIEW.relative_to(ROOT)}")
        print("[design-review] 未通过。P1 接管卡开工前需要 contracts/p1-design-review.md 的审查结论。")
        return 1
    try:
        progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[design-review] 违反：读不到 progress.json（{exc}），状态联动判不了")
        return 1

    def contains(path: Path, needle: str) -> bool:
        try:
            return needle in path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

    errors = check_review(REVIEW.read_text(encoding="utf-8"), progress, Path.is_file, contains)
    for e in errors:
        print(f"[design-review] 违反：{e}")
    if errors:
        print(f"[design-review] 未通过（{len(errors)} 条）。它只判结构与一致性；架构是否正确由文档 §6 的人工确认负责。")
        return 1
    print("[design-review] 通过：五个维度齐全、依据可追、状态与接管卡进度不矛盾。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
