"""`scripts/dev.py` 的单元级验证（P0-0）。

真跑 `up/migrate` 需要 Docker，属 real 级；这里只锁住不依赖容器的部分：
命令面、.env 解析、以及 doctor 对密钥 fail-fast 的判定。
"""

import importlib.util
import sys
from pathlib import Path

DEV_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev.py"

SUBCOMMANDS = ("doctor", "up", "down", "ps", "logs", "migrate", "test", "gen")


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
