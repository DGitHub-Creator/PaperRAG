"""`scripts/audit_schema.py` 的离线部分单测（P0-2 / X6 的 mock 级证据）。

X6 本身要真库才能 pass，这里只保证**判定逻辑**是硬的：每条规则都给一个正向
输入和一个会被抓到的篡改输入。规则松一条，基线就可能带着 DROP 进存量库。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.audit_schema import (  # noqa: E402
    alembic_state,
    check_baseline,
    diff_columns,
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
