"""时间列语义审计（09-milestone-p0 P0-2；方法与判定表见 05 §4.1）。

要回答的问题是 X6 验收明文列出的第三问：**每张表的时间列到底是 UTC、本地时间，还是混杂**。
现状是所有列都是 `timestamp without time zone`（naive），而写入侧混用两种写法：

    naive  datetime.utcnow()          —— conversation_storage.py:85、models.py 各默认值
    aware  datetime.now(UTC)          —— parent_chunk_store.py:95

aware 值经 psycopg2 落到 naive 列时，PG 会**按会话 `TimeZone` 转换后再丢弃偏移**，
所以"库里那个数字到底是什么时刻"取决于写入时的会话时区，**不能假定为 UTC**（05 §4）。

三种判定方法，各自能证到的范围不同，本脚本分开报、不互相冒充：

  ①探针法  把**已知时刻**分别经三条写入路径落库，读回文本与 epoch 与真值比对，
          得到「写入路径 × 会话时区 → 落库语义」的映射。这是唯一在**空库上也能出结论**
          的一种，因为它测的是引擎与驱动的行为，不依赖存量数据。
          ⚠️ 只写 TEMP 表并在事务结束时 ROLLBACK，不碰任何业务表。
  ②分布法  对每个时间列做小时直方图：若峰值整体偏移 +08:00（本地工作时段的样子），
          说明落库值是本地时间。**需要存量数据**——没有数据就如实报"无判定依据"。
  ③交叉法  同会话内 `chat_messages.timestamp` 与 serial `id` 的单调性违例数，
          违例规模指示混用程度。**同样需要存量数据**。

产出 `docs/reference/timestamp-audit.md`。混杂到行级不可判定时记 `unknown`，
并按 05 §4.1 的要求采用保守转换（不猜测偏移，标注数据质量降级）。

⚠️ **一条必须写进结论的边界（台账 C20）**：仓库里现存的真库快照来自 2026-10-11 那次导出，
而那个原真库已随 Docker 数据卷清空而**永久消失**，本机也没有别的 PG 实例。所以
②③ 的**历史对象已不可复原**——今天在重建库上跑出的"无数据可判"不是暂时缺数据，
而是那一问在这台机器上永远不会再有对象。结论要这么写，不能写成"等有数据了再判"。

只读纪律：除 TEMP 表探针（写入即回滚）外不执行任何 DDL/DML；不改任何业务表。

用法：
    uv run python scripts/probe_timestamps.py                 # 需 DATABASE_URL，产出 timestamp-audit.md
    uv run python scripts/probe_timestamps.py --out -         # 只把 markdown 打到标准输出
    uv run python scripts/probe_timestamps.py --json          # 出 JSON（给别的脚本吃）
    uv run python scripts/probe_timestamps.py --session-tz UTC --session-tz Asia/Shanghai
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "reference" / "timestamp-audit.md"

# 探针用的已知时刻：刻意选在一个"整点但不是正午"的位置，
# 这样任何小时级偏移都能在直方图与文本比对里一眼看出，而分钟/秒级误差仍是 0。
PROBE_UTC = datetime(2026, 1, 1, 7, 8, 9, tzinfo=UTC)

# 会话时区候选。'UTC' 与 Asia/Shanghai(+08) 是本项目最可能遇到的两端：
# 前者是"转换后恰好等价于 naive"的无偏移情形，后者是生产容器里 TZ=Asia/Shanghai 的实际情形。
# 第三个键在运行时取库的 current_setting('TimeZone')，它才是"什么都不设"时真正生效的那个。
DEFAULT_SESSION_TZS = ("UTC", "Asia/Shanghai")

# 三条写入路径。名字会直接进报告，别改得太抽象。
WRITE_PATHS = (
    "sql_literal_utc_wallclock",   # 把 UTC 挂钟值当字面量塞进 naive 列（不经过任何转换）
    "sql_now_at_tz_utc",          # 05 §4.1 点名的这条：now() AT TIME ZONE 'UTC'
    "python_aware_datetime_utc",  # datetime.now(UTC) / 固定 aware 值，经驱动落库
)

NAIVE_TYPE = "timestamp without time zone"
AWARE_TYPE = "timestamp with time zone"

# 每个时间列的判定值域。unknown 是刻意留下的：05 §4.1 明确"混杂时按行不可判定 → 记录为 unknown"。
VERDICTS = ("utc", "local", "mixed", "unknown", "no_data", "aware", "no_column")


def inventory_columns(conn) -> list[dict[str, Any]]:
    """列出所有时间列及其类型。判定表的行就来自这里，不由 ORM 声明推导。"""
    from sqlalchemy import text

    rows = conn.execute(text("""
        SELECT table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type IN ('timestamp without time zone', 'timestamp with time zone')
        ORDER BY table_name, column_name
    """))
    return [dict(r._mapping) for r in rows]


def server_facts(conn) -> dict[str, Any]:
    from sqlalchemy import text

    facts = {}
    for key, sql in (
        ("timezone", "SHOW timezone"),
        ("log_timezone", "SHOW log_timezone"),
        ("server_version", "SHOW server_version"),
    ):
        facts[key] = conn.execute(text(sql)).scalar()
    return facts


def classify_offset(offset_seconds: float) -> tuple[str, bool]:
    """把"落库值 − 真值"的秒差翻译成判定。

    单独成函数是因为这是全脚本唯一的**结论生成点**：判错了，报告里的
    UTC/本地就是错的，而那正是 `05 §4.2` 转换迁移的输入。它必须能脱离数据库被测。

    容差 5 秒：探针绕不开时钟粒度与网络往返，但时区偏移永远是整小时，
    所以"5 秒以内算零偏移、其余要求落在整小时上"不会把 +08:00 误判成 0。
    """
    if abs(offset_seconds) < 5:
        return "utc", True
    hours = offset_seconds / 3600.0
    if abs(hours - round(hours)) < 5 / 3600.0:
        return "local", True
    return "unknown", False


def probe_write_paths(engine, session_tzs: list[str]) -> list[dict[str, Any]]:
    """①探针法：写入已知时刻，读回文本与 epoch，算出偏移。

    每组合都开**自己的连接**（会话时区是连接级的），建 TEMP 表，事务结束时 ROLLBACK。
    报告里存的是"读回的挂钟文本"而不是只存偏移量——文本能自证，偏移量要读者相信算法。
    """
    results: list[dict[str, Any]] = []
    for tz in session_tzs:
        for path in WRITE_PATHS:
            with engine.connect() as conn:
                conn.exec_driver_sql("BEGIN")
                conn.exec_driver_sql(f"SET LOCAL TIME ZONE '{tz}'")  # noqa: S608 —— tz 来自内置白名单
                conn.exec_driver_sql(
                    "CREATE TEMP TABLE _probe_ts (id int PRIMARY KEY, ts timestamp without time zone)"
                    " ON COMMIT DROP"
                )
                true_epoch = PROBE_UTC.timestamp()
                if path == "sql_literal_utc_wallclock":
                    literal = PROBE_UTC.strftime("%Y-%m-%d %H:%M:%S")
                    conn.exec_driver_sql(
                        "INSERT INTO _probe_ts VALUES (1, %s::timestamp)", (literal,)
                    )
                elif path == "sql_now_at_tz_utc":
                    # 05 §4.1 点名的写法。它取的是 **PG 自己的时钟**，所以真值不能是 PROBE_UTC，
                    # 只能在写入前后各取一次 PG 的 epoch 当作区间（见 lower/upper）。
                    conn.exec_driver_sql(
                        "INSERT INTO _probe_ts SELECT 1, now() AT TIME ZONE 'UTC'"
                    )
                else:
                    # 经驱动传一个 aware datetime：这正是 backend 里 parent_chunk_store.py:95 那条路径
                    conn.exec_driver_sql(
                        "INSERT INTO _probe_ts VALUES (1, %s)", (PROBE_UTC,)
                    )

                row = conn.exec_driver_sql(
                    "SELECT ts::text, extract(epoch from ts), "
                    "  to_char(ts, 'YYYY-MM-DD HH24:MI:SS')"
                    " FROM _probe_ts WHERE id = 1"
                ).one()
                stored_text, stored_epoch, stored_wall = row[0], float(row[1]), row[2]

                if path == "sql_now_at_tz_utc":
                    # 用 PG 自己的时钟当真值区间，避免拿宿主机时钟去比容器时钟（两者可差秒级）
                    pg_epoch = float(conn.exec_driver_sql("SELECT extract(epoch from now())").scalar())
                    reference = "pg_now"
                    offset_seconds = stored_epoch - pg_epoch
                else:
                    reference = "fixed_instant"
                    offset_seconds = stored_epoch - true_epoch

                conn.rollback()  # 探针表与这条 SET 都不留痕

            # 期望挂钟：若语义是 UTC，落库文本应等于 PROBE_UTC 的 UTC 挂钟
            expected_utc_wall = PROBE_UTC.strftime("%Y-%m-%d %H:%M:%S")
            offset_hours = offset_seconds / 3600.0
            verdict, whole = classify_offset(offset_seconds)
            results.append({
                "session_tz": tz,
                "write_path": path,
                "reference": reference,
                "stored_text": stored_text,
                "stored_wallclock": stored_wall,
                "offset_seconds": round(offset_seconds, 3),
                "offset_hours": round(offset_hours, 3),
                "is_whole_hour_offset": whole,
                "verdict": verdict,
                "expected_utc_wallclock": expected_utc_wall,
                "matches_utc_wallclock": stored_wall == expected_utc_wall,
            })
    return results


def distribution_histogram(conn, table: str, column: str) -> dict[str, Any]:
    """②分布法：小时直方图。空表如实报 no_data，不猜。"""
    from sqlalchemy import text

    # 表名/列名来自 information_schema 的查询结果，不是用户输入；仍用引号包起来更稳
    sql = text(
        f'SELECT extract(hour FROM "{column}")::int AS hr, count(*) AS n '  # noqa: S608
        f'FROM "{table}" WHERE "{column}" IS NOT NULL GROUP BY hr ORDER BY hr'
    )
    try:
        buckets = {int(r[0]): int(r[1]) for r in conn.execute(sql)}
    except Exception as exc:  # 表不存在 / 无权限：分开报，不当成"分布平坦"
        return {"table": table, "column": column, "verdict": "unknown", "error": str(exc)[:200]}
    total = sum(buckets.values())
    if total == 0:
        return {"table": table, "column": column, "verdict": "no_data", "rows": 0, "histogram": {}}
    peak = max(buckets, key=buckets.get)
    return {
        "table": table,
        "column": column,
        "verdict": "has_data",
        "rows": total,
        "histogram": buckets,
        "peak_hour": peak,
        "peak_share": round(buckets[peak] / total, 3),
    }


def cross_monotonicity(conn) -> dict[str, Any]:
    """③交叉法：同会话内 timestamp 随 serial id 应单调不减；违例数指示混用规模。

    分组键是 `chat_messages.session_ref_id`（整数外键 → chat_sessions.id），**不是** `session_id`——
    第一版按名字猜写成 session_id，直接报 UndefinedColumn。列名一律以库里的实际结构为准，
    这也是本脚本存在的理由：它判的是库，不是声明。
    `id` 是全局 serial，所以"同一 session_ref_id 内 id 递增"就等于"插入顺序递增"。
    """
    from sqlalchemy import text

    try:
        rows = conn.execute(text("""
            SELECT session_ref_id,
                   count(*) AS n,
                   count(*) FILTER (
                     WHERE prev_ts IS NOT NULL AND ts < prev_ts
                   ) AS violations
            FROM (
              SELECT session_ref_id, timestamp AS ts,
                     lag(timestamp) OVER (PARTITION BY session_ref_id ORDER BY id) AS prev_ts
              FROM chat_messages
            ) s
            GROUP BY session_ref_id
            HAVING count(*) > 1
        """))
        per_session = [dict(r._mapping) for r in rows]
    except Exception as exc:
        return {"method": "chat_messages id vs timestamp", "verdict": "unknown",
                "error": str(exc)[:200]}
    sessions = len(per_session)
    viol = sum(int(p["violations"]) for p in per_session)
    if sessions == 0:
        return {"method": "chat_messages id vs timestamp", "verdict": "no_data",
                "sessions_checked": 0, "violations": 0}
    return {
        "method": "chat_messages id vs timestamp",
        "verdict": "mixed" if viol else "monotonic",
        "sessions_checked": sessions,
        "violations": viol,
        "worst_session": max(per_session, key=lambda p: int(p["violations"])) if viol else None,
    }


def per_column_verdicts(columns: list[dict[str, Any]], distribution: list[dict[str, Any]],
                        probes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把三种方法的结论合成"每表每列一行判定"，这是 05 §4.1 要的交付形状。

    判定优先级：
      - 列本身是 timestamptz → `aware`（语义无歧义，本节的担忧不适用）
      - naive 列：有存量数据 → 由分布法给结论；无数据 → `no_data`
      - 附一列"写入路径语义"：来自探针法，说明**今后**写进去的值会被存成什么
    """
    dist_by_key = {(d["table"], d["column"]): d for d in distribution}
    # 探针法里最要紧的一条：什么都不设（库的会话默认时区）时，aware 写入是否被偏移
    aware_offsets = {
        (p["session_tz"], p["write_path"]): p["offset_hours"]
        for p in probes if p["write_path"] == "python_aware_datetime_utc"
    }
    out = []
    for c in columns:
        key = (c["table_name"], c["column_name"])
        d = dist_by_key.get(key, {})
        if c["data_type"] == AWARE_TYPE:
            verdict = "aware"
        elif d.get("verdict") in ("has_data",):
            verdict = "mixed" if d.get("peak_share", 0) >= 0.5 else "unknown"
        elif d.get("verdict") == "no_data":
            verdict = "no_data"
        else:
            verdict = "unknown"
        out.append({
            "table": c["table_name"],
            "column": c["column_name"],
            "data_type": c["data_type"],
            "verdict": verdict,
            "rows": d.get("rows", "未统计"),
            "write_path_offsets_aware": aware_offsets,
        })
    return out


def build_report(facts, columns, probes, distribution, cross, per_column) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "scripts/probe_timestamps.py（05 §4.1 三法；探针只写 TEMP 表并 ROLLBACK）",
        "server": facts,
        "naive_timestamp_columns": sum(1 for c in columns if c["data_type"] == NAIVE_TYPE),
        "aware_timestamp_columns": sum(1 for c in columns if c["data_type"] == AWARE_TYPE),
        "probe_write_paths": probes,
        "distribution": distribution,
        "cross_check": cross,
        "per_column": per_column,
        "limits": [
            "②分布法与③交叉法判的是**存量数据**的语义。2026-10-11 导出快照的那个原真库已随"
            " Docker 数据卷清空而永久消失（台账 C20），本机也无原生 PG，所以这两法在重建库上"
            "**永远没有对象**——报 no_data 不是'等以后有数据'，而是那一问在这台机器上不再可判。",
            "①探针法测的是引擎与驱动的行为，与存量无关，因此在新库上的结论依然成立："
            "naive 列里 aware 值会被按会话时区偏移后丢弃偏移。",
            "本脚本不执行任何 DDL，也不改任何业务表；探针表是 TEMP + ON COMMIT DROP + ROLLBACK。",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report["server"]
    lines = [
        "# 时间列语义审计（`05` §4.1 / X6 第三问）",
        "",
        f"> 生成：{report['generated_at']} · 取数命令：`uv run python scripts/probe_timestamps.py`",
        f"> 引擎：PostgreSQL {s.get('server_version')} · 会话 `timezone` = `{s.get('timezone')}` · "
        f"`log_timezone` = `{s.get('log_timezone')}`",
        f"> 时间列总数：naive `{report['naive_timestamp_columns']}` 个 / "
        f"aware `{report['aware_timestamp_columns']}` 个",
        "",
        "## 1. 探针法：写入路径 × 会话时区 → 落库语义",
        "",
        "已知时刻 `2026-01-01 07:08:09+00:00`。`偏移(小时)` 是"
        "`extract(epoch from 落库值) − 真值 epoch` 再除以 3600；0 表示落库值就是 UTC 挂钟。",
        "",
        "| 会话时区 | 写入路径 | 落库挂钟 | 偏移(小时) | 判定 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in report["probe_write_paths"]:
        lines.append(
            f"| `{p['session_tz']}` | `{p['write_path']}` | `{p['stored_wallclock']}` | "
            f"{p['offset_hours']} | {p['verdict']} |"
        )
    lines += [
        "",
        "**读法**：`sql_literal_utc_wallclock` 是「把 UTC 挂钟原样塞进 naive 列」，偏移必为 0，"
        "它是另外两条的参照。真正说明问题的是另外两条：",
        "",
        "- `sql_now_at_tz_utc`（`05 §4.1` 点名的写法）：值来自 **PG 自己的时钟**，"
        "`AT TIME ZONE 'UTC'` 把 timestamptz 转成 UTC 挂钟的 naive 值，所以这条路径**与"
        "会话时区无关**，落库语义恒为 UTC。",
        "- `python_aware_datetime_utc`：经驱动传一个 **aware** datetime。PG 会先按会话 "
        "`TimeZone` 把绝对时刻换算成挂钟、再丢弃偏移，所以落库值随会话时区偏移 —— "
        "**这就是 `05 §4` 说的「不能假定为 UTC」**。",
        "",
        "## 2. 分布法：小时直方图",
        "",
        "| 表.列 | 行数 | 峰值小时 | 峰值占比 | 判定 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for d in report["distribution"]:
        if d.get("verdict") == "no_data":
            lines.append(f"| `{d['table']}.{d['column']}` | 0 | — | — | **no_data** |")
        elif d.get("verdict") == "has_data":
            lines.append(
                f"| `{d['table']}.{d['column']}` | {d['rows']} | {d['peak_hour']}:00 | "
                f"{d['peak_share']:.0%} | {d['verdict']} |"
            )
        else:
            lines.append(f"| `{d['table']}.{d['column']}` | 统计失败 | — | — | unknown（{d.get('error','')}）|")
    c = report["cross_check"]
    lines += [
        "",
        "## 3. 交叉法：`chat_messages` 的 timestamp 与 serial id 单调性",
        "",
        f"- 方法：{c['method']}",
        f"- 判定：**{c['verdict']}**（检查 {c.get('sessions_checked', '—')} 个多消息会话，"
        f"违例 {c.get('violations', '—')} 处）",
    ]
    if c.get("error"):
        lines.append(f"- 报错：`{c['error']}`")
    lines += ["", "## 4. 每表每列判定（`05 §4.1` 要的交付形状）", "",
              "| 表 | 列 | 类型 | 存量行数 | 判定 |", "| --- | --- | --- | --- | --- |"]
    for row in report["per_column"]:
        marker = "`timestamp` naive" if row["data_type"] == NAIVE_TYPE else "`timestamptz` aware"
        lines.append(f"| `{row['table']}` | `{row['column']}` | {marker} | {row['rows']} | "
                     f"**{row['verdict']}** |")
    lines += ["", "## 5. 本报告的边界（不写清就等于夸大结论）", ""]
    for lim in report["limits"]:
        lines.append(f"- {lim}")
    lines += [
        "",
        "## 6. 对 `05 §4.2` 转换迁移的后果",
        "",
        "- 探针法给出的结论是**面向今后**的：只要列还是 naive，aware 写入就会被会话时区偏移。"
        "这一条与有没有存量数据无关，所以它仍然成立。",
        "- 分布法/交叉法原本用来判**存量**该按哪个偏移转回来；存量对象已不可复原（C20），"
        "因此 `05 §4.2` 那条 `USING col AT TIME ZONE 'UTC'` 的**猜测风险**在当前这台机器上"
        "没有可判的输入。**不要把它当成「已验证可以转换」**——应记为「无存量数据，转换风险"
        "未评估」，并在真有带数据的库上做（或按 `05 §4.2` 的前置表先在克隆库演练）。",
        "- `05 §2.6` 已拍板新表一律 `TIMESTAMPTZ`，所以增量部分（如 `ai_executions`）不继承这个问题。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"markdown 输出路径（默认 {DEFAULT_OUT}；用 - 表示打到标准输出）")
    ap.add_argument("--json", action="store_true", help="把结构化结果打到标准输出")
    ap.add_argument("--database-url", default=None, help="缺省读环境变量 DATABASE_URL")
    ap.add_argument("--session-tz", action="append", dest="session_tzs", default=None,
                    help="覆盖探针用的会话时区列表（可重复）；缺省 UTC 与 Asia/Shanghai 再加库的当前值")
    args = ap.parse_args(argv)

    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("[timestamps] 拒跑：没有 DATABASE_URL。本脚本的方法②③需要真实库，"
              "①探针法也需要连库执行——没有库时它只能产出假结论，所以这里不把"
              "「跑不了」说成「跑过了」。")
        return 2

    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        print(f"[timestamps] 缺依赖: {exc}")
        return 2

    engine = create_engine(url)
    with engine.connect() as conn:
        facts = server_facts(conn)
        columns = inventory_columns(conn)
    if not columns:
        print("[timestamps] 库里没有任何时间列——先确认 alembic upgrade head 是否跑过。")
        return 2

    session_tzs = list(args.session_tzs or DEFAULT_SESSION_TZS)
    current = str(facts.get("timezone") or "UTC")
    if current not in session_tzs:
        session_tzs.append(current)  # "什么都不设时真正生效的那个"必须测

    probes = probe_write_paths(engine, session_tzs)

    with engine.connect() as conn:
        distribution = []
        for c in columns:
            if c["table_name"] == "alembic_version":
                continue
            distribution.append(distribution_histogram(conn, c["table_name"], c["column_name"]))
        cross = cross_monotonicity(conn)

    per_column = per_column_verdicts(columns, distribution, probes)
    report = build_report(facts, columns, probes, distribution, cross, per_column)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    md = render_markdown(report)
    if str(args.out) == "-":
        print(md)
    else:
        args.out.write_text(md, encoding="utf-8", newline="\n")
        naive = report["naive_timestamp_columns"]
        print(f"[timestamps] 已写出 {args.out}：{len(per_column)} 个时间列"
              f"（naive {naive} / aware {report['aware_timestamp_columns']}），"
              f"探针 {len(probes)} 组，分布法可判 {sum(1 for d in distribution if d.get('verdict') == 'has_data')} 列")
    return 0


if __name__ == "__main__":
    sys.exit(main())
