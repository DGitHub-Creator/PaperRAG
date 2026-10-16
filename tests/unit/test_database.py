"""E6 —— init_db 的迁移策略：alembic 缺失或失败必须抛错，不得静默 create_all。

静默 create_all 会建出没有 `alembic_version` 记录的库，之后每次迁移都可能与
真实表结构冲突，因此这条兜底被移除，改由启动失败来暴露问题。
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from backend.core.database import Base, init_db


@pytest.fixture(autouse=True)
def legacy_database(_patch_database):
    from backend.core import database
    connection = database.engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar.return_value = None
    return connection


@pytest.mark.parametrize("state", [None, (2, False), (3, True)])
def test_go_managed_database_never_falls_back_to_alembic(legacy_database, state):
    from types import SimpleNamespace

    legacy_database.execute.return_value.scalar.return_value = "schema_migrations"
    legacy_database.execute.return_value.one_or_none.return_value = None if state is None else SimpleNamespace(version=state[0], dirty=state[1])
    with patch("subprocess.run") as migrate:
        with pytest.raises(RuntimeError, match="migrate-go"):
            init_db()
        migrate.assert_not_called()


@pytest.fixture
def no_create_all():
    """断言 create_all 从未被调用。"""
    with patch.object(Base.metadata, "create_all") as mocked:
        yield mocked
    assert not mocked.called, "init_db 不得回退到 Base.metadata.create_all"


def test_init_db_raises_when_alembic_ini_missing(no_create_all):
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(RuntimeError, match="alembic.ini"):
            init_db()


def test_init_db_raises_when_migration_fails(no_create_all):
    result = MagicMock(returncode=1, stdout="apply failed", stderr="Can't locate revision")
    with patch("subprocess.run", return_value=result):
        with pytest.raises(RuntimeError, match="alembic upgrade head 失败") as exc:
            init_db()
    # 异常信息里必须带上 alembic 自己的输出，否则运维无从判断差异
    assert "Can't locate revision" in str(exc.value)


def test_init_db_raises_on_migration_timeout(no_create_all):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="alembic", timeout=60)):
        with pytest.raises(RuntimeError, match="超时"):
            init_db()


def test_init_db_returns_normally_on_success():
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
        init_db()
