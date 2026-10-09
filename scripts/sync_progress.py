#!/usr/bin/env python3
"""进度真相源 → 可读产物的生成器与机检入口。

用法：
  uv run python scripts/sync_progress.py           # 重新生成 PROGRESS.md 与 progress.html
  uv run python scripts/sync_progress.py --check   # CI 门禁：产物漂移或数据违规即失败

数据源只有 docs/progress.json 一份；两份产物是纯函数结果，不手改。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "progress.json"
OUT_MD = ROOT / "docs" / "PROGRESS.md"
OUT_HTML = ROOT / "docs" / "progress.html"

STATUS_RANK = {"pending": 0, "in_progress": 1, "done": 2, "deferred": -1, "cancelled": -2}
ACTIVE_STATUS = {"pending", "in_progress", "done"}
EVIDENCE_RANK = {"none": 0, "mock": 1, "real": 2, "e2e": 3}
EXIT_RESULT = {"pass", "fail", "not_run"}
STATUS_LABEL = {
    "pending": "待办",
    "in_progress": "进行中",
    "done": "完成",
    "deferred": "延期",
    "cancelled": "取消",
}
LEVEL_LABEL = {"none": "未验证", "mock": "mock", "real": "真实链路", "e2e": "端到端"}


class ValidationError(Exception):
    pass


def load() -> dict:
    if not SOURCE.exists():
        raise ValidationError(f"缺少真相源：{SOURCE}")
    try:
        return json.loads(SOURCE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"progress.json 不是合法 JSON：{exc}") from exc


def validate(data: dict) -> list[str]:
    """返回违规清单；空表示合法。"""
    errors: list[str] = []
    tasks: dict[str, dict] = {}

    for phase in data.get("phases", []):
        pid = phase.get("id") or "?"
        if not phase.get("goal"):
            errors.append(f"阶段 {pid} 缺 goal")

        exits = phase.get("exits", [])
        if not exits:
            errors.append(f"阶段 {pid} 没有退出标准")
        levels = set()
        for ex in exits:
            if not ex.get("command"):
                errors.append(f"阶段 {pid} 退出标准 {ex.get('id')} 缺判定命令")
            if ex.get("result") not in EXIT_RESULT:
                errors.append(f"阶段 {pid} 退出标准 {ex.get('id')} result 非法：{ex.get('result')}")
            levels.add(ex.get("level"))
        # 原则①：阶段必须有端到端级（real 或 e2e）验收，不能全是 mock
        if not levels & {"real", "e2e"}:
            errors.append(f"阶段 {pid} 的退出标准全是 mock 级，违反端到端优先（08 §1 ①）")

        for task in phase.get("tasks", []):
            tid = task.get("id") or "?"
            if tid in tasks:
                errors.append(f"任务号重复：{tid}")
            tasks[tid] = task
            status = task.get("status")
            if status not in STATUS_RANK:
                errors.append(f"{tid} status 非法：{status}")
            evidence = task.get("evidence")
            requires = task.get("requires")
            if evidence not in EVIDENCE_RANK:
                errors.append(f"{tid} evidence 非法：{evidence}")
            if requires not in EVIDENCE_RANK:
                errors.append(f"{tid} requires 非法：{requires}")
            # 原则②：宣称完成必须达到要求的证据等级
            if status == "done" and EVIDENCE_RANK.get(evidence, 0) < EVIDENCE_RANK.get(requires, 99):
                errors.append(
                    f"{tid} 标为 done 但证据等级 {evidence} < 要求 {requires}（不允许用 mock 冒充完成）"
                )
            if status == "done" and not task.get("verify"):
                errors.append(f"{tid} 标为 done 但没有可复现的验收命令")
            if not isinstance(task.get("hours"), int) or task.get("hours", 0) <= 0:
                errors.append(f"{tid} 缺正的整数 hours（用于工时加权完成度）")

    for tid, task in tasks.items():
        deps = task.get("deps", [])
        for dep in deps:
            if dep not in tasks:
                errors.append(f"{tid} 依赖不存在的任务：{dep}")
            if dep == tid:
                errors.append(f"{tid} 依赖自身")
        # done 是硬门：前置必须也 done，否则"完成"继承了别人没验完的洞
        if task.get("status") == "done":
            not_done = [d for d in deps if tasks.get(d, {}).get("status") != "done"]
            if not_done:
                errors.append(f"{tid} 标为 done 但依赖尚未完成：{'、'.join(not_done)}")
        # in_progress 允许与"进行中的前置"并行开工（一张卡的 real 部分常常阻塞另一张的 mock 部分），
        # 但不允许依赖还完全没人动就抢跑——那是"边写边补架构"的入口
        if task.get("status") == "in_progress":
            untouched = [d for d in deps if tasks.get(d, {}).get("status") == "pending"]
            if untouched:
                errors.append(f"{tid} 已开工但前置 {'、'.join(untouched)} 尚未开始")

    ids = [s.get("id") for s in data.get("schedule", [])]
    if len(ids) != len(set(ids)):
        errors.append("schedule 周次编号重复")
    return errors


def compute(data: dict) -> dict:
    """完成度、剩余工时、可开工 frontier。"""
    all_tasks = [t for p in data.get("phases", []) for t in p.get("tasks", [])]
    active = [t for t in all_tasks if t.get("status") in ACTIVE_STATUS]

    def hours(ts: list[dict]) -> int:
        return sum(t.get("hours", 0) for t in ts)

    done_h = hours([t for t in active if t["status"] == "done"])
    doing_h = hours([t for t in active if t["status"] == "in_progress"])
    todo_h = hours([t for t in active if t["status"] == "pending"])
    total_h = done_h + doing_h + todo_h

    by_status: dict[str, int] = {}
    for t in all_tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1

    done_ids = {t["id"] for t in all_tasks if t["status"] == "done"}
    frontier = [
        t
        for t in active
        if t["status"] == "pending" and all(d in done_ids for d in t.get("deps", []))
    ]

    phase_stats = {}
    for p in data.get("phases", []):
        pa = [t for t in p.get("tasks", []) if t.get("status") in ACTIVE_STATUS]
        pd = hours([t for t in pa if t["status"] == "done"])
        pt = hours(pa)
        ex = p.get("exits", [])
        phase_stats[p["id"]] = {
            "hours_total": pt,
            "hours_done": pd,
            "percent": round(pd * 100 / pt) if pt else 0,
            "task_total": len(pa),
            "task_done": len([t for t in pa if t["status"] == "done"]),
            "exit_pass": len([e for e in ex if e.get("result") == "pass"]),
            "exit_total": len(ex),
        }

    cap = data.get("capacity_hours_per_week", "15-20")
    low, _, high = str(cap).partition("-")
    try:
        slow = todo_h / float(low)
        fast = todo_h / float(high or low)
    except (ValueError, ZeroDivisionError):
        slow = fast = 0.0
    weeks = f"{min(slow, fast):.1f}-{max(slow, fast):.1f}"

    return {
        "hours_done": done_h,
        "hours_doing": doing_h,
        "hours_todo": todo_h,
        "hours_total": total_h,
        "percent": round(done_h * 100 / total_h) if total_h else 0,
        "counts": by_status,
        "task_total": len(all_tasks),
        "frontier": [t["id"] for t in frontier],
        "phase_stats": phase_stats,
        "weeks_remaining": weeks,
        "exits_pass": sum(
            1
            for p in data.get("phases", [])
            for e in p.get("exits", [])
            if e.get("result") == "pass"
        ),
        "exits_total": sum(len(p.get("exits", [])) for p in data.get("phases", [])),
    }


def render_md(data: dict, stats: dict) -> str:
    L: list[str] = []
    L.append("# 进度报告")
    L.append("")
    L.append("> 本文件由 `scripts/sync_progress.py` 从 [`progress.json`](progress.json) 生成，**请勿手改**。")
    L.append(f"> 数据截止 {data.get('as_of', '？')} · 基线 `{data.get('baseline_commit', '？')}` · 投入 {data.get('capacity_hours_per_week', '？')} 小时/周")
    L.append("")
    L.append("## 一句话现状")
    L.append("")
    L.append(f"- **完成了多少**：{stats['percent']}%（按工时加权；{stats['hours_done']}/{stats['hours_total']} 小时，"
             f"任务完成 {stats['counts'].get('done', 0)}/{stats['task_total']}，验收 {stats['exits_pass']}/{stats['exits_total']} 通过）")
    L.append(f"- **现在在哪**：{data.get('current', '？')}")
    L.append(f"- **还差多少**：待办 {stats['counts'].get('pending', 0)} 项 / {stats['hours_todo']} 小时（约 {stats['weeks_remaining']} 周），"
             f"进行中 {stats['counts'].get('in_progress', 0)} 项；可立即开工：{'、'.join(stats['frontier']) or '无'}")
    L.append("")

    L.append("## 阶段进度")
    L.append("")
    L.append("| 阶段 | 目标 | 状态 | 完成度 | 验收 | 工时 | 周次 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for p in data.get("phases", []):
        s = stats["phase_stats"][p["id"]]
        bar = _bar(s["percent"])
        L.append(
            f"| **{p['id']}** {p['title']} | {p['goal']} | {STATUS_LABEL.get(p.get('status', 'pending'), p.get('status'))} "
            f"| {bar} {s['percent']}% | {s['exit_pass']}/{s['exit_total']} | {s['hours_done']}/{s['hours_total']}h | {p.get('weeks', '—')} |"
        )
    L.append("")

    for p in data.get("phases", []):
        s = stats["phase_stats"][p["id"]]
        L.append(f"## {p['id']} — {p['title']}（{s['percent']}%）")
        L.append("")
        if p.get("demo"):
            L.append(f"**可演示状态**：{p['demo']}")
            L.append("")
        if p.get("exits"):
            L.append("### 退出标准")
            L.append("")
            L.append("| # | 标准 | 判定命令 | 等级 | 结果 |")
            L.append("| --- | --- | --- | --- | --- |")
            for e in p["exits"]:
                badge = {"pass": "✅ pass", "fail": "❌ fail", "not_run": "⬜ 未跑"}[e.get("result", "not_run")]
                secret = "（需密钥）" if e.get("needs_secret") else ""
                L.append(f"| {e['id']} | {e['desc']}{secret} | `{e['command']}` | {LEVEL_LABEL.get(e.get('level'), e.get('level'))} | {badge} |")
            L.append("")
        L.append("### 任务")
        L.append("")
        L.append("| # | 任务 | 状态 | 证据 | 工时 | 依赖 | 验收命令 | 备注 |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for t in p["tasks"]:
            evidence = f"{LEVEL_LABEL.get(t['evidence'], t['evidence'])}（要求 {t['requires']}）"
            deps = "、".join(t.get("deps", [])) or "—"
            verify = t.get("verify") or "—"
            note = t.get("note", "")
            if t.get("needs_secret"):
                note = (note + " " if note else "") + "（需密钥）"
            L.append(
                f"| {t['id']} | {t['title']} | {STATUS_LABEL.get(t['status'], t['status'])} | {evidence} "
                f"| {t['hours']}h | {deps} | `{verify}` | {note} |"
            )
        L.append("")
        if p.get("not_doing"):
            L.append(f"**本阶段不做**：{'· '.join(p['not_doing'])}")
            L.append("")

    L.append("## 日程")
    L.append("")
    L.append("| 周 | 日期 | 目标 | 阶段 | 状态 |")
    L.append("| --- | --- | --- | --- | --- |")
    for w in data.get("schedule", []):
        L.append(f"| {w['id']} | {w.get('dates', '')} | {w['goal']} | {w.get('phase', '')} | {w.get('status', 'planned')} |")
    L.append("")

    if data.get("decisions_pending"):
        L.append("## 待你拍板")
        L.append("")
        for d in data["decisions_pending"]:
            L.append(f"- **{d['id']}** {d['question']} → 建议：{d['recommendation']}（{d.get('blocking', '')}）")
        L.append("")

    if data.get("risks"):
        L.append("## 风险登记（前 8）")
        L.append("")
        for r in data["risks"][:8]:
            L.append(f"- **{r['risk']}** ｜触发：{r.get('trigger', '')} ｜缓解：{r.get('mitigation', '')}")
        L.append("")

    L.append("## 图例")
    L.append("")
    L.append("- 状态：待办 / 进行中 / 完成 / 延期 / 取消。**只有达到要求证据等级才能标完成**（`--check` 强制）。")
    L.append("- 证据等级：`mock` 单元级（外部依赖全 mock）< `real` 真实容器链路 < `e2e` 真实浏览器。")
    L.append("- 完成度按工时加权，`deferred`/`cancelled` 不计入分母。")
    L.append("")
    return "\n".join(L)


def _bar(percent: int, width: int = 5) -> str:
    filled = int(round(percent * width / 100))
    return "█" * filled + "░" * (width - filled)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · 进度看板</title>
<style>
:root{--bg:#0f1117;--card:#171a23;--line:#252a38;--fg:#e6e8ee;--dim:#9aa3b5;
--ok:#3fb27f;--warn:#e0a63f;--bad:#e05f5f;--accent:#5b8def;--bar:#2b3245}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.65 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:26px 0 10px;border-left:3px solid var(--accent);padding-left:9px}
h3{font-size:14px;margin:18px 0 8px;color:var(--dim)}
.wrap{max-width:1180px;margin:0 auto;padding:22px 18px 60px}
.sub{color:var(--dim);font-size:12px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;min-width:190px;flex:1}
.card b{display:block;font-size:24px;margin-top:4px}
.bar{height:8px;background:var(--bar);border-radius:6px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--ok))}
table{width:100%;border-collapse:collapse;margin:6px 0 14px;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:left;vertical-align:top}
th{color:var(--dim);font-weight:600;background:#141722}
code{background:#141722;padding:1px 5px;border-radius:4px;font-size:12px;color:#c7d2f0;word-break:break-all}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid var(--line)}
.s-done{color:var(--ok);border-color:#2b5240}.s-in_progress{color:var(--warn);border-color:#54432a}
.s-pending{color:var(--dim)}.s-deferred,.s-cancelled{color:#6b7383}
.r-pass{color:var(--ok)}.r-fail{color:var(--bad)}.r-not_run{color:var(--dim)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0}
select,button{background:#141722;color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:5px 10px;font-size:13px}
details{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0;background:var(--card)}
summary{cursor:pointer;font-weight:600}
.phasegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.timeline{display:flex;gap:8px;flex-wrap:wrap}
.week{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:9px 11px;min-width:150px;font-size:12px}
.week b{display:block;font-size:13px}
.muted{color:var(--dim)}
ul{margin:6px 0 0;padding-left:20px}li{margin:3px 0}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const S = D.__stats__;
const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SL = {pending:'待办', in_progress:'进行中', done:'完成', deferred:'延期', cancelled:'取消'};
const LL = {none:'未验证', mock:'mock', real:'真实链路', e2e:'端到端'};
const RL = {pass:'通过', fail:'失败', not_run:'未跑'};

function head(){
  return `<h1>${esc(D.project)} · 进度看板</h1>
  <div class="sub">数据截止 ${esc(D.as_of)} ｜ 基线 <code>${esc(D.baseline_commit)}</code> ｜ 投入 ${esc(D.capacity_hours_per_week)} 小时/周 ｜ 真相源 <code>docs/progress.json</code></div>
  <div class="cards">
    <div class="card">完成多少<b>${S.percent}%</b><div class="bar"><i style="width:${S.percent}%"></i></div><div class="sub">${S.hours_done}/${S.hours_total} 工时加权</div></div>
    <div class="card">现在在哪<b class="muted" style="font-size:14px">${esc(D.current)}</b></div>
    <div class="card">还差多少<b>${S.hours_todo}h</b><div class="sub">待办 ${S.counts.pending||0} 项 · 约 ${S.weeks_remaining} 周</div></div>
    <div class="card">验收通过<b>${S.exits_pass}/${S.exits_total}</b><div class="sub">任务 ${S.counts.done||0}/${S.task_total} 完成</div></div>
  </div>
  <div class="row"><b>可立即开工</b>${S.frontier.length ? S.frontier.map(f=>`<span class="pill s-pending">${esc(f)}</span>`).join('') : '<span class="muted">无（等依赖完成）</span>'}</div>`;
}

function phases(){
  return '<h2>阶段</h2><div class="phasegrid">' + D.phases.map(p=>{
    const s=S.phase_stats[p.id];
    return `<div class="card"><div class="sub">${esc(p.weeks||'')}</div>
      <b style="font-size:15px">${esc(p.id)} ${esc(p.title)}</b>
      <div class="sub">${esc(p.goal)}</div>
      <div class="bar"><i style="width:${s.percent}%"></i></div>
      <div class="sub">${s.percent}% ｜ 任务 ${s.task_done}/${s.task_total} ｜ 验收 ${s.exit_pass}/${s.exit_total} ｜ ${s.hours_done}/${s.hours_total}h ｜ ${SL[p.status]||p.status}</div>
    </div>`;
  }).join('') + '</div>';
}

function exits(){
  return '<h2>退出标准（全部可机检）</h2><table><tr><th>阶段</th><th>#</th><th>标准</th><th>判定命令</th><th>等级</th><th>结果</th></tr>' +
    D.phases.flatMap(p=>(p.exits||[]).map(e=>`<tr><td>${esc(p.id)}</td><td>${esc(e.id)}</td><td>${esc(e.desc)}${e.needs_secret?' <span class="r-not_run">(需密钥)</span>':''}</td><td><code>${esc(e.command)}</code></td><td>${LL[e.level]||e.level}</td><td class="r-${e.result}">${RL[e.result]||e.result}</td></tr>`)).join('') + '</table>';
}

function tasks(){
  const rows = D.phases.flatMap(p=>p.tasks.map(t=>({p,t})));
  return `<h2>任务清单</h2>
  <div class="row">阶段 <select id="fp"><option value="">全部</option>${D.phases.map(p=>`<option>${esc(p.id)}</option>`).join('')}</select>
  状态 <select id="fs"><option value="">全部</option>${Object.entries(SL).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select>
  <span class="muted" id="cnt"></span></div>
  <table><tr><th>#</th><th>阶段</th><th>任务</th><th>状态</th><th>证据</th><th>工时</th><th>依赖</th><th>验收命令</th><th>备注</th></tr>
  <tbody id="tb"></tbody></table>`;
}

function draw(){
  const fp=document.getElementById('fp').value, fs=document.getElementById('fs').value;
  const rows=[];
  D.phases.forEach(p=>p.tasks.forEach(t=>{
    if(fp && p.id!==fp) return;
    if(fs && t.status!==fs) return;
    rows.push(`<tr><td>${esc(t.id)}</td><td>${esc(p.id)}</td><td>${esc(t.title)}</td>
      <td class="s-${t.status}">${SL[t.status]||t.status}</td>
      <td>${LL[t.evidence]||t.evidence} <span class="muted">/要求 ${esc(t.requires)}</span></td>
      <td>${t.hours}h</td><td class="muted">${esc((t.deps||[]).join('、')||'—')}</td>
      <td><code>${esc(t.verify||'—')}</code></td><td class="muted">${esc(t.note||'')}${t.needs_secret?' <span class="r-not_run">(需密钥)</span>':''}</td></tr>`);
  }));
  document.getElementById('tb').innerHTML=rows.join('');
  document.getElementById('cnt').textContent=`显示 ${rows.length} 项`;
}

function rest(){
  const sched='<h2>日程</h2><div class="timeline">'+D.schedule.map(w=>`<div class="week"><b>${esc(w.id)} ${esc(w.dates||'')}</b>${esc(w.goal)}<div class="sub">${esc(w.phase||'')} ｜ ${esc(w.status||'')}</div></div>`).join('')+'</div>';
  const dec=D.decisions_pending&&D.decisions_pending.length?'<h2>待拍板决策</h2><ul>'+D.decisions_pending.map(d=>`<li><b>${esc(d.id)}</b> ${esc(d.question)}<br><span class="muted">建议：${esc(d.recommendation)} ｜ 影响：${esc(d.blocking||'')}</span></li>`).join('')+'</ul>':'';
  const risks=D.risks&&D.risks.length?'<h2>风险登记</h2><table><tr><th>风险</th><th>触发</th><th>缓解</th></tr>'+D.risks.map(r=>`<tr><td>${esc(r.risk)}</td><td class="muted">${esc(r.trigger||'')}</td><td>${esc(r.mitigation||'')}</td></tr>`).join('')+'</table>':'';
  const pr='<h2>四条第一性原则</h2><ul>'+D.principles.map(p=>`<li>${esc(p)}</li>`).join('')+'</ul>';
  const nd=D.not_doing&&D.not_doing.length?`<details><summary>明确不做（${D.not_doing.length}）</summary><ul>${D.not_doing.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></details>`:'';
  const lg='<h2>图例</h2><div class="sub">状态：'+Object.values(SL).join(' / ')+'。<br>证据等级：mock &lt; 真实链路 &lt; 端到端。<b>只有达到要求证据等级才允许标完成</b>，由 <code>sync_progress.py --check</code> 强制。<br>完成度按工时加权，延期/取消不计入分母。</div>';
  return sched+dec+risks+pr+nd+lg;
}

document.getElementById('app').innerHTML = head()+phases()+exits()+tasks()+rest();
document.getElementById('fp').onchange=draw; document.getElementById('fs').onchange=draw; draw();
</script>
</body>
</html>
"""


def render_html(data: dict, stats: dict) -> str:
    payload = dict(data)
    payload["__stats__"] = stats
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # 内联到 <script type="application/json"> 时必须避免提前闭合标签；"\/" 是合法 JSON 转义。
    text = text.replace("</", "<\\/")
    out = HTML_TEMPLATE.replace("__TITLE__", data.get("project", "项目"))
    out = out.replace("__DATA__", text)
    out = "<!-- 由 scripts/sync_progress.py 从 progress.json 生成，请勿手改 -->\n" + out
    return out


def write_if_changed(path: Path, text: str, check: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == text:
        return True
    if check:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="生成/校验进度产物")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件；产物漂移即失败")
    args = parser.parse_args()

    try:
        data = load()
    except ValidationError as exc:
        print(f"[progress] 数据不可用：{exc}")
        return 2

    errors = validate(data)
    if errors:
        print(f"[progress] 数据违规 {len(errors)} 条：")
        for e in errors:
            print(f"  - {e}")
        return 1

    stats = compute(data)
    outputs = [(OUT_MD, render_md(data, stats)), (OUT_HTML, render_html(data, stats))]
    ok = all(write_if_changed(path, text, args.check) for path, text in outputs)

    if not ok:
        print("[progress] 产物与 progress.json 不一致，请先运行：uv run python scripts/sync_progress.py")
        return 1

    if args.check:
        print(f"[progress] OK：{stats['percent']}% 完成，{stats['exits_pass']}/{stats['exits_total']} 验收通过，数据校验无违规")
    else:
        print(f"[progress] 已生成 PROGRESS.md 与 progress.html（完成度 {stats['percent']}%，任务 {stats['task_total']} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
