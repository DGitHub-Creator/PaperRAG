"""Schema 核查与基线审计（09-milestone-p0 P0-2 / X6；方法与判定表见 05 §1、§2）。

两种模式**互不替代**，脚本会明确告诉你在跑哪一种：

  --check-baseline   离线：审 `server/migrations/` 里的 `.sql` 是否非破坏、幂等、有配对 down。
                     不需要数据库，本机可跑，也是单测的对象。
  （默认）live        只读连库核查：表集合、`alembic_version`、列级漂移、索引与约束、
                     数据体量、时区真相 → 产出 `docs/refactor/schema-baseline.json`。
                     **需要真实 PostgreSQL**；没有库就报错退出，绝不拿离线检查冒充它。

为什么基线不由 ORM 生成（05 §1 末、§2.2）：`init_db()` 曾在 alembic 失败时静默回退
`create_all`，所以库里可能是"9 张表 + 没有版本行"，也可能是"alembic 到一半"。
两种情况的物理结构不同（已知漂移：`ix_paper_nodes_id` 缺失、`paper_nodes.filename`
是唯一索引而非 UNIQUE 约束）。基线必须抄**实际**结构，不能抄**声明**。

只读纪律：本文件不出现任何 DDL 执行路径。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "server" / "migrations"
DEFAULT_OUT = ROOT / "docs" / "refactor" / "schema-baseline.json"

# ── 离线：基线迁移文件的非破坏性检查 ──────────────────────────────

# up 里出现这些词就是在动存量数据/结构，基线迁移必须只做"登记"。
DESTRUCTIVE_IN_UP = (
    re.compile(r"\bDROP\s+TABLE\b", re.I),
    re.compile(r"\bDROP\s+(COLUMN|CONSTRAINT|INDEX)\b", re.I),
    re.compile(r"\bTRUNCATE\b", re.I),
    re.compile(r"\bDELETE\s+FROM\b", re.I),
    re.compile(r"\bALTER\s+TABLE\b.*\bDROP\b", re.I),
)
CREATE_RE = re.compile(r"\bCREATE\s+(TABLE|INDEX|UNIQUE\s+INDEX)\b", re.I)
IF_NOT_EXISTS_RE = re.compile(r"\bIF\s+NOT\s+EXISTS\b", re.I)
DROP_IF_EXISTS_IN_DOWN_RE = re.compile(r"\bDROP\s+TABLE\s+IF\s+EXISTS\b", re.I)

UP_SUFFIX = ".up.sql"
DOWN_SUFFIX = ".down.sql"


def migration_pairs(migrations_dir: Path) -> list[tuple[str, Path | None, Path | None]]:
    """按版本号归组 `(version, up, down)`；缺哪边哪边就是 None。"""
    versions: dict[str, dict[str, Path]] = {}
    for p in sorted(migrations_dir.glob("*.sql")):
        name = p.name
        if name.endswith(UP_SUFFIX):
            versions.setdefault(name[: -len(UP_SUFFIX)], {})["up"] = p
        elif name.endswith(DOWN_SUFFIX):
            versions.setdefault(name[: -len(DOWN_SUFFIX)], {})["down"] = p
        else:
            versions.setdefault(name[: -len(".sql")], {})["bare"] = p
    out = []
    for ver, files in versions.items():
        out.append((ver, files.get("up"), files.get("down")))
    return out


def _statements(sql: str) -> list[str]:
    """去注释后按分号切句。注释里出现的 DROP/CREATE 不算数——基线文件大量在讲历史。"""
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    body = re.sub(r"--[^\n]*", "", body)
    return [s.strip() for s in body.split(";") if s.strip()]


def check_baseline(migrations_dir: Path) -> list[str]:
    """返回违规条目列表；空列表 = 基线满足 05 §2 的非破坏 + 幂等纪律。"""
    errors: list[str] = []
    pairs = migration_pairs(migrations_dir)
    if not pairs:
        return [f"{migrations_dir.name}/ 里没有任何迁移文件——基线尚未产出（P0-2 需要真库核查）"]

    for ver, up, down in pairs:
        if up is None:
            errors.append(f"{ver}: 缺 {ver}{UP_SUFFIX}")
            continue
        text = up.read_text(encoding="utf-8")
        for i, stmt in enumerate(_statements(text), 1):
            for pat in DESTRUCTIVE_IN_UP:
                if pat.search(stmt):
                    errors.append(
                        f"{up.name} 第 {i} 句含破坏性操作 `{pat.pattern}`：基线只登记现有结构"
                    )
            if CREATE_RE.search(stmt) and not IF_NOT_EXISTS_RE.search(stmt):
                kind = CREATE_RE.search(stmt).group(1)
                errors.append(
                    f"{up.name} 第 {i} 句的 CREATE {kind} 没有 IF NOT EXISTS：存量库上重复执行会报错"
                )
        if down is None:
            errors.append(f"{ver}: 缺 {ver}{DOWN_SUFFIX}（migrate 要求成对）")
        elif DROP_IF_EXISTS_IN_DOWN_RE.search(down.read_text(encoding="utf-8")):
            errors.append(
                f"{down.name}: 出现 `DROP TABLE IF EXISTS`。05 §2 的幂等纪律禁止用它把"
                "'库里本来就没这张表' 当成回退成功——要写就写无 IF EXISTS 的真实回退"
            )
    return errors


# ── live：只读核查（需要真实 PG） ────────────────────────────────

LIVE_SQL = {
    "tables": """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """,
    "columns": """
        SELECT table_name, column_name, data_type, is_nullable,
               column_default, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """,
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname",
    # 唯一性只查 constraint：05 §1 记录过 filename 是 unique index 而非 constraint，
    # 两件事分开查才能把这种漂移暴露出来，而不是让 sqlc 误以为没有约束。
    "constraints": """
        SELECT relname AS table_name, conname, contype
        FROM pg_constraint c JOIN pg_class r ON r.oid = c.conrelid
        WHERE r.relnamespace = 'public'::regnamespace AND contype IN ('p','u','f','c')
        ORDER BY relname, conname
    """,
    "alembic_version": "SELECT version_num FROM alembic_version",
    "session_timezone": "SHOW timezone",
    "log_timezone": "SHOW log_timezone",
    "server_version": "SHOW server_version",
}


def alembic_state(rows: list[str] | None) -> str:
    """把三种情形分开：表不存在 / 表在但无行 / 有 head。含义完全不同（05 §1）。"""
    if rows is None:
        return "no_table"          # 曾走 create_all，从未跑过 alembic
    if not rows:
        return "empty_table"       # 跑过 alembic 但被清过，最危险的一种
    return "head:" + ",".join(sorted(rows))


def collect_live(database_url: str) -> dict[str, Any]:
    """只读地拉结构快照。任何写操作都不在这里发生。"""
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    snapshot: dict[str, Any] = {}
    with engine.connect() as conn:
        for key, sql in LIVE_SQL.items():
            if key == "alembic_version":
                try:
                    snapshot[key] = [r[0] for r in conn.execute(text(sql))]
                except Exception:
                    snapshot[key] = None
                continue
            if key == "tables":
                snapshot[key] = [r[0] for r in conn.execute(text(sql))]
                continue
            if key in ("session_timezone", "log_timezone", "server_version"):
                snapshot[key] = conn.execute(text(sql)).scalar()
                continue
            snapshot[key] = [dict(m._mapping) for m in conn.execute(text(sql))]
    snapshot["state"] = alembic_state(snapshot["alembic_version"])
    engine.dispose()
    return snapshot


def orm_column_types() -> dict[str, dict[str, str]]:
    """ORM 声明侧的 {表: {列: PG 类型串}}。

    必须用 postgresql dialect 编译：默认 dialect 会把 `DateTime` 渲染成 `DATETIME`、
    `String` 渲染成 `VARCHAR`，和 `information_schema` 说的不是一种语言，diff 会全线误报。
    """
    sys.path.insert(0, str(ROOT))
    from sqlalchemy.dialects import postgresql

    from backend.core.database import Base
    import backend.core.models  # noqa: F401  注册全部表到 Base.metadata

    dialect = postgresql.dialect()
    return {
        table.name: {c.name: str(c.type.compile(dialect=dialect)) for c in table.columns}
        for table in Base.metadata.sorted_tables
    }


# information_schema 用的是 SQL 标准名，DDL 侧用的是 PG 简称，同一类型两个写法（05 §1 的列级 diff 先跨这层）。
_PG_INFO_SCHEMA_NAMES = {
    "character varying": "varchar",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamptz",
    "double precision": "float8",
}


def _norm_type(raw: Any) -> str:
    s = re.sub(r"\s*\(.*?\)", "", str(raw)).strip().lower()
    return _PG_INFO_SCHEMA_NAMES.get(s, s)


def diff_columns(live_columns: list[dict], declared: dict[str, dict[str, str]]) -> list[dict]:
    """逐字段 diff：库里有声明没有 / 声明有库里没有 / 同名但类型不符 / 库里没有 DEFAULT。"""
    actual: dict[str, dict[str, dict]] = {}
    for row in live_columns:
        actual.setdefault(row["table_name"], {})[row["column_name"]] = row

    diffs: list[dict] = []
    for name in sorted(set(actual) | set(declared)):
        a, d = actual.get(name, {}), declared.get(name, {})
        for col in sorted(set(a) | set(d)):
            if col not in a:
                diffs.append({"table": name, "column": col, "kind": "only_in_orm"})
            elif col not in d:
                diffs.append({"table": name, "column": col, "kind": "only_in_db"})
            else:
                got, want = _norm_type(a[col].get("data_type", "")), _norm_type(d[col])
                if got != want:
                    diffs.append(
                        {
                            "table": name,
                            "column": col,
                            "kind": "type",
                            "db": a[col].get("data_type"),
                            "orm": d[col],
                        }
                    )
                if a[col].get("column_default") is None:
                    # "值由应用写"这条对 Go 是硬约束：Python 侧的 `default=datetime.utcnow`
                    # 不进 DDL，Go 不显式赋值就会撞 NOT NULL violation。
                    diffs.append(
                        {"table": name, "column": col, "kind": "no_server_default", "db": got}
                    )
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-baseline", action="store_true", help="离线审迁移文件（不需数据库）")
    ap.add_argument("--live", action="store_true", help="连库只读核查（需 DATABASE_URL）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--database-url", default=None, help="缺省读环境变量 DATABASE_URL")
    args = ap.parse_args(argv)

    if args.check_baseline:
        errs = check_baseline(MIGRATIONS)
        if errs:
            print(f"[schema] 基线检查不通过，共 {len(errs)} 条：")
            for e in errs:
                print(f"  - {e}")
            return 1
        print(f"[schema] 基线非破坏 + 幂等检查通过（{MIGRATIONS}）")
        return 0

    if args.live:
        url = args.database_url or os.environ.get("DATABASE_URL")
        if not url:
            print("[schema] --live 需要 DATABASE_URL。本机没有 PG 时请只跑 --check-baseline，"
                  "并把 X6 记为 not_run，不要用离线检查冒充真库核查。")
            return 2
        live = collect_live(url)
        payload = {
            "source": "live-postgres",
            "tables": live["tables"],
            "alembic": live["state"],
            "session_timezone": live["session_timezone"],
            "log_timezone": live["log_timezone"],
            "server_version": live["server_version"],
            "indexes": live["indexes"],
            "constraints": live["constraints"],
            "column_diff": diff_columns(live["columns"], orm_column_types()),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[schema] 已写 {args.out.relative_to(ROOT)}（{len(payload['tables'])} 表，"
              f"alembic={payload['alembic']}，列漂移 {len(payload['column_diff'])} 条）")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
