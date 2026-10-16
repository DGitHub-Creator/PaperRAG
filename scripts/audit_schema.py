"""Schema 核查与基线审计（09-milestone-p0 P0-2 / X6；方法与判定表见 05 §1、§2）。

两种模式**互不替代**，脚本会明确告诉你在跑哪一种：

  --check-baseline   离线：审 `server/migrations/` 里的 `.sql` 是否非破坏、幂等、有配对 down。
                     不需要数据库，本机可跑，也是单测的对象。
  --verify-columns   离线：把迁移里的列定义逐列比到基线快照的 `columns` 段（类型含 varchar
                     长度、NOT NULL、有无 DEFAULT）。**需要快照里已有 columns**（旧快照没有，
                     此时如实退出 2，绝不静默通过）。
  （默认）live        只读连库核查：表集合、`alembic_version`、列级漂移、索引与约束、
                     数据体量、时区真相 → 产出 `docs/reference/schema-baseline.json`。
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
DEFAULT_OUT = ROOT / "docs" / "reference" / "schema-baseline.json"

sys.path.insert(0, str(ROOT))
from scripts.schema_compare import diff_columns as diff_columns, orm_column_specs

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


def _strip_comments(sql: str) -> str:
    """去掉 `--` 与 `/* */` 注释。up 与 down 必须走同一套规则，否则"注释算不算数"
    在两边不一致，写基线的人只能靠猜（12-known-code-issues C2）。"""
    body = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", body)


def _statements(sql: str) -> list[str]:
    """去注释后按分号切句。注释里出现的 DROP/CREATE 不算数——基线文件大量在讲历史。"""
    return [s.strip() for s in _strip_comments(sql).split(";") if s.strip()]


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
                    errors.append(f"{up.name} 第 {i} 句含破坏性操作 `{pat.pattern}`：基线只登记现有结构")
            if CREATE_RE.search(stmt) and not IF_NOT_EXISTS_RE.search(stmt):
                kind = CREATE_RE.search(stmt).group(1)
                errors.append(f"{up.name} 第 {i} 句的 CREATE {kind} 没有 IF NOT EXISTS：存量库上重复执行会报错")
        if down is None:
            errors.append(f"{ver}: 缺 {ver}{DOWN_SUFFIX}（migrate 要求成对）")
        elif DROP_IF_EXISTS_IN_DOWN_RE.search(_strip_comments(down.read_text(encoding="utf-8"))):
            errors.append(f"{down.name}: 语句里出现 `DROP TABLE IF EXISTS`。05 §2 的幂等纪律禁止用它把'库里本来就没这张表' 当成回退成功——要写就写无 IF EXISTS 的真实回退")
    return errors


# ── 离线：基线 DDL 与真库快照的逐列比对（12-known-code-issues C1）──────

CREATE_TABLE_HEAD_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(?P<name>[A-Za-z_][\w]*)\"?\s*\(", re.I)
# 表级约束行不是列，抽列时要整行跳过
TABLE_CONSTRAINT_START_RE = re.compile(r"^(CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK|EXCLUDE)\b", re.I)
_TYPE_LEN_RE = re.compile(r"\(([^)]*)\)")

# DDL 侧写法 → information_schema 的 SQL 标准名；第二项是 SERIAL 这类"DDL 不写 DEFAULT
# 但库里有 nextval"的隐式默认，比 Default 时必须按库侧口径算，否则每次比都假红。
_DDL_TO_INFO_TYPE = {
    "serial": ("integer", True),
    "bigserial": ("bigint", True),
    "smallserial": ("smallint", True),
    "int": ("integer", False),
    "integer": ("integer", False),
    "bigint": ("bigint", False),
    "smallint": ("smallint", False),
    "varchar": ("character varying", False),
    "character varying": ("character varying", False),
    "char": ("character", False),
    "text": ("text", False),
    "timestamp": ("timestamp without time zone", False),
    "timestamp without time zone": ("timestamp without time zone", False),
    "timestamp with time zone": ("timestamp with time zone", False),
    "timestamptz": ("timestamp with time zone", False),
    "date": ("date", False),
    "json": ("json", False),
    "jsonb": ("jsonb", False),
    "bool": ("boolean", False),
    "boolean": ("boolean", False),
    "double precision": ("double precision", False),
    "float8": ("double precision", False),
    "real": ("real", False),
    "numeric": ("numeric", False),
    "uuid": ("uuid", False),
    "bytea": ("bytea", False),
}


def _split_top_level(text: str) -> list[str]:
    """按**顶层**逗号切表体：`VARCHAR(255)` 与 `DEFAULT '{}'` 里的逗号不是分隔符。"""
    parts: list[str] = []
    depth, quote, cur = 0, "", []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _table_body(sql: str, open_at: int) -> tuple[str, int]:
    """从 `(` 之后扫到配对的 `)`，返回 `(表体, 闭括号位置)`。字符串字面量里的括号不算。"""
    depth, i, quote = 1, open_at, ""
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return sql[open_at:i], i
        i += 1
    raise ValueError("CREATE TABLE 的括号没有闭合")


def _column_spec(rest: str) -> dict[str, Any]:
    """把 `VARCHAR(100) NOT NULL DEFAULT ''` 归一成可比对的四个维度。"""
    tokens = rest.split()
    base, used = "", 0
    for n in (3, 2, 1):
        # `VARCHAR(100)` 是一个 token，先把长度后缀摘掉才对得上类型词表
        cand = re.sub(r"\s*\([^)]*\)", "", " ".join(tokens[:n]).lower()).strip()
        if cand in _DDL_TO_INFO_TYPE:
            base, used = cand, n
            break
    if not base:
        raise ValueError(f"无法识别的列类型：{rest!r}")
    info_type, implicit_default = _DDL_TO_INFO_TYPE[base]
    length = None
    if m := _TYPE_LEN_RE.search(" ".join(tokens[:used])):
        length = m.group(1).strip()
    tail = " ".join(tokens[used:]).lower()
    return {
        "type": info_type,
        "length": length,
        "nullable": not bool(re.search(r"\bnot\s+null\b", tail)),
        "has_default": bool(re.search(r"\bdefault\b", tail)) or "generated" in tail or "identity" in tail,
        "serial": implicit_default,
    }


def parse_ddl_columns(sql: str) -> dict[str, dict[str, dict[str, Any]]]:
    """从迁移 DDL 抽 `{表: {列: 规格}}`。

    只认本项目受控的 DDL 形状（`CREATE TABLE … ( 列 类型 [NOT NULL] [DEFAULT …], CONSTRAINT … )`），
    不是通用 SQL 解析器：表级约束行整行跳过，其它方言写法（LIKE / 分区表）不认，遇到不认识的
    类型直接抛错而不是猜——猜错就等于把失真放过去。
    """
    body = _strip_comments(sql)
    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for m in CREATE_TABLE_HEAD_RE.finditer(body):
        ddl, _ = _table_body(body, m.end())
        cols: dict[str, dict[str, Any]] = {}
        for item in _split_top_level(ddl):
            item = item.strip()
            if not item or TABLE_CONSTRAINT_START_RE.match(item):
                continue
            name, rest = item.split(None, 1)
            cols[name.strip('"')] = _column_spec(rest)
        tables[m.group("name")] = cols
    return tables


def verify_columns(migrations_dir: Path, snapshot: dict[str, Any]) -> tuple[list[str], list[str]]:
    """逐列比对，返回 `(错误, 提示)`。快照缺 columns 段时不在这里判定（由调用方拒跑）。

    只比快照覆盖到的表：后续迁移新增的表本来就不在这份快照里，把它算成错误会让"每加一张表
    都要先重导快照"，那是把检查废掉的节奏。
    """
    errors: list[str] = []
    notes: list[str] = []
    live: dict[str, dict[str, dict]] = {}
    for row in snapshot["columns"]:
        live.setdefault(row["table_name"], {})[row["column_name"]] = row

    ddl: dict[str, dict[str, dict[str, Any]]] = {}
    for up in sorted(migrations_dir.glob("*" + UP_SUFFIX)):
        for table, cols in parse_ddl_columns(up.read_text(encoding="utf-8")).items():
            ddl.setdefault(table, {}).update(cols)

    snap_tables = set(snapshot.get("tables", []))
    if "schema_migrations" in snap_tables:
        # golang-migrate 自己管理的版本表，不应复制进业务迁移，但仍核对列形状。
        ddl["schema_migrations"] = parse_ddl_columns(
            "CREATE TABLE schema_migrations (version BIGINT NOT NULL, dirty BOOLEAN NOT NULL);"
        )["schema_migrations"]
        notes.append("schema_migrations: 由 golang-migrate 管理，按工具版本表形状核对")
    for table in sorted(snap_tables):
        ddl_cols, db_cols = ddl.get(table, {}), live.get(table, {})
        if not ddl_cols:
            errors.append(f"{table}: 快照里有这张表，但 migrations/ 的 up 文件不建它")
            continue
        for col in sorted(set(db_cols) | set(ddl_cols)):
            if col not in ddl_cols:
                errors.append(f"{table}.{col}: 真库有这一列，基线 DDL 没写")
                continue
            if col not in db_cols:
                errors.append(f"{table}.{col}: 基线 DDL 写了这一列，真库没有")
                continue
            spec, row = ddl_cols[col], db_cols[col]
            if row["data_type"] != spec["type"]:
                errors.append(f"{table}.{col}: 类型不一致 DDL={spec['type']} 真库={row['data_type']}")
            want_len, got_len = spec["length"], row.get("character_maximum_length")
            if want_len is not None and str(got_len) != str(want_len):
                errors.append(f"{table}.{col}: 长度不一致 DDL=({want_len}) 真库=({got_len})")
            elif want_len is None and got_len is not None:
                errors.append(f"{table}.{col}: 真库限长 {got_len}，但基线 DDL 没写长度")
            if spec["nullable"] != (row["is_nullable"] == "YES"):
                errors.append(f"{table}.{col}: NOT NULL 不一致 DDL={'NULL' if spec['nullable'] else 'NOT NULL'} 真库={row['is_nullable']}")
            db_has_default = row.get("column_default") is not None
            ddl_has_default = spec["has_default"] or spec["serial"]
            if ddl_has_default != db_has_default:
                errors.append(
                    f"{table}.{col}: DEFAULT 不一致 DDL={'有' if ddl_has_default else '无'}"
                    f" 真库={'有' if db_has_default else '无'}" + ("（SERIAL 的 nextval 按库侧口径算作有默认）" if spec["serial"] else "")
                )
    for table in sorted(set(ddl) - snap_tables):
        notes.append(f"{table}: 迁移建的这张表不在快照覆盖范围内（快照需要重导后才能比）")
    return errors, notes


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
        return "no_table"  # 曾走 create_all，从未跑过 alembic
    if not rows:
        return "empty_table"  # 跑过 alembic 但被清过，最危险的一种
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-baseline", action="store_true", help="离线审迁移文件（不需数据库）")
    ap.add_argument("--verify-columns", action="store_true", help="离线：把迁移 DDL 逐列比到快照的 columns 段（类型/长度/NOT NULL/DEFAULT）")
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

    if args.verify_columns:
        if not args.out.exists():
            print(f"[schema] 拒跑：快照 {args.out} 不存在。先跑 --live 导出。")
            return 2
        try:
            snapshot = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[schema] 拒跑：{args.out} 不是合法 JSON：{exc}")
            return 2
        if snapshot.get("columns") is None:
            print("[schema] 拒跑：这份快照没有 columns 段（旧版 --live 导出的）。重跑 `audit_schema.py --live` 拿到带列清单的快照再比。这里不把『比不了』说成『比过了』。")
            return 2
        errs, notes = verify_columns(MIGRATIONS, snapshot)
        for n in notes:
            print(f"[schema] 提示：{n}")
        if errs:
            print(f"[schema] 基线 DDL 与真库快照不一致，共 {len(errs)} 条：")
            for e in errs:
                print(f"  - {e}")
            return 1
        print(f"[schema] 基线 DDL 与真库快照逐列一致（{len(snapshot['columns'])} 列，类型/长度/NOT NULL/DEFAULT 四项均核对）")
        return 0

    if args.live:
        url = args.database_url or os.environ.get("DATABASE_URL")
        if not url:
            print("[schema] --live 需要 DATABASE_URL。本机没有 PG 时请只跑 --check-baseline，并把 X6 记为 not_run，不要用离线检查冒充真库核查。")
            return 2
        live = collect_live(url)
        payload = {
            "source": "live-postgres",
            "tables": live["tables"],
            "alembic": live["state"],
            "session_timezone": live["session_timezone"],
            "log_timezone": live["log_timezone"],
            "server_version": live["server_version"],
            # 列清单是 --verify-columns 的比对基准。缺了它，基线 DDL 的类型长度与 NOT NULL
            # 就只能靠人读（12-known-code-issues C1）。
            "columns": live["columns"],
            "indexes": live["indexes"],
            "constraints": live["constraints"],
            "column_diff": diff_columns(live["columns"], orm_column_specs()),
            "required_inputs": [{"table": c["table_name"], "column": c["column_name"]} for c in live["columns"] if c["is_nullable"] == "NO" and c["column_default"] is None],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[schema] 已写 {args.out.name}（{len(payload['tables'])} 表、{len(payload['columns'])} 列，alembic={payload['alembic']}，列漂移 {len(payload['column_diff'])} 条）")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
