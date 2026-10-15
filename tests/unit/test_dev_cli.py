"""`scripts/dev.py` 的单元级验证（P0-0）。

真跑 `up/migrate` 需要 Docker，属 real 级；这里只锁住不依赖容器的部分：
命令面、.env 解析、以及 doctor 对密钥 fail-fast 的判定。
"""

import importlib.util
import sys
from pathlib import Path

DEV_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev.py"

#: dev.py 的完整命令面。这份清单的用意不是"数一下有几个"，而是**新增子命令必须同时进这里**——
#: 否则 `test_documented_subcommands_are_exposed` 会对一个没人读过的命令默默通过。
SUBCOMMANDS = (
    "doctor", "up", "infra", "serve", "go-serve", "seed-admin",
    "down", "ps", "logs", "migrate", "migrate-go", "test", "gen",
)


def _load_dev():
    spec = importlib.util.spec_from_file_location("dev_cli", DEV_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dev = _load_dev()


class TestCommandSurface:
    def test_documented_subcommands_are_exposed(self):
        help_text = dev.build_parser().format_help()
        for name in SUBCOMMANDS:
            assert f"{name}  " in help_text, f"dev.py 缺少 {name} 子命令"

    def test_test_subcommand_passes_args_through_to_pytest(self, monkeypatch):
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            return 0

        monkeypatch.setattr(dev, "run", fake_run)

        def invoke(argv):
            args = dev.build_parser().parse_args(argv)
            return args.func(args)

        assert invoke(["test", "-m", "unit"]) == 0
        assert seen["cmd"] == [sys.executable, "-m", "pytest", "-m", "unit", "-q"]

        assert invoke(["test", "--", "-k", "auth", "-v"]) == 0
        assert seen["cmd"] == [sys.executable, "-m", "pytest", "-k", "auth", "-v"]

    def test_serve_binds_loopback_by_default(self):
        """`dev.py serve` 的默认监听地址必须是回环。

        这是 P0-7「ai-core 不对外可达」在**源码形态**下的等价判据（容器形态由
        `check_nginx_routes.py` 的 R4 判"不发布宿主端口"）。默认值一旦漂回 `0.0.0.0`，
        内部面 `/internal/v1/ai/*` 就进了局域网，而它只有 `AICORE_INTERNAL_TOKEN` 一道口令。
        """
        args = dev.build_parser().parse_args(["serve"])
        assert args.host == "127.0.0.1", f"serve 默认绑到 {args.host}，内部面会对外可达"

    def test_migrate_runs_alembic_on_the_host_not_in_a_container(self, monkeypatch):
        """dev compose 里已经没有应用服务（定案 + R5），所以 migrate 不能再 `compose exec`。

        从前它是 `compose exec -T backend python -m alembic upgrade head`，
        而那个 backend 容器就是台账 C29 移除的对象——不移除它就得为建库构建 16.5 GB 镜像。
        """
        seen: dict = {}
        called: dict = {}

        monkeypatch.setattr(dev, "run", lambda cmd, **kw: seen.update(cmd=cmd, **kw) or 0)
        monkeypatch.setattr(dev, "compose", lambda *a, **kw: called.__setitem__("a", a) or 0)

        args = dev.build_parser().parse_args(["migrate"])
        assert args.func(args) == 0
        assert seen["cmd"] == [sys.executable, "-m", "alembic", "upgrade", "head"]
        assert not called, "migrate 不该再走 compose"

    def test_migrate_go_defaults_to_up_and_runs_in_server_dir(self, monkeypatch):
        """D8 定案：Go 侧迁移是**显式命令**。省略子命令时补 `up`，且必须跑在 `server/` 下。"""
        seen: dict = {}

        monkeypatch.setattr(dev, "run", lambda cmd, **kw: seen.update(cmd=cmd, **kw) or 0)

        args = dev.build_parser().parse_args(["migrate-go"])
        assert args.func(args) == 0
        assert seen["cmd"][-3:] == ["-path", "migrations", "up"], seen["cmd"]
        assert seen["cwd"] == dev.SERVER_DIR

        args = dev.build_parser().parse_args(["migrate-go", "version"])
        assert args.func(args) == 0
        assert seen["cmd"][-1] == "version"

    def test_missing_env_file_does_not_crash_the_command(self, tmp_path, monkeypatch):
        """没有 `.env` 时命令要给可读结果，不是裸 FileNotFoundError（CI 与全新克隆都是这现场）。

        2026-10-15 的 run 44 后端 job 就是红在这条上：`process_env()` 被当参数调用，
        而它读的是 `ROOT/.env`——CI 上没这个文件，于是新加的两条 migrate 用例直接抛错。
        "缺 .env" 的正确报法由 doctor 负责，这里只要求**不 traceback**。
        """
        missing = tmp_path / ".env"
        monkeypatch.setattr(dev, "ENV_FILE", missing)
        assert dev.read_env_file(missing) == {}

        seen: dict = {}
        monkeypatch.setattr(dev, "run", lambda cmd, **kw: seen.update(cmd=cmd, **kw) or 0)
        assert dev.build_parser().parse_args(["migrate"]).func(
            dev.build_parser().parse_args(["migrate"])) == 0
        assert seen["cmd"][-1] == "head"



class TestEnvFileParsing:
    def test_comments_and_quotes_are_ignored(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text('# c\nJWT_SECRET_KEY= "abc123" \n\nEMPTY=\nAPP_ENV=production\n', encoding="utf-8")
        env = dev.read_env_file(f)
        assert env["JWT_SECRET_KEY"] == "abc123"
        assert env["APP_ENV"] == "production"
        assert env["EMPTY"] == ""

    def test_doctor_blocks_on_empty_or_placeholder_secret(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(dev.shutil, "which", lambda name: "/usr/bin/docker")
        monkeypatch.setattr(dev, "_exec_ok", lambda cmd: True)
        env = tmp_path / ".env"
        monkeypatch.setattr(dev, "ENV_FILE", env)

        for value in ("", "dev-only-insecure-jwt-secret"):
            env.write_text(f"JWT_SECRET_KEY={value}\n", encoding="utf-8")
            capsys.readouterr()
            assert dev.cmd_doctor(None) == 1
            assert "JWT_SECRET_KEY" in capsys.readouterr().out

    def test_doctor_reports_broken_compose_separately_from_a_stopped_daemon(self, tmp_path, monkeypatch, capsys):
        """daemon 没起与 compose 写坏必须是两个可见的失败原因。

        合成一样红的环境，实际坏的是另一样，比全不报更糟：人会先去找没启动的 Docker Desktop。
        """
        monkeypatch.setattr(dev.shutil, "which", lambda name: "/usr/bin/docker")
        monkeypatch.setattr(dev, "_exec_ok", lambda cmd: cmd[:2] == ["docker", "compose"])  # compose 子命令在，daemon 不在
        broken = tmp_path / "docker-compose.yml"
        broken.write_text("services:\n  a:\n    image: x\n    ports: [8000, 8000]\n", encoding="utf-8")
        monkeypatch.setattr(dev, "COMPOSE_FILE", broken)

        class _Proc:
            returncode = 1
            stdout = ""
            stderr = "services.a.ports Expected a string or a list of strings"

        monkeypatch.setattr(dev.subprocess, "run", lambda *a, **k: _Proc())
        capsys.readouterr()
        assert dev.cmd_doctor(None) == 1
        out = capsys.readouterr().out
        assert "静态校验失败" in out and "daemon 没在跑" in out


class TestGen:
    """`gen` 是 K2（生成物入库）的执行面，值得单独钉住三条。"""

    def _invoke(self, argv):
        args = dev.build_parser().parse_args(argv)
        return args.func(args)

    def _stub(self, monkeypatch, *, version_out, diff_rc=0):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "diff"]:
                return diff_rc
            return 0

        def fake_subprocess_run(cmd, **kwargs):
            calls.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": version_out, "stderr": ""})()

        monkeypatch.setattr(dev, "run", fake_run)
        monkeypatch.setattr(dev.subprocess, "run", fake_subprocess_run)
        monkeypatch.setattr(dev, "sqlc_binary", lambda: "/fake/sqlc")
        return calls

    def test_version_mismatch_blocks_before_generation(self, monkeypatch, capsys):
        # 用不同 sqlc 版本重生成会得到结构不同的代码，diff 门禁从此失去意义，
        # 而且失败信息指向"你的改动有问题"——所以宁可在动手前就拒绝。
        self._stub(monkeypatch, version_out="v1.28.0")
        assert self._invoke(["gen"]) == 1
        assert "版本不匹配" in capsys.readouterr().out

    def test_generation_runs_sqlc_in_server_dir(self, monkeypatch):
        calls = self._stub(monkeypatch, version_out=f"{dev.SQLC_VERSION.lstrip('v')}")
        assert self._invoke(["gen"]) == 0
        assert ["/fake/sqlc", "generate"] in calls

    def test_check_mode_asks_git_for_a_clean_diff(self, monkeypatch):
        calls = self._stub(monkeypatch, version_out=f"{dev.SQLC_VERSION.lstrip('v')}")
        assert self._invoke(["gen", "--check"]) == 0
        assert any(c[:2] == ["git", "diff"] and "--exit-code" in c for c in calls), calls

    def test_check_mode_propagates_drift_as_failure(self, monkeypatch, capsys):
        self._stub(monkeypatch, version_out=f"{dev.SQLC_VERSION.lstrip('v')}", diff_rc=1)
        assert self._invoke(["gen", "--check"]) == 1
        assert "不一致" in capsys.readouterr().out

    def test_falls_back_to_pinned_version_when_no_local_binary(self, monkeypatch):
        # 没装 sqlc 的人也要得到同一份生成代码：go run 后面钉死版本，而不是 @latest
        calls = []
        monkeypatch.setattr(dev, "sqlc_binary", lambda: None)
        monkeypatch.setattr(
            dev, "run", lambda cmd, **kw: (calls.append(cmd), 0)[1]
        )
        assert self._invoke(["gen"]) == 0
        assert calls[0] == [
            "go", "run", f"github.com/sqlc-dev/sqlc/cmd/sqlc@{dev.SQLC_VERSION}", "generate"
        ]


# ── gen 的三条前置检查（P0-3 切 schema 源时补的，每条都对应本机真踩过的坑）──

VALID_YAML = """version: "2"
sql:
  - engine: "postgresql"
    schema:
      - "migrations/000001_baseline.up.sql"
    queries:
      - "sql/queries"
    gen:
      go:
        package: "db"
"""


def _fake_server(tmp_path, monkeypatch, *, yaml_text=VALID_YAML, migrations=("000001_baseline.up.sql",),
                 queries=("users.sql",), generated=("users.sql.go",)):
    """搭一棵最小的假 server/ 树，并让 dev.py 的模块级 SERVER_DIR 指向它。

    前置检查读的是模块级常量，不 monkeypatch 它就会拿真仓库去判，测试变成"检查现状"而不是检查规则。
    """
    server = tmp_path / "server"
    (server / "migrations").mkdir(parents=True)
    (server / "sql" / "queries").mkdir(parents=True)
    (server / "internal" / "db").mkdir(parents=True)
    (server / "sqlc.yaml").write_text(yaml_text, encoding="utf-8")
    for name in migrations:
        (server / "migrations" / name).write_text("CREATE TABLE IF NOT EXISTS t (id SERIAL NOT NULL);\n", encoding="utf-8")
    for name in queries:
        (server / "sql" / "queries" / name).write_text("-- name: X :one\nSELECT 1;\n", encoding="utf-8")
    for name in generated:
        (server / "internal" / "db" / name).write_text("package db\n", encoding="utf-8")
    monkeypatch.setattr(dev, "SERVER_DIR", server)
    return server


class TestGenPrechecks:
    def _invoke(self, argv):
        args = dev.build_parser().parse_args(argv)
        return args.func(args)

    def test_shipped_config_passes_both_checks(self):
        """真仓库那份配置必须自证干净，否则"规则实现了但没跑过"。"""
        assert dev.check_sqlc_schema_sources() == []
        assert dev.check_sqlc_orphan_outputs() == []

    def test_schema_list_is_read_from_the_real_config(self):
        sources = dev._sqlc_schema_sources()
        assert sources is not None
        assert sources, "sqlc 的 schema 源为空等于 Go 看不见任何表"
        # 逐条列出而不是写目录：目录里 down 排在 up 前面，sqlc 按文件名顺序读 → 先 DROP 再 CREATE。
        # 这里不断言具体清单（加一张表就要改一次测试，那是把门禁变成 chores），
        # 断言的是"每条都是一个存在的 *.up.sql"这个形状。
        for src in sources:
            assert src.endswith(".up.sql"), f"schema 源不该是目录或 down 文件：{src}"
            assert (dev.SERVER_DIR / src).is_file(), f"schema 源指向不存在的文件：{src}"

    def test_unparseable_schema_list_refuses_instead_of_treating_it_as_empty(self, tmp_path, monkeypatch):
        """解析不出列表时不能"当作没配"然后照常生成——这个函数的存在意义就是确认覆盖面。"""
        _fake_server(tmp_path, monkeypatch, yaml_text='version: "2"\nsql:\n  - engine: "postgresql"\n')
        assert dev._sqlc_schema_sources() is None
        assert any("解析不到" in e for e in dev.check_sqlc_schema_sources())

    def test_directory_schema_source_with_down_files_is_refused(self, tmp_path, monkeypatch):
        """sqlc 按文件名顺序把目录里每个 .sql 都当 schema：down 排在 up 前面 → 先 DROP 再 CREATE。

        生成物看着完全正常，实际是按"回退后的库"生成的，这种错最难发现所以必须挡住。
        """
        _fake_server(
            tmp_path,
            monkeypatch,
            yaml_text=VALID_YAML.replace("- \"migrations/000001_baseline.up.sql\"", "- \"migrations\""),
            migrations=("000001_baseline.up.sql", "000001_baseline.down.sql"),
        )
        errs = dev.check_sqlc_schema_sources()
        assert any(".down.sql" in e and "先 DROP 再 CREATE" in e for e in errs), errs

    def test_new_migration_missing_from_schema_list_is_refused(self, tmp_path, monkeypatch):
        """漏登记的后果是"静默少一张表"：gen 不报错，Go 却永远看不见新表。"""
        _fake_server(tmp_path, monkeypatch, migrations=("000001_baseline.up.sql", "000002_ai_executions.up.sql"))
        errs = dev.check_sqlc_schema_sources()
        assert any("000002_ai_executions.up.sql" in e and "静默少一张表" in e for e in errs), errs

    def test_nonexistent_schema_source_is_refused(self, tmp_path, monkeypatch):
        _fake_server(tmp_path, monkeypatch, migrations=())
        assert any("不存在的源" in e for e in dev.check_sqlc_schema_sources())

    def test_orphan_generated_output_is_refused(self, tmp_path, monkeypatch):
        """sqlc 只写不删 X.sql.go：删掉的查询会留下没人调用、每次 gen 又重现的 Go 类型。"""
        server = _fake_server(tmp_path, monkeypatch, queries=("users.sql",), generated=("users.sql.go",))
        assert dev.check_sqlc_orphan_outputs() == []
        (server / "sql" / "queries" / "users.sql").unlink()
        errs = dev.check_sqlc_orphan_outputs()
        assert any("users.sql" in e for e in errs), errs

    def test_gen_stops_before_touching_sqlc_when_prechecks_fail(self, tmp_path, monkeypatch, capsys):
        """前置检查必须发生在探测 sqlc 版本之前：拒绝生成比"先生成再解释"更诚实。"""
        calls = TestGen()._stub(monkeypatch, version_out=dev.SQLC_VERSION.lstrip("v"))
        _fake_server(tmp_path, monkeypatch, migrations=("000001_baseline.up.sql", "000002_new.up.sql"))
        assert self._invoke(["gen"]) == 1
        assert calls == [], f"前置检查失败却仍然调用了 sqlc：{calls}"
        assert "前置检查不通过" in capsys.readouterr().out
