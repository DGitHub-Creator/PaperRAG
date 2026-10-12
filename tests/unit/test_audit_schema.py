"""`scripts/audit_schema.py` 的离线部分单测（P0-2 / X6 的 mock 级证据）。

X6 本身要真库才能 pass，这里只保证**判定逻辑**是硬的：每条规则都给一个正向
输入和一个会被抓到的篡改输入。规则松一条，基线就可能带着 DROP 进存量库。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit_schema import (  # noqa: E402
    MIGRATIONS,
    alembic_state,
    check_baseline,
    diff_columns,
    parse_ddl_columns,
    verify_columns,
)

GOOD_UP = """
-- 登记现有结构，不新建任何东西
CREATE TABLE IF NOT EXISTS users (
    id INTEGER NOT NULL,
    username VARCHAR(100) NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);
"""
GOOD_DOWN = "DROP TABLE users;\n"


def _write(tmp: Path, up: str = GOOD_UP, down: str = GOOD_DOWN, name="000001_baseline"):
    d = tmp / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    if up is not None:
        (d / f"{name}.up.sql").write_text(up, encoding="utf-8")
    if down is not None:
        (d / f"{name}.down.sql").write_text(down, encoding="utf-8")
    return d


class TestCheckBaseline:
    def test_empty_dir_is_reported_not_silently_ok(self, tmp_path):
        (tmp_path / "migrations").mkdir()
        errs = check_baseline(tmp_path / "migrations")
        assert errs and "没有任何迁移文件" in errs[0]

    def test_compliant_baseline_passes(self, tmp_path):
        assert check_baseline(_write(tmp_path)) == []

    @pytest.mark.parametrize(
        "bad",
        [
            "DROP TABLE users;",
            "ALTER TABLE users DROP COLUMN role;",
            "TRUNCATE TABLE chat_messages;",
            "DELETE FROM users WHERE id = 1;",
            "DROP INDEX ix_users_username;",
        ],
    )
    def test_destructive_up_is_caught(self, tmp_path, bad):
        errs = check_baseline(_write(tmp_path, up=GOOD_UP + "\n" + bad + "\n"))
        assert any("破坏性操作" in e for e in errs), errs

    def test_create_without_if_not_exists_is_caught(self, tmp_path):
        errs = check_baseline(_write(tmp_path, up="CREATE TABLE users (id INTEGER);"))
        assert any("IF NOT EXISTS" in e for e in errs), errs

    def test_comment_text_does_not_count_as_ddl(self, tmp_path):
        """注释里讲历史（'曾经 DROP 过'）不该被判成破坏性操作——那会让没人写得清基线。"""
        up = "-- 本文件不含 DROP，只做登记\n" + GOOD_UP
        assert check_baseline(_write(tmp_path, up=up)) == []

    def test_missing_down_is_caught(self, tmp_path):
        errs = check_baseline(_write(tmp_path, down=None))
        assert any("000001_baseline.down.sql" in e for e in errs), errs

    def test_drop_table_if_exists_in_down_is_caught(self, tmp_path):
        errs = check_baseline(_write(tmp_path, down="DROP TABLE IF EXISTS users;"))
        assert any("DROP TABLE IF EXISTS" in e for e in errs), errs

    def test_down_rule_ignores_comments_just_like_up(self, tmp_path):
        """C2：up 剥注释、down 原文匹配是两套规则，写基线的人只能靠猜。
        现在两边一致——在注释里解释"为什么不用 IF EXISTS"不该被判违规。"""
        down = "-- 这里刻意不写 DROP TABLE IF EXISTS，理由见 05 §2\nDROP TABLE users;\n"
        assert check_baseline(_write(tmp_path, down=down)) == []


class TestAlembicState:
    """三种情形的含义完全不同（05 §1），不能都收成 '有/无'。"""

    def test_missing_table_means_create_all_was_used(self):
        assert alembic_state(None) == "no_table"

    def test_empty_table_is_its_own_state(self):
        assert alembic_state([]) == "empty_table"

    def test_head_is_reported(self):
        assert alembic_state(["21f6caf0b15b"]) == "head:21f6caf0b15b"


class TestDiffColumns:
    DECLARED = {"users": {"id": "INTEGER", "username": "VARCHAR(100)"}}

    @staticmethod
    def _row(name, data_type, nullable="NO", default=None):
        return {
            "table_name": "users",
            "column_name": name,
            "data_type": data_type,
            "is_nullable": nullable,
            "column_default": default,
        }

    @staticmethod
    def _row_in(table, name, data_type, default=None):
        return {
            "table_name": table,
            "column_name": name,
            "data_type": data_type,
            "is_nullable": "YES",
            "column_default": default,
        }

    def _live(self):
        # 与 DECLARED 逐字对齐的一版库结构
        return [self._row("id", "integer"), self._row("username", "character varying")]

    def test_aligned_shape_still_reports_missing_server_defaults(self):
        """Python 侧 `default=datetime.utcnow` 不进 DDL，库里没有 DEFAULT：
        这是真发现而不是噪声——Go 插入必须自己给这些列写值。"""
        diffs = diff_columns(self._live(), self.DECLARED)
        assert {d["kind"] for d in diffs} == {"no_server_default"}
        assert {d["column"] for d in diffs} == {"id", "username"}

    def test_column_missing_in_db_is_caught(self):
        declared = {"users": dict(self.DECLARED["users"], role="VARCHAR(20)")}
        diffs = diff_columns(self._live(), declared)
        assert {"table": "users", "column": "role", "kind": "only_in_orm"} in diffs

    def test_column_not_declared_is_caught(self):
        rows = self._live() + [self._row("legacy", "text", "YES")]
        diffs = diff_columns(rows, self.DECLARED)
        assert {"table": "users", "column": "legacy", "kind": "only_in_db"} in diffs

    def test_type_drift_is_caught(self):
        rows = [self._row("id", "bigint"), self._row("username", "character varying")]
        diffs = diff_columns(rows, self.DECLARED)
        assert any(d["kind"] == "type" and d["column"] == "id" for d in diffs), diffs

    def test_two_vocabularies_for_the_same_type_are_not_drift(self):
        """information_schema 说 SQL 标准名、DDL 说 PG 简称，这不是漂移。

        不认这层映射的话，真库跑一次会得到 9 张表全线 type 漂移的噪声报告，
        等于把这条核查废掉——所以它必须有专门用例钉住。
        """
        declared = {"events": {"at": "TIMESTAMP", "payload": "VARCHAR(255)"}}
        rows = [
            self._row_in("events", "at", "timestamp without time zone", "now()"),
            self._row_in("events", "payload", "character varying", "''"),
        ]
        assert diff_columns(rows, declared) == []


# ── C1：基线 DDL 的列清单比对（类型长度与 NOT NULL 此前无机检覆盖）──────

DDL_UP = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL       NOT NULL,
    username      VARCHAR(100) NOT NULL,
    role          VARCHAR(20)  NOT NULL DEFAULT 'user',
    prefs         JSON         NOT NULL DEFAULT '{"a": 1, "b": 2}',
    workspace_id  INTEGER      NULL,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_ws_fkey FOREIGN KEY (workspace_id)
        REFERENCES workspaces (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);
"""


def _snap(table, col, data_type, *, nullable="NO", default=None, length=None):
    return {
        "table_name": table,
        "column_name": col,
        "data_type": data_type,
        "is_nullable": nullable,
        "column_default": default,
        "character_maximum_length": length,
    }


def _snapshot_rows():
    """与 DDL_UP 逐项对应的一版真库列快照。"""
    return [
        _snap("users", "id", "integer", default="nextval('users_id_seq'::regclass)"),
        _snap("users", "username", "character varying", length=100),
        _snap("users", "role", "character varying", default="'user'::character varying", length=20),
        _snap("users", "prefs", "json", default="'{\"a\": 1, \"b\": 2}'::json"),
        _snap("users", "workspace_id", "integer", nullable="YES"),
    ]


def _snapshots(rows, tables=("users",)):
    return {"tables": list(tables), "columns": rows}


def _migrations(tmp, up=DDL_UP):
    d = tmp / "migrations"
    d.mkdir(parents=True, exist_ok=True)
    (d / "000001_baseline.up.sql").write_text(up, encoding="utf-8")
    return d


class TestParseDdlColumns:
    def test_real_baseline_parses_into_the_documented_shape(self):
        """解析器必须能吃下真正那份基线：10 张表 / 59 列是 --live 快照记下的数。
        这条挂了说明解析器已经跟不上 DDL 写法，`--verify-columns` 就成了摆设。"""
        text = (MIGRATIONS / "000001_baseline.up.sql").read_text(encoding="utf-8")
        tables = parse_ddl_columns(text)
        assert len(tables) == 10, sorted(tables)
        assert sum(len(cols) for cols in tables.values()) == 59

    def test_table_constraints_and_nested_parens_are_not_columns(self):
        cols = parse_ddl_columns(DDL_UP)["users"]
        assert list(cols) == ["id", "username", "role", "prefs", "workspace_id"]
        assert cols["id"] == {
            "type": "integer",
            "length": None,
            "nullable": False,
            "has_default": False,
            "serial": True,
        }
        assert cols["username"]["length"] == "100"
        assert cols["role"]["has_default"] is True
        assert cols["workspace_id"]["nullable"] is True

    def test_comma_inside_a_string_default_does_not_split_the_column(self):
        """DEFAULT 里的 JSON 字符串带逗号，切错了就会凭空多出半列。"""
        cols = parse_ddl_columns(DDL_UP)["users"]
        assert cols["prefs"]["type"] == "json"
        assert cols["prefs"]["nullable"] is False

    def test_unrecognised_type_raises_instead_of_guessing(self):
        with pytest.raises(ValueError, match="无法识别的列类型"):
            parse_ddl_columns("CREATE TABLE IF NOT EXISTS t (a CITVTYPE NOT NULL);")


class TestVerifyColumns:
    def test_matching_snapshot_passes(self, tmp_path):
        errs, notes = verify_columns(_migrations(tmp_path), _snapshots(_snapshot_rows()))
        assert (errs, notes) == ([], [])

    def test_varchar_length_drift_is_caught(self, tmp_path):
        """C1 的正主：长度此前完全没有机检。DDL 写 100、库里是 255 必须红。"""
        rows = _snapshot_rows()
        rows[1] = _snap("users", "username", "character varying", length=255)
        errs, _ = verify_columns(_migrations(tmp_path), _snapshots(rows))
        assert any("长度不一致" in e and "username" in e for e in errs), errs

    def test_ddl_without_length_but_db_limits_it_is_caught(self, tmp_path):
        rows = _snapshot_rows()
        rows[1] = _snap("users", "username", "character varying", length=100)
        up = DDL_UP.replace("VARCHAR(100)", "TEXT")
        errs, _ = verify_columns(_migrations(tmp_path, up=up), _snapshots(rows))
        assert any("没写长度" in e for e in errs), errs

    def test_not_null_drift_is_caught(self, tmp_path):
        rows = _snapshot_rows()
        rows[1] = _snap("users", "username", "character varying", nullable="YES", length=100)
        errs, _ = verify_columns(_migrations(tmp_path), _snapshots(rows))
        assert any("NOT NULL 不一致" in e for e in errs), errs

    def test_missing_server_default_is_caught(self, tmp_path):
        rows = _snapshot_rows()
        rows[2] = _snap("users", "role", "character varying", length=20)  # 库里没有 DEFAULT
        errs, _ = verify_columns(_migrations(tmp_path), _snapshots(rows))
        assert any("DEFAULT 不一致" in e and "role" in e for e in errs), errs

    def test_serial_that_lost_its_sequence_is_caught(self, tmp_path):
        """SERIAL 在 DDL 里不写 DEFAULT、库侧靠 nextval 兜——两边都按有默认算才不会假红；
        真库里 nextval 没了（比如被改成 plain integer）就必须红。"""
        rows = _snapshot_rows()
        rows[0] = _snap("users", "id", "integer")
        errs, _ = verify_columns(_migrations(tmp_path), _snapshots(rows))
        assert any("id" in e and "DEFAULT" in e for e in errs), errs

    def test_column_in_db_but_not_in_ddl_is_caught(self, tmp_path):
        rows = _snapshot_rows() + [_snap("users", "legacy", "text")]
        errs, _ = verify_columns(_migrations(tmp_path), _snapshots(rows))
        assert any("基线 DDL 没写" in e and "legacy" in e for e in errs), errs

    def test_column_in_ddl_but_not_in_db_is_caught(self, tmp_path):
        rows = [r for r in _snapshot_rows() if r["column_name"] != "prefs"]
        errs, _ = verify_columns(_migrations(tmp_path), _snapshots(rows))
        assert any("真库没有" in e and "prefs" in e for e in errs), errs

    def test_snapshot_table_without_any_ddl_is_caught(self, tmp_path):
        errs, _ = verify_columns(
            _migrations(tmp_path),
            _snapshots(_snapshot_rows(), tables=("users", "workspaces")),
        )
        assert any("workspaces" in e and "不建它" in e for e in errs), errs

    def test_table_added_by_a_later_migration_is_a_note_not_an_error(self, tmp_path):
        """快照是加新表之前导的，把它算成错误等于每加一张表都要先重导快照。"""
        up = DDL_UP + "\nCREATE TABLE IF NOT EXISTS ai_executions (id SERIAL NOT NULL);\n"
        errs, notes = verify_columns(_migrations(tmp_path, up=up), _snapshots(_snapshot_rows()))
        assert errs == []
        assert any("ai_executions" in n for n in notes), notes
